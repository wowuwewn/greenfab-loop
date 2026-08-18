"""Domain enums persisted by the GreenFab Loop backend."""

from enum import StrEnum


class DomainEnum(StrEnum):
    """String-valued enum whose serialized value matches the data contract."""

    pass


class SourceType(DomainEnum):
    REAL = "REAL"
    DEMO = "DEMO"
    SCENARIO = "SCENARIO"


class WorkflowStatus(DomainEnum):
    DETECTED = "DETECTED"
    CONFIRMATION_PENDING = "CONFIRMATION_PENDING"
    RESOURCE_CONFIRMED = "RESOURCE_CONFIRMED"
    PASSPORT_READY = "PASSPORT_READY"
    MATCH_READY = "MATCH_READY"
    DECIDED = "DECIDED"
    SCENARIO_READY = "SCENARIO_READY"
    RECEIPT_CREATED = "RECEIPT_CREATED"
    NOT_CONFIRMED = "NOT_CONFIRMED"
    CLOSED = "CLOSED"


class ResourceConfirmationStatus(DomainEnum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    NOT_CONFIRMED = "NOT_CONFIRMED"


class MatchRunStatus(DomainEnum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class MatchCandidateStatus(DomainEnum):
    REVIEW = "REVIEW"
    NEEDS_INFO = "NEEDS_INFO"
    RULE_FAIL = "RULE_FAIL"


class DecisionStatus(DomainEnum):
    APPROVED = "APPROVED"
    HOLD = "HOLD"
    REJECTED = "REJECTED"


class HandoffStatus(DomainEnum):
    RESOURCE_CONFIRMED = "RESOURCE_CONFIRMED"
    APPROVED = "APPROVED"
    HANDOFF_CONFIRMED = "HANDOFF_CONFIRMED"
