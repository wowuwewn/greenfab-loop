export type SourceType = 'REAL' | 'DEMO' | 'SCENARIO'

export type ResourceConfirmationStatus =
  | 'PENDING'
  | 'CONFIRMED'
  | 'NOT_CONFIRMED'

export interface DetectCase {
  case_id: string
  risk_rank: number | null
  shap_top_features: null
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

export interface Match {
  model: string
  created_at: string | null
  source_type: SourceType
  candidates: MatchCandidate[]
}

export type DecisionStatus = 'APPROVED' | 'HOLD' | 'REJECTED'

export interface Decision {
  status: DecisionStatus
  selected_demand_id: string | null
  reason: string | null
  decided_by: string
  decided_at: string
}

export interface EsgScenario {
  source_type: 'SCENARIO'
  inputs: Record<string, unknown>
  results: Record<string, unknown>
  formula_version: string | null
  factor_source: string | null
}

export type ReceiptHandoffStatus = 'RESOURCE_CONFIRMED' | 'APPROVED'

export interface Receipt {
  receipt_id: string
  case_id: string
  passport_id: string
  selected_demand_id: string | null
  decision_status: DecisionStatus
  handoff_status: ReceiptHandoffStatus
  created_at: string
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
