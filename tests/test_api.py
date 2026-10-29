"""Contract tests for the HTTP boundary; no production graph is required."""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from incidentiq.api import app, get_graph
from incidentiq.schemas import IncidentRequest


class StubGraph:
    def __init__(self, state=None, error=None):
        self.state = state or {
            "answer": "The restart restored service.",
            "citations": ["incident-1:chunk-2"],
            "specialist_route": "operations",
            "provider": "llama",
            "abstained": False,
            "evidence": [{
                "document_id": "incident-1",
                "chunk_id": "incident-1:chunk-2",
                "text": "Restart restored service.",
                "similarity_score": 0.91,
                "metadata": {},
            }],
        }
        self.error = error
        self.calls = []

    async def ainvoke(self, inputs, config):
        self.calls.append((inputs, config))
        if self.error:
            raise self.error
        return self.state


@pytest.fixture
def client():
    graph = StubGraph()
    app.dependency_overrides[get_graph] = lambda: graph
    with TestClient(app) as test_client:
        yield test_client, graph
    app.dependency_overrides.clear()


def test_health_is_independent_of_graph():
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}


def test_ready_without_graph_is_controlled(monkeypatch):
    from incidentiq import api

    def missing_graph():
        raise RuntimeError("graph missing")

    monkeypatch.setattr(api, "_build_graph", missing_graph)
    with TestClient(app) as client:
        result = client.get("/ready")
    assert result.status_code == 503
    assert result.json() == {"detail": "Incident analysis is unavailable."}


def test_ready_checks_dependencies_after_graph_is_cached(monkeypatch):
    from functools import lru_cache
    from incidentiq import api

    @lru_cache(maxsize=1)
    def cached_graph():
        return StubGraph()

    cached_graph()
    monkeypatch.setattr(api, "_build_graph", cached_graph)
    monkeypatch.setattr(api, "_check_dependencies", lambda: (_ for _ in ()).throw(RuntimeError("corpus missing")))
    with TestClient(app) as client:
        result = client.get("/ready")
    assert result.status_code == 503
    assert result.json() == {"detail": "Incident analysis is unavailable."}
    assert cached_graph.cache_info().hits == 1


def test_ready_with_graph(client):
    test_client, _ = client
    assert test_client.get("/ready").json() == {"status": "ready"}


def test_ask_maps_graph_state_and_preserves_thread_id(client):
    test_client, graph = client
    result = test_client.post("/ask", json={"question": "What restored service?", "thread_id": "incident.123"})
    assert result.status_code == 200
    payload = result.json()
    assert payload["answer"] == "The restart restored service."
    assert payload["citations"] == ["incident-1:chunk-2"]
    assert payload["specialist_route"] == "operations"
    assert payload["provider"] == "llama"
    assert payload["abstained"] is False
    assert payload["latency_ms"] >= 0
    assert graph.calls == [(
        {"question": "What restored service?", "thread_id": "incident.123"},
        {"configurable": {"thread_id": "incident.123"}},
    )]


def test_sync_graph_can_be_injected(client):
    test_client, graph = client

    class SyncGraph:
        def invoke(self, inputs, config):
            assert config == {"configurable": {"thread_id": "abc"}}
            return graph.state

    app.dependency_overrides[get_graph] = SyncGraph
    result = test_client.post("/ask", json={"question": "What happened?", "thread_id": "abc"})
    assert result.status_code == 200


@pytest.mark.parametrize("body", [
    {"question": "", "thread_id": "abc"},
    {"question": "  ", "thread_id": "abc"},
    {"question": "x" * 2001, "thread_id": "abc"},
    {"question": "hello", "thread_id": ""},
    {"question": "hello", "thread_id": "bad id"},
    {"question": "hello", "thread_id": "a" * 129},
])
def test_invalid_requests_never_invoke_graph(client, body):
    test_client, graph = client
    result = test_client.post("/ask", json=body)
    assert result.status_code == 422
    assert graph.calls == []


