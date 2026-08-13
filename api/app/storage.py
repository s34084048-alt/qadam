"""Object storage abstraction.

Images and overlays live in object storage; only the key is written to the
database. `s3` targets any S3-compatible service (MinIO locally, AWS S3 or a
UAE-resident equivalent in production). `local` writes to a directory so the
API runs with no services attached -- used by the test suite and laptop runs.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Protocol

from .config import settings


class StorageBackend(Protocol):
    def put(self, key: str, data: bytes, content_type: str) -> str: ...
    def get(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...
    def exists(self, key: str) -> bool: ...


class LocalStorage:
    """Filesystem-backed. Encryption at rest is delegated to the volume."""

    def __init__(self, root: str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        # Keys are server-generated; still refuse anything that escapes root.
        safe = key.replace("\\", "/").lstrip("/")
        if ".." in safe.split("/"):
            raise ValueError("invalid storage key")
        return self.root / safe

    def put(self, key: str, data: bytes, content_type: str) -> str:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        path = self._path(key)
        if path.exists():
            path.unlink()

    def exists(self, key: str) -> bool:
        return self._path(key).exists()


class S3Storage:
    def __init__(self) -> None:
        import boto3
        from botocore.config import Config

        self._bucket = settings.s3_bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            region_name=settings.s3_region,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            use_ssl=settings.s3_use_ssl,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )
        self._ensure_bucket()

    def _ensure_bucket(self) -> None:
        from botocore.exceptions import ClientError

        try:
            self._client.head_bucket(Bucket=self._bucket)
        except ClientError:
            try:
                self._client.create_bucket(Bucket=self._bucket)
            except ClientError:
                # Bucket may be pre-provisioned with restricted permissions.
                pass

    def put(self, key: str, data: bytes, content_type: str) -> str:
        self._client.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
            # Server-side encryption at rest where the endpoint supports it.
            **({"ServerSideEncryption": "AES256"} if settings.s3_use_ssl else {}),
        )
        return key

    def get(self, key: str) -> bytes:
        obj = self._client.get_object(Bucket=self._bucket, Key=key)
        return obj["Body"].read()

    def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=key)

    def exists(self, key: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
            return True
        except ClientError:
            return False


_storage: StorageBackend | None = None


def get_storage() -> StorageBackend:
    global _storage
    if _storage is None:
        _storage = (
            S3Storage() if settings.storage_backend == "s3"
            else LocalStorage(settings.local_storage_dir)
        )
    return _storage


def reset_storage() -> None:
    """Test hook."""
    global _storage
    _storage = None


def build_key(case_id: str, kind: str, data: bytes, ext: str) -> str:
    """Content-addressed key. Carries no patient identifier."""
    digest = hashlib.sha256(data).hexdigest()[:16]
    return f"cases/{case_id}/{kind}/{digest}.{ext}"
