# IncidentIQ interview build postmortem

## 1. Executive summary

IncidentIQ is a working interview demonstration of incident RAG with a LangGraph supervisor, three specialist routes, MiniLM embeddings, Chroma, FastAPI, Streamlit, local llama.cpp, and Vertex Gemini. Local and cloud inference have both been observed. This pass focused on bounded execution, retrieval relevance, route paraphrases, honest citation metrics, and a verifiable release SHA. It does not make the service production ready.

## 2. Original nine-point rubric

1. Deployment: FastAPI, Streamlit, Docker.
2. GitHub: new documented repository.
3. LLM evaluation: accuracy, grounding, latency.
4. Multi-agent: LangGraph supervisor and specialists.
5. Embedding: all-MiniLM-L6-v2.
6. Framework: LangGraph and FastAPI.
7. Vector database: Chroma.
8. Memory: LangGraph checkpointer.
9. Guardrails: Pydantic, tool restrictions, citation validation.

The demo implements all nine. Item 3's citation score measures source-ID validity, not factual entailment. Item 8 uses ephemeral process memory. Item 9's tool allowlist blocks arbitrary tool dispatch but does not prove every generated claim.

## 3. Architecture overview

Streamlit sends `IncidentRequest` to FastAPI `/ask`. FastAPI validates the request, optionally checks a shared server-side API key, and invokes a LangGraph workflow. Chroma returns MiniLM-ranked chunks. The supervisor chooses Investigator, Planner, or Communicator. A Llama or Gemini provider generates JSON; citation validation admits only retrieved chunk IDs. `MemorySaver` keeps same-thread context in one process. The cloud image contains a read-only baseline Chroma index and calls Vertex Gemini with a Cloud Run service identity.

## 4. Initial implementation results

Before this pass, the last verified local run had 33/33 unit tests, 18/19 answer accuracy, 17/19 retrieval accuracy, 19/19 citation-ID validity, 19/19 curated routing, 19/19 abstention, and 1/1 memory. The 19-case reference evaluation used a local Chroma reference index. A separate 19-case Vertex run reached 19/19 answers, 17/19 retrieval, 19/19 citation IDs, 19/19 routing and abstention, and 1/1 memory; it did not traverse Cloud Run. These are historical observations, not claims about the new code or currently deployed image.

## 5. Problems encountered during development

The local Compose file required `GGUF_MODEL_PATH`; missing it prevented startup. Docker host port conflicts were reported during setup; the precise conflict log was not retained, so that detail is historical user context rather than a reproduced finding in this pass. Docker CPU llama.cpp exceeded the API's 120-second timeout while the same GGUF ran effectively on host Metal. The Streamlit container once served a health page while its script failed to import `incidentiq`. An existing Llama API image also failed to build its graph because `google-auth` was imported eagerly even on the Llama path. A direct raw-model question returned a generic no-records answer because it bypassed RAG.

## 6. Root causes

The original UI image lacked a package import path; `Dockerfile.ui` now sets `PYTHONPATH` and checks the import at build time. The inference module's Vertex credential imports were moved into the Gemini-only function. Docker Desktop did not provide Metal to its CPU llama.cpp container; local development now uses the host Metal endpoint. Raw llama.cpp is not an incident retrieval application. Prior readiness checks tested process/dependency availability but could not prove an actual answer. Cloud Run image tags remained on an earlier commit after local code advanced.

## 7. Corrective actions in this pass

Routing now handles common prevention and customer-communication paraphrases plus negation without an extra LLM call. Retrieval keeps Chroma top-k but rejects insufficient evidence; a no-ID similarity boundary was calibrated from bundled positive and unrelated queries, while named IDs require matching records and topical overlap. Llama multipart requests are limited to four parts, at most four calls, and 256 generated tokens per call; Gemini is also limited to 256 output tokens. A comma-separated list of incident facets is split into bounded calls so a short answer does not drop requested facets. FastAPI validates before dependency probes, enforces a 110-second response deadline, and permits two in-flight analyses per process. The local raw llama.cpp port is bound to loopback. Optional API-key checking uses a server-side header from Streamlit. `/version` reports a configured Git SHA; the deployment script sets it from the commit. `/ready` remains a cheap dependency probe, while `scripts/smoke_inference.py` performs an optional real answer check.

