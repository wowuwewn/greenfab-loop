"""Storage provider boundaries used by the backend."""

from app.storage.evidence import (
    EvidenceStorage,
    LocalEvidenceStorage,
    S3EvidenceStorage,
    StoredEvidence,
    build_evidence_storage,
)

__all__ = [
    "EvidenceStorage",
    "LocalEvidenceStorage",
    "S3EvidenceStorage",
    "StoredEvidence",
    "build_evidence_storage",
]
