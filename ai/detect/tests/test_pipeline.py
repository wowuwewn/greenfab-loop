from __future__ import annotations

import os
from pathlib import Path
import hashlib
import json
import sys
import tempfile
from types import SimpleNamespace
import unittest

import numpy as np
import pandas as pd

TEST_DIR = Path(__file__).resolve().parent
DETECT_DIR = TEST_DIR.parent
REPOSITORY_ROOT = DETECT_DIR.parents[1]
sys.path.insert(0, str(DETECT_DIR))

import run_pipeline as pipeline  # noqa: E402


class PipelineUnitTests(unittest.TestCase):
    def test_committed_reference_dashboard_matches_golden_run(self) -> None:
        path = REPOSITORY_ROOT / "data" / "outputs" / "detect" / "dashboard_data.json"
        raw = path.read_bytes()
        self.assertEqual(
            hashlib.sha256(raw.rstrip(b"\n")).hexdigest(),
            "2d9f8dd5963d2804080ffbd83153ae604cd4430842721524e2e79fe2ece3813c",
        )
        dashboard = json.loads(raw)
        self.assertEqual(dashboard["summary"]["선정모델명"], "LightGBM")
        self.assertEqual(sum(dashboard["confusion_matrix"].values()), 1567)
        self.assertEqual(sum(dashboard["risk_distribution"].values()), 1567)
        self.assertEqual(len(dashboard["top_features"]), 15)
        self.assertEqual(len(dashboard["risk_items"]), 30)
        golden_case = next(
            item for item in dashboard["risk_items"] if item["id"] == "SECOM-0116"
        )
        self.assertEqual(golden_case["observed_label"], "불량")

    def test_normalize_target_accepts_supported_binary_encodings(self) -> None:
        np.testing.assert_array_equal(
            pipeline.normalize_target(pd.Series([0, 1, 0])),
            np.array([0, 1, 0]),
        )
        np.testing.assert_array_equal(
            pipeline.normalize_target(pd.Series([-1, 1, -1])),
            np.array([0, 1, 0]),
        )
        np.testing.assert_array_equal(
            pipeline.normalize_target(pd.Series(["정상", "불량", "정상"])),
            np.array([0, 1, 0]),
        )

    def test_fold_preprocessor_fits_feature_filter_on_training_rows(self) -> None:
        X_train = np.array(
            [
                [1.0, 0.0, 5.0],
                [1.0, 1.0, 5.0],
                [1.0, 2.0, 5.0],
                [1.0, 3.0, 5.0],
            ]
        )
        preprocessor = pipeline.FoldPreprocessor.fit(
            X_train,
            scale=False,
            near_constant_ratio=0.999,
        )
        np.testing.assert_array_equal(
            preprocessor.original_feature_indices,
            np.array([1]),
        )
        transformed = preprocessor.transform(np.array([[1.0, 10.0, 5.0]]))
        np.testing.assert_array_equal(transformed, np.array([[10.0]]))

    def test_threshold_respects_precision_floor(self) -> None:
        y = np.array([0, 0, 1, 1])
        scores = np.array([0.10, 0.20, 0.70, 0.80])
        threshold, info = pipeline.choose_threshold(y, scores, 0.50)
        self.assertGreaterEqual(info["inner_precision"], 0.50)
        self.assertEqual(info["inner_recall"], 1.0)
        self.assertAlmostEqual(threshold, 0.70)

    def test_fold_normalized_percentile_is_computed_within_each_fold(self) -> None:
        values = pipeline.fold_normalized_percentile(
            np.array([0.1, 0.2, 0.3, 0.4]),
            np.array([1, 1, 2, 2]),
        )
        np.testing.assert_array_equal(values, np.array([0.5, 1.0, 0.5, 1.0]))

    def test_model_selection_uses_predeclared_precision_floor(self) -> None:
        comparison = pd.DataFrame(
            [
                {
                    "model_code": "xgb",
                    "recall": 0.80,
                    "precision": 0.14,
                    "f2": 0.50,
                    "pr_auc": 0.30,
                },
                {
                    "model_code": "lgbm",
                    "recall": 0.50,
                    "precision": 0.16,
                    "f2": 0.40,
                    "pr_auc": 0.20,
                },
            ]
        )
        selected, rule = pipeline.select_model(comparison, 0.15)
        self.assertEqual(selected, "lgbm")
        self.assertIn("precision", rule.lower())

    def test_lightgbm_reference_subsampling_is_not_silently_disabled(self) -> None:
        args = SimpleNamespace(
            models=["lgbm"],
            boost_rounds=350,
            rf_trees=350,
        )
        spec = pipeline.build_model_specs(args)["lgbm"]
        model = spec.factory(np.array([0, 0, 1]), 42)
        parameters = model.get_params()
        self.assertEqual(parameters["subsample"], 0.85)
        self.assertEqual(parameters["subsample_freq"], 1)

    def test_artifact_contract_rejects_inconsistent_totals(self) -> None:
        dashboard = {
            "confusion_matrix": {"tp": 1, "fp": 1, "fn": 1, "tn": 1},
            "risk_distribution": {"high": 2, "medium": 1, "low": 1},
            "fold_thresholds": [{"fold": 1}, {"fold": 2}],
            "top_features": [],
            "risk_items": [],
        }
        oof = pd.DataFrame({"row": [0, 1, 2, 3]})
        pipeline.validate_artifact_contract(
            dashboard,
            oof,
            expected_rows=4,
            expected_folds=2,
        )
        dashboard["risk_distribution"]["low"] = 0
        with self.assertRaisesRegex(ValueError, "위험 등급 합계"):
            pipeline.validate_artifact_contract(
                dashboard,
                oof,
                expected_rows=4,
                expected_folds=2,
            )

    def test_load_excel_validates_shape_labels_and_hash(self) -> None:
        frame = pd.DataFrame(
            {
                "result": [0, 1, 0, 1],
                "Sensor0": [1.0, 2.0, 3.0, 4.0],
                "Sensor1": [4.0, 3.0, 2.0, 1.0],
            }
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "fixture.xlsx"
            frame.to_excel(path, sheet_name="SECOM_Data", index=False)
            X, y, names, _, diagnostics = pipeline.load_excel(
                path,
                "SECOM_Data",
                "result",
            )
        self.assertEqual(X.shape, (4, 2))
        np.testing.assert_array_equal(y, np.array([0, 1, 0, 1]))
        self.assertEqual(names, ["Sensor0", "Sensor1"])
        self.assertEqual(diagnostics["missing_cells"], 0)
        self.assertEqual(len(diagnostics["file_sha256"]), 64)

    @unittest.skipUnless(os.getenv("SECOM_XLSX"), "SECOM_XLSX not set")
    def test_team_excel_matches_reference_contract(self) -> None:
        path = Path(os.environ["SECOM_XLSX"])
        X, y, names, _, diagnostics = pipeline.load_excel(
            path,
            "SECOM_Data",
            "result",
        )
        self.assertEqual(X.shape, (1567, 446))
        self.assertEqual(int(y.sum()), 104)
        self.assertEqual(len(names), 446)
        self.assertEqual(
            diagnostics["file_sha256"],
            "196cea8a01998f0d951e1d76a94f5561b778833ac907d186bc8a90078aa1f377",
        )


if __name__ == "__main__":
    unittest.main()
