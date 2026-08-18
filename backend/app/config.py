"""Application configuration loaded from environment variables."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.enums import ApiRole


class ApiKeyCredential(BaseModel):
    """One API principal configured by a SHA-256 secret digest."""

    key_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")
    secret_sha256: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    actor: str = Field(min_length=1, max_length=120)
    role: ApiRole

    @field_validator("actor")
    @classmethod
    def strip_actor(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("actor cannot be blank")
        return stripped


class Settings(BaseSettings):
    """Runtime settings shared by the API, database, and migration tooling."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "GreenFab Loop API"
    environment: str = "development"
    api_v1_prefix: str = "/api/v1"
    database_url: str = "postgresql+psycopg://greenfab:greenfab@localhost:5432/greenfab"
    database_echo: bool = False
    database_pool_size: int = Field(default=5, ge=1, le=50)
    database_max_overflow: int = Field(default=10, ge=0, le=100)
    database_pool_timeout_seconds: int = Field(default=10, ge=1, le=120)
    demo_mode: bool = True
    seed_demo_data: bool = True
    demo_reset_enabled: bool = False
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    auth_mode: Literal["demo", "required"] = "demo"
    api_key_credentials: list[ApiKeyCredential] = Field(default_factory=list)
    demo_actor: str = Field(default="demo_operator", min_length=1, max_length=120)
    evidence_storage_root: Path = Path("var/evidence")
    evidence_max_bytes: int = Field(default=5 * 1024 * 1024, ge=1024, le=25 * 1024 * 1024)
    detect_artifact_max_bytes: int = Field(
        default=20 * 1024 * 1024,
        ge=1024,
        le=100 * 1024 * 1024,
    )

    @field_validator("demo_actor")
    @classmethod
    def strip_demo_actor(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("DEMO_ACTOR cannot be blank")
        return stripped

    @field_validator("cors_origins")
    @classmethod
    def reject_wildcard_cors(cls, value: list[str]) -> list[str]:
        origins = [origin.strip().rstrip("/") for origin in value if origin.strip()]
        if not origins or "*" in origins:
            raise ValueError("CORS_ORIGINS must contain explicit origins")
        return list(dict.fromkeys(origins))

    @model_validator(mode="after")
    def forbid_demo_mutations_in_production(self) -> "Settings":
        environment = self.environment.strip().casefold()
        demo_environments = {"development", "test", "local"}
        if environment not in demo_environments and (
            self.demo_mode or self.seed_demo_data or self.demo_reset_enabled
        ):
            raise ValueError(
                "DEMO_MODE, SEED_DEMO_DATA, and DEMO_RESET_ENABLED must be false "
                "outside development, test, or local"
            )
        if environment == "production":
            if self.auth_mode != "required":
                raise ValueError("AUTH_MODE must be required in production")
        if self.auth_mode == "demo" and environment not in demo_environments:
            raise ValueError("AUTH_MODE=demo is allowed only in development, test, or local")
        if self.auth_mode == "demo" and not self.demo_mode:
            raise ValueError("AUTH_MODE=demo requires DEMO_MODE=true")
        if self.auth_mode == "required" and not self.api_key_credentials:
            raise ValueError("API_KEY_CREDENTIALS must contain at least one key in required mode")
        key_ids = [credential.key_id for credential in self.api_key_credentials]
        if len(key_ids) != len(set(key_ids)):
            raise ValueError("API_KEY_CREDENTIALS key_id values must be unique")
        secret_hashes = [
            credential.secret_sha256.casefold() for credential in self.api_key_credentials
        ]
        if len(secret_hashes) != len(set(secret_hashes)):
            raise ValueError("API_KEY_CREDENTIALS secret hashes must be unique")
        return self


@lru_cache
def get_settings() -> Settings:
    """Return one cached settings object per process."""

    return Settings()


settings = get_settings()
