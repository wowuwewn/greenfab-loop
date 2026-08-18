from __future__ import annotations

import math
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.enums import (
    DecisionStatus,
    EvidenceType,
    HandoffStatus,
    MatchCandidateStatus,
    ResourceConfirmationStatus,
    SourceType,
    WorkflowStatus,
)


class ContractModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
        str_strip_whitespace=True,
    )


class ShapFeature(ContractModel):
    feature_name: str
    shap_value: float


class CaseOut(ContractModel):
    case_id: str
    risk_rank: int | None
    shap_top_features: list[ShapFeature] | None
    source_type: SourceType


class ResourceConfirmationRequest(ContractModel):
    status: ResourceConfirmationStatus
    confirmed_by: str | None = Field(default=None, min_length=1, max_length=120)

    @model_validator(mode="after")
    def disallow_pending_submission(self) -> ResourceConfirmationRequest:
        if self.status is ResourceConfirmationStatus.PENDING:
            raise ValueError("PENDING is a server-managed initial state")
        return self


class ResourceConfirmationOut(ContractModel):
    status: ResourceConfirmationStatus
    confirmed_by: str | None
    confirmed_at: datetime | None
    source_type: SourceType


class ResourcePassportRequest(ContractModel):
    description: str = Field(min_length=1, max_length=2000)
    quantity: float | None = Field(default=None, ge=0)
    unit: str | None = Field(default=None, max_length=32)
    condition: str | None = Field(default=None, max_length=1000)
    location: str | None = Field(default=None, max_length=500)
    composition: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def require_quantity_unit_pair(self) -> ResourcePassportRequest:
        has_quantity = self.quantity is not None
        has_unit = bool(self.unit)
        if has_quantity != has_unit:
            raise ValueError("quantity and unit must be provided together")
        return self


class ResourcePassportOut(ContractModel):
    passport_id: str
    description: str | None
    quantity: float | None
    unit: str | None
    condition: str | None
    location: str | None
    composition: str | None
    source_type: SourceType


class RuleCheckOut(ContractModel):
    quantity: bool | None
    required_info: bool | None
    location: bool | None
    missing_fields: list[str] | None


class MatchCandidateOut(ContractModel):
    demand_id: str
    company_name: str
    demand_description: str
    semantic_similarity: float | None
    rule_check: RuleCheckOut
    status: MatchCandidateStatus


class RulePolicyLineageOut(ContractModel):
    policy_key: str
    version: int
    definition_sha256: str


class MatchOut(ContractModel):
    model: str
    model_revision: str | None
    created_at: datetime | None
    source_type: SourceType
    rule_policy: RulePolicyLineageOut
    candidates: list[MatchCandidateOut]


class MatchRequest(ContractModel):
    top_k: int = Field(default=3, ge=1, le=3)


class DecisionRequest(ContractModel):
    status: DecisionStatus
    selected_demand_id: str | None = Field(default=None, max_length=120)
    reason: str = Field(min_length=10, max_length=2000)
    decided_by: str | None = Field(default=None, min_length=1, max_length=120)

    @model_validator(mode="after")
    def require_selected_candidate_for_approval(self) -> DecisionRequest:
        if self.status is DecisionStatus.APPROVED and not self.selected_demand_id:
            raise ValueError("selected_demand_id is required for APPROVED")
        return self


class DecisionOut(ContractModel):
    status: DecisionStatus
    selected_demand_id: str | None
    reason: str
    decided_by: str
    decided_at: datetime


