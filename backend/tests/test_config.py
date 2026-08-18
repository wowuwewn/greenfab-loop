import pytest
from pydantic import ValidationError

from app.config import ApiKeyCredential, Settings
from app.enums import ApiRole

PRODUCTION_STORAGE = {
    "evidence_storage_backend": "s3",
    "evidence_s3_bucket": "greenfab-evidence",
    "evidence_s3_access_key_id": "test-access-key",
    "evidence_s3_secret_access_key": "test-secret-key",
}


def test_production_rejects_demo_seed_and_reset() -> None:
    for overrides in (
        {"seed_demo_data": True, "demo_reset_enabled": False},
        {"seed_demo_data": False, "demo_reset_enabled": True},
    ):
        with pytest.raises(ValidationError, match="must be false outside"):
            Settings(
                environment="production",
                demo_mode=False,
                **PRODUCTION_STORAGE,
                **overrides,
            )


def test_production_accepts_disabled_demo_mutations() -> None:
    production = Settings(
        environment="production",
        demo_mode=False,
        seed_demo_data=False,
        demo_reset_enabled=False,
        auth_mode="required",
        **PRODUCTION_STORAGE,
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
            **PRODUCTION_STORAGE,
        )
    with pytest.raises(ValidationError, match="at least one key"):
        Settings(
            environment="production",
            demo_mode=False,
            seed_demo_data=False,
            demo_reset_enabled=False,
            auth_mode="required",
            **PRODUCTION_STORAGE,
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


def test_match_rule_policy_key_is_fixed_until_provisioning_exists() -> None:
    with pytest.raises(ValidationError):
        Settings(match_rule_policy_key="custom-policy")


def test_render_postgres_url_uses_installed_psycopg_driver() -> None:
    settings = Settings(database_url="postgresql://user:password@db.internal/greenfab")

    assert settings.database_url == "postgresql+psycopg://user:password@db.internal/greenfab"


def test_production_requires_managed_evidence_storage() -> None:
    with pytest.raises(ValidationError, match="must be s3 in production"):
        Settings(
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


def test_s3_storage_requires_credentials() -> None:
    with pytest.raises(ValidationError, match="EVIDENCE_S3_BUCKET"):
        Settings(evidence_storage_backend="s3")


def test_production_s3_endpoint_requires_https_but_local_minio_allows_http() -> None:
    credentials = {
        **PRODUCTION_STORAGE,
        "evidence_s3_endpoint_url": "http://object-storage.internal:9000",
    }
    with pytest.raises(ValidationError, match="must use HTTPS"):
        Settings(
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
            **credentials,
        )

    local = Settings(environment="local", **credentials)
    assert local.evidence_s3_endpoint_url == "http://object-storage.internal:9000"
