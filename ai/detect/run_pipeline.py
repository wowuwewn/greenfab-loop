#!/usr/bin/env python3
"""전처리된 UCI SECOM 데이터의 불량 예측 벤치마크.

Logistic Regression, Random Forest, XGBoost, LightGBM을 동일한
Stratified outer cross-validation 분할에서 비교한다. 각 outer fold의 분류
임계값은 해당 학습 구간의 inner OOF 예측만으로 결정한다. 주요 산출물은
모델별 성능, OOF 위험 순위, SHAP 설명, 대시보드 데이터와 추론 모델이다.

Notes
-----
입력 Excel은 전체 표본 기준 중앙값 대체가 완료된 자료이므로 평가 결과에는
소량의 transductive preprocessing bias가 남는다. 또한 inner CV는 임계값
선택에 사용되며, 모델군 선택까지 감싼 완전한 nested model selection은 아니다.
"""

from __future__ import annotations

import argparse
import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
import logging
import math
import os
import platform
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

INSTALL_COMMAND = (
    "python -m pip install -r ai/detect/requirements.txt"
)

try:
    import joblib
    import numpy as np
    import pandas as pd
    from sklearn.base import BaseEstimator
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import (
        average_precision_score,
        balanced_accuracy_score,
        confusion_matrix,
        f1_score,
        precision_recall_curve,
        precision_score,
        recall_score,
    )
    from sklearn.model_selection import StratifiedKFold
    from sklearn.preprocessing import StandardScaler
except ModuleNotFoundError as exc:
    raise SystemExit(
        f"필수 패키지 '{exc.name}'가 없습니다.\n"
        f"다음 명령을 실행하세요:\n{INSTALL_COMMAND}"
    ) from exc

XGB_IMPORT_ERROR: Exception | None = None
try:
    from xgboost import XGBClassifier
except (ModuleNotFoundError, ImportError, OSError) as exc:
    XGBClassifier = None  # type: ignore[assignment]
    XGB_IMPORT_ERROR = exc

LGBM_IMPORT_ERROR: Exception | None = None
try:
    from lightgbm import LGBMClassifier
except (ModuleNotFoundError, ImportError, OSError) as exc:
    LGBMClassifier = None  # type: ignore[assignment]
    LGBM_IMPORT_ERROR = exc

os.environ.setdefault(
    "MPLCONFIGDIR",
    str(Path(os.environ.get("TMPDIR", "/tmp")) / "greenfab-matplotlib"),
)

PIPELINE_VERSION = "1.0.0"
OUTPUT_SCHEMA_VERSION = "greenfab-insight-dashboard-v1"

RANDOM_STATE = 42
DEFAULT_OUTER_FOLDS = 5
DEFAULT_INNER_FOLDS = 3
DEFAULT_PRECISION_FLOOR = 0.15
DEFAULT_NEAR_CONSTANT_RATIO = 0.999
DEFAULT_TIME_HOLDOUT_FRACTION = 0.20

MISSING_RATE_LIMIT = 0.50
HIGH_RISK_PERCENTILE = 0.80
MEDIUM_RISK_PERCENTILE = 0.50
PRIMARY_INSPECTION_FRACTION = 0.20
INSPECTION_FRACTIONS = (0.10, PRIMARY_INSPECTION_FRACTION, 0.30)
GLOBAL_SHAP_TOP_K = 15
RISK_ITEM_TOP_K = 30
LOCAL_SHAP_TOP_K = 5
SHAP_BACKGROUND_MAX_ROWS = 500

INNER_SEED_MULTIPLIER = 100
ORDERED_HOLDOUT_CV_SEED_OFFSET = 9000
ORDERED_HOLDOUT_MODEL_SEED_OFFSET = 9001
FINAL_MODEL_SEED_OFFSET = 10000

MODEL_CODES = ("lr", "rf", "xgb", "lgbm")
METHODOLOGICAL_LIMITATIONS = (
    "전체 데이터 중앙값으로 이미 대체된 입력이므로 원자료부터 완전한 "
    "누수 방지 검증은 아님.",
    "4개 알고리즘을 같은 CV 결과로 선택하고 그 성능을 보고하므로 완전 "
    "nested model-selection 추정치는 아님.",
    "Excel에 timestamp가 없어 시간순 검증은 행 순서 보존을 가정한 "
    "강건성 점검임.",
    "익명 센서 SHAP은 모델 연관 설명이며 물리적 공정 원인이나 "
    "인과효과가 아님.",
    "상관 센서 사이에서 SHAP 중요도가 분산될 수 있음.",
    "class-weight 모델 score는 보정된 실제 불량확률이 아님.",
    "fold별 모델 점수 척도 차이를 줄이기 위해 전체 위험 순위와 "
    "Top 20%는 fold 내부 백분위로 비교함.",
)
LOGGER = logging.getLogger(__name__)


def configure_logging() -> None:
    """분석 진행 상황을 재현 가능한 형식으로 기록한다."""

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%H:%M:%S",
    )


# Configuration and fold-wise preprocessing

@dataclass(frozen=True)
class ModelSpec:
    """모델 생성 규칙과 전처리 요구사항을 묶은 불변 설정."""

    code: str
    name: str
    scale: bool
    factory: Callable[[np.ndarray, int], BaseEstimator]


@dataclass
class FoldPreprocessor:
    """학습 fold에만 적합되는 결측·근상수·스케일 전처리기."""

    missing_keep: np.ndarray
    near_constant_keep: np.ndarray
    imputer: SimpleImputer
    scaler: StandardScaler | None
    original_feature_indices: np.ndarray

    @classmethod
    def fit(
        cls,
        X: np.ndarray,
        *,
        scale: bool,
        near_constant_ratio: float,
    ) -> "FoldPreprocessor":
        missing_keep = np.mean(np.isnan(X), axis=0) <= MISSING_RATE_LIMIT
        if not missing_keep.any():
            raise ValueError("결측률 50% 이하인 변수가 하나도 없습니다.")

        X_kept = X[:, missing_keep]
        imputer = SimpleImputer(strategy="median", keep_empty_features=True)
        X_imputed = imputer.fit_transform(X_kept)

        dominant_ratios = np.empty(X_imputed.shape[1], dtype=float)
        for column_index in range(X_imputed.shape[1]):
            _, counts = np.unique(X_imputed[:, column_index], return_counts=True)
            dominant_ratios[column_index] = counts.max() / len(X_imputed)

        near_constant_keep = dominant_ratios < near_constant_ratio
        if not near_constant_keep.any():
            raise ValueError("근상수 변수 제거 후 남은 변수가 없습니다.")

        X_variable = X_imputed[:, near_constant_keep]
        scaler: StandardScaler | None = None
        if scale:
            scaler = StandardScaler()
            scaler.fit(X_variable)

        missing_indices = np.flatnonzero(missing_keep)
        original_feature_indices = missing_indices[near_constant_keep]
        return cls(
            missing_keep=missing_keep,
            near_constant_keep=near_constant_keep,
            imputer=imputer,
            scaler=scaler,
            original_feature_indices=original_feature_indices,
        )

    def transform(self, X: np.ndarray) -> np.ndarray:
        X_kept = X[:, self.missing_keep]
        X_imputed = self.imputer.transform(X_kept)
        X_variable = X_imputed[:, self.near_constant_keep]
        if self.scaler is not None:
            return self.scaler.transform(X_variable)
        return X_variable


