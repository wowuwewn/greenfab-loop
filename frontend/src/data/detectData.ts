import type {
  DetectAnalysis,
  ValidationMetrics,
  WorkflowStep,
} from '../types/loop'

export const WORKFLOW_STEPS: WorkflowStep[] = [
  { id: '01', label: '위험 선별' },
  { id: '02', label: '현장 확인' },
  { id: '03', label: '자원 정보' },
  { id: '04', label: '후보 탐색' },
  { id: '05', label: '최종 검토' },
  { id: '06', label: '결과 기록' },
]

export const DETECT_ANALYSIS: DetectAnalysis = {
  dataset_name: 'UCI SECOM',
  model_name: 'LightGBM',
  total_cases: 1567,
  defect_cases: 104,
  captured_defects_top_20: 56,
  capture_rate_top_20: 53.85,
}

export const VALIDATION_METRICS: ValidationMetrics = {
  recall: 47.12,
  precision: 16.67,
  f1: 24.62,
  balanced_accuracy: 65.18,
}
