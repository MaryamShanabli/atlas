"""
Central application configuration.

Design decision: API keys default to None rather than raising on import.
This lets the app boot and serve /health and core CRUD even before every
third-party key is provisioned (relevant during incremental development —
see Phase 7 Stage 0 discussion). Each service that depends on a specific
key checks for its presence at call time and returns a clear degraded-mode
error rather than letting the whole app fail to start.
"""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str = "postgresql://atlas:atlas@db:5432/atlas"

    # Third-party API keys — optional at boot, required at call time
    openweathermap_api_key: str | None = None
    youtube_api_key: str | None = None
    google_maps_api_key: str | None = None
    rest_countries_api_key: str | None = None

    # App
    app_env: str = "development"
    log_level: str = "info"

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor — avoids re-reading the environment on every call."""
    return Settings()