def parse_args() -> argparse.Namespace:
    script_dir = Path(__file__).resolve().parent
    repository_root = script_dir.parents[1]
    default_input = repository_root / "data" / "real" / "secom_preprocessed.xlsx"
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=default_input,
        help="전처리 Excel 경로",
    )
    parser.add_argument("--sheet", default="SECOM_Data", help="Excel 시트명")
    parser.add_argument("--target", default="result", help="라벨 컬럼명")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=repository_root / "data" / "outputs" / "detect",
        help="결과 저장 폴더",
    )
    parser.add_argument("--seed", type=int, default=RANDOM_STATE)
    parser.add_argument(
        "--precision-floor", type=float, default=DEFAULT_PRECISION_FLOOR
    )
    parser.add_argument("--outer-folds", type=int, default=DEFAULT_OUTER_FOLDS)
    parser.add_argument("--inner-folds", type=int, default=DEFAULT_INNER_FOLDS)
    parser.add_argument(
        "--near-constant-ratio",
        type=float,
        default=DEFAULT_NEAR_CONSTANT_RATIO,
        help="학습 fold에서 최빈값 비율이 이 값 이상인 변수 제거",
    )
    parser.add_argument(
        "--models",
        nargs="+",
        choices=MODEL_CODES,
        default=list(MODEL_CODES),
        help="실행 모델: lr rf xgb lgbm (기본: 전체)",
    )
    parser.add_argument("--rf-trees", type=int, default=350)
    parser.add_argument("--boost-rounds", type=int, default=350)
    parser.add_argument(
        "--skip-shap",
        action="store_true",
        help="설치/속도 점검용. 최종 제출 분석에서는 사용하지 마세요.",
    )
    parser.add_argument(
        "--no-time-holdout",
        action="store_true",
        help="마지막 20%% 행 순서 강건성 검증을 생략",
    )
    parser.add_argument(
        "--time-holdout-fraction",
        type=float,
        default=DEFAULT_TIME_HOLDOUT_FRACTION,
    )
    parser.add_argument(
        "--expected-input-sha256",
        help="선택 사항: 입력 파일 SHA-256이 다르면 실행을 중단",
    )
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    if args.outer_folds < 2 or args.inner_folds < 2:
        raise ValueError("outer-folds와 inner-folds는 2 이상이어야 합니다.")
    if not 0 < args.precision_floor < 1:
        raise ValueError("precision-floor는 0과 1 사이여야 합니다.")
    if not 0.95 <= args.near_constant_ratio <= 1.0:
        raise ValueError("near-constant-ratio는 0.95 이상 1.0 이하여야 합니다.")
    if not 0 < args.time_holdout_fraction < 0.5:
        raise ValueError("time-holdout-fraction은 0과 0.5 사이여야 합니다.")
    if args.rf_trees < 10 or args.boost_rounds < 10:
        raise ValueError("트리/부스팅 반복 수는 10 이상이어야 합니다.")


def require_dependencies(model_codes: Iterable[str], skip_shap: bool) -> None:
    missing: list[str] = []
    if "xgb" in model_codes and XGBClassifier is None:
        missing.append("xgboost")
    if "lgbm" in model_codes and LGBMClassifier is None:
        missing.append("lightgbm")
    if not skip_shap:
        try:
            import shap  # noqa: F401
        except (ModuleNotFoundError, ImportError):
            missing.append("shap")
    if missing:
        unique = ", ".join(dict.fromkeys(missing))
        import_errors = [
            str(error)
            for error in (XGB_IMPORT_ERROR, LGBM_IMPORT_ERROR)
            if error is not None
        ]
        detail = f"\n로드 오류: {' | '.join(import_errors)}" if import_errors else ""
        raise SystemExit(
            f"필수 패키지가 없습니다: {unique}\n"
            f"다음 명령을 실행하세요:\n{INSTALL_COMMAND}\n\n"
            "macOS에서 LightGBM이 libomp 오류를 내면 먼저 "
            "'brew install libomp'를 실행하세요."
            f"{detail}"
        )


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def package_versions() -> dict[str, str | None]:
    result: dict[str, str | None] = {}
    for package in (
        "numpy",
        "pandas",
        "scikit-learn",
        "openpyxl",
        "xgboost",
        "lightgbm",
        "shap",
        "joblib",
    ):
        try:
            result[package] = version(package)
        except PackageNotFoundError:
            result[package] = None
    return result


# Data loading and validation


def normalize_target(series: pd.Series) -> np.ndarray:
    if series.isna().any():
        raise ValueError("라벨 컬럼에 결측치가 있습니다.")

    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.notna().all():
        unique = set(numeric.unique().tolist())
        if unique.issubset({0, 1}):
            return numeric.astype(int).to_numpy()
        if unique.issubset({-1, 1}):
            return (numeric.astype(int).to_numpy() == 1).astype(int)

    mapping = {
        "normal": 0,
        "pass": 0,
        "good": 0,
        "정상": 0,
        "fail": 1,
        "defect": 1,
        "bad": 1,
        "불량": 1,
    }
    text = series.astype(str).str.strip().str.lower()
    mapped = text.map(mapping)
    if mapped.isna().any():
        raise ValueError(
            "라벨은 0/1, -1/1 또는 정상/불량이어야 합니다. "
            f"실제 값: {series.unique()[:10]}"
        )
    return mapped.astype(int).to_numpy()


def display_feature_name(name: str) -> str:
    match = re.fullmatch(r"Sensor\s*(\d+)", str(name), flags=re.IGNORECASE)
    if match:
        return f"Sensor {match.group(1)}"
    return str(name)


def load_excel(
    path: Path, sheet_name: str, target: str
) -> tuple[np.ndarray, np.ndarray, list[str], pd.DataFrame, dict[str, Any]]:
    """Excel 입력을 검증하고 모델 행렬, 라벨, 변수명과 진단 정보를 반환한다.

    라벨은 0/1 또는 -1/1과 정상·불량 계열 문자열을 허용한다. 입력 변수의
    열 순서는 저장 모델의 추론 계약으로 사용되므로 원본 순서를 유지한다.
    """

    if not path.exists():
        raise FileNotFoundError(
            f"입력 파일을 찾을 수 없습니다: {path}\n"
            "data/real/secom_preprocessed.xlsx에 두거나 --input으로 경로를 "
            "지정하세요. 원본 파일은 저장소에 커밋하지 않습니다."
        )

    try:
        frame = pd.read_excel(path, sheet_name=sheet_name, engine="openpyxl")
    except ValueError as exc:
        sheet_names = pd.ExcelFile(path, engine="openpyxl").sheet_names
        raise ValueError(
            f"시트 '{sheet_name}'를 찾을 수 없습니다. 실제 시트: {sheet_names}"
        ) from exc

    if target not in frame.columns:
        matches = [c for c in frame.columns if str(c).lower() == target.lower()]
        if len(matches) == 1:
            target = str(matches[0])
        else:
            raise ValueError(
                f"라벨 컬럼 '{target}'가 없습니다. "
                f"앞쪽 컬럼: {list(frame.columns[:12])}"
            )

    unnamed = [c for c in frame.columns if str(c).startswith("Unnamed:")]
    if unnamed:
        frame = frame.drop(columns=unnamed)

    if frame.columns.duplicated().any():
        duplicates = frame.columns[frame.columns.duplicated()].tolist()
        raise ValueError(f"중복 컬럼명이 있습니다: {duplicates[:10]}")

    y = normalize_target(frame[target])
    feature_frame = frame.drop(columns=[target]).copy()
    if target in feature_frame.columns:
        raise AssertionError("라벨 컬럼이 입력 변수에 포함되었습니다.")
    if feature_frame.empty:
        raise ValueError("입력 센서 변수가 없습니다.")

    for column in feature_frame.columns:
        feature_frame[column] = pd.to_numeric(feature_frame[column], errors="raise")

    X = feature_frame.to_numpy(dtype=float)
    if np.isinf(X).any():
        locations = np.argwhere(np.isinf(X))[:5].tolist()
        raise ValueError(f"무한대 값이 있습니다. 위치 예시: {locations}")

    unique_labels, counts = np.unique(y, return_counts=True)
    label_counts = {int(k): int(v) for k, v in zip(unique_labels, counts)}
    if set(label_counts) != {0, 1}:
        raise ValueError(f"이진 라벨 0/1이 모두 필요합니다: {label_counts}")

    dominant_ratio: dict[str, float] = {}
    for column in feature_frame.columns:
        counts_col = feature_frame[column].value_counts(dropna=False)
        dominant_ratio[str(column)] = float(counts_col.iloc[0] / len(feature_frame))

    diagnostics = {
        "sheet": sheet_name,
        "rows": int(len(frame)),
        "total_columns": int(frame.shape[1]),
        "feature_count": int(feature_frame.shape[1]),
        "label_counts": label_counts,
        "defect_rate": float(y.mean()),
        "missing_cells": int(np.isnan(X).sum()),
        "infinite_cells": 0,
        "duplicate_rows": int(frame.duplicated().sum()),
        "constant_features": [
            name for name, ratio in dominant_ratio.items() if ratio >= 1.0
        ],
        "near_constant_features_99_9pct": [
            name for name, ratio in dominant_ratio.items() if ratio >= 0.999
        ],
        "file_sha256": file_sha256(path),
    }

    if len(frame) == 1567 and label_counts != {0: 1463, 1: 104}:
        raise ValueError(
            "SECOM 1,567행의 예상 라벨 분포(정상 1,463/불량 104)와 다릅니다: "
            f"{label_counts}"
        )

    return X, y, [str(c) for c in feature_frame.columns], frame, diagnostics


