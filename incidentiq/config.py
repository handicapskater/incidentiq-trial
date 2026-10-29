"""Environment-driven configuration."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    MODEL_PROVIDER: str = "llama"
    LLAMA_URL: str = "http://localhost:8080"
    GGUF_MODEL_PATH: str = ""
    CHROMA_PATH: str = "data/chroma"
    DATA_DIR: str = "data"
    GCP_PROJECT: str = "handicapskater-gcp"
    GCP_LOCATION: str = "us-central1"
    VERTEX_LOCATION: str = "global"
    GEMINI_MODEL: str = "gemini-3.5-flash-lite"
    API_URL: str = "http://localhost:8000"
    INCIDENTIQ_API_KEY: str = ""
    REQUEST_DEADLINE_SECONDS: int = 110
    GIT_COMMIT_SHA: str = "unknown"
