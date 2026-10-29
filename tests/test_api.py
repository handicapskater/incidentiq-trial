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
