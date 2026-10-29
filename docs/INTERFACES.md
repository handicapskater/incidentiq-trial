# Shared interfaces

Import contracts from `incidentiq.schemas`; do not redefine them.

| Type | Fields | Use |
| --- | --- | --- |
| `IncidentRequest` | `question: str`, `thread_id: str` | API request; both nonempty |
| `RetrievedEvidence` | `document_id: str`, `chunk_id: str`, `text: str`, `similarity_score: float`, `metadata: dict[str, Any]` | Retrieval result |
| `IncidentResponse` | `answer: str`, `citations: list[str]`, `specialist_route: str`, `provider: str`, `latency_ms: float`, `abstained: bool` | API response; latency in milliseconds |
| `AgentState` | `question`, `thread_id`, `specialist_route`, `evidence`, `answer`, `citations`, `provider`, `abstained`, `latency_ms`, `messages` | Typed LangGraph state |

`citations` contains retrieved `chunk_id` values. Every citation must occur in `evidence`; abstentions have no unsupported citations. `specialist_route` names the selected specialist. `provider` names the inference backend, such as `llama` or `gemini`. A higher `similarity_score` means a better match; Agent B documents the exact metric before evaluation. Pass `thread_id` unchanged as the LangGraph checkpointer thread key.

The graph returns `AgentState`; the API maps it to `IncidentResponse`. Specialists may add private state keys, but shared keys keep these types and meanings. Read configuration through `incidentiq.config.Settings`.