# -----------------------------------------------------------------------------
# Model definitions
# -----------------------------------------------------------------------------


def class_ratio(y: np.ndarray) -> float:
    positives = int(y.sum())
    negatives = int(len(y) - positives)
    if positives == 0:
        raise ValueError("학습 데이터에 불량 샘플이 없습니다.")
    return negatives / positives


def build_model_specs(args: argparse.Namespace) -> dict[str, ModelSpec]:
    def xgb_factory(y: np.ndarray, seed: int) -> BaseEstimator:
        if XGBClassifier is None:
            raise RuntimeError("xgboost가 설치되지 않았습니다.")
        return XGBClassifier(
            n_estimators=args.boost_rounds,
            learning_rate=0.035,
            max_depth=3,
            min_child_weight=3,
            subsample=0.85,
            colsample_bytree=0.75,
            reg_alpha=0.10,
            reg_lambda=2.0,
            scale_pos_weight=class_ratio(y),
            eval_metric="logloss",
            n_jobs=-1,
            random_state=seed,
        )

    def lgbm_factory(y: np.ndarray, seed: int) -> BaseEstimator:
        if LGBMClassifier is None:
            raise RuntimeError("lightgbm이 설치되지 않았습니다.")
        return LGBMClassifier(
            n_estimators=args.boost_rounds,
            learning_rate=0.025,
            num_leaves=15,
            max_depth=-1,
            min_child_samples=25,
            subsample=0.85,
            # LightGBM은 subsample_freq=0이면 subsample 값을 적용하지 않는다.
            # 참조 dashboard_data.json을 만든 설정을 명시적으로 고정한다.
            subsample_freq=1,
            colsample_bytree=0.75,
            reg_alpha=0.10,
            reg_lambda=2.0,
            scale_pos_weight=class_ratio(y),
            n_jobs=-1,
            random_state=seed,
            verbosity=-1,
        )

    all_specs = {
        "lr": ModelSpec(
            code="lr",
            name="Logistic Regression",
            scale=True,
            factory=lambda y, seed: LogisticRegression(
                class_weight="balanced",
                C=0.1,
                max_iter=5000,
                solver="liblinear",
                random_state=seed,
            ),
        ),
        "rf": ModelSpec(
            code="rf",
            name="Random Forest",
            scale=False,
            factory=lambda y, seed: RandomForestClassifier(
                n_estimators=args.rf_trees,
                max_depth=None,
                min_samples_leaf=3,
                max_features="sqrt",
                class_weight="balanced_subsample",
                n_jobs=-1,
                random_state=seed,
            ),
        ),
        "xgb": ModelSpec(
            code="xgb", name="XGBoost", scale=False, factory=xgb_factory
        ),
        "lgbm": ModelSpec(
            code="lgbm", name="LightGBM", scale=False, factory=lgbm_factory
        ),
    }
    return {code: all_specs[code] for code in args.models}


# Cross-validation and threshold selection

def predict_positive(model: BaseEstimator, X: np.ndarray) -> np.ndarray:
    probabilities = model.predict_proba(X)
    if probabilities.ndim != 2 or probabilities.shape[1] != 2:
        raise ValueError("이진 분류 predict_proba 결과가 아닙니다.")
    return probabilities[:, 1].astype(float)


def fit_fold_model(
    spec: ModelSpec,
    X_train: np.ndarray,
    y_train: np.ndarray,
    *,
    seed: int,
    near_constant_ratio: float,
) -> tuple[FoldPreprocessor, BaseEstimator]:
    preprocessor = FoldPreprocessor.fit(
        X_train,
        scale=spec.scale,
        near_constant_ratio=near_constant_ratio,
    )
    transformed = preprocessor.transform(X_train)
    model = spec.factory(y_train, seed)
    model.fit(transformed, y_train)
    return preprocessor, model


def inner_oof_scores(
    X: np.ndarray,
    y: np.ndarray,
    spec: ModelSpec,
    *,
    inner_folds: int,
    seed: int,
    near_constant_ratio: float,
) -> np.ndarray:
    if int(y.sum()) < inner_folds:
        raise ValueError(
            f"inner {inner_folds}-fold에 필요한 불량 샘플이 부족합니다: "
            f"{int(y.sum())}"
        )
    scores = np.full(len(y), np.nan, dtype=float)
    splitter = StratifiedKFold(
        n_splits=inner_folds, shuffle=True, random_state=seed
    )
    for inner_fold, (train_idx, valid_idx) in enumerate(
        splitter.split(X, y), start=1
    ):
        prep, model = fit_fold_model(
            spec,
            X[train_idx],
            y[train_idx],
            seed=seed + inner_fold,
            near_constant_ratio=near_constant_ratio,
        )
        scores[valid_idx] = predict_positive(model, prep.transform(X[valid_idx]))
    if np.isnan(scores).any():
        raise RuntimeError("inner OOF 위험 점수에 결측이 있습니다.")
    return scores


def f_beta_score_from_pr(precision: np.ndarray, recall: np.ndarray, beta: float) -> np.ndarray:
    beta_squared = beta**2
    denominator = beta_squared * precision + recall
    return (1 + beta_squared) * precision * recall / np.maximum(denominator, 1e-12)


def choose_threshold(
    y_true: np.ndarray,
    scores: np.ndarray,
    precision_floor: float,
) -> tuple[float, dict[str, Any]]:
    """Inner OOF 점수에서 불량 판정 임계값을 선택한다.

    Precision 하한을 만족하는 후보 중 Recall이 최대인 지점을 사용한다.
    유효 후보가 없으면 Recall에 가중치를 둔 F2 최대 지점으로 대체한다.
    """

    precision, recall, thresholds = precision_recall_curve(y_true, scores)
    if len(thresholds) == 0:
        return 0.5, {
            "threshold_rule": "fallback_0.5_no_threshold",
            "inner_precision": None,
            "inner_recall": None,
            "inner_f2": None,
        }

    candidate_precision = precision[:-1]
    candidate_recall = recall[:-1]
    candidate_f2 = f_beta_score_from_pr(
        candidate_precision, candidate_recall, beta=2.0
    )
    valid = np.flatnonzero(candidate_precision >= precision_floor)

    if len(valid):
        # lexsort의 마지막 키가 1순위: Recall → Precision → F2 → 높은 threshold.
        order = np.lexsort(
            (
                thresholds[valid],
                candidate_f2[valid],
                candidate_precision[valid],
                candidate_recall[valid],
            )
        )
        chosen = int(valid[order[-1]])
        rule = f"max_recall_with_inner_precision_at_least_{precision_floor:.3f}"
    else:
        chosen = int(np.nanargmax(candidate_f2))
        rule = "fallback_max_inner_f2_no_precision_floor_candidate"

    return float(thresholds[chosen]), {
        "threshold_rule": rule,
        "inner_precision": float(candidate_precision[chosen]),
        "inner_recall": float(candidate_recall[chosen]),
        "inner_f2": float(candidate_f2[chosen]),
    }


def classification_metrics(
    y_true: np.ndarray, scores: np.ndarray, predicted: np.ndarray
) -> dict[str, Any]:
    tn, fp, fn, tp = confusion_matrix(
        y_true, predicted, labels=[0, 1]
    ).ravel()
    precision = precision_score(y_true, predicted, zero_division=0)
    recall = recall_score(y_true, predicted, zero_division=0)
    f1 = f1_score(y_true, predicted, zero_division=0)
    f2 = float(
        f_beta_score_from_pr(
            np.array([precision]), np.array([recall]), beta=2.0
        )[0]
    )
    return {
        "recall": float(recall),
        "precision": float(precision),
        "f1": float(f1),
        "f2": f2,
        "pr_auc": float(average_precision_score(y_true, scores)),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, predicted)),
        "tp": int(tp),
        "fp": int(fp),
        "fn": int(fn),
        "tn": int(tn),
    }


