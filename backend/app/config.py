"""Application configuration loaded from environment variables."""

from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    demo_mode: bool = True
    seed_demo_data: bool = True
    demo_reset_enabled: bool = False
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    @model_validator(mode="after")
    def forbid_demo_mutations_in_production(self) -> "Settings":
        if self.environment.casefold() == "production" and (
            self.seed_demo_data or self.demo_reset_enabled
        ):
            raise ValueError("SEED_DEMO_DATA and DEMO_RESET_ENABLED must be false in production")
        return self


@lru_cache
def get_settings() -> Settings:
    """Return one cached settings object per process."""

    return Settings()


settings = get_settings()
