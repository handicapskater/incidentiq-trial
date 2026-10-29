# Target architecture

Streamlit calls FastAPI with `IncidentRequest`. FastAPI invokes a LangGraph supervisor using `thread_id` for checkpointer memory. The supervisor routes to incident specialists, which retrieve Chroma evidence embedded with all-MiniLM-L6-v2 and use a configured Llama or Gemini provider. The graph returns cited evidence and an answer; the API validates citations and serializes `IncidentResponse`. Evaluation records accuracy, grounding, and latency.

This is the integration target, not an implemented application. Agent boundaries and contracts are in `AGENTS.md` and `docs/INTERFACES.md`.