def cross_validated_evaluate(
    X: np.ndarray,
    y: np.ndarray,
    specs: dict[str, ModelSpec],
    args: argparse.Namespace,
) -> tuple[
    pd.DataFrame,
    dict[str, np.ndarray],
    dict[str, np.ndarray],
    np.ndarray,
]:
    """모델별 OOF 성능을 평가하고 fold별 임계값을 기록한다.

    각 outer validation은 모델 학습뿐 아니라 임계값 선택에도 사용되지 않는다.
    다만 모델군 자체의 선택은 동일한 outer 결과를 사용하므로, 이 함수는 완전한
    nested model-selection 성능 추정기가 아니다.
    """

    if int(y.sum()) < args.outer_folds:
        raise ValueError(
            f"outer {args.outer_folds}-fold에 필요한 불량 샘플이 부족합니다."
        )

    outer = StratifiedKFold(
        n_splits=args.outer_folds, shuffle=True, random_state=args.seed
    )
    outer_splits = list(outer.split(X, y))
    fold_assignment = np.full(len(y), -1, dtype=int)
    for fold, (_, valid_idx) in enumerate(outer_splits, start=1):
        fold_assignment[valid_idx] = fold

    records: list[dict[str, Any]] = []
    oof_scores = {code: np.full(len(y), np.nan) for code in specs}
    oof_predictions = {code: np.full(len(y), -1, dtype=int) for code in specs}

    for model_number, (code, spec) in enumerate(specs.items(), start=1):
        LOGGER.info("[%d/%d] %s 평가", model_number, len(specs), spec.name)
        for fold, (train_idx, valid_idx) in enumerate(outer_splits, start=1):
            inner_scores = inner_oof_scores(
                X[train_idx],
                y[train_idx],
                spec,
                inner_folds=args.inner_folds,
                seed=args.seed + fold * 100,
                near_constant_ratio=args.near_constant_ratio,
            )
            threshold, threshold_info = choose_threshold(
                y[train_idx], inner_scores, args.precision_floor
            )

            prep, model = fit_fold_model(
                spec,
                X[train_idx],
                y[train_idx],
                seed=args.seed + fold,
                near_constant_ratio=args.near_constant_ratio,
            )
            scores = predict_positive(model, prep.transform(X[valid_idx]))
            predicted = (scores >= threshold).astype(int)
            metrics = classification_metrics(y[valid_idx], scores, predicted)

            oof_scores[code][valid_idx] = scores
            oof_predictions[code][valid_idx] = predicted
            records.append(
                {
                    "model_code": code,
                    "model": spec.name,
                    "fold": fold,
                    "threshold": threshold,
                    "train_rows": int(len(train_idx)),
                    "valid_rows": int(len(valid_idx)),
                    "features_used": int(len(prep.original_feature_indices)),
                    **metrics,
                    **threshold_info,
                }
            )
            LOGGER.info(
                "fold=%d threshold=%.6f recall=%.3f precision=%.3f PR-AUC=%.3f",
                fold,
                threshold,
                metrics["recall"],
                metrics["precision"],
                metrics["pr_auc"],
            )

    for code in specs:
        if np.isnan(oof_scores[code]).any() or (oof_predictions[code] < 0).any():
            raise RuntimeError(f"{specs[code].name}의 OOF 예측이 완성되지 않았습니다.")
    if (fold_assignment < 0).any():
        raise RuntimeError("outer fold 할당이 완성되지 않았습니다.")

    return pd.DataFrame(records), oof_scores, oof_predictions, fold_assignment


def summarize_models(fold_metrics: pd.DataFrame) -> pd.DataFrame:
    metric_names = [
        "recall",
        "precision",
        "f1",
        "f2",
        "pr_auc",
        "balanced_accuracy",
    ]
    rows: list[dict[str, Any]] = []
    for (code, name), group in fold_metrics.groupby(
        ["model_code", "model"], sort=False
    ):
        row: dict[str, Any] = {"model_code": code, "model": name}
        for metric in metric_names:
            row[metric] = float(group[metric].mean())
            row[f"{metric}_std"] = float(group[metric].std(ddof=0))
        row["threshold_median"] = float(group["threshold"].median())
        row["features_used_min"] = int(group["features_used"].min())
        row["features_used_max"] = int(group["features_used"].max())
        rows.append(row)
    return pd.DataFrame(rows)


def select_model(summary: pd.DataFrame, precision_floor: float) -> tuple[str, str]:
    eligible = summary[summary["precision"] >= precision_floor]
    if not eligible.empty:
        ranked = eligible.sort_values(
            ["recall", "pr_auc", "precision"], ascending=[False, False, False]
        )
        rule = (
            f"평균 outer precision이 {precision_floor:.2f} 이상인 모델 중 "
            "평균 recall 최대; PR-AUC와 precision을 순서대로 동률 기준으로 사용"
        )
    else:
        ranked = summary.sort_values(
            ["f2", "pr_auc", "recall"], ascending=[False, False, False]
        )
        rule = (
            f"평균 outer precision {precision_floor:.2f} 조건을 충족한 모델이 없어 "
            "평균 F2 최대 모델 선택"
        )
    return str(ranked.iloc[0]["model_code"]), rule


# Risk ranking and model interpretation

def capture_strategy(
    y: np.ndarray, scores: np.ndarray, fraction: float
) -> dict[str, Any]:
    inspection_count = int(math.ceil(len(y) * fraction))
    ranking = np.argsort(-scores, kind="stable")
    selected = ranking[:inspection_count]
    captured = int(y[selected].sum())
    total = int(y.sum())
    return {
        "fraction": float(fraction),
        "inspection_count": inspection_count,
        "captured_defects": captured,
        "total_defects": total,
        "capture_rate": float(captured / total) if total else 0.0,
    }


def fold_normalized_percentile(
    scores: np.ndarray, fold_assignment: np.ndarray
) -> np.ndarray:
    """서로 다른 fold 모델의 raw score를 fold 내부 백분위로 변환한다.

    Class weight 모델의 점수는 확률 보정되지 않았고 fold마다 척도가 다를 수
    있으므로, 전체 OOF 우선순위는 fold 내부 상대 순위를 기준으로 비교한다.
    """

    percentiles = np.full(len(scores), np.nan, dtype=float)
    for fold in np.unique(fold_assignment):
        indices = np.flatnonzero(fold_assignment == fold)
        order = np.argsort(scores[indices], kind="stable")
        ranks = np.empty(len(indices), dtype=int)
        ranks[order] = np.arange(1, len(indices) + 1)
        percentiles[indices] = ranks / len(indices)
    if np.isnan(percentiles).any():
        raise RuntimeError("fold 정규화 위험 백분위 계산에 실패했습니다.")
    return percentiles


def normalize_shap_values(values: Any) -> np.ndarray:
    if isinstance(values, list):
        values = values[-1]
    array = np.asarray(values)
    if array.ndim == 3:
        if array.shape[-1] == 2:
            array = array[:, :, 1]
        elif array.shape[0] == 2:
            array = array[1]
        else:
            raise ValueError(f"지원하지 않는 3차원 SHAP shape: {array.shape}")
    if array.ndim != 2:
        raise ValueError(f"지원하지 않는 SHAP shape: {array.shape}")
    return array.astype(float)


