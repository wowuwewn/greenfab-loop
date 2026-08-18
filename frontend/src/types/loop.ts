export type SourceType = 'REAL' | 'DEMO' | 'SCENARIO'

export type WorkflowStatus =
  | 'DETECTED'
  | 'CONFIRMATION_PENDING'
  | 'RESOURCE_CONFIRMED'
  | 'PASSPORT_READY'
  | 'MATCH_READY'
  | 'DECIDED'
  | 'SCENARIO_READY'
  | 'RECEIPT_CREATED'
  | 'NOT_CONFIRMED'
  | 'CLOSED'

export type ResourceConfirmationStatus =
  | 'PENDING'
  | 'CONFIRMED'
  | 'NOT_CONFIRMED'

export interface ShapFeature {
  feature_name: string
  shap_value: number
}

export interface DetectCase {
  case_id: string
  risk_rank: number | null
  shap_top_features: ShapFeature[] | null
  source_type: SourceType
}

export interface ResourceConfirmation {
  status: ResourceConfirmationStatus
  confirmed_by: string | null
  confirmed_at: string | null
  source_type: SourceType
}

export interface ResourcePassport {
  passport_id: string
  description: string | null
  quantity: number | null
  unit: string | null
  condition: string | null
  location: string | null
  composition: string | null
  source_type: SourceType
}

export interface RuleCheck {
  quantity: boolean | null
  required_info: boolean | null
  location: boolean | null
  missing_fields: string[] | null
}

export type MatchCandidateStatus = 'REVIEW' | 'NEEDS_INFO' | 'RULE_FAIL'

export interface MatchCandidate {
  demand_id: string
  company_name: string
  demand_description: string
  semantic_similarity: number | null
  rule_check: RuleCheck
  status: MatchCandidateStatus
}

export interface RulePolicyLineage {
  policy_key: string
  version: number
  definition_sha256: string
}

export interface Match {
  model: string
  model_revision: string | null
  created_at: string | null
  source_type: SourceType
  rule_policy: RulePolicyLineage
  candidates: MatchCandidate[]
}

export type DecisionStatus = 'APPROVED' | 'HOLD' | 'REJECTED'

export interface Decision {
  status: DecisionStatus
  selected_demand_id: string | null
  reason: string
  decided_by: string
  decided_at: string
}

export interface EsgScenarioInputs {
  resource_quantity: number | null
  unit: string | null
  decision_status: DecisionStatus
}

export interface EsgScenarioResults {
  candidate_diversion_quantity: number | null
  unit: string | null
}

export interface EsgScenario {
  source_type: 'SCENARIO'
  inputs: EsgScenarioInputs
  results: EsgScenarioResults
  formula_version: string | null
  factor_source: string | null
}

export type ReceiptHandoffStatus =
  | 'RESOURCE_CONFIRMED'
  | 'APPROVED'
  | 'HANDOFF_CONFIRMED'

export interface Receipt {
  receipt_id: string
  case_id: string
  passport_id: string
  selected_demand_id: string | null
  decision_status: DecisionStatus
  handoff_status: ReceiptHandoffStatus
  created_at: string | null
}

export interface DetectAnalysis {
  dataset_name: string
  model_name: string
  total_cases: number
  defect_cases: number
  captured_defects_top_20: number
  capture_rate_top_20: number
}

export interface ValidationMetrics {
  recall: number
  precision: number
  f1: number
  balanced_accuracy: number
}

export interface WorkflowStep {
  id: string
  label: string
}

export interface CaseSummary {
  case_id: string
  risk_rank: number | null
  source_type: SourceType
  workflow_status: WorkflowStatus
  updated_at: string
}

export interface CaseEnvelope {
  case: DetectCase
  resource_confirmation: ResourceConfirmation
  resource_passport: ResourcePassport | null
  match: Match | null
  decision: Decision | null
  esg_scenario: EsgScenario | null
  receipt: Receipt | null
}

export interface ResourceConfirmationRequest {
  status: Exclude<ResourceConfirmationStatus, 'PENDING'>
  confirmed_by: string
}

export interface ResourcePassportRequest {
  description: string
  quantity: number | null
  unit: string | null
  condition: string | null
  location: string | null
  composition: string | null
}

export type ResourcePassportDraft = ResourcePassportRequest

export interface MatchRequest {
  top_k: 1 | 2 | 3
}

export interface DecisionRequest {
  status: DecisionStatus
  selected_demand_id: string | null
  reason: string
  decided_by: string
}

export type DecisionDraft = Omit<DecisionRequest, 'decided_by'>

export interface ApiFieldError {
  field: string
  message: string
}

export interface ApiErrorBody {
  error: {
    code: string
    message: string
    field_errors: ApiFieldError[]
    trace_id: string
  }
}
