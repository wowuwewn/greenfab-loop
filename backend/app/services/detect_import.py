"""Import a verified Detect dashboard artifact into workflow Cases."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import ResourceConfirmationStatus, SourceType, WorkflowStatus
from app.errors import DomainError
from app.models import AuditEvent, Case, DetectImport, ResourceConfirmation
from app.schemas import DetectImportOut


class _ArtifactFactor(BaseModel):
    model_config = ConfigDict(extra="ignore", allow_inf_nan=False, str_strip_whitespace=True)

    feature: str = Field(min_length=1, max_length=255)
    contribution: float


class _ArtifactRiskItem(BaseModel):
    model_config = ConfigDict(extra="ignore", allow_inf_nan=False, str_strip_whitespace=True)

    id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._:-]+$")
    risk_score: float = Field(ge=0, le=1)
    risk_score_type: str = Field(min_length=1, max_length=500)
    risk_rank: int = Field(ge=1)
    top_factors: list[_ArtifactFactor] = Field(default_factory=list, max_length=20)


class _DashboardArtifact(BaseModel):
    model_config = ConfigDict(extra="ignore")

    metadata: dict[str, Any]
    summary: dict[str, Any]
    selected_model_metrics: dict[str, Any] = Field(default_factory=dict)
    risk_items: list[_ArtifactRiskItem] = Field(min_length=1, max_length=100_000)

    @model_validator(mode="after")
    def validate_unique_cases(self) -> _DashboardArtifact:
        case_ids = [item.id for item in self.risk_items]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("risk_items must contain unique case ids")
        return self


_SAFE_METADATA_KEYS = (
    "dataset",
    "input_shape",
    "input_sheet",
    "target_column",
    "validation",
    "preprocessing_scope",
    "strict_cv_preprocessing_from_raw",
    "evaluation_threshold_policy",
    "deployment_threshold_policy",
    "score_type",
    "model_selection_rule",
    "threshold_rule",
    "risk_grade_rule",
    "limitations",
)
_SAFE_SUMMARY_KEYS = (
    "선정모델명",
    "총생산건수",
    "불량건수",
    "불량률",
    "고위험건수",
    "선정임계값",
    "임계값용도",
)
_SAFE_METRIC_KEYS = (
    "balanced_accuracy",
    "balanced_accuracy_std",
    "f1",
    "f1_std",
    "pr_auc",
    "pr_auc_std",
    "precision",
    "precision_std",
    "recall",
    "recall_std",
    "source",
)


def import_detect_artifact(
    session: Session,
    artifact_path: Path,
    *,
    source_type: SourceType = SourceType.REAL,
    actor: str = "detect_import_cli",
    max_bytes: int = 20 * 1024 * 1024,
) -> DetectImportOut:
    """Validate and idempotently upsert Cases from dashboard_data.json.

    A file hash identifies the immutable import run. Re-importing the same bytes
    revalidates and reconciles Case detect fields without duplicating the import
    row or audit events for unchanged Cases. Existing workflow progress and all
    human-entered records are preserved.
    """

    if source_type not in {SourceType.REAL, SourceType.DEMO}:
        raise DomainError("INVALID_SOURCE_TYPE", "Detect import는 REAL 또는 DEMO여야 합니다.", 422)
    actor = actor.strip()
    if not actor or len(actor) > 255:
        raise DomainError("INVALID_ACTOR", "Import actor는 1~255자여야 합니다.", 422)

    raw = _read_artifact(artifact_path, max_bytes=max_bytes)
    artifact_sha256 = hashlib.sha256(raw).hexdigest()
    try:
        parsed_json = json.loads(raw, parse_constant=_reject_nonfinite_json)
        artifact = _DashboardArtifact.model_validate(parsed_json)
    except (json.JSONDecodeError, ValueError) as exc:
        raise DomainError(
            "INVALID_DETECT_ARTIFACT",
            "Detect artifact가 dashboard_data.json 계약과 맞지 않습니다.",
            422,
        ) from exc

    dataset_name = _required_text(artifact.metadata.get("dataset"), "metadata.dataset")
    model_name = _required_text(artifact.summary.get("선정모델명"), "summary.선정모델명")
    artifact_name = artifact_path.name[:255] or "dashboard_data.json"
    model_revision = f"artifact-sha256:{artifact_sha256}"
    provenance = {
        "artifact_sha256": artifact_sha256,
        "metadata": {
            key: artifact.metadata[key] for key in _SAFE_METADATA_KEYS if key in artifact.metadata
        },
        "summary": {
            key: artifact.summary[key] for key in _SAFE_SUMMARY_KEYS if key in artifact.summary
        },
        "selected_model_metrics": {
            key: artifact.selected_model_metrics[key]
            for key in _SAFE_METRIC_KEYS
            if key in artifact.selected_model_metrics
        },
    }

    detect_import = session.scalar(
        select(DetectImport).where(DetectImport.artifact_sha256 == artifact_sha256)
    )
    created_import = detect_import is None
    if detect_import is not None and detect_import.source_type is not source_type:
        raise DomainError(
            "DETECT_IMPORT_SOURCE_CONFLICT",
            "같은 Detect artifact를 다른 source_type으로 다시 등록할 수 없습니다.",
            409,
        )
    if detect_import is None:
        detect_import = DetectImport(
            artifact_sha256=artifact_sha256,
            artifact_name=artifact_name,
            dataset_name=dataset_name,
            model_name=model_name,
            model_revision=model_revision,
            validation_method=_optional_text(artifact.metadata.get("validation")),
            score_type=_optional_text(artifact.metadata.get("score_type")),
            source_type=source_type,
            case_count=len(artifact.risk_items),
            provenance_json=provenance,
            imported_by=actor,
        )
        session.add(detect_import)
        session.flush()

    created_cases = 0
    updated_cases = 0
    unchanged_cases = 0
    for item in artifact.risk_items:
        shap_features = [
            {"feature_name": factor.feature, "shap_value": factor.contribution}
            for factor in item.top_factors
        ]
        record = session.get(Case, item.id)
        if record is None:
            record = Case(
                case_id=item.id,
                risk_rank=item.risk_rank,
                risk_score=item.risk_score,
                risk_score_type=item.risk_score_type,
                shap_top_features=shap_features,
                source_type=source_type,
                workflow_status=WorkflowStatus.CONFIRMATION_PENDING,
                detect_import_id=detect_import.detect_import_id,
            )
            record.resource_confirmation = ResourceConfirmation(
                status=ResourceConfirmationStatus.PENDING,
                confirmed_by=None,
                confirmed_at=None,
                source_type=SourceType.DEMO,
            )
            record.audit_events.append(
                AuditEvent(
                    event_type="CASE_IMPORTED_FROM_DETECT",
                    actor=actor,
                    from_status=WorkflowStatus.DETECTED,
                    to_status=WorkflowStatus.CONFIRMATION_PENDING,
                    payload_json={
                        "detect_import_id": detect_import.detect_import_id,
                        "artifact_sha256": artifact_sha256,
                        "model_name": model_name,
                        "model_revision": model_revision,
                    },
                )
            )
            session.add(record)
            created_cases += 1
            continue

        changed = any(
            (
                record.risk_rank != item.risk_rank,
                record.risk_score != item.risk_score,
                record.risk_score_type != item.risk_score_type,
                record.shap_top_features != shap_features,
                record.source_type != source_type,
                record.detect_import_id != detect_import.detect_import_id,
            )
        )
        if not changed:
            unchanged_cases += 1
            continue

        previous_detect_import_id = record.detect_import_id
        previous_risk_rank = record.risk_rank
        previous_risk_score = record.risk_score
        record.risk_rank = item.risk_rank
        record.risk_score = item.risk_score
        record.risk_score_type = item.risk_score_type
        record.shap_top_features = shap_features
        record.source_type = source_type
        record.detect_import_id = detect_import.detect_import_id
        if record.resource_confirmation is None:
            if record.workflow_status not in {
                WorkflowStatus.DETECTED,
                WorkflowStatus.CONFIRMATION_PENDING,
            }:
                raise DomainError(
                    "DETECT_CASE_INTEGRITY_ERROR",
                    "진행 중인 Case에 Resource Confirmation이 없어 "
                    "Detect 결과를 갱신할 수 없습니다.",
                    409,
                )
            record.resource_confirmation = ResourceConfirmation(
                status=ResourceConfirmationStatus.PENDING,
                source_type=SourceType.DEMO,
            )
            record.workflow_status = WorkflowStatus.CONFIRMATION_PENDING
        record.audit_events.append(
            AuditEvent(
                event_type="DETECT_RESULT_UPDATED",
                actor=actor,
                from_status=record.workflow_status,
                to_status=record.workflow_status,
                payload_json={
                    "detect_import_id": detect_import.detect_import_id,
                    "previous_detect_import_id": previous_detect_import_id,
                    "artifact_sha256": artifact_sha256,
                    "model_name": model_name,
                    "model_revision": model_revision,
                    "previous_risk_rank": previous_risk_rank,
                    "previous_risk_score": previous_risk_score,
                },
            )
        )
        updated_cases += 1

    session.flush()
    return DetectImportOut(
        detect_import_id=detect_import.detect_import_id,
        artifact_sha256=detect_import.artifact_sha256,
        artifact_name=detect_import.artifact_name,
        dataset_name=detect_import.dataset_name,
        model_name=detect_import.model_name,
        model_revision=detect_import.model_revision,
        source_type=detect_import.source_type,
        case_count=len(artifact.risk_items),
        created_case_count=created_cases,
        updated_case_count=updated_cases,
        unchanged_case_count=unchanged_cases,
        created=created_import,
    )


def _read_artifact(path: Path, *, max_bytes: int) -> bytes:
    try:
        stat = path.stat()
    except OSError as exc:
        raise DomainError(
            "DETECT_ARTIFACT_NOT_FOUND", "Detect artifact를 읽을 수 없습니다.", 404
        ) from exc
    if not path.is_file():
        raise DomainError("DETECT_ARTIFACT_NOT_FOUND", "Detect artifact 파일이 아닙니다.", 404)
    if stat.st_size <= 0 or stat.st_size > max_bytes:
        raise DomainError(
            "DETECT_ARTIFACT_SIZE_INVALID",
            f"Detect artifact는 1~{max_bytes} bytes여야 합니다.",
            422,
        )
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise DomainError(
            "DETECT_ARTIFACT_NOT_FOUND", "Detect artifact를 읽을 수 없습니다.", 404
        ) from exc
    if not raw or len(raw) > max_bytes:
        raise DomainError(
            "DETECT_ARTIFACT_SIZE_INVALID",
            f"Detect artifact는 1~{max_bytes} bytes여야 합니다.",
            422,
        )
    return raw


def _required_text(value: object, field_name: str) -> str:
    text = _optional_text(value)
    if text is None:
        raise DomainError(
            "INVALID_DETECT_ARTIFACT",
            f"Detect artifact의 {field_name} 필드가 필요합니다.",
            422,
        )
    return text[:255]


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _reject_nonfinite_json(value: str) -> None:
    raise ValueError(f"non-finite JSON number is not allowed: {value}")
