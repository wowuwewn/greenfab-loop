import pytest
from pydantic import ValidationError

from app.config import ApiKeyCredential, Settings
from app.enums import ApiRole


def test_production_rejects_demo_seed_and_reset() -> None:
    for overrides in (
        {"seed_demo_data": True, "demo_reset_enabled": False},
        {"seed_demo_data": False, "demo_reset_enabled": True},
    ):
        with pytest.raises(ValidationError, match="must be false outside"):
            Settings(environment="production", demo_mode=False, **overrides)


def test_production_accepts_disabled_demo_mutations() -> None:
    production = Settings(
        environment="production",
        demo_mode=False,
        seed_demo_data=False,
        demo_reset_enabled=False,
        auth_mode="required",
        api_key_credentials=[
            ApiKeyCredential(
                key_id="production-admin",
                secret_sha256="a" * 64,
                actor="production_admin",
                role=ApiRole.ADMIN,
            )
        ],
    )

    assert production.environment == "production"


def test_production_rejects_demo_auth_and_required_auth_without_keys() -> None:
    with pytest.raises(ValidationError, match="AUTH_MODE must be required"):
        Settings(
            environment="production",
            demo_mode=False,
            seed_demo_data=False,
            demo_reset_enabled=False,
            auth_mode="demo",
        )
    with pytest.raises(ValidationError, match="at least one key"):
        Settings(
            environment="production",
            demo_mode=False,
            seed_demo_data=False,
            demo_reset_enabled=False,
            auth_mode="required",
            api_key_credentials=[],
        )


def test_non_local_environment_rejects_demo_features() -> None:
    with pytest.raises(ValidationError, match="must be false outside"):
        Settings(
            environment="staging",
            auth_mode="required",
            api_key_credentials=[
                ApiKeyCredential(
                    key_id="staging-admin",
                    secret_sha256="b" * 64,
                    actor="staging_admin",
                    role=ApiRole.ADMIN,
                )
            ],
            demo_mode=True,
            seed_demo_data=False,
            demo_reset_enabled=False,
        )


def test_cors_requires_explicit_origins() -> None:
    with pytest.raises(ValidationError, match="explicit origins"):
        Settings(cors_origins=["*"])

    settings = Settings(cors_origins=[" http://localhost:5173/ ", "http://localhost:5173"])

    assert settings.cors_origins == ["http://localhost:5173"]


def test_demo_actor_cannot_be_blank() -> None:
    with pytest.raises(ValidationError, match="DEMO_ACTOR cannot be blank"):
        Settings(demo_actor="   ")