## 8. Red-team findings

The earlier review demonstrated an unauthenticated public Cloud API, client-chosen thread IDs, source-ID-only citation checks, keyword route errors, unscoped irrelevant retrieval, and multipart request amplification. The current corpus is synthetic, but these remain relevant before accepting private operational data.

## 9. Fixed versus deferred

Fixed for the demo: the three reported routing errors, an unrelated payroll retrieval path, bounded Llama multipart work, input validation order, local loopback port binding, a separate version endpoint, and an honestly named citation-ID metric. Optional key validation is implemented and unit tested. Deferred: enabling a cloud key, per-user thread ownership, durable memory, distributed rate limiting, and claim-level entailment. The process-local execution slots are not a distributed rate limiter. The cloud services remain on the prior image until a verified deployment of this commit.

## 10. Evaluation before and after

| Metric | Before, local Llama | After, local Llama |
| --- | ---: | ---: |
| Unit tests | 33 passing | 54 passing |
| Answer accuracy | 18/19 | 18/19 |
| Retrieval accuracy | 17/19 | 19/19 |
| Citation-ID validity | 19/19 | 19/19 |
| Curated routing | 19/19 | 19/19 |
| Abstention | 19/19 | 19/19 |
| Memory | 1/1 | 1/1 |
| Mean latency | Not retained for baseline | 1,043 ms |
| p95 latency | Not retained for baseline | 1,722 ms |
| Evaluation errors | Not retained for baseline | 0 |

The post-change local Llama run used the unchanged 19 cases and a separate local Chroma reference index. A separate post-change local Vertex run scored 19/19 answers, retrieval, citation IDs, routing and abstention, 1/1 memory, with 918 ms mean, 1,717 ms p95, and zero errors; it did not traverse Cloud Run. The citation metric is named `citation_id_validity`; `citation_validity` remains a compatibility alias. A negative test proves that an unsupported claim can still carry a valid source ID. The adversarial route and relevance checks are separate from the unchanged 19 cases. A live local `/ask` call using host Metal returned the preliminary network and processor hypotheses, the pool reduction from 80 to 20, and rollback to 80 with transaction cleanup; it selected Investigator and cited `INC-1042-POSTMORTEM` chunks.

## 11. Known limitations

Cloud Run filesystem writes and Chroma changes are ephemeral. `MemorySaver` is neither durable nor tied to a real user identity; the optional key authenticates the application, not individual UI users. A 110-second API response deadline may not immediately cancel an already running synchronous provider request. The public cloud API remains unauthenticated. Local Docker CPU inference remains much slower than host Metal. `/health` and `/ready` cannot guarantee successful model generation. The currently deployed Cloud images are tagged from `6546d1d28b38`, so GitHub code and live revisions must not be conflated.

## 12. Production-readiness roadmap

If the prototype were continued beyond the interview, add an authenticated user identity, per-user thread ownership, durable checkpointer and vector persistence, external rate limits, secret-managed service-to-service credentials, claim-level support evaluation, broader adversarial cases, pinned dependencies and model revisions, and a release gate that compares `/version` with the intended SHA. None of these were added to this time-boxed pass.

## 13. Lessons for the next 60-minute build

Verify the host GGUF bind path and free ports first. Test one real question through the UI and API early because green health endpoints can hide import or inference failures. Prefer host Metal for the local Apple Silicon demo, while recording Docker CPU limits honestly. Separate source-ID validation from claim grounding in metrics. Keep the evaluation set unchanged, record actual traces, and place the Git SHA into the live service before claiming a deployment matches the repository.
