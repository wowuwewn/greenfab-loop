from __future__ import annotations

from pathlib import Path

import yaml


def test_render_blueprint_keeps_production_safety_contract() -> None:
    root = Path(__file__).resolve().parents[2]
    blueprint = yaml.safe_load((root / "render.yaml").read_text())

    service = blueprint["services"][0]
    assert service["type"] == "web"
    assert service["rootDir"] == "backend"
    assert service["healthCheckPath"] == "/health/live"
    assert service["numInstances"] == 1
    assert service["startCommand"].endswith("--workers 1")
    assert service["preDeployCommand"] == "alembic upgrade head"
    assert service["disk"]["mountPath"] == "/var/data"

    environment = {item["key"]: item for item in service["envVars"]}
    assert environment["ENVIRONMENT"]["value"] == "production"
    assert environment["AUTH_MODE"]["value"] == "required"
    assert environment["DEMO_MODE"]["value"] == "false"
    assert environment["SEED_DEMO_DATA"]["value"] == "false"
    assert environment["DEMO_RESET_ENABLED"]["value"] == "false"
    assert environment["EVIDENCE_STORAGE_BACKEND"]["value"] == "s3"
    assert environment["MATCH_PROVIDER"]["value"] == "bge_chroma"
    assert environment["BGE_DEVICE"]["value"] == "cpu"
    assert environment["API_KEY_CREDENTIALS"]["sync"] is False
    assert environment["CORS_ORIGINS"]["sync"] is False

    database = blueprint["databases"][0]
    assert database["postgresMajorVersion"] == "16"
    assert database["ipAllowList"] == []
