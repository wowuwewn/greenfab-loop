"""Pure, deterministic checks applied after semantic candidate retrieval.

This module deliberately has no database, HTTP, embedding-model, or vector-store
dependencies.  It can therefore be reused by the API service and by an eventual
BGE-M3/Chroma adapter without importing either layer.

``None`` is a first-class rule value: it means that a rule was not evaluated
(usually because it is not configured or its input is unavailable).  A ``None``
value alone does not make a candidate ``NEEDS_INFO``.  Missing required fields
are represented explicitly by ``required_info=False`` and ``missing_fields``.
"""

from __future__ import annotations

from dataclasses import dataclass
from numbers import Real
from typing import Literal

RuleStatus = Literal["REVIEW", "NEEDS_INFO", "RULE_FAIL"]
RuleValue = bool | None

_PASSPORT_FIELDS = frozenset(
    {
        "description",
        "quantity",
        "unit",
        "condition",
        "location",
        "composition",
    }
)


@dataclass(frozen=True, slots=True)
class ResourcePassportInput:
    """The small, persistence-agnostic input required by matching and rules."""

    passport_id: str
    description: str | None = None
    quantity: float | None = None
    unit: str | None = None
    condition: str | None = None
    location: str | None = None
    composition: str | None = None
    source_type: str = "DEMO"


@dataclass(frozen=True, slots=True)
class DemandRules:
    """Only constraints that can be checked deterministically in the MVP.

    An empty constraint is *not applicable*, not a failed rule.  For example,
    an empty ``accepted_locations`` produces ``location=None`` (미평가).
    """

    quantity_min: float | None = None
    quantity_max: float | None = None
    unit: str | None = None
    accepted_locations: tuple[str, ...] = ()
    required_fields: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        unknown_fields = set(self.required_fields) - _PASSPORT_FIELDS
        if unknown_fields:
            fields = ", ".join(sorted(unknown_fields))
            raise ValueError(f"Unknown passport field(s) in required_fields: {fields}")
        if (
            self.quantity_min is not None
            and self.quantity_max is not None
            and self.quantity_min > self.quantity_max
        ):
            raise ValueError("quantity_min cannot be greater than quantity_max")


@dataclass(frozen=True, slots=True)
class RuleCheck:
    """Data Contract-compatible deterministic rule result."""

    quantity: RuleValue
    required_info: RuleValue
    location: RuleValue
    missing_fields: tuple[str, ...] = ()

    @property
    def status(self) -> RuleStatus:
        return resolve_rule_status(self)

    def as_dict(self) -> dict[str, bool | list[str] | None]:
        return {
            "quantity": self.quantity,
            "required_info": self.required_info,
            "location": self.location,
            "missing_fields": list(self.missing_fields),
        }

    def display_labels(self) -> dict[str, str]:
        """Return Korean UI labels, surfacing an unassessed value as 미평가."""

        return {
            "quantity": rule_value_label(self.quantity),
            "required_info": rule_value_label(self.required_info),
            "location": rule_value_label(self.location),
        }


def rule_value_label(value: RuleValue) -> str:
    """Translate a tri-state rule value without turning ``None`` into failure."""

    if value is True:
        return "충족"
    if value is False:
        return "불충족"
    return "미평가"


def resolve_rule_status(rule_check: RuleCheck) -> RuleStatus:
    """Resolve candidate status with contract-safe priority.

    Quantity/location are actual pass/fail rules, so their explicit ``False``
    takes priority.  ``required_info=False`` represents information that the
    operator can still provide and therefore maps to ``NEEDS_INFO`` rather than
    ``RULE_FAIL``.  Optional, unconfigured checks may remain ``None`` while the
    candidate stays reviewable.
    """

    if rule_check.quantity is False or rule_check.location is False:
        return "RULE_FAIL"
    if rule_check.required_info is False or rule_check.missing_fields:
        return "NEEDS_INFO"
    return "REVIEW"


def evaluate_rules(
    passport: ResourcePassportInput,
    rules: DemandRules,
) -> RuleCheck:
    """Evaluate configured rules without guessing unknown passport values."""

    missing_fields = _missing_required_fields(passport, rules.required_fields)
    quantity = _evaluate_quantity(passport, rules, missing_fields)
    location = _evaluate_location(passport, rules, missing_fields)

    ordered_missing = tuple(dict.fromkeys(missing_fields))
    return RuleCheck(
        quantity=quantity,
        required_info=not bool(ordered_missing),
        location=location,
        missing_fields=ordered_missing,
    )


def _missing_required_fields(
    passport: ResourcePassportInput,
    required_fields: tuple[str, ...],
) -> list[str]:
    missing: list[str] = []
    for field_name in required_fields:
        if _is_missing(getattr(passport, field_name)):
            missing.append(field_name)
    return missing


def _evaluate_quantity(
    passport: ResourcePassportInput,
    rules: DemandRules,
    missing_fields: list[str],
) -> RuleValue:
    configured = any(
        value is not None for value in (rules.quantity_min, rules.quantity_max, rules.unit)
    )
    if not configured:
        return None

    quantity = passport.quantity
    if _is_missing(quantity) or not isinstance(quantity, Real) or isinstance(quantity, bool):
        missing_fields.append("quantity")
        return None

    if rules.unit is not None:
        if _is_missing(passport.unit):
            missing_fields.append("unit")
            return None
        if _normalise(passport.unit) != _normalise(rules.unit):
            return False

    numeric_quantity = float(quantity)
    if numeric_quantity < 0:
        return False
    if rules.quantity_min is not None and numeric_quantity < rules.quantity_min:
        return False
    if rules.quantity_max is not None and numeric_quantity > rules.quantity_max:
        return False
    return True


def _evaluate_location(
    passport: ResourcePassportInput,
    rules: DemandRules,
    missing_fields: list[str],
) -> RuleValue:
    if not rules.accepted_locations:
        return None
    if _is_missing(passport.location):
        missing_fields.append("location")
        return None

    actual = _normalise(passport.location)
    return any(
        actual == accepted or actual.startswith(f"{accepted} ")
        for accepted in map(_normalise, rules.accepted_locations)
    )


def _is_missing(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _normalise(value: object) -> str:
    return " ".join(str(value).strip().casefold().split())
