import pytest
from pydantic import ValidationError

from app.config import Settings


def test_production_rejects_demo_seed_and_reset() -> None:
    for overrides in (
        {"seed_demo_data": True, "demo_reset_enabled": False},
        {"seed_demo_data": False, "demo_reset_enabled": True},
    ):
        with pytest.raises(ValidationError, match="must be false in production"):
            Settings(environment="production", **overrides)


def test_production_accepts_disabled_demo_mutations() -> None:
    production = Settings(
        environment="production",
        seed_demo_data=False,
        demo_reset_enabled=False,
    )

    assert production.environment == "production"
