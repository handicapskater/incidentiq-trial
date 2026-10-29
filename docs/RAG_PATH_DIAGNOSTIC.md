# INC-1042 RAG path diagnostic (2026-10-29)

Question: “For incident INC-1042, what was the initially suspected root cause, what did the final postmortem establish as the actual root cause, and what corrective action resolved the incident?”

## Finding

A direct call to the raw host Metal-backed llama.cpp chat endpoint reproduced the reported generic “I don't have access to the specific details” answer. The original user request has no request ID or body log, so its exact historical path cannot be proven. It did not produce a successful local RAG response: the earlier Streamlit container raised `ModuleNotFoundError: incidentiq` when loading the app, and the local API had a 503 path because it eagerly imported `google-auth` for the Llama provider even though its existing image lacked that package. Docker CPU inference also exceeded the 120-second application timeout. The deployed Cloud Run UI had the same missing package path; its revision `incidentiq-trial-ui-00002-4fj` now sets `PYTHONPATH=/app` and is Ready with 100% traffic.

The repaired local path is Streamlit chat input → `http://api:8000/ask` → LangGraph supervisor → `incident_retrieval` → Chroma's 31-chunk incident collection → Investigator → host Metal llama.cpp at `http://host.docker.internal:8082/v1/chat/completions` → citation validation → API response → Streamlit history. The UI container's Streamlit AppTest submitted the exact question through its chat input and recorded no exceptions. The public Cloud Run UI was HTTP checked after its configuration repair; browser interaction with that remote revision was not available in this environment.

## Retrieved evidence

The live API log recorded these document and chunk IDs for the exact question:

| Document ID | Chunk ID |
| --- | --- |
| `INC-1042-POSTMORTEM` | `INC-1042-POSTMORTEM:chunk-001` |
| `INC-1042-LOGS` | `INC-1042-LOGS:chunk-000` |
| `INC-1042-RUNBOOK` | `INC-1042-RUNBOOK:chunk-000` |
| `INC-1042-POSTMORTEM` | `INC-1042-POSTMORTEM:chunk-000` |
| `INC-1042-REPORT` | `INC-1042-REPORT:chunk-000` |

The supervisor recorded `investigator`. The Llama prompt includes actual retrieved text and allowed chunk IDs. The regression test parses the exact prompt sent to the inference provider and verifies that the preliminary hypothesis text, the 80-to-20 pool change, and the rollback text appear in the appropriate question-clause prompts. The first clause uses only retrieved sentences marked preliminary or proposed, preventing the confirmed cause from replacing the initial hypotheses. The API logs document/chunk IDs, selected specialist, prompt evidence IDs, and validated citations without logging the full prompt.

## Live comparison

Both final local runs returned provider `llama`, route `investigator`, `abstained=false`, and citations containing `INC-1042-REPORT:chunk-000` and `INC-1042-POSTMORTEM:chunk-000` plus `INC-1042-POSTMORTEM:chunk-001`. The direct API request returned HTTP 200 in 22.6 seconds; Streamlit's chat-input submission completed in 17.4 seconds. The API log recorded two `POST /ask` requests with HTTP 200, including one from the UI container (`172.20.0.4`).

Direct API answer: “1. a network partition between the API and PostgreSQL and a sudden card processor slowdown; these were preliminary and unverified. 2. a deployment changed the PostgreSQL connection pool maximum from 80 to 20 per pod while six pods held long transactions; all available connections were exhausted. 3. rolled back the pool setting to 80, terminated orphaned long transactions, and added pool saturation alerts.”

Streamlit answer: “1. A network partition between the API and PostgreSQL and a sudden card processor slowdown were initially suspected root causes. 2. a deployment changed the PostgreSQL connection pool maximum from 80 to 20 per pod while six pods held long transactions; all available connections were exhausted. 3. rolled back the pool setting to 80, terminated orphaned long transactions, and added pool saturation alerts.”

The unchanged 19-case host Llama evaluation after this fix scored 18/19 answers, 17/19 retrieval, 19/19 citations, 19/19 abstention, 19/19 routing, and 1/1 memory, with zero errors. All 33 unit tests passed. No synthetic incident facts or evaluation expectations were changed.
