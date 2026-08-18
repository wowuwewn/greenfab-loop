from __future__ import annotations

import hashlib

import pytest
from sqlalchemy import select

from app.config import ApiKeyCredential, settings
from app.enums import (
    ApiRole,
    ResourceConfirmationStatus,
    SourceType,
    WorkflowStatus,
)
from app.errors import DomainError
from app.models import Case, PassportEvidence, ResourceConfirmation
from app.seed import GOLDEN_CASE_ID

CONFIRMATION = {"status": "CONFIRMED", "confirmed_by": "demo_operator"}
PASSPORT = {
    "description": "반도체 세정 공정에서 회수된 미세 무기질 분말",
    "quantity": 12,
    "unit": "kg",
    "condition": "건조 분말",
    "location": "제조동 A",
    "composition": "이산화규소 중심 합성 성분표",
}


def _credential(key_id: str, secret: str, actor: str, role: ApiRole) -> ApiKeyCredential:
    return ApiKeyCredential(
        key_id=key_id,
        secret_sha256=hashlib.sha256(secret.encode()).hexdigest(),
        actor=actor,
        role=role,
    )


def test_required_auth_injects_actor_and_enforces_roles(client, monkeypatch) -> None:
    viewer_key = "viewer-secret-0001"
    operator_key = "operator-secret-01"
    decision_key = "decision-secret-01"
    monkeypatch.setattr(settings, "auth_mode", "required")
    monkeypatch.setattr(
        settings,
        "api_key_credentials",
        [
            _credential("viewer", viewer_key, "viewer_user", ApiRole.VIEWER),
            _credential("operator", operator_key, "field_operator", ApiRole.OPERATOR),
            _credential("decision", decision_key, "decision_owner", ApiRole.DECISION_MAKER),
        ],
    )

    unauthenticated = client.get(f"/api/v1/cases/{GOLDEN_CASE_ID}")
    assert unauthenticated.status_code == 401
    assert unauthenticated.json()["error"]["code"] == "AUTH_REQUIRED"

    viewer_headers = {"X-API-Key": viewer_key}
    assert client.get(f"/api/v1/cases/{GOLDEN_CASE_ID}", headers=viewer_headers).status_code == 200
    forbidden = client.put(
        f"/api/v1/cases/{GOLDEN_CASE_ID}/resource-confirmation",
        json={"status": "CONFIRMED"},
        headers=viewer_headers,
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "FORBIDDEN"

    operator_headers = {"X-API-Key": operator_key}
    confirmation = client.put(
        f"/api/v1/cases/{GOLDEN_CASE_ID}/resource-confirmation",
        json={"status": "CONFIRMED", "confirmed_by": "spoofed_actor"},
        headers=operator_headers,
    )
    assert confirmation.status_code == 200
    assert confirmation.json()["resource_confirmation"]["confirmed_by"] == "field_operator"
    passport = client.put(
        f"/api/v1/cases/{GOLDEN_CASE_ID}/resource-passport",
        json=PASSPORT,
        headers=operator_headers,
    )
    assert passport.status_code == 200
    match = client.post(
        f"/api/v1/cases/{GOLDEN_CASE_ID}/matches",
        json={"top_k": 3},
        headers=operator_headers,
    )
    assert match.status_code == 200

    decision_payload = {
        "status": "APPROVED",
        "selected_demand_id": "D01",
        "reason": "성분 분석 완료 후 파일럿 검토를 진행합니다.",
        "decided_by": "spoofed_manager",
    }
    forbidden_decision = client.put(
        f"/api/v1/cases/{GOLDEN_CASE_ID}/decision",
        json=decision_payload,
        headers=operator_headers,
    )
    assert forbidden_decision.status_code == 403
    decision = client.put(
        f"/api/v1/cases/{GOLDEN_CASE_ID}/decision",
        json=decision_payload,
        headers={"X-API-Key": decision_key},
    )
    assert decision.status_code == 200
    assert decision.json()["decision"]["decided_by"] == "decision_owner"


def test_passport_evidence_upload_validates_and_downloads(
    client, session_factory, evidence_storage
) -> None:
    assert (
        client.put(
            f"/api/v1/cases/{GOLDEN_CASE_ID}/resource-confirmation", json=CONFIRMATION
        ).status_code
        == 200
    )
    assert (
        client.put(f"/api/v1/cases/{GOLDEN_CASE_ID}/resource-passport", json=PASSPORT).status_code
        == 200
    )

    png = b"\x89PNG\r\n\x1a\n" + b"safe-demo-bytes"
    uploaded = client.post(
        f"/api/v1/cases/{GOLDEN_CASE_ID}/resource-passport/evidence",
        data={"evidence_type": "PHOTO", "description": "현장 확인 사진"},
        files={"file": ("../../inspection.png", png, "image/png")},
        headers={"X-Actor": "evidence_operator"},
    )
    assert uploaded.status_code == 201, uploaded.text
    body = uploaded.json()
    assert body["original_filename"] == "inspection.png"
    assert body["uploaded_by"] == "evidence_operator"
    assert body["sha256"] == hashlib.sha256(png).hexdigest()
    assert body["source_type"] == "DEMO"
    assert "storage_key" not in body

    listing = client.get(f"/api/v1/cases/{GOLDEN_CASE_ID}/resource-passport/evidence")
    assert listing.status_code == 200
    assert [item["evidence_id"] for item in listing.json()] == [body["evidence_id"]]

    downloaded = client.get(
        f"/api/v1/cases/{GOLDEN_CASE_ID}/resource-passport/evidence/{body['evidence_id']}/content"
    )
    assert downloaded.status_code == 200
    assert downloaded.content == png
    assert downloaded.headers["content-type"] == "image/png"
    assert downloaded.headers["content-length"] == str(len(png))
    assert downloaded.headers["cache-control"] == "private, no-store, max-age=0"
    assert downloaded.headers["pragma"] == "no-cache"
    assert downloaded.headers["x-content-type-options"] == "nosniff"

    with session_factory() as session:
        stored = session.scalar(
            select(PassportEvidence).where(PassportEvidence.evidence_id == body["evidence_id"])
        )
        assert stored is not None
        stored_path = evidence_storage.resolve(stored.storage_key)
        assert stored_path.read_bytes() == png
        stored_path.write_bytes(png + b"tampered")

    corrupted = client.get(
        f"/api/v1/cases/{GOLDEN_CASE_ID}/resource-passport/evidence/{body['evidence_id']}/content"
    )
    assert corrupted.status_code == 503
    assert corrupted.json()["error"]["code"] == "EVIDENCE_INTEGRITY_FAILED"

    mismatched = client.post(
        f"/api/v1/cases/{GOLDEN_CASE_ID}/resource-passport/evidence",
        data={"evidence_type": "DOCUMENT"},
        files={"file": ("fake.pdf", b"not a pdf", "application/pdf")},
    )
    assert mismatched.status_code == 422
    assert mismatched.json()["error"]["code"] == "EVIDENCE_CONTENT_MISMATCH"
    with pytest.raises(DomainError) as traversal:
        evidence_storage.resolve("../outside.png")
    assert traversal.value.code == "INVALID_STORAGE_KEY"


def test_evidence_size_limit_and_demo_reset_cleanup(
    client, session_factory, evidence_storage, monkeypatch
) -> None:
    client.put(f"/api/v1/cases/{GOLDEN_CASE_ID}/resource-confirmation", json=CONFIRMATION)
    client.put(f"/api/v1/cases/{GOLDEN_CASE_ID}/resource-passport", json=PASSPORT)
    monkeypatch.setattr(settings, "evidence_max_bytes", 1024)
    too_large = b"\x89PNG\r\n\x1a\n" + b"x" * 1024
    rejected = client.post(
        f"/api/v1/cases/{GOLDEN_CASE_ID}/resource-passport/evidence",
        data={"evidence_type": "PHOTO"},
        files={"file": ("large.png", too_large, "image/png")},
    )
    assert rejected.status_code == 413
    assert rejected.json()["error"]["code"] == "EVIDENCE_TOO_LARGE"

    valid = b"\x89PNG\r\n\x1a\nsmall"
    uploaded = client.post(
        f"/api/v1/cases/{GOLDEN_CASE_ID}/resource-passport/evidence",
        data={"evidence_type": "PHOTO"},
        files={"file": ("small.png", valid, "image/png")},
    )
    assert uploaded.status_code == 201
    with session_factory() as session:
        stored = session.scalar(select(PassportEvidence))
        assert stored is not None
        storage_key = stored.storage_key
        assert evidence_storage.resolve(storage_key).is_file()

    monkeypatch.setattr(settings, "demo_reset_enabled", True)
    assert client.post("/api/v1/demo/reset").status_code == 200
    with pytest.raises(DomainError):
        evidence_storage.resolve(storage_key)


def test_evidence_upload_rechecks_state_after_object_io_and_compensates(
    client, session_factory, evidence_storage, monkeypatch
) -> None:
    client.put(f"/api/v1/cases/{GOLDEN_CASE_ID}/resource-confirmation", json=CONFIRMATION)
    client.put(f"/api/v1/cases/{GOLDEN_CASE_ID}/resource-passport", json=PASSPORT)
    original_save = evidence_storage.save
    captured = {}

    def racing_save(stream, *, media_type: str, max_bytes: int):
        stored = original_save(stream, media_type=media_type, max_bytes=max_bytes)
        captured["storage_key"] = stored.storage_key
        with session_factory.begin() as session:
            case = session.get(Case, GOLDEN_CASE_ID)
            assert case is not None
            case.workflow_status = WorkflowStatus.DECIDED
        return stored

    monkeypatch.setattr(evidence_storage, "save", racing_save)
    png = b"\x89PNG\r\n\x1a\nstate-race"

    rejected = client.post(
        f"/api/v1/cases/{GOLDEN_CASE_ID}/resource-passport/evidence",
        data={"evidence_type": "PHOTO"},
        files={"file": ("inspection.png", png, "image/png")},
    )

    assert rejected.status_code == 409
    assert rejected.json()["error"]["code"] == "INVALID_STATE"
    with pytest.raises(DomainError):
        evidence_storage.resolve(captured["storage_key"])
    with session_factory() as session:
        assert session.scalar(select(PassportEvidence)) is None


def test_rule_policy_catalog_versions_and_activation(client) -> None:
    first_payload = {
        "display_name": "기본 자원 검토 정책",
        "description": "Match와 독립된 versioned catalog",
        "rules": [
            {
                "rule_id": "quantity.minimum",
                "field": "quantity",
                "operator": "GTE",
                "value": 5,
                "severity": "BLOCK",
                "message": "최소 수량을 확인하세요.",
            },
            {
                "rule_id": "composition.required",
                "field": "composition",
                "operator": "REQUIRED",
                "value": None,
                "severity": "NEEDS_INFO",
                "message": "조성 정보가 필요합니다.",
            },
        ],
    }
    first = client.post("/api/v1/rule-policies/resource-default/versions", json=first_payload)
    assert first.status_code == 201, first.text
    first_hash = first.json()["versions"][0]["definition_sha256"]
    assert first.json()["active_version"] is None

    activated = client.post("/api/v1/rule-policies/resource-default/versions/1/activate")
    assert activated.status_code == 200
    assert activated.json()["active_version"] == 1
    assert activated.json()["versions"][0]["is_active"] is True

    second_payload = {**first_payload, "rules": [first_payload["rules"][0]]}
    second = client.post("/api/v1/rule-policies/resource-default/versions", json=second_payload)
    assert second.status_code == 201
    assert [version["version"] for version in second.json()["versions"]] == [1, 2]
    assert second.json()["versions"][0]["definition_sha256"] == first_hash

    listing = client.get("/api/v1/rule-policies")
    assert listing.status_code == 200
    assert [policy["policy_key"] for policy in listing.json()] == [
        "match-deterministic-v0",
        "resource-default",
    ]

    invalid = client.post(
        "/api/v1/rule-policies/invalid-policy/versions",
        json={
            "display_name": "Invalid",
            "rules": [
                {
                    "rule_id": "bad.required",
                    "field": "description",
                    "operator": "REQUIRED",
                    "value": "must not exist",
                    "severity": "BLOCK",
                    "message": "invalid",
                }
            ],
        },
    )
    assert invalid.status_code == 422

    invalid_numeric_field = client.post(
        "/api/v1/rule-policies/invalid-numeric-field/versions",
        json={
            "display_name": "Invalid numeric field",
            "rules": [
                {
                    "rule_id": "description.minimum",
                    "field": "description",
                    "operator": "GTE",
                    "value": 10,
                    "severity": "BLOCK",
                    "message": "invalid",
                }
            ],
        },
    )
    assert invalid_numeric_field.status_code == 422

    reserved = client.post(
        "/api/v1/rule-policies/match-deterministic-v0/versions",
        json=first_payload,
    )
    assert reserved.status_code == 409
    assert reserved.json()["error"]["code"] == "RULE_POLICY_RESERVED"


def test_case_list_pagination_search_and_status_filter(client, session_factory) -> None:
    with session_factory.begin() as session:
        for index, status in enumerate(
            (WorkflowStatus.CONFIRMATION_PENDING, WorkflowStatus.CLOSED), start=1
        ):
            record = Case(
                case_id=f"SEARCH-{index:02d}",
                risk_rank=10 + index,
                shap_top_features=[],
                source_type=SourceType.REAL,
                workflow_status=status,
            )
            record.resource_confirmation = ResourceConfirmation(
                status=(
                    ResourceConfirmationStatus.PENDING
                    if status is WorkflowStatus.CONFIRMATION_PENDING
                    else ResourceConfirmationStatus.NOT_CONFIRMED
                ),
                confirmed_by=None if status is WorkflowStatus.CONFIRMATION_PENDING else "operator",
                confirmed_at=None,
                source_type=SourceType.REAL,
            )
            if status is WorkflowStatus.CLOSED:
                from app.services.workflow import utcnow

                record.resource_confirmation.confirmed_at = utcnow()
            session.add(record)

    page = client.get("/api/v1/cases?limit=1&offset=0")
    assert page.status_code == 200
    assert len(page.json()) == 1
    assert int(page.headers["X-Total-Count"]) == 3
    assert page.headers["X-Limit"] == "1"

    searched = client.get("/api/v1/cases?search=search-")
    assert searched.status_code == 200
    assert [record["case_id"] for record in searched.json()] == ["SEARCH-01", "SEARCH-02"]

    closed = client.get("/api/v1/cases?workflow_status=CLOSED")
    assert closed.status_code == 200
    assert [record["case_id"] for record in closed.json()] == ["SEARCH-02"]