def compute_oof_shap(
    X: np.ndarray,
    y: np.ndarray,
    spec: ModelSpec,
    args: argparse.Namespace,
) -> tuple[np.ndarray, np.ndarray]:
    """선정 모델의 outer-validation 행에 대해 OOF SHAP 값을 계산한다.

    각 행은 자신을 학습하지 않은 fold 모델로 설명하며, 전처리에서 제거된
    변수의 위치는 원래 변수 공간에서 0으로 유지한다.
    """

    try:
        import shap
    except (ModuleNotFoundError, ImportError) as exc:
        raise RuntimeError(
            f"SHAP이 필요합니다. 다음 명령을 실행하세요: {INSTALL_COMMAND}"
        ) from exc

    outer = StratifiedKFold(
        n_splits=args.outer_folds, shuffle=True, random_state=args.seed
    )
    local_values = np.zeros((len(y), X.shape[1]), dtype=float)

    LOGGER.info("%s의 OOF SHAP 계산", spec.name)
    for fold, (train_idx, valid_idx) in enumerate(outer.split(X, y), start=1):
        prep, model = fit_fold_model(
            spec,
            X[train_idx],
            y[train_idx],
            seed=args.seed + fold,
            near_constant_ratio=args.near_constant_ratio,
        )
        X_train = prep.transform(X[train_idx])
        X_valid = prep.transform(X[valid_idx])

        if spec.code == "lr":
            background = X_train
            if len(background) > SHAP_BACKGROUND_MAX_ROWS:
                rng = np.random.default_rng(args.seed + fold)
                background = background[
                    rng.choice(
                        len(background),
                        size=SHAP_BACKGROUND_MAX_ROWS,
                        replace=False,
                    )
                ]
            explainer = shap.LinearExplainer(model, background)
            values = explainer.shap_values(X_valid)
        else:
            explainer = shap.TreeExplainer(model)
            values = explainer.shap_values(X_valid)

        fold_values = normalize_shap_values(values)
        if fold_values.shape[1] != len(prep.original_feature_indices):
            raise ValueError(
                "SHAP 변수 수와 전처리 변수 매핑이 다릅니다: "
                f"{fold_values.shape[1]} vs {len(prep.original_feature_indices)}"
            )
        local_values[np.ix_(valid_idx, prep.original_feature_indices)] = fold_values

    return local_values, np.mean(np.abs(local_values), axis=0)


def risk_grade(risk_percentile: float) -> str:
    """상대 위험 백분위에 따른 데모용 운영 등급."""

    if risk_percentile >= HIGH_RISK_PERCENTILE:
        return "고위험"
    if risk_percentile >= MEDIUM_RISK_PERCENTILE:
        return "중위험"
    return "저위험"


# Ordered holdout robustness check

def temporal_holdout_evaluation(
    X: np.ndarray,
    y: np.ndarray,
    spec: ModelSpec,
    args: argparse.Namespace,
) -> dict[str, Any]:
    """행 순서 마지막 구간에서 선정 모델의 강건성을 점검한다.

    입력 Excel에 timestamp가 없으므로 정식 시간 기반 외부검증이 아니라,
    원본 행 순서가 보존됐다는 가정 아래 수행하는 보조 분석이다.
    """

    split_index = int(math.floor(len(y) * (1 - args.time_holdout_fraction)))
    X_train, X_test = X[:split_index], X[split_index:]
    y_train, y_test = y[:split_index], y[split_index:]
    if y_train.sum() == 0 or y_test.sum() == 0:
        raise ValueError(
            "행 순서 holdout의 학습 또는 평가 구간에 불량 샘플이 없습니다."
        )

    inner_scores = inner_oof_scores(
        X_train,
        y_train,
        spec,
        inner_folds=args.inner_folds,
        seed=args.seed + ORDERED_HOLDOUT_CV_SEED_OFFSET,
        near_constant_ratio=args.near_constant_ratio,
    )
    threshold, threshold_info = choose_threshold(
        y_train, inner_scores, args.precision_floor
    )
    prep, model = fit_fold_model(
        spec,
        X_train,
        y_train,
        seed=args.seed + ORDERED_HOLDOUT_MODEL_SEED_OFFSET,
        near_constant_ratio=args.near_constant_ratio,
    )
    scores = predict_positive(model, prep.transform(X_test))
    predicted = (scores >= threshold).astype(int)
    metrics = classification_metrics(y_test, scores, predicted)
    capture20 = capture_strategy(
        y_test,
        scores,
        PRIMARY_INSPECTION_FRACTION,
    )
    return {
        "assumption": (
            "Excel에 timestamp가 없어 원본 행 순서가 시간순으로 유지됐다고 가정한 "
            "마지막 구간 강건성 검증"
        ),
        "train_rows": int(len(y_train)),
        "test_rows": int(len(y_test)),
        "train_defects": int(y_train.sum()),
        "test_defects": int(y_test.sum()),
        "test_fraction": float(args.time_holdout_fraction),
        "threshold": threshold,
        **threshold_info,
        **metrics,
        "top20_capture": capture20,
    }


def python_scalar(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (np.floating, float)) and np.isnan(value):
        return None
    if isinstance(value, (np.floating, float)):
        return float(value)
    if isinstance(value, (np.integer, int)):
        return int(value)
    if pd.isna(value):
        return None
    return value


def markdown_table(frame: pd.DataFrame, columns: list[str]) -> str:
    display = frame[columns].copy()
    for column in display.columns:
        if column != "model":
            display[column] = display[column].map(lambda x: f"{float(x):.3f}")
    header = "| " + " | ".join(display.columns) + " |"
    divider = "| " + " | ".join(["---"] * len(display.columns)) + " |"
    rows = [
        "| " + " | ".join(str(value) for value in row) + " |"
        for row in display.itertuples(index=False, name=None)
    ]
    return "\n".join([header, divider, *rows])


# Artifact generation and persistence

