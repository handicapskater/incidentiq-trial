"""Synchronous inference adapters for local and cloud model APIs."""

import os
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
                "stream": False,
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]


class GeminiProvider:
    """Call Gemini's generateContent REST API without an additional SDK."""

    name = "gemini"

    def __init__(self, model: str, api_key: str | None = None, timeout: float = 120.0):
        self.model = model
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self.timeout = timeout

    def generate(self, prompt: str) -> str:
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is required for the Gemini provider")
        response = httpx.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent",
            headers={"x-goog-api-key": self.api_key},
            json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0}},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return "".join(
            part.get("text", "")
            for candidate in response.json()["candidates"]
            for part in candidate["content"]["parts"]
        )


def get_provider(settings: Settings | None = None) -> InferenceProvider:
    settings = settings or Settings()
    name = settings.MODEL_PROVIDER.lower()
    if name == "llama":
        return LlamaProvider(settings.LLAMA_URL)
    if name == "gemini":
        return GeminiProvider(settings.GEMINI_MODEL)
    raise ValueError(f"Unsupported MODEL_PROVIDER: {settings.MODEL_PROVIDER}")
