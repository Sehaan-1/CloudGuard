from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: Literal["development", "staging", "production", "testing"] = Field(
        default="development"
    )
    log_level: str = Field(default="INFO")
    default_provider: str = Field(default="mock")
    data_dir: Path = Field(default=Path("./data"))

    azure_tenant_id: str | None = Field(default=None)
    azure_client_id: str | None = Field(default=None)
    azure_client_secret: str | None = Field(default=None)
    azure_subscription_id: str | None = Field(default=None)

    aws_access_key_id: str | None = Field(default=None)
    aws_secret_access_key: str | None = Field(default=None)
    aws_default_region: str = Field(default="us-east-1")
    aws_session_token: str | None = Field(default=None)

    zscore_threshold: float = Field(default=3.0, ge=1.0)
    iqr_multiplier: float = Field(default=1.5, ge=0.5)
    idle_cpu_threshold_pct: float = Field(default=5.0, ge=0.0, le=100.0)
    idle_period_days: int = Field(default=7, ge=1)
    orphaned_storage_days: int = Field(default=30, ge=1)
    underutilized_vm_threshold_pct: float = Field(default=20.0, ge=0.0, le=100.0)

    database_url: str = Field(default="sqlite+aiosqlite:///./data/cloudguard.db")
    redis_url: str = Field(default="redis://localhost:6379/0")
    cache_ttl_seconds: int = Field(default=300, ge=1)

    @property
    def anomaly_zscore_threshold(self) -> float:
        return self.zscore_threshold

    @property
    def anomaly_iqr_multiplier(self) -> float:
        return self.iqr_multiplier

    @property
    def has_azure_credentials(self) -> bool:
        return bool(self.azure_subscription_id)

    @property
    def has_aws_credentials(self) -> bool:
        return bool(self.aws_access_key_id and self.aws_secret_access_key)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
