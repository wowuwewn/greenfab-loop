"""Passport evidence metadata and storage orchestration."""

from __future__ import annotations

import hashlib
import hmac
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import PurePath
from tempfile import SpooledTemporaryFile
from typing import BinaryIO

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import EvidenceType, WorkflowStatus
from app.errors import DomainError
from app.models import AuditEvent, Case, PassportEvidence, ResourcePassport
from app.schemas import PassportEvidenceOut
from app.services.workflow import get_case, get_case_for_update
from app.storage import EvidenceStorage, StoredEvidence

logger = logging.getLogger(__name__)


def preflight_passport_evidence_target(session: Session, case_id: str) -> None:
    """Reject an invalid target before performing object-storage I/O."""

    _passport_evidence_target(session, case_id, for_update=False)


def attach_passport_evidence(
    session: Session,
    case_id: str,
    *,
    stored: StoredEvidence,
    filename: str | None,
    media_type: str | None,
    evidence_type: EvidenceType,
    description: str | None,
    actor: str,
    trace_id: str | None,
) -> PassportEvidence:
    record, passport = _passport_evidence_target(session, case_id, for_update=True)

    safe_filename = _safe_filename(filename)
    normalized_media_type = (media_type or "").split(";", 1)[0].strip().casefold()
    evidence = PassportEvidence(
        passport_id=passport.passport_id,
        storage_key=stored.storage_key,
        original_filename=safe_filename,
        media_type=normalized_media_type,
        size_bytes=stored.size_bytes,
        sha256=stored.sha256,
        evidence_type=evidence_type,
        description=_optional_trimmed(description),
        source_type=passport.source_type,
        uploaded_by=actor,
    )
    session.add(evidence)
    session.flush()
    session.add(
        AuditEvent(
            case_id=case_id,
            event_type="PASSPORT_EVIDENCE_ADDED",
            actor=actor,
            from_status=record.workflow_status,
            to_status=record.workflow_status,
            payload_json={
                "evidence_id": evidence.evidence_id,
                "evidence_type": evidence_type.value,
                "media_type": normalized_media_type,
                "size_bytes": stored.size_bytes,
                "sha256": stored.sha256,
            },
            trace_id=trace_id,
        )
    )
    session.flush()
    return evidence


def _passport_evidence_target(
    session: Session,
    case_id: str,
    *,
    for_update: bool,
) -> tuple[Case, ResourcePassport]:
    record = get_case_for_update(session, case_id) if for_update else get_case(session, case_id)
    if record.workflow_status not in {WorkflowStatus.PASSPORT_READY, WorkflowStatus.MATCH_READY}:
        raise DomainError(
            "INVALID_STATE",
            "Passport 저장 후 Decision 전까지만 Evidence를 추가할 수 있습니다.",
            409,
        )
    passport = record.resource_passport
    if passport is None:
        raise DomainError("INVALID_STATE", "저장된 Passport가 없습니다.", 409)
    return record, passport


@contextmanager
def open_verified_evidence(
    storage: EvidenceStorage,
    *,
    storage_key: str,
    expected_size: int,
    expected_sha256: str,
) -> Iterator[BinaryIO]:
    """Verify a bounded object completely before returning any response bytes."""

    hard_limit = 25 * 1024 * 1024
    if expected_size < 1 or expected_size > hard_limit:
        raise DomainError(
            "EVIDENCE_INTEGRITY_FAILED",
            "Evidence 무결성을 확인할 수 없습니다.",
            503,
        )
    digest = hashlib.sha256()
    actual_size = 0
    try:
        with (
            storage.open(storage_key) as source,
            SpooledTemporaryFile(max_size=min(expected_size, 1024 * 1024), mode="w+b") as verified,
        ):
            while True:
                chunk = source.read(64 * 1024)
                if not chunk:
                    break
                if not isinstance(chunk, bytes):
                    raise DomainError(
                        "EVIDENCE_INTEGRITY_FAILED",
                        "Evidence 무결성을 확인할 수 없습니다.",
                        503,
                    )
                actual_size += len(chunk)
                if actual_size > expected_size:
                    raise DomainError(
                        "EVIDENCE_INTEGRITY_FAILED",
                        "Evidence 무결성을 확인할 수 없습니다.",
                        503,
                    )
                digest.update(chunk)
                verified.write(chunk)
            if actual_size != expected_size or not hmac.compare_digest(
                digest.hexdigest(), expected_sha256
            ):
                raise DomainError(
                    "EVIDENCE_INTEGRITY_FAILED",
                    "Evidence 무결성을 확인할 수 없습니다.",
                    503,
                )
            verified.seek(0)
            yield verified
    except DomainError:
        raise
    except Exception as exc:
        raise DomainError(
            "EVIDENCE_STORAGE_UNAVAILABLE",
            "Evidence storage에서 파일을 읽을 수 없습니다.",
            503,
        ) from exc


