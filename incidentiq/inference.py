"""Synchronous inference adapters for local and cloud model APIs."""

from typing import Protocol

import httpx

from incidentiq.config import Settings


class InferenceProvider(Protocol):
    name: str

    def generate(self, prompt: str) -> str: ...


class LlamaProvider:
    """Call llama.cpp's OpenAI-compatible chat completion endpoint."""

    name = "llama"

    def __init__(self, base_url: str, timeout: float = 120.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def generate(self, prompt: str) -> str:
        response = httpx.post(
            f"{self.base_url}/v1/chat/completions",
            json={
                "model": "local",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0,
                "max_tokens": 256,
                "stream": False,
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]


class GeminiProvider:
    """Call Vertex AI Gemini with Application Default Credentials."""

    name = "gemini"

    def __init__(self, model: str, project: str, location: str, timeout: float = 120.0):
        self.model = model
        self.project = project
        self.location = location
        self.timeout = timeout

    def _url(self) -> str:
        endpoint = "aiplatform.googleapis.com" if self.location == "global" else f"{self.location}-aiplatform.googleapis.com"
        return (f"https://{endpoint}/v1/projects/{self.project}/locations/{self.location}"
                f"/publishers/google/models/{self.model}:generateContent")

    def generate(self, prompt: str) -> str:
        token = vertex_access_token()
        response = httpx.post(
            self._url(),
            headers={"Authorization": f"Bearer {token}"},
            json={"contents": [{"role": "user", "parts": [{"text": prompt}]}],
                  "generationConfig": {"temperature": 0, "maxOutputTokens": 512,
                                       "responseMimeType": "application/json"}},
            timeout=self.timeout,
        )
        response.raise_for_status()
        content = "".join(
            part.get("text", "")
            for candidate in response.json()["candidates"]
            for part in candidate["content"]["parts"]
            if not part.get("thought", False)
        )
        if not content.strip():
            raise ValueError("Vertex AI returned no text")
        return content


def vertex_access_token() -> str:
    """Resolve Cloud Run's service identity; never use a stored API key."""
    import google.auth
    from google.auth.transport.requests import Request

    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    if not credentials.valid:
        credentials.refresh(Request())
    if not credentials.token:
        raise RuntimeError("Vertex AI credentials have no access token")
    return credentials.token


def get_provider(settings: Settings | None = None) -> InferenceProvider:
    settings = settings or Settings()
    name = settings.MODEL_PROVIDER.lower()
    if name == "llama":
        return LlamaProvider(settings.LLAMA_URL)
    if name == "gemini":
        return GeminiProvider(settings.GEMINI_MODEL, settings.GCP_PROJECT, settings.VERTEX_LOCATION)
    raise ValueError(f"Unsupported MODEL_PROVIDER: {settings.MODEL_PROVIDER}")