def test_shared_request_schema_rejects_empty_fields():
    with pytest.raises(ValidationError):
        IncidentRequest(question="", thread_id="abc")
    with pytest.raises(ValidationError):
        IncidentRequest(question="hello", thread_id="")


@pytest.mark.parametrize("state", [
    {"answer": "made up", "citations": ["missing"], "specialist_route": "ops", "provider": "llama", "abstained": False},
    {"answer": "text", "citations": [], "specialist_route": "ops", "provider": "llama"},
    {"answer": "text", "specialist_route": "ops", "provider": "llama", "abstained": False},
    {"answer": " ", "citations": [], "specialist_route": "ops", "provider": "llama", "abstained": True},
    {"answer": "text", "citations": ["x"], "specialist_route": "ops", "provider": "llama", "abstained": True},
])
def test_invalid_graph_output_is_controlled(client, state):
    test_client, graph = client
    graph.state = state
    result = test_client.post("/ask", json={"question": "What happened?", "thread_id": "abc"})
    assert result.status_code == 502
    assert result.json() == {"detail": "Incident analysis returned an invalid response."}


def test_graph_failure_is_controlled(client):
    test_client, graph = client
    graph.error = RuntimeError("secret detail")
    result = test_client.post("/ask", json={"question": "What happened?", "thread_id": "abc"})
    assert result.status_code == 503
    assert "secret" not in str(result.json())


def test_invalid_input_is_rejected_before_dependency_probe(monkeypatch):
    from incidentiq import api

    calls = []
    monkeypatch.setattr(api, "_build_graph", lambda: StubGraph())
    monkeypatch.setattr(api, "_check_dependencies", lambda: calls.append("probed"))
    with TestClient(app) as test_client:
        assert test_client.post("/ask", json={"question": "   ", "thread_id": "x"}).status_code == 422
        assert test_client.post("/ask", json={"question": "what a, what b, what c, what d, what e", "thread_id": "x"}).status_code == 422
    assert calls == []


def test_optional_api_key_protects_ask_but_not_health(client, monkeypatch):
    test_client, graph = client
    monkeypatch.setenv("INCIDENTIQ_API_KEY", "demo-test-key")
    body = {"question": "What happened?", "thread_id": "auth-test"}
    assert test_client.get("/health").status_code == 200
    assert test_client.post("/ask", json=body).status_code == 401
    assert test_client.post("/ask", json=body, headers={"X-IncidentIQ-Key": "wrong"}).status_code == 401
    assert test_client.post("/ask", json=body, headers={"X-IncidentIQ-Key": "demo-test-key"}).status_code == 200
    assert len(graph.calls) == 1


def test_version_reports_configured_commit_without_graph(monkeypatch):
    monkeypatch.setenv("GIT_COMMIT_SHA", "abc123")
    monkeypatch.setenv("MODEL_PROVIDER", "llama")
    with TestClient(app) as test_client:
        assert test_client.get("/version").json() == {"git_commit_sha": "abc123", "model_provider": "llama"}


def test_process_local_concurrency_limit_returns_429(client):
    from incidentiq import api

    test_client, graph = client
    assert api._INFERENCE_SLOTS.acquire(blocking=False)
    assert api._INFERENCE_SLOTS.acquire(blocking=False)
    try:
        response = test_client.post("/ask", json={"question": "What happened?", "thread_id": "busy"})
        assert response.status_code == 429
        assert graph.calls == []
    finally:
        api._INFERENCE_SLOTS.release()
        api._INFERENCE_SLOTS.release()


def test_analysis_deadline_returns_controlled_504(client, monkeypatch):
    import asyncio

    test_client, _ = client
    monkeypatch.setenv("REQUEST_DEADLINE_SECONDS", "1")

    class SlowGraph:
        async def ainvoke(self, inputs, config):
            await asyncio.sleep(2)

    app.dependency_overrides[get_graph] = SlowGraph
    result = test_client.post("/ask", json={"question": "What happened?", "thread_id": "deadline"})
    assert result.status_code == 504
    assert result.json() == {"detail": "Incident analysis deadline exceeded."}
