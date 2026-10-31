"""Private S3-compatible object storage (Garage in the reference deployment).

Objects are never public: there are no presigned URLs. Every download goes through
an authorised API endpoint that streams the object.
"""

from __future__ import annotations

import io
from collections.abc import Iterator
from functools import lru_cache

from minio import Minio
from minio.error import S3Error

from app.core.config import get_settings


@lru_cache(maxsize=1)
def client() -> Minio:
    import urllib3

    s = get_settings()
    http = urllib3.PoolManager(
        timeout=urllib3.Timeout(connect=3.0, read=60.0),
        retries=urllib3.Retry(total=1, backoff_factor=0.2, status_forcelist=[500, 502, 503, 504]),
        maxsize=10,
    )
    return Minio(
        s.storage_endpoint,
        access_key=s.storage_access_key,
        secret_key=s.storage_secret_key.get_secret_value(),
        secure=s.storage_secure,
        region=s.storage_region,
        http_client=http,
    )


def put_bytes(key: str, data: bytes, content_type: str) -> None:
    client().put_object(get_settings().storage_bucket, key, io.BytesIO(data), len(data), content_type=content_type)


def get_stream(key: str) -> Iterator[bytes]:
    resp = client().get_object(get_settings().storage_bucket, key)
    try:
        yield from resp.stream(64 * 1024)
    finally:
        resp.close()
        resp.release_conn()


def get_bytes(key: str) -> bytes:
    return b"".join(get_stream(key))


def delete(key: str) -> None:
    client().remove_object(get_settings().storage_bucket, key)


def ping() -> bool:
    try:
        return client().bucket_exists(get_settings().storage_bucket)
    except S3Error:
        return False
