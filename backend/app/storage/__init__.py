"""Storage provider boundaries used by the backend."""

from app.storage.evidence import EvidenceStorage, LocalEvidenceStorage, StoredEvidence

__all__ = ["EvidenceStorage", "LocalEvidenceStorage", "StoredEvidence"]