def write_analysis_report(
    path: Path,
    *,
    diagnostics: dict[str, Any],
    comparison: pd.DataFrame,
    selected_name: str,
    selected_metrics: pd.Series,
    pooled_metrics: dict[str, Any],
    confusion: dict[str, int],
    top20: dict[str, Any],
    temporal: dict[str, Any] | None,
    shap_enabled: bool,
    outer_folds: int,
) -> None:
    """실행 결과와 방법론적 한계를 Markdown 보고서로 저장한다."""

    comparison_table = markdown_table(
        comparison,
        ["model", "recall", "precision", "f1", "pr_auc", "balanced_accuracy"],
    )
    majority_rate = max(diagnostics["label_counts"].values()) / diagnostics["rows"]
    temporal_section = ""
    if temporal is not None:
        temporal_section = f"""
## 행 순서 마지막 {temporal['test_fraction']:.0%} 강건성 검증

- 가정: Excel 행 순서가 원본의 시간순을 유지함
- 학습/평가: {temporal['train_rows']:,}건 / {temporal['test_rows']:,}건
- 평가 구간 불량: {temporal['test_defects']:,}건
- Recall: {temporal['recall']:.3f}
- Precision: {temporal['precision']:.3f}
- PR-AUC: {temporal['pr_auc']:.3f}
- Balanced Accuracy: {temporal['balanced_accuracy']:.3f}

무작위 교차검증보다 이 결과가 크게 낮으면 공정 시점 변화에 따른 성능 저하 가능성이
있다는 뜻입니다. timestamp가 삭제됐으므로 정식 시간 검증이 아니라 강건성 점검입니다.
"""

    shap_text = (
        "선정 모델을 각 outer fold에서 다시 학습하고 해당 validation 행을 설명한 OOF SHAP입니다."
        if shap_enabled
        else "--skip-shap 옵션으로 SHAP 계산을 생략한 실행입니다."
    )

    text = f"""# GreenFab Insight — SECOM 모델 분석 결과

## 데이터 확인

- 행: {diagnostics['rows']:,}건
- 센서 변수: {diagnostics['feature_count']:,}개
- 정상/불량: {diagnostics['label_counts'][0]:,}건 / {diagnostics['label_counts'][1]:,}건
- 불량률: {diagnostics['defect_rate']:.2%}
- 현재 결측치: {diagnostics['missing_cells']:,}개
- 99.9% 이상 근상수 변수: {len(diagnostics['near_constant_features_99_9pct']):,}개

## 전처리 범위와 평가 한계

이 Excel은 전체 {diagnostics['rows']:,}행을 기준으로 컬럼 제거와 중앙값 대체가 이미 끝난 파일입니다.
라벨을 사용한 직접적인 정답 누수는 아니지만, 검증 fold의 분포가 중앙값 계산에 소량
반영된 상태입니다. 따라서 본 결과는 `global_preprocessed_input` 기반 내부 검증이며,
실제 도입 전에는 원본 NaN 데이터에서 전처리를 fold 내부에 넣고 재검증해야 합니다.

## 모델 비교 — Stratified {outer_folds}-Fold + 학습 fold 내부 임계값 탐색

{comparison_table}

다수 클래스만 예측해도 Accuracy가 {majority_rate:.2%}이므로 이를 주요 지표로 사용하지 않았습니다.
PR-AUC는 fold별 연속 위험 점수로, Recall·Precision·F1·Balanced Accuracy는 각
학습 fold 내부에서 선정한 임계값으로 계산했습니다. 네 알고리즘 중 모델 선택까지
완전히 감싼 nested model-selection 추정치는 아니므로 소규모 선택 편향은 남습니다.

## 선정 결과 — Fold 평균

- 선정 모델: **{selected_name}**
- Recall: {selected_metrics['recall']:.3f} ± {selected_metrics['recall_std']:.3f}
- Precision: {selected_metrics['precision']:.3f} ± {selected_metrics['precision_std']:.3f}
- PR-AUC: {selected_metrics['pr_auc']:.3f} ± {selected_metrics['pr_auc_std']:.3f}
- Balanced Accuracy: {selected_metrics['balanced_accuracy']:.3f} ± {selected_metrics['balanced_accuracy_std']:.3f}

## 대시보드용 Pooled OOF 결과

- Recall: {pooled_metrics['recall']:.3f}
- Precision: {pooled_metrics['precision']:.3f}
- F1: {pooled_metrics['f1']:.3f}
- PR-AUC: {pooled_metrics['pr_auc']:.3f} (fold 내부 위험 백분위 사용)
- Balanced Accuracy: {pooled_metrics['balanced_accuracy']:.3f}
- 혼동행렬: TP={confusion['tp']}, FP={confusion['fp']}, FN={confusion['fn']}, TN={confusion['tn']}
- 위험도 상위 20% 점검: 불량 {top20['captured_defects']}/{top20['total_defects']}건 포착 ({top20['capture_rate']:.2%}, fold 내부 위험 백분위 기준)

혼동행렬의 각 행은 해당 outer fold 학습 데이터 안에서 고른 서로 다른 임계값을
사용했습니다. 저장 모델의 단일 임시 임계값과 혼동하면 안 됩니다.

## SHAP 해석

{shap_text}

SECOM 센서는 익명화돼 있으므로 `Sensor59` 등을 온도·압력·식각 변수처럼 번역하면
안 됩니다. SHAP은 모델이 사용한 연관 기여도이지 불량의 물리적 원인이나 인과효과가
아닙니다. 강하게 상관된 센서 사이에서는 중요도가 나뉘어 나타날 수도 있습니다.

## 위험 점수 해석

class weight를 적용한 모델의 `predict_proba`는 보정된 실제 불량 확률이 아닙니다.
따라서 대시보드 위험 점수는 fold 내부 순위를 0~1 백분위로 바꿨으며, **불량 확률**이
아니라 **상대 위험 점수**라고 표현해야 합니다. 고/중/저 등급은 {HIGH_RISK_PERCENTILE:.0%}와 {MEDIUM_RISK_PERCENTILE:.0%}를 경계로
한 데모용 운영 규칙이며 현장 비용 검증 전 확정 기준이 아닙니다.
{temporal_section}
"""
    path.write_text(text.strip() + "\n", encoding="utf-8")


def save_full_model(
    path: Path,
    *,
    X: np.ndarray,
    y: np.ndarray,
    feature_names: list[str],
    target: str,
    spec: ModelSpec,
    args: argparse.Namespace,
    deployment_threshold: float,
) -> dict[str, float]:
    """전체 데이터로 모델을 재학습하고 추론에 필요한 전처리와 함께 저장한다.

    저장 임계값과 위험 등급 경계는 프로토타입 운영을 위한 임시 기준이며,
    외부 검증이나 확률 보정을 거친 배포 기준이 아니다.
    """

    prep, model = fit_fold_model(
        spec,
        X,
        y,
        seed=args.seed + FINAL_MODEL_SEED_OFFSET,
        near_constant_ratio=args.near_constant_ratio,
    )
    transformed = prep.transform(X)
    full_training_scores = predict_positive(model, transformed)
    grade_cutoffs = {
        "high_raw_score": float(
            np.quantile(full_training_scores, HIGH_RISK_PERCENTILE)
        ),
        "medium_raw_score": float(
            np.quantile(full_training_scores, MEDIUM_RISK_PERCENTILE)
        ),
    }
    bundle = {
        "model_name": spec.name,
        "model_code": spec.code,
        "target": target,
        "input_feature_names": feature_names,
        "model_feature_names": [
            feature_names[index] for index in prep.original_feature_indices
        ],
        "missing_keep": prep.missing_keep,
        "near_constant_keep": prep.near_constant_keep,
        "imputer": prep.imputer,
        "scaler": prep.scaler,
        "model": model,
        "provisional_binary_threshold": float(deployment_threshold),
        "risk_grade_raw_score_cutoffs": grade_cutoffs,
        "risk_grade_rule": (
            f"고위험: full-training score의 {HIGH_RISK_PERCENTILE:.0%} "
            "백분위 경계 이상, "
            f"중위험: {MEDIUM_RISK_PERCENTILE:.0%}~"
            f"{HIGH_RISK_PERCENTILE:.0%} 백분위 구간, "
            f"저위험: {MEDIUM_RISK_PERCENTILE:.0%} 백분위 경계 미만"
        ),
        "inference_helper": "run_pipeline.predict_with_saved_bundle",
        "package_versions": package_versions(),
        "notice": "상대 위험 점수 모델이며 실제 불량확률로 보정되지 않음",
    }
    joblib.dump(bundle, path)
    return grade_cutoffs


def predict_with_saved_bundle(
    bundle: dict[str, Any], data: pd.DataFrame | np.ndarray
) -> pd.DataFrame:
    """저장된 joblib bundle로 새 행의 위험 점수와 임시 등급을 계산한다.

    반환 점수는 class weight 모델의 raw positive-class score이며 보정 확률이
    아니다. DataFrame 입력은 학습 당시 변수 순서로 자동 정렬한다.
    """

    if isinstance(data, pd.DataFrame):
        missing = [
            column
            for column in bundle["input_feature_names"]
            if column not in data.columns
        ]
        if missing:
            raise ValueError(f"추론 데이터에 센서 컬럼이 없습니다: {missing[:10]}")
        X_input = data[bundle["input_feature_names"]].to_numpy(dtype=float)
    else:
        X_input = np.asarray(data, dtype=float)
        expected = len(bundle["input_feature_names"])
        if X_input.ndim != 2 or X_input.shape[1] != expected:
            raise ValueError(
                f"추론 배열은 2차원이며 변수 {expected}개여야 합니다: "
                f"{X_input.shape}"
            )

    transformed = X_input[:, bundle["missing_keep"]]
    transformed = bundle["imputer"].transform(transformed)
    transformed = transformed[:, bundle["near_constant_keep"]]
    if bundle["scaler"] is not None:
        transformed = bundle["scaler"].transform(transformed)
    scores = predict_positive(bundle["model"], transformed)
    cutoffs = bundle["risk_grade_raw_score_cutoffs"]
    grades = np.where(
        scores >= cutoffs["high_raw_score"],
        "고위험",
        np.where(scores >= cutoffs["medium_raw_score"], "중위험", "저위험"),
    )
    predicted = (scores >= bundle["provisional_binary_threshold"]).astype(int)
    return pd.DataFrame(
        {
            "relative_risk_score": scores,
            "risk_grade": grades,
            "predicted_class_provisional_threshold": predicted,
        }
    )


def write_json(path: Path, payload: dict[str, Any]) -> None:
    """NaN을 허용하지 않는 UTF-8 JSON을 저장한다."""

    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, allow_nan=False)


