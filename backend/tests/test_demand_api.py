from __future__ import annotations

import hashlib

from sqlalchemy import select

from app.config import ApiKeyCredential, settings
from app.enums import ApiRole
from app.models import DemandIndexEvent
from app.services.match import IndexSyncResult, MockMatchProvider

DEMAND = {
    "demand_id": "DEMAND-TEST-001",
    "company_name": "테스트 세라믹",
    "demand_description": "실리콘계 미분말 5~20kg 수요",
    "quantity_min": 5,
    "quantity_max": 20,
    "unit": "kg",
    "location": "경상북도",
    "accepted_conditions": ["건조"],
    "required_fields": ["description", "quantity", "unit", "composition"],
    "source_type": "DEMO",
}


class IndexingMockProvider(MockMatchProvider):
    provider_name = "fake-index"

    def __init__(self) -> None:
        self.upserted: list[str] = []
        self.deleted: list[str] = []
        self.sync_calls = 0

    def sync_all_demands(self):
        self.sync_calls += 1
        return IndexSyncResult(upserted=4, deleted=1)

    def upsert_demand(self, demand_id):
        self.upserted.append(demand_id)

    def delete_demand(self, demand_id):
        self.deleted.append(demand_id)


def test_demand_crud_keeps_postgres_as_source_and_synchronizes_index(client) -> None:
    provider = IndexingMockProvider()
    client.app.state.match_provider = provider

    created = client.post("/api/v1/demands", json=DEMAND)
    assert created.status_code == 201, created.text
    assert created.json()["is_active"] is True
    assert provider.upserted == ["DEMAND-TEST-001"]

    listed = client.get("/api/v1/demands")
    assert listed.status_code == 200
    assert "DEMAND-TEST-001" in {item["demand_id"] for item in listed.json()}

    update_payload = {
        key: value for key, value in DEMAND.items() if key not in {"demand_id", "source_type"}
    }
    update_payload["company_name"] = "수정된 세라믹"
    updated = client.put("/api/v1/demands/DEMAND-TEST-001", json=update_payload)
    assert updated.status_code == 200
    assert updated.json()["company_name"] == "수정된 세라믹"
    assert provider.upserted[-1] == "DEMAND-TEST-001"

    deactivated = client.post("/api/v1/demands/DEMAND-TEST-001/deactivate")
    assert deactivated.status_code == 200
    assert deactivated.json()["is_active"] is False
    assert provider.deleted == ["DEMAND-TEST-001"]
    assert "DEMAND-TEST-001" not in {
        item["demand_id"] for item in client.get("/api/v1/demands").json()
    }
    inactive = client.get("/api/v1/demands?include_inactive=true").json()
    assert "DEMAND-TEST-001" in {item["demand_id"] for item in inactive}

    sync = client.post("/api/v1/demands/index/sync")
    assert sync.status_code == 200
    assert sync.json() == {"provider": "fake-index", "upserted": 4, "deleted": 1}


def test_demand_validation_and_duplicate_conflict(client) -> None:
    assert client.post("/api/v1/demands", json=DEMAND).status_code == 201
    duplicate = client.post("/api/v1/demands", json=DEMAND)
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "DEMAND_ALREADY_EXISTS"

    invalid = {**DEMAND, "demand_id": "DEMAND-INVALID", "unit": None}
    response = client.post("/api/v1/demands", json=invalid)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    scenario = {**DEMAND, "demand_id": "DEMAND-SCENARIO", "source_type": "SCENARIO"}
    assert client.post("/api/v1/demands", json=scenario).status_code == 422


def test_index_sync_is_explicitly_unavailable_for_mock_provider(client) -> None:
    response = client.post("/api/v1/demands/index/sync")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "DEMAND_INDEX_NOT_CONFIGURED"


def test_index_failure_reports_committed_postgres_write(client) -> None:
    class FailingIndexProvider(IndexingMockProvider):
        def upsert_demand(self, demand_id):
            raise RuntimeError(f"cannot index {demand_id}")

    client.app.state.match_provider = FailingIndexProvider()
    response = client.post("/api/v1/demands", json=DEMAND)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "DEMAND_INDEX_UNAVAILABLE"

    persisted = client.get("/api/v1/demands").json()
    assert "DEMAND-TEST-001" in {item["demand_id"] for item in persisted}
    events = client.get("/api/v1/demands/index/events").json()
    assert events[0]["status"] == "FAILED"
    assert events[0]["error_message"] == "RuntimeError"
    assert "cannot index" not in events[0]["error_message"]
    assert events[0]["target_version"] == 1
    assert len(events[0]["target_content_sha256"]) == 64


