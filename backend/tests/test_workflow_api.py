from __future__ import annotations

from sqlalchemy import func, select

from app.config import settings
from app.enums import ResourceConfirmationStatus, SourceType, WorkflowStatus
from app.models import (
    AuditEvent,
    Case,
    Decision,
    ESGScenario,
    MatchRun,
    Receipt,
    ResourceConfirmation,
)
from app.seed import GOLDEN_CASE_ID

CONFIRMATION = {
    "status": "CONFIRMED",
    "confirmed_by": "demo_operator",
}

PASSPORT = {
    "description": (
        "반도체 세정 공정에서 회수된 미세 무기질 분말. "
        "이산화규소 비중이 높아 성분 분석 후 재활용 후보 검토가 필요함."
    ),
    "quantity": 12,
    "unit": "kg",
    "condition": "건조 분말",
    "location": "제조동 A",
    "composition": "이산화규소 중심 합성 DEMO 성분표",
}


def _confirm_and_save_passport(client) -> None:
    response = client.put(
        f"/api/v1/cases/{GOLDEN_CASE_ID}/resource-confirmation",
        json=CONFIRMATION,
    )
    assert response.status_code == 200, response.text
    response = client.put(
        f"/api/v1/cases/{GOLDEN_CASE_ID}/resource-passport",
        json=PASSPORT,
    )
    assert response.status_code == 200, response.text


def test_golden_case_completes_full_workflow(client, session_factory) -> None:
    initial = client.get(f"/api/v1/cases/{GOLDEN_CASE_ID}")
    assert initial.status_code == 200
    initial_body = initial.json()
    assert list(initial_body) == [
        "case",
        "resource_confirmation",
        "resource_passport",
        "match",
        "decision",
        "esg_scenario",
        "receipt",
    ]
    assert initial_body["case"]["source_type"] == "REAL"
    assert initial_body["resource_confirmation"]["status"] == "PENDING"
    assert initial_body["resource_passport"] is None

    _confirm_and_save_passport(client)

    match = client.post(
        f"/api/v1/cases/{GOLDEN_CASE_ID}/matches",
        json={"top_k": 3},
        headers={"Idempotency-Key": "golden-match-v1"},
    )
    assert match.status_code == 200, match.text
    match_body = match.json()["match"]
    assert match_body["model"] == "Xenova/bge-m3"
    assert match_body["source_type"] == "DEMO"
    assert [candidate["demand_id"] for candidate in match_body["candidates"]] == [
        "D01",
        "D15",
        "D11",
    ]
    assert match_body["candidates"][0]["status"] == "REVIEW"
    assert match_body["candidates"][0]["rule_check"]["location"] is None

    repeated = client.post(
        f"/api/v1/cases/{GOLDEN_CASE_ID}/matches",
        json={"top_k": 3},
        headers={"Idempotency-Key": "golden-match-v1"},
    )
    assert repeated.status_code == 200

    decision = client.put(
        f"/api/v1/cases/{GOLDEN_CASE_ID}/decision",
        json={
            "status": "APPROVED",
            "selected_demand_id": "D01",
            "reason": "성분 분석 완료 후 파일럿 검토를 진행합니다.",
            "decided_by": "demo_manager",
        },
    )
    assert decision.status_code == 200, decision.text
    assert decision.json()["decision"]["status"] == "APPROVED"

    scenario = client.post(f"/api/v1/cases/{GOLDEN_CASE_ID}/esg-scenario")
    assert scenario.status_code == 200, scenario.text
    scenario_body = scenario.json()["esg_scenario"]
    assert scenario_body["source_type"] == "SCENARIO"
    assert scenario_body["results"] == {
        "candidate_diversion_quantity": 12.0,
        "unit": "kg",
    }
    assert scenario_body["factor_source"] is None

    receipt = client.post(
        f"/api/v1/cases/{GOLDEN_CASE_ID}/receipt",
        headers={"Idempotency-Key": "golden-receipt-v1"},
    )
    assert receipt.status_code == 200, receipt.text
    receipt_body = receipt.json()["receipt"]
    assert receipt_body["decision_status"] == "APPROVED"
    assert receipt_body["handoff_status"] == "APPROVED"

    downloaded = client.get(f"/api/v1/cases/{GOLDEN_CASE_ID}/receipt")
    assert downloaded.status_code == 200
    downloaded_body = downloaded.json()
    assert list(downloaded_body) == list(initial_body)
    assert downloaded_body["receipt"]["receipt_id"] == receipt_body["receipt_id"]
    assert downloaded_body["decision"]["reason"] == ("성분 분석 완료 후 파일럿 검토를 진행합니다.")

    with session_factory() as session:
        assert session.scalar(select(func.count(MatchRun.match_run_id))) == 1
        stored_receipt = session.scalar(select(Receipt))
        stored_decision = session.scalar(select(Decision))
        stored_scenario = session.scalar(select(ESGScenario))
        assert stored_receipt is not None
        assert stored_decision is not None
        assert stored_scenario is not None
        assert stored_decision.selected_match_candidate_id is not None
        assert stored_scenario.decision_id == stored_decision.decision_id
        assert stored_receipt.decision_id == stored_decision.decision_id
        assert stored_receipt.scenario_id == stored_scenario.scenario_id
        assert stored_receipt.payload_json["receipt"]["receipt_id"] == receipt_body["receipt_id"]
        assert session.scalar(select(func.count(AuditEvent.audit_event_id))) == 7


