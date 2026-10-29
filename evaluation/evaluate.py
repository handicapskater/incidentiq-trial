"""Score versioned IncidentIQ cases against captured graph or API predictions.

Usage: python -m evaluation.evaluate predictions.jsonl
Each line: {"case_id": "...", "response": IncidentResponse fields,
            "evidence": [RetrievedEvidence fields], "error": optional string}
"""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from typing import Any

from incidentiq.schemas import IncidentResponse, RetrievedEvidence

ROOT = Path(__file__).resolve().parent


def load_cases(path: Path = ROOT / "cases.json") -> list[dict[str, Any]]:
    cases = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(cases, list) or len(cases) < 15:
        raise ValueError("Expected at least 15 evaluation cases")
    required = {"id", "category", "question", "thread_id", "expected_chunks", "must_include", "expected_route", "abstain"}
    ids: set[str] = set()
    for case in cases:
        if not isinstance(case, dict) or not required <= case.keys():
            raise ValueError(f"Malformed case: {case!r}")
        if not all(isinstance(case[key], str) and case[key] for key in ("id", "category", "question", "thread_id", "expected_route")):
            raise ValueError(f"Empty or invalid case field: {case!r}")
        if case["id"] in ids:
            raise ValueError(f"Duplicate case ID: {case['id']}")
        ids.add(case["id"])
        if not isinstance(case["abstain"], bool) or not isinstance(case["expected_chunks"], list) or not isinstance(case["must_include"], list):
            raise ValueError(f"Invalid expectations: {case['id']}")
        if not all(isinstance(value, str) and value for key in ("expected_chunks", "must_include", "must_exclude") for value in case.get(key, [])):
            raise ValueError(f"Invalid expectation text: {case['id']}")
        if case["abstain"] and case["must_include"]:
            raise ValueError(f"Abstention cannot require answer text: {case['id']}")
    for case in cases:
        if "depends_on" in case and (case["depends_on"] not in ids or case["depends_on"] == case["id"]):
            raise ValueError(f"Invalid memory dependency: {case['id']}")
    return cases


def load_predictions(path: Path) -> dict[str, dict[str, Any]]:
    predictions: dict[str, dict[str, Any]] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        record = json.loads(line)
        case_id = record.get("case_id")
        if not isinstance(case_id, str) or case_id in predictions:
            raise ValueError(f"Missing or duplicate case_id on line {line_number}")
        predictions[case_id] = record
    return predictions


def _contains(haystack: str, needle: str) -> bool:
    normalize = lambda value: re.sub(r"\s+", " ", value.casefold()).strip()
    return normalize(needle) in normalize(haystack)


def _rate(values: list[bool]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def score(cases: list[dict[str, Any]], predictions: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Missing or invalid predictions count as errors; rates use applicable cases."""
    allowed_ids = {case["id"] for case in cases}
    unknown = set(predictions) - allowed_ids
    if unknown:
        raise ValueError(f"Unknown prediction case IDs: {sorted(unknown)}")
    metrics: dict[str, list[bool]] = {name: [] for name in (
        "answer_accuracy", "retrieval_accuracy", "citation_id_validity", "citation_validity",
        "abstention", "routing", "memory"
    )}
    latencies: list[float] = []
    errors: list[dict[str, str]] = []
    details: list[dict[str, Any]] = []
    for case in cases:
        case_id = case["id"]
        record = predictions.get(case_id)
        result: dict[str, Any] = {"case_id": case_id, "category": case["category"]}
        try:
            if record is None:
                raise ValueError("missing prediction")
            if record.get("error"):
                raise ValueError(str(record["error"]))
            response = IncidentResponse.model_validate(record["response"])
            evidence = [RetrievedEvidence.model_validate(item) for item in record["evidence"]]
            available = {item.chunk_id for item in evidence}
            expected = set(case["expected_chunks"])
            answer_ok = all(_contains(response.answer, term) for term in case["must_include"])
            answer_ok &= all(not _contains(response.answer, term) for term in case.get("must_exclude", []))
            answer_ok &= response.abstained == case["abstain"]
            citation_ok = set(response.citations) <= available
            citation_ok &= len(response.citations) == len(set(response.citations))
            citation_ok &= not (response.abstained and response.citations)
            if expected and not response.abstained:
                citation_ok &= bool(set(response.citations) & expected)
            result.update(
                answer_accuracy=bool(answer_ok),
                retrieval_accuracy=expected <= available if expected else not available,
                citation_id_validity=bool(citation_ok),
                citation_validity=bool(citation_ok),  # Compatibility alias; not claim-level grounding.
                abstention=response.abstained == case["abstain"],
                routing=(response.specialist_route == case["expected_route"]
                         and ("specialist_trace" not in record
                              or (isinstance(record["specialist_trace"], list)
                                  and case["expected_route"] in record["specialist_trace"]))),
            )
            if "depends_on" in case:
                previous = predictions.get(case["depends_on"], {})
                result["memory"] = bool(
                    answer_ok
                    and record.get("thread_id") == case["thread_id"]
                    and previous.get("thread_id") == case["thread_id"]
                )
            latencies.append(response.latency_ms)
        except (KeyError, TypeError, ValueError) as exc:
            errors.append({"case_id": case_id, "error": str(exc)})
            result.update(answer_accuracy=False, retrieval_accuracy=False,
                          citation_id_validity=False, citation_validity=False,
                          abstention=False, routing=False)
            if "depends_on" in case:
                result["memory"] = False
        for name in metrics:
            if name in result and (name != "retrieval_accuracy" or case["expected_chunks"] or case["abstain"]):
                metrics[name].append(result[name])
        details.append(result)
    sorted_latencies = sorted(latencies)
    p95_index = math.ceil(0.95 * len(sorted_latencies)) - 1 if sorted_latencies else 0
    return {
        "case_count": len(cases),
        "prediction_count": len(predictions),
        "metrics": {name: _rate(values) for name, values in metrics.items()},
        "latency_ms": {"mean": round(sum(latencies) / len(latencies), 2) if latencies else None, "p95": sorted_latencies[p95_index] if latencies else None},
        "error_count": len(errors),
        "errors": errors,
        "cases": details,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("predictions", type=Path)
    parser.add_argument("--output", type=Path, help="Write JSON report to this path")
    args = parser.parse_args()
    report = score(load_cases(), load_predictions(args.predictions))
    rendered = json.dumps(report, indent=2)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)


if __name__ == "__main__":
    main()
