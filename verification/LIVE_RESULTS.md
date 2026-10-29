# IncidentIQ live verification — 2026-10-29

## Readiness and corpus

- After the repaired API image started with an empty Chroma volume, `GET http://localhost:8000/ready` returned HTTP 503 with the controlled unavailable message.
- Container ingestion indexed 20 unchanged corpus documents into 31 Chroma chunks. The collection contains `INC-1042-POSTMORTEM:chunk-000` and `INC-1042-POSTMORTEM:chunk-001`.
- After llama.cpp and the corpus were ready, Docker API `/ready` returned HTTP 200. Docker API, Streamlit UI, and llama.cpp health checks were healthy.
- The original Docker llama.cpp configuration was OOM-killed (exit 137) after allocating four 131072-token slots. Compose now sets one 4096-token slot. Docker reports no accelerator device. A 17-token smoke response took 1.96 seconds: 7.38 prompt tokens/s and 3.27 generated tokens/s. A full 1707-token evidence prompt still exceeded the API's 120-second timeout; this remains a performance blocker.

## Real INC-1042 questions

The host FastAPI process used the same source code and GGUF through Metal-enabled local llama.cpp on port 8082. Its `/ready` returned HTTP 200.

| Question | HTTP | Answer excerpt | Citations | Latency |
| --- | --- | --- | --- | --- |
| What was the final root cause of INC-1042, and what evidence confirmed it? | 200 | Deployment changed PostgreSQL pool maximum from 80 to 20 per pod; connections exhausted. | `INC-1042-POSTMORTEM:chunk-001`, `INC-1042-POSTMORTEM:chunk-000`, `INC-1042-REPORT:chunk-000` | 12530.97 ms |
| What caused INC-1042? | 200 | Same connection-pool root cause. | Both INC-1042 postmortem chunks and INC-1042 report | 12324.35 ms |
| What fixed it? (same thread, after repair) | 200 | Rolled back pool setting to 80, terminated orphaned transactions, added alerts. | INC-1042 postmortem, logs, and report chunks | 5688.12 ms |

Before the retrieval continuity repair, the same follow-up question incorrectly cited INC-1046 and described recreating its database index. The graph checkpointer retained the conversation, but retrieval did not carry the previous incident ID. A regression test now checks the anchored retrieval query.

## Supervisor and evaluation

Graph update stream: `prepare → supervisor → retrieval → supervisor → [intent specialist] → supervisor → citation_validation`. The selected Investigator, Planner, or Communicator node is recorded in each prediction's `specialist_trace`; the evaluator requires that executed node to match the expected route.

The unchanged 19-case reference set ran through real all-MiniLM-L6-v2 retrieval, the LangGraph workflow, and the same GGUF on Metal llama.cpp. Actual responses and retrieved evidence are in `live_evaluation_predictions.jsonl`; scorer output is in `live_evaluation_report.json`.

| Metric | Result |
| --- | ---: |
| Answer accuracy | 18/19 (0.9474) |
| Retrieval accuracy | 17/19 (0.8947) |
| Citation validity | 19/19 (1.0) |
| Abstention | 19/19 (1.0) |
| Semantic routing | 19/19 (1.0) |
| Memory follow-up | 1/1 (1.0) |
| Mean / p95 latency | 1221.36 / 1727.70 ms |
| Invocation errors | 0 |

`multi-01` missed the expected answer phrase despite retrieving both reference chunks. The two unsupported questions retrieved unrelated chunks, then abstained. These facts and expected answers were not edited.

After hardening, `python -m pytest -v` passed all 31 tests, including specialist execution trace, tool allowlist, prompt-injection, and citation checks.
