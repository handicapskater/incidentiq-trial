"""Run the 19 unchanged reference cases through the real graph and llama.cpp."""

import json
import re
from pathlib import Path

import chromadb

from evaluation.evaluate import ROOT, load_cases, score
from incidentiq.embeddings import embed_query, embed_texts
from incidentiq.graph import build_graph
from incidentiq.schemas import RetrievedEvidence


OUT = Path("verification")
INDEX = Path("data/evaluation-chroma")
COLLECTION = "incidentiq_evaluation"


def main() -> None:
    chunks = json.loads((ROOT / "reference_chunks.json").read_text())
    index = chromadb.PersistentClient(path=str(INDEX))
    collection = index.get_or_create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})
    collection.upsert(
        ids=[chunk["chunk_id"] for chunk in chunks],
        documents=[chunk["text"] for chunk in chunks],
        embeddings=embed_texts([chunk["text"] for chunk in chunks]),
        metadatas=[{"document_id": chunk["document_id"], "incident_id": chunk["document_id"]} for chunk in chunks],
    )

    def retrieve(question: str) -> list[RetrievedEvidence]:
        incident_ids = sorted(set(re.findall(r"INC-\d+", question.upper())))
        where = None
        if len(incident_ids) == 1:
            where = {"incident_id": incident_ids[0]}
        elif len(incident_ids) > 1:
            where = {"$or": [{"incident_id": item} for item in incident_ids]}
        if where and not collection.get(where=where, limit=1, include=[])["ids"]:
            return []
        result = collection.query(
            query_embeddings=[embed_query(question)], n_results=5, where=where,
            include=["documents", "metadatas", "distances"],
        )
        return [RetrievedEvidence(
            document_id=metadata["document_id"], chunk_id=chunk_id, text=text,
            similarity_score=1 - distance, metadata=metadata,
        ) for chunk_id, text, metadata, distance in zip(
            result["ids"][0], result["documents"][0], result["metadatas"][0], result["distances"][0]
        )]

    graph = build_graph(retriever=retrieve)
    predictions = {}
    path = OUT / "live_evaluation_predictions.jsonl"
    with path.open("w") as output:
        for case in load_cases():
            record = {"case_id": case["id"], "thread_id": case["thread_id"]}
            try:
                state = graph.invoke(
                    {"question": case["question"], "thread_id": case["thread_id"]},
                    config={"configurable": {"thread_id": case["thread_id"]}},
                )
                record["response"] = {key: state[key] for key in (
                    "answer", "citations", "specialist_route", "provider", "latency_ms", "abstained"
                )}
                record["specialist_trace"] = state.get("specialist_trace", [])
                record["evidence"] = [RetrievedEvidence.model_validate(item).model_dump() for item in state.get("evidence", [])]
            except Exception as exc:
                record["error"] = f"{type(exc).__name__}: {exc}"
            predictions[case["id"]] = record
            output.write(json.dumps(record) + "\n")
            output.flush()
            print(f"{case['id']}: {record.get('error', record.get('response', {}).get('answer'))}", flush=True)
    report = score(load_cases(), predictions)
    (OUT / "live_evaluation_report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"metrics": report["metrics"], "latency_ms": report["latency_ms"], "error_count": report["error_count"]}, indent=2))


if __name__ == "__main__":
    main()
