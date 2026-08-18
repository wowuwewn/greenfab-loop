"""Persistence-agnostic GreenFab Loop services."""

from .match import (
    DemandIndexDocument,
    DemandIndexManager,
    DemandSnapshot,
    IndexSyncResult,
    MatchCandidate,
    MatchProvider,
    MatchResult,
    MockMatchProvider,
    SemanticSearchAdapter,
    SemanticSearchHit,
)
from .rules import (
    DemandRules,
    ResourcePassportInput,
    RuleCheck,
    RuleStatus,
    evaluate_rules,
    resolve_rule_status,
    rule_value_label,
)

__all__ = [
    "DemandRules",
    "DemandIndexDocument",
    "DemandIndexManager",
    "DemandSnapshot",
    "IndexSyncResult",
    "MatchCandidate",
    "MatchProvider",
    "MatchResult",
    "MockMatchProvider",
    "ResourcePassportInput",
    "RuleCheck",
    "RuleStatus",
    "SemanticSearchAdapter",
    "SemanticSearchHit",
    "evaluate_rules",
    "resolve_rule_status",
    "rule_value_label",
]