def evidence_storage_keys_for_case(session: Session, case_id: str) -> list[str]:
    return list(
        session.scalars(
            select(PassportEvidence.storage_key)
            .join(ResourcePassport, PassportEvidence.passport_id == ResourcePassport.passport_id)
            .where(ResourcePassport.case_id == case_id)
        ).all()
    )


def delete_evidence_safely(storage: EvidenceStorage, storage_key: str) -> None:
    """Best-effort compensation without masking the original DB/API result."""

    try:
        storage.delete(storage_key)
    except Exception as exc:
        logger.error(
            "Evidence cleanup failed storage_key=%s error_type=%s",
            storage_key,
            type(exc).__name__,
        )


def list_passport_evidence(session: Session, case_id: str) -> list[PassportEvidenceOut]:
    _get_passport_for_case(session, case_id)
    records = session.scalars(
        select(PassportEvidence)
        .join(ResourcePassport, PassportEvidence.passport_id == ResourcePassport.passport_id)
        .where(ResourcePassport.case_id == case_id)
        .order_by(PassportEvidence.created_at.asc(), PassportEvidence.evidence_id.asc())
    ).all()
    return [to_evidence_out(record) for record in records]


def get_passport_evidence(session: Session, case_id: str, evidence_id: str) -> PassportEvidence:
    _get_passport_for_case(session, case_id)
    evidence = session.scalar(
        select(PassportEvidence)
        .join(ResourcePassport, PassportEvidence.passport_id == ResourcePassport.passport_id)
        .where(
            ResourcePassport.case_id == case_id,
            PassportEvidence.evidence_id == evidence_id,
        )
    )
    if evidence is None:
        raise DomainError("EVIDENCE_NOT_FOUND", "Passport Evidence를 찾을 수 없습니다.", 404)
    return evidence


def to_evidence_out(record: PassportEvidence) -> PassportEvidenceOut:
    return PassportEvidenceOut(
        evidence_id=record.evidence_id,
        passport_id=record.passport_id,
        original_filename=record.original_filename,
        media_type=record.media_type,
        size_bytes=record.size_bytes,
        sha256=record.sha256,
        evidence_type=record.evidence_type,
        description=record.description,
        source_type=record.source_type,
        uploaded_by=record.uploaded_by,
        created_at=record.created_at,
    )


def _get_passport_for_case(session: Session, case_id: str) -> ResourcePassport:
    passport = session.scalar(select(ResourcePassport).where(ResourcePassport.case_id == case_id))
    if passport is None:
        raise DomainError("PASSPORT_NOT_FOUND", "Resource Passport를 찾을 수 없습니다.", 404)
    return passport


def _safe_filename(filename: str | None) -> str:
    normalized = (filename or "upload").replace("\\", "/")
    basename = PurePath(normalized).name
    basename = "".join(character for character in basename if character.isprintable()).strip()
    if not basename:
        basename = "upload"
    return basename[:255]


def _optional_trimmed(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None
