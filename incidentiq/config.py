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
    GEMINI_MODEL: str = "gemini-2.5-flash"
    API_URL: str = "http://localhost:8000"