def test_not_confirmed_closes_case_and_blocks_passport(client) -> None:
    confirmation = client.put(
        f"/api/v1/cases/{GOLDEN_CASE_ID}/resource-confirmation",
        json={"status": "NOT_CONFIRMED", "confirmed_by": "demo_operator"},
    )
    assert confirmation.status_code == 200
    body = confirmation.json()
    assert body["resource_confirmation"]["status"] == "NOT_CONFIRMED"
    assert all(
        body[key] is None
        for key in (
            "resource_passport",
            "match",
            "decision",
            "esg_scenario",
            "receipt",
        )
    )

    blocked = client.put(
        f"/api/v1/cases/{GOLDEN_CASE_ID}/resource-passport",
        json=PASSPORT,
    )
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "INVALID_STATE"


def test_invalid_state_and_validation_errors_use_common_shape(client) -> None:
    premature = client.post(
        f"/api/v1/cases/{GOLDEN_CASE_ID}/matches",
        json={"top_k": 3},
    )
    assert premature.status_code == 409
    assert premature.json()["error"]["trace_id"]

    _confirm_and_save_passport(client)
    invalid_passport = client.put(
        f"/api/v1/cases/{GOLDEN_CASE_ID}/resource-passport",
        json={"description": "수량 단위 누락", "quantity": 12},
    )
    assert invalid_passport.status_code == 422
    assert invalid_passport.json()["error"]["code"] == "VALIDATION_ERROR"

    unit_without_quantity = client.put(
        f"/api/v1/cases/{GOLDEN_CASE_ID}/resource-passport",
        json={"description": "수량 미확인", "unit": "kg"},
    )
    assert unit_without_quantity.status_code == 422


def test_whitespace_only_human_inputs_are_rejected(client) -> None:
    confirmation = client.put(
        f"/api/v1/cases/{GOLDEN_CASE_ID}/resource-confirmation",
        json={"status": "CONFIRMED", "confirmed_by": "   "},
    )
    assert confirmation.status_code == 422

    accepted = client.put(
        f"/api/v1/cases/{GOLDEN_CASE_ID}/resource-confirmation",
        json=CONFIRMATION,
    )
    assert accepted.status_code == 200
    empty_passport = client.put(
        f"/api/v1/cases/{GOLDEN_CASE_ID}/resource-passport",
        json={"description": "   "},
    )
    assert empty_passport.status_code == 422

    whitespace_actor = client.put(
        f"/api/v1/cases/{GOLDEN_CASE_ID}/resource-passport",
        json=PASSPORT,
        headers={"X-Actor": "   "},
    )
    assert whitespace_actor.status_code == 422


def test_needs_info_candidate_cannot_be_approved(client) -> None:
    confirmation = client.put(
        f"/api/v1/cases/{GOLDEN_CASE_ID}/resource-confirmation",
        json=CONFIRMATION,
    )
    assert confirmation.status_code == 200
    passport = client.put(
        f"/api/v1/cases/{GOLDEN_CASE_ID}/resource-passport",
        json={
            "description": "반도체 세정 공정에서 회수된 성분 미확인 무기질 분말",
            "quantity": 12,
            "unit": "kg",
        },
    )
    assert passport.status_code == 200
    match = client.post(
        f"/api/v1/cases/{GOLDEN_CASE_ID}/matches",
        json={"top_k": 3},
    )
    assert match.status_code == 200
    assert match.json()["match"]["candidates"][0]["status"] == "NEEDS_INFO"

    decision = client.put(
        f"/api/v1/cases/{GOLDEN_CASE_ID}/decision",
        json={
            "status": "APPROVED",
            "selected_demand_id": "D01",
            "reason": "성분 미확인 상태에서 승인을 시도합니다.",
            "decided_by": "demo_manager",
        },
    )
    assert decision.status_code == 409
    assert decision.json()["error"]["code"] == "CANDIDATE_NOT_REVIEWABLE"


