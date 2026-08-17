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
