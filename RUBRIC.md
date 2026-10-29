# Nine-point rubric

| # | Requirement | Status | Verified evidence |
| --- | --- | --- | --- |
| 1 | Deployment: FastAPI, Streamlit, Docker | VERIFIED LOCALLY | Compose API, UI, and llama health checks passed on 2026-10-29; GCP deployment not attempted. Docker CPU inference exceeded the API's 120-second timeout. |
| 2 | GitHub: New documented repository | PENDING PUBLICATION | Local repository and documentation are ready; remote creation and push are the final publication step. |
| 3 | LLM Evaluation: Accuracy, grounding, latency | VERIFIED | Unchanged 19-case reference set: answer accuracy 0.9474, retrieval accuracy 0.8947, citation validity 1.0, abstention 1.0, mean latency 1221.36 ms, p95 1727.70 ms, zero errors. See `verification/live_evaluation_report.json`. Run used the same GGUF via host Metal llama.cpp. |
| 4 | Multi-Agent: LangGraph supervisor and specialists | VERIFIED | Supervisor executed retrieval, one intent-selected Investigator/Planner/Communicator node, and citation validation. Prediction traces confirm the executed specialist; semantic routing scored 1.0 across 19 cases. |
| 5 | Embedding: all-MiniLM-L6-v2 | VERIFIED | Ingestion loaded the cached model and indexed 20 documents into 31 chunks using 384-dimensional normalized embeddings. |
| 6 | Framework: LangGraph and FastAPI | VERIFIED | 31 automated tests passed; live FastAPI `/ask` returned a grounded INC-1042 response through the LangGraph workflow. |
| 7 | Vector Database: Chroma | VERIFIED | Persistent Chroma container collection held 31 incident chunks, including both `INC-1042-POSTMORTEM` chunks. |
| 8 | Memory: LangGraph checkpointer | VERIFIED | Same-thread graph state retained prior messages; live follow-up “What fixed it?” returned the INC-1042 rollback with INC-1042 citations after retrieval continuity repair. Evaluation memory score 1.0. |
| 9 | Guardrails: Pydantic, tool restrictions, citation validation | VERIFIED | Pydantic API validation passed; the only graph tool is allowlisted incident retrieval. Tests reject shell/file tool names and model tool-call output. Live evaluator citation validity and abstention were both 1.0, including prompt-injection cases. |

Evaluation details: `verification/live_evaluation_predictions.jsonl` records each actual model response, evidence, and specialist execution trace. The 19-case evaluation used `evaluation/reference_chunks.json` in a separate Chroma index; the application corpus was not changed. One answer case (`multi-01`) missed the exact phrase expectation, and two unsupported questions retrieved unrelated chunks before the model abstained. Docker CPU inference remains slower than the host Metal-backed run.
