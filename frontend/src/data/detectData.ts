import type {
  DetectAnalysis,
  DetectCase,
  ResourceConfirmation,
  ValidationMetrics,
  WorkflowStep,
} from '../types/loop'

export const WORKFLOW_STEPS: WorkflowStep[] = [
  { id: '01', label: 'Detect' },
  { id: '02', label: 'Confirm' },
  { id: '03', label: 'Passport' },
  { id: '04', label: 'Match' },
  { id: '05', label: 'Review' },
  { id: '06', label: 'Receipt' },
]

export const DETECT_ANALYSIS: DetectAnalysis = {
  dataset_name: 'UCI SECOM',
  model_name: 'LightGBM',
  total_cases: 1567,
  defect_cases: 104,
  captured_defects_top_20: 56,
  capture_rate_top_20: 53.85,
}

export const PRIORITY_CASE: DetectCase = {
  case_id: 'SECOM-0116',
  risk_rank: 4,
  shap_top_features: null,
  source_type: 'REAL',
}

export const RESOURCE_CONFIRMATION: ResourceConfirmation = {
  status: 'PENDING',
  confirmed_by: null,
  confirmed_at: null,
  source_type: 'REAL',
}

export const VALIDATION_METRICS: ValidationMetrics = {
  recall: 47.12,
  precision: 16.67,
  f1: 24.62,
  balanced_accuracy: 65.18,
}
