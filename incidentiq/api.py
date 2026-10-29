"""HTTP interface for the IncidentIQ graph."""

import inspect
import math
import re
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from time import perf_counter
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
import chromadb
import httpx
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from incidentiq.schemas import IncidentRequest, IncidentResponse, RetrievedEvidence
from incidentiq.config import Settings
from incidentiq.retrieval import COLLECTION_NAME


app = FastAPI(title="IncidentIQ")
_THREAD_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]*\Z")


@lru_cache(maxsize=1)
def _build_graph() -> Any:
    """Keep one graph instance so its checkpointer retains thread memory."""
    from incidentiq.graph import build_graph

    graph = build_graph()
    if graph is None or not (callable(getattr(graph, "ainvoke", None)) or callable(getattr(graph, "invoke", None))):
        raise RuntimeError("Graph has no invocation method")
    return graph


def _check_dependencies() -> None:
    """Probe current corpus and inference availability, not cached startup state."""
    settings = Settings()
    chroma_path = Path(settings.CHROMA_PATH)
    if not chroma_path.is_dir():
        raise RuntimeError("Chroma directory is missing")
    collection = chromadb.PersistentClient(path=str(chroma_path)).get_collection(COLLECTION_NAME)
    if collection.count() == 0:
        raise RuntimeError("Incident corpus is not indexed")
    provider = settings.MODEL_PROVIDER.lower()
    if provider == "llama":
        response = httpx.get(f"{settings.LLAMA_URL.rstrip('/')}/health", timeout=3.0)
        response.raise_for_status()
        if response.json().get("status") != "ok":
            raise RuntimeError("llama.cpp model is not ready")
    elif provider == "gemini":
        from incidentiq.inference import vertex_access_token

        vertex_access_token()
    else:
        raise RuntimeError("Unsupported model provider")


def get_graph() -> Any:
    """Resolve the cached graph and verify live dependencies for each request."""
    try:
        graph = _build_graph()
        _check_dependencies()
        return graph
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Incident analysis is unavailable.") from exc


def _validate_request(request: IncidentRequest) -> None:
    if not request.question.strip() or len(request.question) > 2000:
        raise HTTPException(status_code=422, detail="Question must contain 1 to 2000 characters.")
    if len(request.thread_id) > 128 or not _THREAD_ID.fullmatch(request.thread_id):
        raise HTTPException(status_code=422, detail="Thread ID must be 1 to 128 characters using letters, numbers, '.', '_', ':' or '-'.")


def _response_from_state(state: Any, elapsed_ms: float) -> IncidentResponse:
    if not isinstance(state, Mapping):
        raise ValueError("Graph returned no state")
    evidence = state.get("evidence", [])
    if not isinstance(evidence, list):
        raise ValueError("Invalid evidence")
    chunks = {RetrievedEvidence.model_validate(item).chunk_id for item in evidence}
    required = ("answer", "citations", "specialist_route", "provider", "abstained")
    data = {key: state[key] for key in required}
    data["latency_ms"] = state.get("latency_ms", elapsed_ms)
    response = IncidentResponse.model_validate(data, strict=True)
    if not response.answer.strip() or not response.specialist_route.strip() or not response.provider.strip():
        raise ValueError("Graph returned empty response fields")
    if not math.isfinite(response.latency_ms):
        raise ValueError("Graph returned invalid latency")
    if any(citation not in chunks for citation in response.citations):
        raise ValueError("Citation is absent from evidence")
    if response.abstained and response.citations:
        raise ValueError("Abstention contains citations")
    return response


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
def ready(graph: Any = Depends(get_graph)) -> dict[str, str]:
    return {"status": "ready"}


@app.post("/ask", response_model=IncidentResponse)
async def ask(request: IncidentRequest, graph: Any = Depends(get_graph)) -> IncidentResponse:
    _validate_request(request)
    inputs = {"question": request.question, "thread_id": request.thread_id}
    config = {"configurable": {"thread_id": request.thread_id}}
    start = perf_counter()
    try:
        if callable(getattr(graph, "ainvoke", None)):
            result = graph.ainvoke(inputs, config=config)
            state = await result if inspect.isawaitable(result) else result
        else:
            state = await run_in_threadpool(graph.invoke, inputs, config=config)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Incident analysis is unavailable.") from exc
    try:
        return _response_from_state(state, (perf_counter() - start) * 1000)
    except (ValueError, TypeError, KeyError, ValidationError) as exc:
        raise HTTPException(status_code=502, detail="Incident analysis returned an invalid response.") from exc
