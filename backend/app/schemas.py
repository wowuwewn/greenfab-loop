from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.enums import (
    DecisionStatus,
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
    confirmed_by: str = Field(min_length=1, max_length=120)

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


class MatchOut(ContractModel):
    model: str
    created_at: datetime | None
    source_type: SourceType
    candidates: list[MatchCandidateOut]


class MatchRequest(ContractModel):
    top_k: int = Field(default=3, ge=1, le=3)


class DecisionRequest(ContractModel):
    status: DecisionStatus
    selected_demand_id: str | None = Field(default=None, max_length=120)
    reason: str = Field(min_length=10, max_length=2000)
    decided_by: str = Field(min_length=1, max_length=120)

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


class HealthOut(ContractModel):
    status: str
    database: str | None = None
    match_provider: str | None = None


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