def test_failed_index_event_can_be_retried_as_current_desired_state(client) -> None:
    class RecoverableIndexProvider(IndexingMockProvider):
        available = False

        def upsert_demand(self, demand_id):
            if not self.available:
                raise RuntimeError("temporary outage")
            super().upsert_demand(demand_id)

    provider = RecoverableIndexProvider()
    client.app.state.match_provider = provider
    failed = client.post("/api/v1/demands", json=DEMAND)
    assert failed.status_code == 503
    original = client.get("/api/v1/demands/index/events").json()[0]
    assert original["status"] == "FAILED"

    provider.available = True
    retried = client.post(f"/api/v1/demands/index/events/{original['event_id']}/retry")
    assert retried.status_code == 201, retried.text
    assert retried.json()["status"] == "SUCCEEDED"
    assert retried.json()["event_id"] != original["event_id"]
    assert provider.upserted == [DEMAND["demand_id"]]


def test_demand_rbac_uses_api_principal_and_ignores_x_actor(
    client, session_factory, monkeypatch
) -> None:
    viewer_key = "viewer-demand-key-0001"
    operator_key = "operator-demand-key-01"
    admin_key = "admin-demand-key-00001"

    def credential(key_id, secret, actor, role):
        return ApiKeyCredential(
            key_id=key_id,
            secret_sha256=hashlib.sha256(secret.encode()).hexdigest(),
            actor=actor,
            role=role,
        )

    monkeypatch.setattr(settings, "auth_mode", "required")
    monkeypatch.setattr(
        settings,
        "api_key_credentials",
        [
            credential("viewer", viewer_key, "demand_viewer", ApiRole.VIEWER),
            credential("operator", operator_key, "demand_operator", ApiRole.OPERATOR),
            credential("admin", admin_key, "demand_admin", ApiRole.ADMIN),
        ],
    )

    assert client.get("/api/v1/demands").status_code == 401
    assert client.get("/api/v1/demands", headers={"X-API-Key": viewer_key}).status_code == 200
    assert (
        client.post(
            "/api/v1/demands",
            json=DEMAND,
            headers={"X-API-Key": operator_key},
        ).status_code
        == 403
    )
    created = client.post(
        "/api/v1/demands",
        json=DEMAND,
        headers={"X-API-Key": admin_key, "X-Actor": "spoofed-admin"},
    )
    assert created.status_code == 201, created.text

    with session_factory() as session:
        event = session.scalar(
            select(DemandIndexEvent).where(DemandIndexEvent.demand_id == DEMAND["demand_id"])
        )
        assert event is not None
        assert event.requested_by == "demand_admin"
        assert event.status == "SKIPPED"


def test_demo_reset_reconciles_demand_index(client, monkeypatch) -> None:
    provider = IndexingMockProvider()
    client.app.state.match_provider = provider
    monkeypatch.setattr(settings, "demo_reset_enabled", True)

    deactivated = client.post("/api/v1/demands/D01/deactivate")
    assert deactivated.status_code == 200
    assert provider.deleted == ["D01"]

    reset = client.post("/api/v1/demo/reset")
    assert reset.status_code == 200, reset.text
    assert provider.sync_calls == 1
    restored = {item["demand_id"] for item in client.get("/api/v1/demands").json()}
    assert "D01" in restored
    assert (
        client.put(
            "/api/v1/cases/SECOM-0116/resource-confirmation",
            json={"status": "CONFIRMED"},
        ).status_code
        == 200
    )
    assert (
        client.put(
            "/api/v1/cases/SECOM-0116/resource-passport",
            json={
                "description": "반도체 세정 공정에서 회수된 미세 무기질 분말",
                "quantity": 12,
                "unit": "kg",
                "composition": "이산화규소 중심 합성 DEMO 성분표",
            },
        ).status_code
        == 200
    )
    rematched = client.post("/api/v1/cases/SECOM-0116/matches", json={"top_k": 3})
    assert rematched.status_code == 200, rematched.text


def test_openapi_exposes_demand_management_contract(client) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert set(paths["/api/v1/demands"]) >= {"get", "post"}
    assert "put" in paths["/api/v1/demands/{demand_id}"]
    assert "post" in paths["/api/v1/demands/{demand_id}/deactivate"]
    assert "post" in paths["/api/v1/demands/index/sync"]
    assert "get" in paths["/api/v1/demands/index/events"]
    assert "post" in paths["/api/v1/demands/index/events/{event_id}/retry"]


def test_readiness_fails_when_selected_provider_is_not_ready(client) -> None:
    class UnreadyProvider(MockMatchProvider):
        def ready(self):
            raise RuntimeError("chroma unavailable")

    client.app.state.match_provider = UnreadyProvider()
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "MATCH_UNAVAILABLE"
    assert "chroma" not in response.json()["error"]["message"]
