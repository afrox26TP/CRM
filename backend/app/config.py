from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    database_url: str = "sqlite:///./dokladflow.db"
    storage_path: Path = Path("./storage")
    cors_origins: str = "http://localhost:5173"
    document_ai_provider: str = "mock"
    google_cloud_project: str = ""
    google_cloud_location: str = "eu"
    google_document_ai_processor_id: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [value.strip() for value in self.cors_origins.split(",") if value.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
