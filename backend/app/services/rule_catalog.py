"""Versioned, immutable Rule policy catalog foundation.

The current Match provider does not consume this catalog yet. It intentionally
establishes versioning and activation semantics without changing Match ranking.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.errors import DomainError
from app.models import RulePolicy, RulePolicyVersion
from app.schemas import (
    RuleDefinition,
    RulePolicyOut,
    RulePolicyVersionCreate,
    RulePolicyVersionOut,
)


@dataclass(frozen=True, slots=True)
class ActiveRulePolicySnapshot:
    policy_key: str
    version: int
    definition_sha256: str
    definition_json: dict


def get_active_rule_policy_snapshot(
    session: Session,
    policy_key: str,
) -> ActiveRulePolicySnapshot:
    """Resolve the active immutable policy revision used for Match lineage."""

    policy = session.scalar(
        select(RulePolicy)
        .where(RulePolicy.policy_key == policy_key)
        .options(selectinload(RulePolicy.versions))
    )
    if policy is None or policy.active_version is None:
        raise DomainError(
            "RULE_POLICY_NOT_ACTIVE",
            "Match에 사용할 active Rule policy가 없습니다.",
            409,
        )
    version = next(
        (item for item in policy.versions if item.version == policy.active_version),
        None,
    )
    if version is None:
        raise DomainError(
            "RULE_POLICY_INTEGRITY_ERROR",
            "Active Rule policy revision을 찾을 수 없습니다.",
            500,
        )
    if version.definition_json.get("evaluator") != "demand-rules-v0.1":
        raise DomainError(
            "RULE_POLICY_INCOMPATIBLE",
            "Active policy는 현재 deterministic evaluator 계약과 호환되지 않습니다.",
            409,
        )
    return ActiveRulePolicySnapshot(
        policy_key=policy.policy_key,
        version=version.version,
        definition_sha256=version.definition_sha256,
        definition_json=dict(version.definition_json),
    )


def list_rule_policies(session: Session) -> list[RulePolicyOut]:
    records = session.scalars(
        select(RulePolicy)
        .options(selectinload(RulePolicy.versions))
        .order_by(RulePolicy.policy_key.asc())
    ).all()
    return [to_policy_out(record) for record in records]


def get_rule_policy(session: Session, policy_key: str) -> RulePolicyOut:
    record = session.scalar(
        select(RulePolicy)
        .where(RulePolicy.policy_key == policy_key)
        .options(selectinload(RulePolicy.versions))
    )
    if record is None:
        raise DomainError("RULE_POLICY_NOT_FOUND", "Rule policy를 찾을 수 없습니다.", 404)
    return to_policy_out(record)


def create_rule_policy_version(
    session: Session,
    policy_key: str,
    payload: RulePolicyVersionCreate,
    *,
    actor: str,
) -> RulePolicyOut:
    record = session.scalar(
        select(RulePolicy).where(RulePolicy.policy_key == policy_key).with_for_update()
    )
    if record is None:
        record = RulePolicy(
            policy_key=policy_key,
            display_name=payload.display_name,
            description=payload.description,
        )
        session.add(record)
        session.flush()
        next_version = 1
    else:
        next_version = max((version.version for version in record.versions), default=0) + 1
        record.display_name = payload.display_name
        record.description = payload.description

    rules_json = [rule.model_dump(mode="json") for rule in payload.rules]
    canonical = json.dumps(rules_json, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    version = RulePolicyVersion(
        policy_key=policy_key,
        version=next_version,
        definition_json={"rules": rules_json},
        definition_sha256=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        created_by=actor,
    )
    record.versions.append(version)
    session.flush()
    return to_policy_out(record)


def activate_rule_policy_version(
    session: Session,
    policy_key: str,
    version_number: int,
    *,
    actor: str,
) -> RulePolicyOut:
    record = session.scalar(
        select(RulePolicy).where(RulePolicy.policy_key == policy_key).with_for_update()
    )
    if record is None:
        raise DomainError("RULE_POLICY_NOT_FOUND", "Rule policy를 찾을 수 없습니다.", 404)
    selected = next(
        (version for version in record.versions if version.version == version_number),
        None,
    )
    if selected is None:
        raise DomainError(
            "RULE_POLICY_VERSION_NOT_FOUND", "Rule policy version을 찾을 수 없습니다.", 404
        )
    record.active_version = version_number
    selected.activated_at = datetime.now(UTC)
    selected.activated_by = actor
    session.flush()
    return to_policy_out(record)


def to_policy_out(record: RulePolicy) -> RulePolicyOut:
    return RulePolicyOut(
        policy_key=record.policy_key,
        display_name=record.display_name,
        description=record.description,
        active_version=record.active_version,
        versions=[
            RulePolicyVersionOut(
                rule_policy_version_id=version.rule_policy_version_id,
                policy_key=version.policy_key,
                version=version.version,
                definition_sha256=version.definition_sha256,
                rules=[
                    RuleDefinition.model_validate(rule)
                    for rule in version.definition_json.get("rules", [])
                ],
                created_by=version.created_by,
                created_at=version.created_at,
                activated_at=version.activated_at,
                activated_by=version.activated_by,
                is_active=record.active_version == version.version,
            )
            for version in sorted(record.versions, key=lambda item: item.version)
        ],
    )
