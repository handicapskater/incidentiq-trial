# IncidentIQ evaluation

`cases.json` contains 19 synthetic scenarios. `reference_chunks.json` is the evidence fixture. Agent B and the integration lead need to ingest these chunks with the listed `chunk_id` values, or map the IDs before running the live suite. The scenario routes (`investigator`, `planner`, `communicator`) should be reconciled with Agent A's implemented specialist names.

Capture one JSON object per case in a JSONL file, in case order for the memory pair. Each object has `case_id`, `response` (the `IncidentResponse` fields), and `evidence` (the retrieved `RetrievedEvidence` objects). Include `thread_id` when measuring memory. A failed invocation may use `error` instead of `response`. Preserve the `thread_id` in each case when invoking the graph.

```sh
python -m evaluation.evaluate predictions.jsonl --output report.json
```

The scorer reports answer phrase coverage, retrieval accuracy (all expected chunks returned), citation validity (citations present in retrieved evidence, unique, and at least one expected chunk for supported cases), abstention, routing, memory follow-up, mean and p95 latency, and error count. Answer matching is a deterministic proxy, so a human should review borderline semantic answers and conflict resolution. The scorer only measures memory after a caller runs the dependent pair in one session; it cannot prove checkpointer use from a response alone. API responses omit evidence by contract, so a graph-level harness or retrieval trace is needed for retrieval and citation scoring. No model calls or model weights are needed for dataset and scorer validation.

The reference chunks are fictional and intended for the evaluation index only. Keep them separate from production incident data.
