"""Safe, replaceable binary storage for Passport evidence attachments."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Protocol, runtime_checkable
from uuid import uuid4

from app.errors import DomainError


@dataclass(frozen=True, slots=True)
class StoredEvidence:
    storage_key: str
    size_bytes: int
    sha256: str


@runtime_checkable
class EvidenceStorage(Protocol):
    def save(self, stream: BinaryIO, *, media_type: str, max_bytes: int) -> StoredEvidence: ...

    def resolve(self, storage_key: str) -> Path: ...

    def delete(self, storage_key: str) -> None: ...

    def check_ready(self) -> None: ...


_MEDIA_EXTENSIONS = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
}


class LocalEvidenceStorage:
    """Local-development storage with generated keys and containment checks.

    User filenames are never used as paths. Production deployments should
    replace this provider with managed object storage and malware scanning.
    """

    def __init__(self, root: Path | str):
        self.root = Path(root).expanduser().resolve()

    def save(self, stream: BinaryIO, *, media_type: str, max_bytes: int) -> StoredEvidence:
        normalized_media_type = media_type.split(";", 1)[0].strip().casefold()
        extension = _MEDIA_EXTENSIONS.get(normalized_media_type)
        if extension is None:
            raise DomainError(
                "EVIDENCE_TYPE_NOT_ALLOWED",
                "Evidence는 PDF, JPEG 또는 PNG만 업로드할 수 있습니다.",
                422,
            )

        identifier = uuid4().hex
        storage_key = f"{identifier[:2]}/{identifier}{extension}"
        destination = self._contained_path(storage_key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(f"{destination.suffix}.{uuid4().hex}.part")
        digest = hashlib.sha256()
        size_bytes = 0
        first_bytes = bytearray()
        try:
            with temporary.open("xb") as handle:
                while True:
                    chunk = stream.read(64 * 1024)
                    if not chunk:
                        break
                    if not isinstance(chunk, bytes):
                        raise DomainError(
                            "INVALID_EVIDENCE_FILE", "Evidence binary stream이 필요합니다.", 422
                        )
                    size_bytes += len(chunk)
                    if size_bytes > max_bytes:
                        raise DomainError(
                            "EVIDENCE_TOO_LARGE",
                            f"Evidence 크기는 {max_bytes} bytes 이하여야 합니다.",
                            413,
                        )
                    if len(first_bytes) < 16:
                        first_bytes.extend(chunk[: 16 - len(first_bytes)])
                    digest.update(chunk)
                    handle.write(chunk)
            if size_bytes == 0:
                raise DomainError("EMPTY_EVIDENCE", "빈 Evidence 파일은 업로드할 수 없습니다.", 422)
            if not _signature_matches(normalized_media_type, bytes(first_bytes)):
                raise DomainError(
                    "EVIDENCE_CONTENT_MISMATCH",
                    "파일 내용이 선언된 Content-Type과 일치하지 않습니다.",
                    422,
                )
            os.replace(temporary, destination)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        return StoredEvidence(
            storage_key=storage_key,
            size_bytes=size_bytes,
            sha256=digest.hexdigest(),
        )

    def resolve(self, storage_key: str) -> Path:
        path = self._contained_path(storage_key)
        if not path.is_file():
            raise DomainError(
                "EVIDENCE_CONTENT_NOT_FOUND", "Evidence 파일을 찾을 수 없습니다.", 404
            )
        return path

    def delete(self, storage_key: str) -> None:
        self._contained_path(storage_key).unlink(missing_ok=True)

    def check_ready(self) -> None:
        try:
            self.root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise DomainError(
                "EVIDENCE_STORAGE_UNAVAILABLE", "Evidence storage를 사용할 수 없습니다.", 503
            ) from exc
        if not os.access(self.root, os.R_OK | os.W_OK | os.X_OK):
            raise DomainError(
                "EVIDENCE_STORAGE_UNAVAILABLE", "Evidence storage를 사용할 수 없습니다.", 503
            )

    def _contained_path(self, storage_key: str) -> Path:
        pure_key = PurePosixPath(storage_key)
        if pure_key.is_absolute() or ".." in pure_key.parts or len(pure_key.parts) != 2:
            raise DomainError(
                "INVALID_STORAGE_KEY", "Evidence storage key가 올바르지 않습니다.", 500
            )
        candidate = (self.root / Path(*pure_key.parts)).resolve()
        if not candidate.is_relative_to(self.root):
            raise DomainError(
                "INVALID_STORAGE_KEY", "Evidence storage key가 올바르지 않습니다.", 500
            )
        return candidate


def _signature_matches(media_type: str, content: bytes) -> bool:
    if media_type == "application/pdf":
        return content.startswith(b"%PDF-")
    if media_type == "image/png":
        return content.startswith(b"\x89PNG\r\n\x1a\n")
    if media_type == "image/jpeg":
        return content.startswith(b"\xff\xd8\xff")
    return False
