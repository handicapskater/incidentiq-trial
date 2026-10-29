"""Vertex provider uses service identity and the configured global endpoint."""

from incidentiq import inference
import google.auth
from google.auth.transport import requests as google_requests


def test_llama_output_is_limited_to_256_tokens(monkeypatch):
    calls = []

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": "ok"}}]}

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return Response()

    monkeypatch.setattr(inference.httpx, "post", fake_post)
    assert inference.LlamaProvider("http://llama:8080").generate("prompt") == "ok"
    assert calls[0][1]["json"]["max_tokens"] == 256


def test_gemini_provider_uses_adc_and_vertex_global_endpoint(monkeypatch):
    class Credentials:
        valid = False
        token = None

        def refresh(self, request):
            self.valid = True
            self.token = "test-token"

    credentials = Credentials()
    monkeypatch.setattr(google.auth, "default", lambda scopes: (credentials, "test-project"))
    monkeypatch.setattr(google_requests, "Request", lambda: object())
    calls = []

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"candidates": [{"content": {"parts": [
                {"text": "private reasoning", "thought": True},
                {"text": '{"answer":"ok","citations":[],"abstained":true}'},
            ]}}]}

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return Response()

    monkeypatch.setattr(inference.httpx, "post", fake_post)
    provider = inference.GeminiProvider("gemini-3.5-flash-lite", "test-project", "global")
    assert provider.generate("test prompt") == '{"answer":"ok","citations":[],"abstained":true}'
    assert calls[0][0] == ("https://aiplatform.googleapis.com/v1/projects/test-project/"
                           "locations/global/publishers/google/models/gemini-3.5-flash-lite:generateContent")
    assert calls[0][1]["headers"] == {"Authorization": "Bearer test-token"}
    assert calls[0][1]["json"]["generationConfig"]["responseMimeType"] == "application/json"
    assert calls[0][1]["json"]["generationConfig"]["maxOutputTokens"] == 256
