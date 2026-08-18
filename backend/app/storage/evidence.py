"""Safe, replaceable binary storage for Passport evidence attachments."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from tempfile import SpooledTemporaryFile
from threading import Lock
from typing import TYPE_CHECKING, Any, BinaryIO, Protocol, runtime_checkable
from uuid import uuid4

from app.errors import DomainError

if TYPE_CHECKING:
    from app.config import Settings


@dataclass(frozen=True, slots=True)
class StoredEvidence:
    storage_key: str
    size_bytes: int
    sha256: str


@runtime_checkable
class EvidenceStorage(Protocol):
    def save(self, stream: BinaryIO, *, media_type: str, max_bytes: int) -> StoredEvidence: ...

    def open(self, storage_key: str) -> AbstractContextManager[BinaryIO]: ...

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
        normalized_media_type, storage_key = _new_storage_key(media_type)
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

    @contextmanager
    def open(self, storage_key: str) -> Iterator[BinaryIO]:
        path = self.resolve(storage_key)
        with path.open("rb") as handle:
            yield handle

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


class S3EvidenceStorage:
    """S3-compatible Evidence storage for AWS S3, Cloudflare R2, and peers.

    The database stores only generated relative keys. Bucket, endpoint, and
    credentials are configuration, never request data or committed source.
    """

    def __init__(
        self,
        *,
        bucket: str,
        prefix: str = "greenfab/evidence",
        region: str | None = None,
        endpoint_url: str | None = None,
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
        session_token: str | None = None,
        addressing_style: str = "auto",
        connect_timeout_seconds: int = 3,
        read_timeout_seconds: int = 10,
        max_attempts: int = 2,
        client: Any | None = None,
    ) -> None:
        self.bucket = bucket.strip()
        self.prefix = prefix.strip().strip("/")
        self._ready_lock = Lock()
        self._permissions_verified = False
        if not self.bucket:
            raise ValueError("S3 bucket is required")
        self._client = client or self._build_client(
            region=region,
            endpoint_url=endpoint_url,
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
            session_token=session_token,
            addressing_style=addressing_style,
            connect_timeout_seconds=connect_timeout_seconds,
            read_timeout_seconds=read_timeout_seconds,
            max_attempts=max_attempts,
        )

    def save(self, stream: BinaryIO, *, media_type: str, max_bytes: int) -> StoredEvidence:
        normalized_media_type, storage_key = _new_storage_key(media_type)
        digest = hashlib.sha256()
        size_bytes = 0
        first_bytes = bytearray()
        with SpooledTemporaryFile(max_size=min(max_bytes, 1024 * 1024), mode="w+b") as temporary:
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
                temporary.write(chunk)
            _validate_content(normalized_media_type, size_bytes, bytes(first_bytes))
            temporary.seek(0)
            try:
                self._client.upload_fileobj(
                    temporary,
                    self.bucket,
                    self._object_key(storage_key),
                    ExtraArgs={"ContentType": normalized_media_type},
                )
            except Exception as exc:
                raise DomainError(
                    "EVIDENCE_STORAGE_UNAVAILABLE",
                    "Evidence storage에 파일을 저장할 수 없습니다.",
                    503,
                ) from exc
        return StoredEvidence(
            storage_key=storage_key,
            size_bytes=size_bytes,
            sha256=digest.hexdigest(),
        )

    @contextmanager
    def open(self, storage_key: str) -> Iterator[BinaryIO]:
        object_key = self._object_key(storage_key)
        try:
            response = self._client.get_object(
                Bucket=self.bucket,
                Key=object_key,
            )
        except Exception as exc:
            if _is_s3_not_found(exc):
                raise DomainError(
                    "EVIDENCE_CONTENT_NOT_FOUND", "Evidence 파일을 찾을 수 없습니다.", 404
                ) from exc
            raise DomainError(
                "EVIDENCE_STORAGE_UNAVAILABLE",
                "Evidence storage에서 파일을 읽을 수 없습니다.",
                503,
            ) from exc
        body = response.get("Body")
        if body is None or not hasattr(body, "read"):
            raise DomainError(
                "EVIDENCE_STORAGE_UNAVAILABLE",
                "Evidence storage 응답이 올바르지 않습니다.",
                503,
            )
        try:
            yield body
        finally:
            close = getattr(body, "close", None)
            if callable(close):
                close()

    def delete(self, storage_key: str) -> None:
        object_key = self._object_key(storage_key)
        try:
            self._client.delete_object(
                Bucket=self.bucket,
                Key=object_key,
            )
        except Exception as exc:
            raise DomainError(
                "EVIDENCE_STORAGE_UNAVAILABLE",
                "Evidence storage에서 파일을 삭제할 수 없습니다.",
                503,
            ) from exc

    def check_ready(self) -> None:
        try:
            self._client.head_bucket(Bucket=self.bucket)
            if not self._permissions_verified:
                with self._ready_lock:
                    if not self._permissions_verified:
                        self._verify_object_permissions()
                        self._permissions_verified = True
        except Exception as exc:
            if isinstance(exc, DomainError):
                raise
            raise DomainError(
                "EVIDENCE_STORAGE_UNAVAILABLE",
                "Evidence storage를 사용할 수 없습니다.",
                503,
            ) from exc

    def _verify_object_permissions(self) -> None:
        payload = b"greenfab-evidence-storage-ready"
        storage_key = f"health/{uuid4().hex}.probe"
        object_key = self._object_key(storage_key)
        created = False
        body: Any | None = None
        try:
            self._client.put_object(
                Bucket=self.bucket,
                Key=object_key,
                Body=payload,
                ContentType="application/octet-stream",
            )
            created = True
            response = self._client.get_object(Bucket=self.bucket, Key=object_key)
            body = response.get("Body")
            if body is None or not hasattr(body, "read") or body.read(len(payload) + 1) != payload:
                raise RuntimeError("S3 Evidence readiness probe returned unexpected content")
            self._client.delete_object(Bucket=self.bucket, Key=object_key)
            created = False
        finally:
            close = getattr(body, "close", None)
            if callable(close):
                close()
            if created:
                try:
                    self._client.delete_object(Bucket=self.bucket, Key=object_key)
                except Exception:
                    pass

    def _object_key(self, storage_key: str) -> str:
        _validate_relative_storage_key(storage_key)
        return f"{self.prefix}/{storage_key}" if self.prefix else storage_key

    @staticmethod
    def _build_client(
        *,
        region: str | None,
        endpoint_url: str | None,
        access_key_id: str | None,
        secret_access_key: str | None,
        session_token: str | None,
        addressing_style: str,
        connect_timeout_seconds: int,
        read_timeout_seconds: int,
        max_attempts: int,
    ) -> Any:
        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:  # pragma: no cover - optional runtime dependency
            raise RuntimeError(
                'S3 Evidence runtime is not installed; install the backend with ".[storage]"'
            ) from exc
        return boto3.client(
            "s3",
            region_name=region or None,
            endpoint_url=endpoint_url or None,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            aws_session_token=session_token,
            config=Config(
                connect_timeout=connect_timeout_seconds,
                read_timeout=read_timeout_seconds,
                retries={"mode": "standard", "total_max_attempts": max_attempts},
                tcp_keepalive=True,
                s3={"addressing_style": addressing_style},
            ),
        )


def build_evidence_storage(settings: Settings) -> EvidenceStorage:
    if settings.evidence_storage_backend == "local":
        return LocalEvidenceStorage(settings.evidence_storage_root)
    return S3EvidenceStorage(
        bucket=settings.evidence_s3_bucket,
        prefix=settings.evidence_s3_prefix,
        region=settings.evidence_s3_region,
        endpoint_url=settings.evidence_s3_endpoint_url,
        access_key_id=(
            settings.evidence_s3_access_key_id.get_secret_value()
            if settings.evidence_s3_access_key_id
            else None
        ),
        secret_access_key=(
            settings.evidence_s3_secret_access_key.get_secret_value()
            if settings.evidence_s3_secret_access_key
            else None
        ),
        session_token=(
            settings.evidence_s3_session_token.get_secret_value()
            if settings.evidence_s3_session_token
            else None
        ),
        addressing_style=settings.evidence_s3_addressing_style,
        connect_timeout_seconds=settings.evidence_s3_connect_timeout_seconds,
        read_timeout_seconds=settings.evidence_s3_read_timeout_seconds,
        max_attempts=settings.evidence_s3_max_attempts,
    )


def _new_storage_key(media_type: str) -> tuple[str, str]:
    normalized_media_type = media_type.split(";", 1)[0].strip().casefold()
    extension = _MEDIA_EXTENSIONS.get(normalized_media_type)
    if extension is None:
        raise DomainError(
            "EVIDENCE_TYPE_NOT_ALLOWED",
            "Evidence는 PDF, JPEG 또는 PNG만 업로드할 수 있습니다.",
            422,
        )
    identifier = uuid4().hex
    return normalized_media_type, f"{identifier[:2]}/{identifier}{extension}"


def _validate_content(media_type: str, size_bytes: int, first_bytes: bytes) -> None:
    if size_bytes == 0:
        raise DomainError("EMPTY_EVIDENCE", "빈 Evidence 파일은 업로드할 수 없습니다.", 422)
    if not _signature_matches(media_type, first_bytes):
        raise DomainError(
            "EVIDENCE_CONTENT_MISMATCH",
            "파일 내용이 선언된 Content-Type과 일치하지 않습니다.",
            422,
        )


def _validate_relative_storage_key(storage_key: str) -> None:
    pure_key = PurePosixPath(storage_key)
    if pure_key.is_absolute() or ".." in pure_key.parts or len(pure_key.parts) != 2:
        raise DomainError("INVALID_STORAGE_KEY", "Evidence storage key가 올바르지 않습니다.", 500)


def _is_s3_not_found(exc: Exception) -> bool:
    response = getattr(exc, "response", None)
    if not isinstance(response, dict):
        return False
    error = response.get("Error")
    metadata = response.get("ResponseMetadata")
    code = str(error.get("Code", "")) if isinstance(error, dict) else ""
    status = metadata.get("HTTPStatusCode") if isinstance(metadata, dict) else None
    return code in {"404", "NoSuchKey", "NotFound"} or status == 404


def _signature_matches(media_type: str, content: bytes) -> bool:
    if media_type == "application/pdf":
        return content.startswith(b"%PDF-")
    if media_type == "image/png":
        return content.startswith(b"\x89PNG\r\n\x1a\n")
    if media_type == "image/jpeg":
        return content.startswith(b"\xff\xd8\xff")
    return False
