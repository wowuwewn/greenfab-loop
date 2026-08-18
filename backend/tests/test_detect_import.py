from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.enums import SourceType, WorkflowStatus
from app.errors import DomainError
from app.models import AuditEvent, Case, DetectImport
from app.services.detect_import import import_detect_artifact


def _artifact(*, first_rank: int = 1) -> dict:
    return {
        "metadata": {
            "dataset": "contract-test dataset",
            "validation": "stratified outer CV",
            "score_type": "within-fold relative risk percentile",
            "input_shape": [2, 3],
            "untrusted_extra": "not persisted",
        },
        "summary": {
            "선정모델명": "LightGBM",
            "총생산건수": 2,
            "untrusted_path": "/Users/example/private",
        },
        "selected_model_metrics": {
            "recall": 0.5,
            "precision": 0.2,
            "untrusted_metric": "not persisted",
        },
        "risk_items": [
            {
                "id": "LINE-0001",
                "risk_score": 0.95,
                "risk_score_type": "within-fold relative risk percentile",
                "risk_rank": first_rank,
                "top_factors": [
                    {"feature": "Sensor1", "contribution": 0.25, "feature_value": 12.0}
                ],
            },
            {
                "id": "LINE-0002",
                "risk_score": 0.75,
                "risk_score_type": "within-fold relative risk percentile",
                "risk_rank": 2,
                "top_factors": [{"feature": "Sensor2", "contribution": -0.1}],
            },
        ],
    }


def _write_artifact(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_detect_import_is_idempotent_and_records_safe_provenance(session_factory, tmp_path) -> None:
    artifact_path = tmp_path / "dashboard_data.json"
    _write_artifact(artifact_path, _artifact())

    with session_factory.begin() as session:
        first = import_detect_artifact(
            session,
            artifact_path,
            source_type=SourceType.REAL,
            actor="pipeline_operator",
        )
    assert first.created is True
    assert first.created_case_count == 2
    assert first.updated_case_count == 0

    with session_factory.begin() as session:
        repeated = import_detect_artifact(
            session,
            artifact_path,
            source_type=SourceType.REAL,
            actor="pipeline_operator",
        )
    assert repeated.created is False
    assert repeated.created_case_count == 0
    assert repeated.unchanged_case_count == 2
    assert repeated.detect_import_id == first.detect_import_id

    with session_factory.begin() as session:
        with pytest.raises(DomainError) as conflict:
            import_detect_artifact(
                session,
                artifact_path,
                source_type=SourceType.DEMO,
                actor="pipeline_operator",
            )
    assert conflict.value.code == "DETECT_IMPORT_SOURCE_CONFLICT"

    with session_factory() as session:
        assert session.scalar(select(func.count(DetectImport.detect_import_id))) == 1
        line_case = session.get(Case, "LINE-0001")
        assert line_case is not None
        assert line_case.workflow_status is WorkflowStatus.CONFIRMATION_PENDING
        assert line_case.resource_confirmation is not None
        assert line_case.resource_confirmation.source_type is SourceType.DEMO
        assert line_case.shap_top_features == [{"feature_name": "Sensor1", "shap_value": 0.25}]
        detect_import = session.get(DetectImport, first.detect_import_id)
        assert detect_import is not None
        assert "untrusted_extra" not in detect_import.provenance_json["metadata"]
        assert "untrusted_path" not in detect_import.provenance_json["summary"]
        assert "untrusted_metric" not in detect_import.provenance_json["selected_model_metrics"]
        assert str(tmp_path) not in json.dumps(detect_import.provenance_json)
        event_count = session.scalar(
            select(func.count(AuditEvent.audit_event_id)).where(
                AuditEvent.case_id.in_(["LINE-0001", "LINE-0002"])
            )
        )
        assert event_count == 2


def test_new_detect_artifact_updates_detect_fields_without_reopening_workflow(
    session_factory, tmp_path
) -> None:
    first_path = tmp_path / "first.json"
    second_path = tmp_path / "second.json"
    _write_artifact(first_path, _artifact(first_rank=1))
    _write_artifact(second_path, _artifact(first_rank=7))

    with session_factory.begin() as session:
        import_detect_artifact(session, first_path, actor="pipeline_operator")
    with session_factory.begin() as session:
        record = session.get(Case, "LINE-0001")
        assert record is not None
        record.workflow_status = WorkflowStatus.CLOSED

    with session_factory.begin() as session:
        result = import_detect_artifact(session, second_path, actor="pipeline_operator")
    assert result.created is True
    assert result.updated_case_count == 2

    with session_factory() as session:
        record = session.get(Case, "LINE-0001")
        assert record is not None
        assert record.risk_rank == 7
        assert record.workflow_status is WorkflowStatus.CLOSED
        assert session.scalar(select(func.count(DetectImport.detect_import_id))) == 2


def test_detect_import_rejects_invalid_or_oversized_artifact(session_factory, tmp_path) -> None:
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{}", encoding="utf-8")
    with session_factory.begin() as session:
        with pytest.raises(DomainError, match="dashboard_data.json"):
            import_detect_artifact(session, invalid)

    oversized = tmp_path / "oversized.json"
    oversized.write_text("{}", encoding="utf-8")
    with session_factory.begin() as session:
        with pytest.raises(DomainError) as error:
            import_detect_artifact(session, oversized, max_bytes=1)
    assert error.value.code == "DETECT_ARTIFACT_SIZE_INVALID"

    nonfinite = tmp_path / "nonfinite.json"
    payload = _artifact()
    payload["risk_items"][0]["top_factors"][0]["contribution"] = float("nan")
    _write_artifact(nonfinite, payload)
    with session_factory.begin() as session:
        with pytest.raises(DomainError) as error:
            import_detect_artifact(session, nonfinite)
    assert error.value.code == "INVALID_DETECT_ARTIFACT"
