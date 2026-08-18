"""Deterministic demo seed shared by local development and API tests."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import ResourceConfirmationStatus, SourceType, WorkflowStatus
from app.models import (
    AuditEvent,
    Case,
    Demand,
    ResourceConfirmation,
    RulePolicy,
    RulePolicyVersion,
)
from app.services.demand import demand_content_sha256

GOLDEN_CASE_ID = "SECOM-0116"
MATCH_RULE_POLICY_KEY = "match-deterministic-v0"
MATCH_RULE_POLICY_VERSION_ID = "RULEPOLICY-MATCH-DETERMINISTIC-V0-V1"
MATCH_RULE_POLICY_DEFINITION = {
    "evaluator": "demand-rules-v0.1",
    "evaluated_conditions": [
        "quantity_and_unit",
        "required_fields",
        "location",
    ],
    "interpretation": (
        "This revision identifies the deterministic evaluator contract. "
        "Demand-specific values remain in each immutable candidate snapshot."
    ),
    "rules": [],
}


def _match_rule_policy_sha256() -> str:
    canonical = json.dumps(
        MATCH_RULE_POLICY_DEFINITION,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


MATCH_RULE_POLICY_DEFINITION_SHA256 = _match_rule_policy_sha256()

# These values are copied from the verified Detect artifact at
# data/outputs/detect/dashboard_data.json.  They are model-output contributions,
# not causal process variables.
GOLDEN_SHAP_FEATURES = [
    {"feature_name": "Sensor59", "shap_value": 1.0598370403631927},
    {"feature_name": "Sensor477", "shap_value": 0.32137874424728663},
    {"feature_name": "Sensor341", "shap_value": 0.31629686899686277},
]


DEMO_DEMANDS = (
    {
        "demand_id": "D01",
        "company_name": "제주 세라믹랩",
        "demand_description": (
            "세라믹 복합재 연구를 위해 규소계 미분말을 5~20kg 단위로 찾고 있음. "
            "성분표 확인과 실험실 적합성 시험 후 소량 파일럿 사용 가능."
        ),
        "quantity_min": 5,
        "quantity_max": 20,
        "unit": "kg",
        "location": None,
        "accepted_conditions": [],
        "required_fields": ["description", "quantity", "unit", "composition"],
        "is_active": True,
    },
    {
        "demand_id": "D15",
        "company_name": "시멘트서큘러랩",
        "demand_description": (
            "건조된 무기성 침전물 중 칼슘 함량이 높은 재료를 소성 시험용 "
            "보조 원료로 검토. 유해성 분석 필수."
        ),
        "quantity_min": None,
        "quantity_max": None,
        "unit": None,
        "location": None,
        "accepted_conditions": [],
        "required_fields": ["description", "composition", "condition"],
        "is_active": True,
    },
    {
        "demand_id": "D11",
        "company_name": "제주메탈리턴",
        "demand_description": (
            "합금 계열이 확인되고 절삭유이 제거된 경량 금속 칩을 재용해 원료로 매입."
        ),
        "quantity_min": None,
        "quantity_max": None,
        "unit": None,
        "location": None,
        "accepted_conditions": [],
        "required_fields": ["description", "composition", "condition"],
        "is_active": True,
    },
)


def seed_system_data(session: Session) -> RulePolicy:
    """Ensure non-demo system policy data exists in every environment.

    The matching evaluator is reserved application data, not a demo fixture.
    A hash mismatch is treated as deployment drift instead of silently
    overwriting an auditable policy revision.
    """

    policy = session.get(RulePolicy, MATCH_RULE_POLICY_KEY)
    if policy is None:
        now = datetime.now(UTC)
        policy = RulePolicy(
            policy_key=MATCH_RULE_POLICY_KEY,
            display_name="Deterministic demand rule evaluator",
            description="Tracks the evaluator contract; it is not a safety or legal policy.",
            active_version=1,
        )
        policy.versions.append(
            RulePolicyVersion(
                rule_policy_version_id=MATCH_RULE_POLICY_VERSION_ID,
                version=1,
                definition_json=MATCH_RULE_POLICY_DEFINITION,
                definition_sha256=MATCH_RULE_POLICY_DEFINITION_SHA256,
                created_by="system",
                activated_at=now,
                activated_by="system",
            )
        )
        session.add(policy)
        session.flush()
        return policy

    version = session.scalar(
        select(RulePolicyVersion).where(
            RulePolicyVersion.policy_key == MATCH_RULE_POLICY_KEY,
            RulePolicyVersion.version == 1,
        )
    )
    if version is None or version.definition_sha256 != MATCH_RULE_POLICY_DEFINITION_SHA256:
        raise RuntimeError("Built-in Match rule policy is missing or has drifted")
    if policy.active_version != 1:
        policy.active_version = 1
    session.flush()
    return policy


def seed_demo_data(session: Session) -> Case:
    """Insert the Golden Case and DEMO demands when they do not exist."""

    seed_system_data(session)
    case = session.get(Case, GOLDEN_CASE_ID)
    if case is None:
        case = Case(
            case_id=GOLDEN_CASE_ID,
            risk_rank=4,
            shap_top_features=GOLDEN_SHAP_FEATURES,
            source_type=SourceType.REAL,
            workflow_status=WorkflowStatus.CONFIRMATION_PENDING,
        )
        case.resource_confirmation = ResourceConfirmation(
            status=ResourceConfirmationStatus.PENDING,
            confirmed_by=None,
            confirmed_at=None,
            source_type=SourceType.DEMO,
        )
        case.audit_events.append(
            AuditEvent(
                event_type="CASE_INITIALIZED",
                actor="system",
                from_status=None,
                to_status=WorkflowStatus.CONFIRMATION_PENDING,
                payload_json={
                    "detect_source": "data/outputs/detect/dashboard_data.json",
                    "source_type": SourceType.REAL.value,
                },
                trace_id=None,
            )
        )
        session.add(case)

    for payload in DEMO_DEMANDS:
        demand = session.get(Demand, payload["demand_id"])
        if demand is None:
            demand = Demand(**payload, source_type=SourceType.DEMO, version=1)
            session.add(demand)
        elif demand.source_type is SourceType.DEMO:
            for field_name, value in payload.items():
                setattr(demand, field_name, value)
            demand.version = 1
        if demand is not None:
            demand.content_sha256 = demand_content_sha256(demand)

    session.flush()
    return case


def reset_demo_data(session: Session) -> Case:
    """Reset only the Golden Case while preserving every unrelated record."""

    case = session.get(Case, GOLDEN_CASE_ID)
    if case is not None:
        session.delete(case)
        session.flush()
    return seed_demo_data(session)
