"""The Streamlit server sends its optional shared key only to the API."""

from incidentiq import ui
from incidentiq.schemas import IncidentRequest


def test_ui_sends_configured_key_from_server_environment(monkeypatch):
    monkeypatch.setenv("INCIDENTIQ_API_KEY", "server-only-test-key")
    calls = []

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"answer": "Supported answer", "citations": ["chunk-1"],
                    "specialist_route": "investigator", "provider": "llama",
                    "latency_ms": 1.0, "abstained": False}

    class Client:
        def __init__(self, timeout):
            assert timeout == 120.0

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, url, **kwargs):
            calls.append((url, kwargs))
            return Response()

    monkeypatch.setattr(ui.httpx, "Client", Client)
    response = ui._ask("http://api:8000/", IncidentRequest(question="What happened?", thread_id="t1"))
    assert response.answer == "Supported answer"
    assert calls[0][0] == "http://api:8000/ask"
    assert calls[0][1]["headers"] == {"X-IncidentIQ-Key": "server-only-test-key"}
    assert calls[0][1]["json"] == {"question": "What happened?", "thread_id": "t1"}
