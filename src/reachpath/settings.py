from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="REACHPATH_", extra="ignore")

    app_name: str = "ReachPath"
    environment: str = "local"
    dry_run: bool = True
    auto_execute: bool = True
    require_auth: bool = False
    api_keys: str = ""
    admin_api_keys: str = ""
    database_url: str = "sqlite:///./reachpath.db"
    argus_url: str = "http://127.0.0.1:8000"
    searchswarm_url: str = "http://127.0.0.1:8012"
    reportforge_url: str = "http://127.0.0.1:8011"
    argus_api_key: str | None = None
    searchswarm_api_key: str | None = None
    reportforge_api_key: str | None = None
    service_poll_interval_seconds: float = 1.0
    monthly_budget_usd: float = 100.0
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"


@lru_cache
def get_settings() -> Settings:
    return Settings()