class ESGScenarioRequest(ContractModel):
    scenario_quantity_kg: float = Field(gt=0)
    baseline_pathway: str = Field(min_length=1, max_length=1000)
    alternative_pathway: str = Field(min_length=1, max_length=2000)
    baseline_energy_factor_kwh_per_kg: float | None = Field(default=None, ge=0)
    alternative_energy_factor_kwh_per_kg: float | None = Field(default=None, ge=0)
    baseline_carbon_factor_kgco2e_per_kg: float | None = Field(default=None, ge=0)
    alternative_carbon_factor_kgco2e_per_kg: float | None = Field(default=None, ge=0)
    factor_source: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def require_source_for_factors(self) -> ESGScenarioRequest:
        factors = (
            self.baseline_energy_factor_kwh_per_kg,
            self.alternative_energy_factor_kwh_per_kg,
            self.baseline_carbon_factor_kgco2e_per_kg,
            self.alternative_carbon_factor_kgco2e_per_kg,
        )
        if any(value is not None for value in factors) and not self.factor_source:
            raise ValueError("factor_source is required when an ESG factor is provided")
        return self


class ESGScenarioOut(ContractModel):
    source_type: SourceType
    inputs: dict[str, Any]
    results: dict[str, Any]
    formula_version: str | None
    factor_source: str | None


class ReceiptOut(ContractModel):
    receipt_id: str
    case_id: str
    passport_id: str
    selected_demand_id: str | None
    decision_status: DecisionStatus
    handoff_status: HandoffStatus
    created_at: datetime | None


class PassportEvidenceOut(ContractModel):
    evidence_id: str
    passport_id: str
    original_filename: str
    media_type: str
    size_bytes: int
    sha256: str
    evidence_type: EvidenceType
    description: str | None
    source_type: SourceType
    uploaded_by: str
    created_at: datetime


class DetectImportOut(ContractModel):
    detect_import_id: str
    artifact_sha256: str
    artifact_name: str
    dataset_name: str
    model_name: str
    model_revision: str
    source_type: SourceType
    case_count: int
    created_case_count: int
    updated_case_count: int
    unchanged_case_count: int
    created: bool


RuleField = Literal[
    "description",
    "quantity",
    "unit",
    "condition",
    "location",
    "composition",
]
RuleOperator = Literal["REQUIRED", "GTE", "LTE", "EQUALS", "IN"]
RuleSeverity = Literal["NEEDS_INFO", "BLOCK"]


class RuleDefinition(ContractModel):
    rule_id: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    field: RuleField
    operator: RuleOperator
    value: Any = None
    severity: RuleSeverity
    message: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_operator_value(self) -> RuleDefinition:
        if self.operator == "REQUIRED" and self.value is not None:
            raise ValueError("REQUIRED rules must not define value")
        if self.operator in {"GTE", "LTE"} and (
            not isinstance(self.value, int | float) or isinstance(self.value, bool)
        ):
            raise ValueError(f"{self.operator} rules require a numeric value")
        if self.operator in {"GTE", "LTE"} and not math.isfinite(float(self.value)):
            raise ValueError(f"{self.operator} rules require a finite numeric value")
        if self.operator in {"GTE", "LTE"} and self.field != "quantity":
            raise ValueError(f"{self.operator} rules are supported only for quantity")
        if self.operator == "IN":
            if not isinstance(self.value, list) or not 1 <= len(self.value) <= 100:
                raise ValueError("IN rules require 1 to 100 scalar values")
            if any(not _is_bounded_scalar(item) for item in self.value):
                raise ValueError("IN rules require finite scalar values")
        if self.operator == "EQUALS" and not _is_bounded_scalar(self.value):
            raise ValueError("EQUALS rules require a finite scalar value")
        return self


class RulePolicyVersionCreate(ContractModel):
    display_name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    rules: list[RuleDefinition] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique_rule_ids(self) -> RulePolicyVersionCreate:
        rule_ids = [rule.rule_id for rule in self.rules]
        if len(rule_ids) != len(set(rule_ids)):
            raise ValueError("rule_id values must be unique within a policy version")
        return self


class RulePolicyVersionOut(ContractModel):
    rule_policy_version_id: str
    policy_key: str
    version: int
    definition_sha256: str
    rules: list[RuleDefinition]
    created_by: str
    created_at: datetime
    activated_at: datetime | None
    activated_by: str | None
    is_active: bool


class RulePolicyOut(ContractModel):
    policy_key: str
    display_name: str
    description: str | None
    active_version: int | None
    versions: list[RulePolicyVersionOut]