def validate_artifact_contract(
    dashboard: dict[str, Any],
    oof: pd.DataFrame,
    *,
    expected_rows: int,
    expected_folds: int,
) -> None:
    """저장 직전 대시보드와 OOF 산출물의 구조적 일관성을 검증한다."""

    confusion_total = sum(dashboard["confusion_matrix"].values())
    if confusion_total != expected_rows:
        raise ValueError(
            "혼동행렬 합계가 전체 행 수와 다릅니다: "
            f"{confusion_total} != {expected_rows}"
        )

    risk_total = sum(dashboard["risk_distribution"].values())
    if risk_total != expected_rows:
        raise ValueError(
            "위험 등급 합계가 전체 행 수와 다릅니다: "
            f"{risk_total} != {expected_rows}"
        )

    if len(oof) != expected_rows:
        raise ValueError(f"OOF 행 수가 올바르지 않습니다: {len(oof)} != {expected_rows}")
    if len(dashboard["fold_thresholds"]) != expected_folds:
        raise ValueError(
            "선정 모델의 fold별 임계값 수가 outer fold 수와 다릅니다."
        )
    if len(dashboard["top_features"]) > GLOBAL_SHAP_TOP_K:
        raise ValueError("전역 SHAP 변수 수가 설정된 상한을 초과했습니다.")
    if len(dashboard["risk_items"]) > RISK_ITEM_TOP_K:
        raise ValueError("위험 생산 건 수가 설정된 상한을 초과했습니다.")

    json.dumps(dashboard, ensure_ascii=False, allow_nan=False)


# Analysis orchestration

