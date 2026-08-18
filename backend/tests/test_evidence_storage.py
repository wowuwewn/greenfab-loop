from __future__ import annotations

import io
from contextlib import contextmanager

import pytest

from app.errors import DomainError
from app.services.evidence import open_verified_evidence
from app.storage import S3EvidenceStorage


class FakeS3Error(Exception):
    def __init__(self, code: str, status: int):
        self.response = {
            "Error": {"Code": code},
            "ResponseMetadata": {"HTTPStatusCode": status},
        }


class FakeS3Client:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], tuple[bytes, str]] = {}
        self.head_calls: list[str] = []
        self.put_calls: list[tuple[str, str]] = []

    def upload_fileobj(self, stream, bucket: str, key: str, ExtraArgs: dict[str, str]) -> None:
        self.objects[(bucket, key)] = (stream.read(), ExtraArgs["ContentType"])

    def put_object(
        self,
        *,
        Bucket: str,
        Key: str,
        Body: bytes,
        ContentType: str,
    ) -> None:
        self.put_calls.append((Bucket, Key))
        self.objects[(Bucket, Key)] = (Body, ContentType)

    def get_object(self, *, Bucket: str, Key: str):
        try:
            content, _media_type = self.objects[(Bucket, Key)]
        except KeyError as exc:
            raise FakeS3Error("NoSuchKey", 404) from exc
        return {"Body": io.BytesIO(content)}

    def delete_object(self, *, Bucket: str, Key: str) -> None:
        self.objects.pop((Bucket, Key), None)

    def head_bucket(self, *, Bucket: str) -> None:
        self.head_calls.append(Bucket)


def test_s3_storage_round_trip_uses_generated_prefixed_key() -> None:
    client = FakeS3Client()
    storage = S3EvidenceStorage(
        bucket="evidence-bucket",
        prefix="production/passports",
        client=client,
    )
    png = b"\x89PNG\r\n\x1a\nmanaged-object-storage"

    stored = storage.save(io.BytesIO(png), media_type="image/png", max_bytes=1024)

    assert stored.storage_key.count("/") == 1
    object_key = f"production/passports/{stored.storage_key}"
    assert client.objects[("evidence-bucket", object_key)] == (png, "image/png")
    with storage.open(stored.storage_key) as stream:
        assert stream.read() == png
    storage.check_ready()
    storage.check_ready()
    assert client.head_calls == ["evidence-bucket", "evidence-bucket"]
    assert len(client.put_calls) == 1
    assert not any("/health/" in key for _bucket, key in client.objects)
    storage.delete(stored.storage_key)
    assert client.objects == {}


def test_s3_storage_rejects_content_before_upload_and_maps_missing_object() -> None:
    client = FakeS3Client()
    storage = S3EvidenceStorage(bucket="evidence-bucket", client=client)

    with pytest.raises(DomainError, match="파일 내용") as mismatched:
        storage.save(io.BytesIO(b"not-a-pdf"), media_type="application/pdf", max_bytes=1024)
    assert mismatched.value.code == "EVIDENCE_CONTENT_MISMATCH"
    assert client.objects == {}

    with pytest.raises(DomainError) as missing:
        with storage.open("ab/abcdef.png"):
            pass
    assert missing.value.code == "EVIDENCE_CONTENT_NOT_FOUND"
    assert missing.value.status_code == 404


def test_s3_storage_rejects_untrusted_database_key() -> None:
    storage = S3EvidenceStorage(bucket="evidence-bucket", client=FakeS3Client())

    with pytest.raises(DomainError) as traversal:
        with storage.open("../outside.png"):
            pass
    assert traversal.value.code == "INVALID_STORAGE_KEY"


def test_s3_client_uses_bounded_timeouts_and_retries(monkeypatch) -> None:
    boto3 = pytest.importorskip("boto3")
    captured = {}

    def fake_client(service_name: str, **kwargs):
        captured["service_name"] = service_name
        captured.update(kwargs)
        return FakeS3Client()

    monkeypatch.setattr(boto3, "client", fake_client)

    S3EvidenceStorage(
        bucket="evidence-bucket",
        endpoint_url="https://objects.example.com",
        connect_timeout_seconds=2,
        read_timeout_seconds=7,
        max_attempts=3,
    )

    config = captured["config"]
    assert captured["service_name"] == "s3"
    assert captured["endpoint_url"] == "https://objects.example.com"
    assert config.connect_timeout == 2
    assert config.read_timeout == 7
    assert config.retries["total_max_attempts"] == 3
    assert config.retries["mode"] == "standard"
    assert config.tcp_keepalive is True


def test_verified_download_maps_stream_failure_to_storage_unavailable() -> None:
    class FailingBody:
        def read(self, _size: int) -> bytes:
            raise OSError("synthetic object stream failure")

    class FailingStorage:
        @contextmanager
        def open(self, _storage_key: str):
            yield FailingBody()

    with pytest.raises(DomainError) as unavailable:
        with open_verified_evidence(
            FailingStorage(),  # type: ignore[arg-type]
            storage_key="ab/abcdef.png",
            expected_size=8,
            expected_sha256="0" * 64,
        ):
            pass

    assert unavailable.value.code == "EVIDENCE_STORAGE_UNAVAILABLE"
    assert unavailable.value.status_code == 503