class CaseEnvelope(ContractModel):
    case: CaseOut
    resource_confirmation: ResourceConfirmationOut
    resource_passport: ResourcePassportOut | None
    match: MatchOut | None
    decision: DecisionOut | None
    esg_scenario: ESGScenarioOut | None
    receipt: ReceiptOut | None


class CaseSummary(ContractModel):
    case_id: str
    risk_rank: int | None
    source_type: SourceType
    workflow_status: WorkflowStatus
    updated_at: datetime


class DemandPayload(ContractModel):
    company_name: str = Field(min_length=1, max_length=255)
    demand_description: str = Field(min_length=1, max_length=4000)
    quantity_min: float | None = Field(default=None, ge=0)
    quantity_max: float | None = Field(default=None, ge=0)
    unit: str | None = Field(default=None, max_length=64)
    location: str | None = Field(default=None, max_length=255)
    accepted_conditions: list[Annotated[str, Field(min_length=1, max_length=500)]] = Field(
        default_factory=list, max_length=100
    )
    required_fields: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("accepted_conditions", "required_fields")
    @classmethod
    def normalise_unique_values(cls, values: list[str]) -> list[str]:
        normalised = [value.strip() for value in values if value.strip()]
        if len(normalised) != len(set(normalised)):
            raise ValueError("list values must be unique")
        return normalised

    @field_validator("required_fields")
    @classmethod
    def validate_required_fields(cls, values: list[str]) -> list[str]:
        allowed = {
            "description",
            "quantity",
            "unit",
            "condition",
            "location",
            "composition",
        }
        unknown = sorted(set(values) - allowed)
        if unknown:
            raise ValueError(f"unknown Passport fields: {', '.join(unknown)}")
        return values

    @model_validator(mode="after")
    def validate_quantity_rule(self) -> DemandPayload:
        if (
            self.quantity_min is not None
            and self.quantity_max is not None
            and self.quantity_min > self.quantity_max
        ):
            raise ValueError("quantity_min cannot exceed quantity_max")
        if (self.quantity_min is not None or self.quantity_max is not None) and not self.unit:
            raise ValueError("unit is required when a quantity rule is configured")
        return self


class DemandCreate(DemandPayload):
    demand_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")
    source_type: SourceType = SourceType.DEMO

    @field_validator("source_type")
    @classmethod
    def disallow_scenario_source(cls, source_type: SourceType) -> SourceType:
        if source_type is SourceType.SCENARIO:
            raise ValueError("Demand source_type cannot be SCENARIO")
        return source_type


class DemandUpdate(DemandPayload):
    pass


class DemandOut(DemandPayload):
    demand_id: str
    source_type: SourceType
    is_active: bool
    version: int
    content_sha256: str | None
    created_at: datetime
    updated_at: datetime


class DemandIndexSyncOut(ContractModel):
    provider: str
    upserted: int
    deleted: int


class DemandIndexEventOut(ContractModel):
    event_id: str
    demand_id: str | None
    operation: Literal["UPSERT", "DELETE", "SYNC_ALL"]
    status: Literal["PENDING", "SUCCEEDED", "FAILED", "SKIPPED"]
    requested_by: str
    target_version: int | None
    target_content_sha256: str | None
    attempt_count: int
    error_message: str | None
    trace_id: str | None
    created_at: datetime
    processed_at: datetime | None


class HealthOut(ContractModel):
    status: str
    database: str | None = None
    match_provider: str | None = None
    evidence_storage: str | None = None


class FieldError(ContractModel):
    field: str
    message: str


class ErrorDetail(ContractModel):
    code: str
    message: str
    field_errors: list[FieldError] = Field(default_factory=list)
    trace_id: str


class ErrorResponse(ContractModel):
    error: ErrorDetail


def _is_bounded_scalar(value: Any) -> bool:
    if value is None or isinstance(value, dict | list):
        return False
    if isinstance(value, float) and not math.isfinite(value):
        return False
    if isinstance(value, str) and len(value) > 2000:
        return False
    return isinstance(value, str | int | float | bool)
