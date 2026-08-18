from __future__ import annotations

import io

import pytest

from app.errors import DomainError
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

    def upload_fileobj(self, stream, bucket: str, key: str, ExtraArgs: dict[str, str]) -> None:
        self.objects[(bucket, key)] = (stream.read(), ExtraArgs["ContentType"])

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
    assert client.head_calls == ["evidence-bucket"]
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
