from __future__ import annotations

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

    def sync_all_demands(self):
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


def test_openapi_exposes_demand_management_contract(client) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert set(paths["/api/v1/demands"]) >= {"get", "post"}
    assert "put" in paths["/api/v1/demands/{demand_id}"]
    assert "post" in paths["/api/v1/demands/{demand_id}/deactivate"]
    assert "post" in paths["/api/v1/demands/index/sync"]


def test_readiness_fails_when_selected_provider_is_not_ready(client) -> None:
    class UnreadyProvider(MockMatchProvider):
        def ready(self):
            raise RuntimeError("chroma unavailable")

    client.app.state.match_provider = UnreadyProvider()
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "MATCH_UNAVAILABLE"
    assert "chroma" not in response.json()["error"]["message"]
