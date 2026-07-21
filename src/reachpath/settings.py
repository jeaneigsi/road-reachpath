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
    service_max_retries: int = 2
    service_retry_backoff_seconds: float = 0.25
    monthly_budget_usd: float = 100.0
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    oauth_encryption_key: str | None = None
    oauth_state_ttl_seconds: int = 600
    hubspot_client_id: str | None = None
    hubspot_client_secret: str | None = None
    hubspot_redirect_uri: str | None = None
    salesforce_client_id: str | None = None
    salesforce_client_secret: str | None = None
    salesforce_redirect_uri: str | None = None
    pipedrive_client_id: str | None = None
    pipedrive_client_secret: str | None = None
    pipedrive_redirect_uri: str | None = None
    salesforce_api_version: str = "v60.0"


@lru_cache
def get_settings() -> Settings:
    return Settings()
