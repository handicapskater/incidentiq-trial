# IncidentIQ agent instructions

Implement features in the assigned worktree and keep edits within owned files. Only the integration lead changes shared files: `schemas.py`, `config.py`, `docs/INTERFACES.md`, `requirements.txt`, `README.md`, `ARCHITECTURE.md`, `RUBRIC.md`, and this file.

| Agent | Branch | Owned paths | Deliverable |
| --- | --- | --- | --- |
| A: Core AI | `agent/core-ai` | `incidentiq/graph.py`, `incidentiq/inference.py`, `incidentiq/agents/` | LangGraph supervisor, specialists, local Llama inference |
| B: RAG and Data | `agent/rag-data` | `incidentiq/retrieval.py`, `incidentiq/embeddings.py`, `corpus/`, `scripts/ingest.py` | Synthetic incidents, MiniLM embeddings, Chroma retrieval |
| C: Application | `agent/application` | `incidentiq/api.py`, `incidentiq/ui.py`, API and UI tests in `tests/` | FastAPI and Streamlit |
| D: Quality and Deployment | `agent/quality-deployment` | `evaluation/`, deployment scripts in `scripts/`, `Dockerfile`, `compose.yaml`, `.dockerignore`, `.github/workflows/`, evaluation tests in `tests/` | Evaluation, containers, CI, GCP deployment |

All agents import shared types from `incidentiq.schemas` and follow `docs/INTERFACES.md`. Coordinate cross-workstream needs with the integration lead. Keep environments, credentials, models, and databases out of Git. Run relevant checks before handoff.
