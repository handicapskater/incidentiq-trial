import json

import pytest

from evaluation.evaluate import ROOT, load_cases, score


def test_dataset_has_categories_and_valid_references():
    cases = load_cases()
    chunks = json.loads((ROOT / "reference_chunks.json").read_text())
    chunk_ids = [item["chunk_id"] for item in chunks]
    assert len(chunk_ids) == len(set(chunk_ids))
    assert {chunk for case in cases for chunk in case["expected_chunks"]} <= set(chunk_ids)
    assert {case["category"] for case in cases} == {
        "exact_retrieval", "multi_document", "conflicting_evidence", "unsupported",
        "supervisor_routing", "memory", "citation_validation", "prompt_injection", "synthetic_canary",
    }
    memory_cases = {case["id"]: case for case in cases if case["category"] == "memory"}
    assert memory_cases["memory-02"]["depends_on"] == "memory-01"
    assert memory_cases["memory-01"]["thread_id"] == memory_cases["memory-02"]["thread_id"]


def test_scorer_detects_unsupported_citations_and_wrong_answers():
    cases = [case for case in load_cases() if case["id"] in ("exact-01", "unsupported-01")]
    predictions = {
        "exact-01": {
            "response": {"answer": "An expired certificate caused it.", "citations": ["fabricated"], "specialist_route": "investigator", "provider": "llama", "latency_ms": 120, "abstained": False},
            "evidence": [{"document_id": "INC-104", "chunk_id": "inc-104-cause", "text": "expired certificate", "similarity_score": 0.9, "metadata": {}}],
        },
        "unsupported-01": {
            "response": {"answer": "The number is 555-0100", "citations": [], "specialist_route": "investigator", "provider": "llama", "latency_ms": 80, "abstained": False},
            "evidence": [],
        },
    }
    report = score(cases, predictions)
    assert report["metrics"]["answer_accuracy"] == 0.5
    assert report["metrics"]["retrieval_accuracy"] == 1.0
    assert report["metrics"]["citation_validity"] == 0.5
    assert report["metrics"]["citation_id_validity"] == 0.5
    assert report["metrics"]["abstention"] == 0.5
    assert report["latency_ms"] == {"mean": 100.0, "p95": 120.0}
    assert report["error_count"] == 0


def test_valid_citation_id_does_not_prove_unsupported_claim():
    case = next(case for case in load_cases() if case["id"] == "exact-01")
    valid_id = case["expected_chunks"][0]
    record = {
        "response": {
            "answer": "Sabotage caused the outage.", "citations": [valid_id],
            "specialist_route": "investigator", "provider": "llama",
            "latency_ms": 1, "abstained": False,
        },
        "evidence": [{"document_id": "INC-104", "chunk_id": valid_id,
                      "text": "An expired certificate caused the outage.",
                      "similarity_score": 1.0, "metadata": {}}],
    }
    report = score([case], {case["id"]: record})
    assert report["metrics"]["citation_id_validity"] == 1.0
    assert report["metrics"]["answer_accuracy"] == 0.0


def test_missing_and_invalid_predictions_are_errors():
    cases = load_cases()[:2]
    report = score(cases, {cases[0]["id"]: {"response": {"answer": "invalid"}, "evidence": []}})
    assert report["error_count"] == 2
    assert report["metrics"]["routing"] == 0.0


def test_unknown_case_rejected():
    with pytest.raises(ValueError, match="Unknown prediction"):
        score(load_cases()[:1], {"unknown": {}})


def test_routing_score_requires_executed_specialist_when_trace_exists():
    case = next(case for case in load_cases() if case["id"] == "routing-02")
    response = {
        "answer": "Improve monitoring", "citations": ["inc-113-postmortem"],
        "specialist_route": "planner", "provider": "llama", "latency_ms": 10, "abstained": False,
    }
    evidence = [{
        "document_id": "INC-113", "chunk_id": "inc-113-postmortem",
        "text": "Improve monitoring", "similarity_score": 1.0, "metadata": {},
    }]
    record = {"response": response, "evidence": evidence, "specialist_trace": ["retrieval", "investigator", "citation_validation"]}
    assert score([case], {case["id"]: record})["metrics"]["routing"] == 0.0
    record["specialist_trace"] = ["retrieval", "planner", "citation_validation"]
    assert score([case], {case["id"]: record})["metrics"]["routing"] == 1.0


def test_memory_requires_same_explicit_thread_id():
    cases = [case for case in load_cases() if case["category"] == "memory"]
    predictions = {}
    for case in cases:
        predictions[case["id"]] = {
            "response": {
                "answer": case["must_include"][0], "citations": case["expected_chunks"],
                "specialist_route": "investigator", "provider": "llama", "latency_ms": 10, "abstained": False,
            },
            "evidence": [
                {"document_id": "INC-115", "chunk_id": chunk, "text": "test", "similarity_score": 1.0, "metadata": {}}
                for chunk in case["expected_chunks"]
            ],
            "thread_id": case["thread_id"],
        }
    assert score(cases, predictions)["metrics"]["memory"] == 1.0
    predictions["memory-01"]["thread_id"] = "different"
    assert score(cases, predictions)["metrics"]["memory"] == 0.0