def test_match_provider_failure_does_not_leak_internal_details(client) -> None:
    class FailingProvider:
        def match(self, passport, *, top_k=3):
            raise RuntimeError("/private/model-cache: connection password=secret")

    _confirm_and_save_passport(client)
    client.app.state.match_provider = FailingProvider()
    response = client.post(
        f"/api/v1/cases/{GOLDEN_CASE_ID}/matches",
        json={"top_k": 3},
    )
    assert response.status_code == 503
    body = response.json()
    assert body["error"]["code"] == "MATCH_UNAVAILABLE"
    assert "private" not in body["error"]["message"]
    assert "secret" not in body["error"]["message"]


def test_hold_flow_keeps_zero_as_a_deliberate_scenario_result(client) -> None:
    _confirm_and_save_passport(client)
    match = client.post(
        f"/api/v1/cases/{GOLDEN_CASE_ID}/matches",
        json={"top_k": 3},
    )
    assert match.status_code == 200
    decision = client.put(
        f"/api/v1/cases/{GOLDEN_CASE_ID}/decision",
        json={
            "status": "HOLD",
            "selected_demand_id": None,
            "reason": "추가 성분 검토 전까지 의사결정을 보류합니다.",
            "decided_by": "demo_manager",
        },
    )
    assert decision.status_code == 200
    scenario = client.post(f"/api/v1/cases/{GOLDEN_CASE_ID}/esg-scenario")
    assert scenario.status_code == 200
    assert scenario.json()["esg_scenario"]["results"] == {
        "candidate_diversion_quantity": 0,
        "unit": "kg",
    }
    receipt = client.post(f"/api/v1/cases/{GOLDEN_CASE_ID}/receipt")
    assert receipt.status_code == 200
    assert receipt.json()["receipt"]["handoff_status"] == "RESOURCE_CONFIRMED"


def test_openapi_exposes_contract_envelope_and_common_errors(client) -> None:
    document = client.get("/openapi.json").json()
    paths = document["paths"]
    receipt_get = paths["/api/v1/cases/{case_id}/receipt"]["get"]
    receipt_schema = receipt_get["responses"]["200"]["content"]["application/json"]["schema"]
    assert receipt_schema["$ref"].endswith("/CaseEnvelope")
    for status_code in ("404", "409", "422", "500", "503"):
        error_schema = receipt_get["responses"][status_code]["content"]["application/json"][
            "schema"
        ]
        assert error_schema["$ref"].endswith("/ErrorResponse")


def test_demo_reset_is_disabled_by_default(client) -> None:
    response = client.post("/api/v1/demo/reset")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_demo_reset_is_repeatable_and_scoped(client, session_factory, monkeypatch) -> None:
    monkeypatch.setattr(settings, "demo_reset_enabled", True)
    with session_factory.begin() as session:
        unrelated = Case(
            case_id="SECOM-UNRELATED",
            risk_rank=None,
            shap_top_features=[],
            source_type=SourceType.REAL,
            workflow_status=WorkflowStatus.CONFIRMATION_PENDING,
        )
        unrelated.resource_confirmation = ResourceConfirmation(
            status=ResourceConfirmationStatus.PENDING,
            source_type=SourceType.DEMO,
        )
        session.add(unrelated)

    _confirm_and_save_passport(client)
    first = client.post("/api/v1/demo/reset")
    second = client.post("/api/v1/demo/reset")
    assert first.status_code == second.status_code == 200
    assert second.json()["resource_confirmation"]["status"] == "PENDING"
    assert second.json()["resource_passport"] is None
    with session_factory() as session:
        assert session.get(Case, "SECOM-UNRELATED") is not None


def test_health_checks_database_and_match_provider(client) -> None:
    live = client.get("/health/live")
    ready = client.get("/health/ready")
    assert live.status_code == 200
    assert ready.status_code == 200
    assert ready.json() == {
        "status": "ready",
        "database": "ok",
        "match_provider": "MockMatchProvider",
        "evidence_storage": "LocalEvidenceStorage",
    }


def test_oversized_trace_id_is_replaced_with_a_safe_server_id(client) -> None:
    supplied = "x" * 65
    response = client.get("/health/live", headers={"X-Trace-Id": supplied})
    assert response.status_code == 200
    assert response.headers["X-Trace-Id"] != supplied
    assert len(response.headers["X-Trace-Id"]) <= 64
