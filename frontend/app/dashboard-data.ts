import rawDashboardData from "./dashboard_data.json";

export type ModelMetric = {
  model_code: string;
  model: string;
  recall: number;
  recall_std: number;
  precision: number;
  precision_std: number;
  f1: number;
  f1_std: number;
  f2: number;
  f2_std: number;
  pr_auc: number;
  pr_auc_std: number;
  balanced_accuracy: number;
  balanced_accuracy_std: number;
  threshold_median: number;
  features_used_min: number;
  features_used_max: number;
};

export type RiskFactor = {
  feature: string;
  display_feature: string;
  contribution: number;
  direction: "위험 증가" | "위험 감소";
  feature_value: number;
};

export type RiskItem = {
  id: string;
  row_index: number;
  risk_score: number;
  risk_score_type: string;
  raw_model_score: number;
  risk_rank: number;
  risk_grade: "고위험" | "중위험" | "저위험";
  observed_label: "정상" | "불량";
  top_factors: RiskFactor[];
};

export type InspectionStrategy = {
  fraction: number;
  inspection_count: number;
  captured_defects: number;
  total_defects: number;
  capture_rate: number;
};

type MetricSet = {
  recall: number;
  recall_std?: number;
  precision: number;
  precision_std?: number;
  f1: number;
  f1_std?: number;
  f2?: number;
  pr_auc: number;
  pr_auc_std?: number;
  balanced_accuracy: number;
  balanced_accuracy_std?: number;
  tp?: number;
  fp?: number;
  fn?: number;
  tn?: number;
  source?: string;
  pr_auc_raw_fold_scores?: number;
};

export type DashboardData = {
  metadata: {
    dataset: string;
    input_shape: [number, number];
    validation: string;
    preprocessing_scope: string;
    strict_cv_preprocessing_from_raw: boolean;
    evaluation_threshold_policy: string;
    deployment_threshold_policy: string;
    score_type: string;
    model_selection_rule: string;
    threshold_rule: string;
    risk_grade_rule: Record<string, string>;
    limitations: string[];
  };
  summary: {
    총생산건수: number;
    불량건수: number;
    불량률: number;
    선정모델명: string;
    선정임계값: number;
    임계값용도: string;
    고위험건수: number;
  };
  selected_model_metrics: MetricSet;
  cv_fold_mean_metrics: MetricSet;
  pooled_oof_metrics: MetricSet;
  model_comparison: ModelMetric[];
  confusion_matrix: { tp: number; fp: number; fn: number; tn: number };
  confusion_matrix_policy: string;
  fold_thresholds: Array<{
    fold: number;
    threshold: number;
    inner_precision: number;
    inner_recall: number;
  }>;
  provisional_deployment: {
    binary_threshold: number;
    full_model_grade_raw_score_cutoffs: {
      high_raw_score: number;
      medium_raw_score: number;
    };
    notice: string;
  };
  inspection_strategies: InspectionStrategy[];
  top20_capture_rate: number;
  top_features: Array<{
    feature: string;
    display_feature: string;
    shap_value: number;
  }>;
  risk_items: RiskItem[];
  risk_distribution: { high: number; medium: number; low: number };
  temporal_holdout: {
    assumption: string;
    train_rows: number;
    test_rows: number;
    train_defects: number;
    test_defects: number;
    test_fraction: number;
    threshold: number;
    recall: number;
    precision: number;
    f1: number;
    f2: number;
    pr_auc: number;
    balanced_accuracy: number;
    tp: number;
    fp: number;
    fn: number;
    tn: number;
    top20_capture: InspectionStrategy;
  };
  scenario_defaults: {
    monthly_production: number;
    rework_energy_kwh_per_defect: number;
    waste_kg_per_defect: number;
    unit_cost_krw: number;
    action_success_rate: number;
    emission_factor_tco2eq_per_mwh: number;
    disclaimer: string;
  };
};

export const dashboardData = rawDashboardData as unknown as DashboardData;