def run_analysis(args: argparse.Namespace) -> None:
    """검증, 모델 비교, 해석과 산출물 저장을 순서대로 수행한다."""

    validate_args(args)
    require_dependencies(args.models, args.skip_shap)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    X, y, feature_names, _, diagnostics = load_excel(
        args.input, args.sheet, args.target
    )
    if (
        args.expected_input_sha256
        and diagnostics["file_sha256"].lower()
        != args.expected_input_sha256.lower()
    ):
        raise ValueError(
            "입력 파일 SHA-256이 기대값과 다릅니다: "
            f"{diagnostics['file_sha256']} != {args.expected_input_sha256}"
        )
    LOGGER.info(
        "데이터 로드: X=%s, 정상=%d, 불량=%d, 결측=%d",
        X.shape,
        int((y == 0).sum()),
        int(y.sum()),
        int(np.isnan(X).sum()),
    )
    if diagnostics["near_constant_features_99_9pct"]:
        LOGGER.info(
            "근상수 변수(학습 fold 내부 제거 대상): %s",
            ", ".join(diagnostics["near_constant_features_99_9pct"]),
        )

    specs = build_model_specs(args)
    (
        fold_metrics,
        all_scores,
        all_predictions,
        fold_assignment,
    ) = cross_validated_evaluate(X, y, specs, args)
    comparison = summarize_models(fold_metrics)
    selected_code, selection_rule = select_model(
        comparison, args.precision_floor
    )
    selected_spec = specs[selected_code]
    selected_row = comparison[comparison["model_code"] == selected_code].iloc[0]
    selected_scores = all_scores[selected_code]
    selected_predictions = all_predictions[selected_code]
    selected_folds = fold_metrics[
        fold_metrics["model_code"] == selected_code
    ]
    deployment_threshold = float(selected_folds["threshold"].median())
    fold_threshold_map = {
        int(row.fold): float(row.threshold)
        for row in selected_folds[["fold", "threshold"]].itertuples(index=False)
    }
    evaluation_threshold_used = np.array(
        [fold_threshold_map[int(fold)] for fold in fold_assignment], dtype=float
    )
    risk_percentiles = fold_normalized_percentile(
        selected_scores, fold_assignment
    )

    pooled_oof_metrics = classification_metrics(
        y, selected_scores, selected_predictions
    )
    pooled_oof_metrics["pr_auc_raw_fold_scores"] = pooled_oof_metrics["pr_auc"]
    pooled_oof_metrics["pr_auc"] = float(
        average_precision_score(y, risk_percentiles)
    )
    confusion = {
        key: int(pooled_oof_metrics[key]) for key in ("tp", "fp", "fn", "tn")
    }
    strategies = [
        capture_strategy(y, risk_percentiles, fraction)
        for fraction in INSPECTION_FRACTIONS
    ]
    top20 = next(
        item
        for item in strategies
        if item["fraction"] == PRIMARY_INSPECTION_FRACTION
    )

    LOGGER.info("선정 모델: %s", selected_spec.name)
    LOGGER.info("선정 규칙: %s", selection_rule)

    local_shap: np.ndarray | None = None
    global_shap: np.ndarray | None = None
    if not args.skip_shap:
        local_shap, global_shap = compute_oof_shap(
            X, y, selected_spec, args
        )

    temporal: dict[str, Any] | None = None
    if not args.no_time_holdout:
        LOGGER.info(
            "행 순서 마지막 %.0f%% 강건성 검증",
            args.time_holdout_fraction * 100,
        )
        temporal = temporal_holdout_evaluation(X, y, selected_spec, args)

    final_model_grade_cutoffs = save_full_model(
        args.output_dir / "selected_model.joblib",
        X=X,
        y=y,
        feature_names=feature_names,
        target=args.target,
        spec=selected_spec,
        args=args,
        deployment_threshold=deployment_threshold,
    )

    grades = np.array([risk_grade(score) for score in risk_percentiles])
    ranking = np.argsort(-risk_percentiles, kind="stable")
    rank_numbers = np.empty(len(y), dtype=int)
    rank_numbers[ranking] = np.arange(1, len(y) + 1)
    ids = np.array([f"SECOM-{index + 1:04d}" for index in range(len(y))])

    top_features: list[dict[str, Any]] = []
    if global_shap is not None:
        for index in np.argsort(-global_shap, kind="stable")[:GLOBAL_SHAP_TOP_K]:
            top_features.append(
                {
                    "feature": feature_names[index],
                    "display_feature": display_feature_name(feature_names[index]),
                    "shap_value": float(global_shap[index]),
                }
            )

    risk_items: list[dict[str, Any]] = []
    for index in ranking[:RISK_ITEM_TOP_K]:
        factors: list[dict[str, Any]] = []
        if local_shap is not None:
            factor_order = np.argsort(
                -np.abs(local_shap[index]), kind="stable"
            )[:LOCAL_SHAP_TOP_K]
            for feature_index in factor_order:
                contribution = float(local_shap[index, feature_index])
                factors.append(
                    {
                        "feature": feature_names[feature_index],
                        "display_feature": display_feature_name(
                            feature_names[feature_index]
                        ),
                        "contribution": contribution,
                        "direction": "위험 증가" if contribution > 0 else "위험 감소",
                        "feature_value": python_scalar(X[index, feature_index]),
                    }
                )
        risk_items.append(
            {
                "id": str(ids[index]),
                "row_index": int(index),
                "risk_score": float(risk_percentiles[index]),
                "risk_score_type": "within-fold relative risk percentile",
                "raw_model_score": float(selected_scores[index]),
                "risk_rank": int(rank_numbers[index]),
                "risk_grade": str(grades[index]),
                "observed_label": "불량" if y[index] == 1 else "정상",
                "top_factors": factors,
            }
        )

    risk_distribution = {
        "high": int((grades == "고위험").sum()),
        "medium": int((grades == "중위험").sum()),
        "low": int((grades == "저위험").sum()),
    }

    dashboard = {
        "metadata": {
            "dataset": "UCI SECOM — team preprocessed Excel",
            "input_shape": [int(X.shape[0]), int(X.shape[1])],
            "input_sheet": args.sheet,
            "target_column": args.target,
            "validation": (
                f"stratified {args.outer_folds}-fold CV with "
                f"inner {args.inner_folds}-fold threshold tuning"
            ),
            "preprocessing_scope": "global_preprocessed_input",
            "strict_cv_preprocessing_from_raw": False,
            "evaluation_threshold_policy": "fold_specific_inner_oof_threshold",
            "deployment_threshold_policy": (
                "provisional median of fold-specific thresholds; stored full model requires "
                "external calibration before deployment"
            ),
            "score_type": (
                "within-fold relative risk percentile for ranking; raw model score is not "
                "a calibrated defect probability"
            ),
            "model_selection_rule": selection_rule,
            "threshold_rule": (
                f"각 fold 학습 데이터 내부 OOF에서 precision >= {args.precision_floor:.2f}인 "
                "임계값 중 recall 최대; 없으면 F2 최대"
            ),
            "risk_grade_rule": {
                "고위험": (
                    f"OOF 상대 위험 백분위 >= {HIGH_RISK_PERCENTILE:.0%}"
                ),
                "중위험": (
                    f"{MEDIUM_RISK_PERCENTILE:.0%} <= OOF 상대 위험 백분위 "
                    f"< {HIGH_RISK_PERCENTILE:.0%}"
                ),
                "저위험": (
                    f"OOF 상대 위험 백분위 < {MEDIUM_RISK_PERCENTILE:.0%}"
                ),
                "notice": "데모용 운영 등급이며 공정 비용 기반 검증 전 확정 기준이 아님",
            },
            "limitations": list(METHODOLOGICAL_LIMITATIONS),
        },
        "summary": {
            "총생산건수": int(len(y)),
            "불량건수": int(y.sum()),
            "불량률": float(y.mean()),
            "선정모델명": selected_spec.name,
            "선정임계값": deployment_threshold,
            "임계값용도": "임시 배포 참고값; OOF 혼동행렬은 fold별 임계값 사용",
            "고위험건수": risk_distribution["high"],
        },
        "selected_model_metrics": {
            "source": (
                "pooled OOF classification metrics; PR-AUC is the outer-fold mean "
                "shown in model_comparison"
            ),
            "recall": python_scalar(pooled_oof_metrics["recall"]),
            "recall_std": python_scalar(selected_row["recall_std"]),
            "precision": python_scalar(pooled_oof_metrics["precision"]),
            "precision_std": python_scalar(selected_row["precision_std"]),
            "f1": python_scalar(pooled_oof_metrics["f1"]),
            "f1_std": python_scalar(selected_row["f1_std"]),
            "pr_auc": python_scalar(selected_row["pr_auc"]),
            "pr_auc_std": python_scalar(selected_row["pr_auc_std"]),
            "balanced_accuracy": python_scalar(
                pooled_oof_metrics["balanced_accuracy"]
            ),
            "balanced_accuracy_std": python_scalar(
                selected_row["balanced_accuracy_std"]
            ),
        },
        "cv_fold_mean_metrics": {
            key: python_scalar(selected_row[key])
            for key in (
                "recall",
                "recall_std",
                "precision",
                "precision_std",
                "f1",
                "f1_std",
                "pr_auc",
                "pr_auc_std",
                "balanced_accuracy",
                "balanced_accuracy_std",
            )
        },
        "pooled_oof_metrics": {
            key: python_scalar(value) for key, value in pooled_oof_metrics.items()
        },
        "model_comparison": [
            {key: python_scalar(value) for key, value in row.items()}
            for row in comparison.to_dict(orient="records")
        ],
        "confusion_matrix": confusion,
        "confusion_matrix_policy": (
            "pooled OOF predicted classes; each row uses its outer fold's "
            "inner-OOF-selected threshold"
        ),
        "fold_thresholds": [
            {
                "fold": int(row.fold),
                "threshold": float(row.threshold),
                "inner_precision": python_scalar(row.inner_precision),
                "inner_recall": python_scalar(row.inner_recall),
            }
            for row in selected_folds[
                ["fold", "threshold", "inner_precision", "inner_recall"]
            ].itertuples(index=False)
        ],
        "provisional_deployment": {
            "binary_threshold": deployment_threshold,
            "full_model_grade_raw_score_cutoffs": final_model_grade_cutoffs,
            "notice": "외부 검증/확률 보정 전 임시 기준",
        },
        "inspection_strategies": strategies,
        "top20_capture_rate": float(top20["capture_rate"]),
        "top_features": top_features,
        "risk_items": risk_items,
        "risk_distribution": risk_distribution,
        "temporal_holdout": temporal,
        # 기존 Insight 프런트 호환용 시나리오 입력값이다. Detect 모델의
        # 예측·검증 결과가 아니며 Loop ESG 계약에는 근거/버전과 함께 별도로 둔다.
        "scenario_defaults": {
            "monthly_production": 10000,
            "rework_energy_kwh_per_defect": 12.0,
            "waste_kg_per_defect": 0.8,
            "unit_cost_krw": 50000,
            "action_success_rate": 0.60,
            "emission_factor_tco2eq_per_mwh": 0.4173,
            "disclaimer": "본 수치는 실제 감축 실적이 아니라 사용자 입력 조건에 따른 시나리오 분석 결과입니다.",
        },
    }

    oof = pd.DataFrame(
        {
            "id": ids,
            "row_index": np.arange(len(y)),
            "outer_fold": fold_assignment,
            "label": y,
            "selected_model": selected_spec.name,
            "selected_raw_model_score": selected_scores,
            "selected_relative_risk_percentile": risk_percentiles,
            "evaluation_threshold_used": evaluation_threshold_used,
            "selected_predicted_class": selected_predictions,
            "risk_rank": rank_numbers,
            "risk_grade_relative_percentile": grades,
        }
    )
    for code, spec in specs.items():
        oof[f"{code}_raw_model_score"] = all_scores[code]
        oof[f"{code}_predicted_class"] = all_predictions[code]
    oof = oof.sort_values("risk_rank")

    run_metadata = {
        "pipeline_version": PIPELINE_VERSION,
        "output_schema_version": OUTPUT_SCHEMA_VERSION,
        "python": sys.version,
        "platform": platform.platform(),
        "package_versions": package_versions(),
        "random_seed": args.seed,
        "precision_floor": args.precision_floor,
        "outer_folds": args.outer_folds,
        "inner_folds": args.inner_folds,
        "near_constant_ratio": args.near_constant_ratio,
        "models": list(args.models),
        "rf_trees": args.rf_trees,
        "boost_rounds": args.boost_rounds,
        "lightgbm_subsample_freq": 1,
        "input_file_name": args.input.name,
        "input_sha256": diagnostics["file_sha256"],
        "input_diagnostics": diagnostics,
        "selected_model": selected_spec.name,
        "provisional_deployment_threshold": deployment_threshold,
        "fold_thresholds": fold_threshold_map,
        "final_model_grade_raw_score_cutoffs": final_model_grade_cutoffs,
        "evaluation_threshold_policy": "fold_specific_inner_oof_threshold",
        "ranking_score_policy": "within_fold_percentile",
        "preprocessing_scope": "global_preprocessed_input",
        "strict_cv_preprocessing_from_raw": False,
        "shap_computed": not args.skip_shap,
        "temporal_holdout_computed": not args.no_time_holdout,
    }

    validate_artifact_contract(
        dashboard,
        oof,
        expected_rows=len(y),
        expected_folds=args.outer_folds,
    )

    write_json(args.output_dir / "dashboard_data.json", dashboard)
    write_json(args.output_dir / "run_metadata.json", run_metadata)
    fold_metrics.to_csv(args.output_dir / "fold_metrics.csv", index=False)
    comparison.to_csv(args.output_dir / "model_comparison.csv", index=False)
    oof.to_csv(args.output_dir / "oof_predictions.csv", index=False)
    pd.DataFrame(
        top_features,
        columns=["feature", "display_feature", "shap_value"],
    ).to_csv(
        args.output_dir / "top_features.csv", index=False
    )
    pd.DataFrame(risk_items).drop(columns=["top_factors"]).to_csv(
        args.output_dir / "risk_top30.csv", index=False
    )

    if temporal is not None:
        write_json(args.output_dir / "temporal_holdout.json", temporal)

    write_analysis_report(
        args.output_dir / "analysis_report.md",
        diagnostics=diagnostics,
        comparison=comparison,
        selected_name=selected_spec.name,
        selected_metrics=selected_row,
        pooled_metrics=pooled_oof_metrics,
        confusion=confusion,
        top20=top20,
        temporal=temporal,
        shap_enabled=not args.skip_shap,
        outer_folds=args.outer_folds,
    )

    LOGGER.info(
        "모델 비교\n%s",
        comparison[
            ["model", "recall", "precision", "f1", "pr_auc", "balanced_accuracy"]
        ].to_string(index=False),
    )
    LOGGER.info(
        "상위 %.0f%% 포착률: %d/%d (%.2f%%)",
        PRIMARY_INSPECTION_FRACTION * 100,
        top20["captured_defects"],
        top20["total_defects"],
        top20["capture_rate"] * 100,
    )
    LOGGER.info("결과 저장: %s", args.output_dir.resolve())


def main() -> None:
    configure_logging()
    run_analysis(parse_args())


if __name__ == "__main__":
    main()
