"""
app/modules/storage/object_store.py — MinIO object storage wrapper.
"""
from __future__ import annotations

import io
from functools import lru_cache
from typing import Optional

import structlog
from minio import Minio
from minio.error import S3Error

from app.core.settings import settings

logger = structlog.get_logger()


@lru_cache(maxsize=1)
def get_minio() -> Minio:
    return Minio(
        settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ROOT_USER,
        secret_key=settings.MINIO_ROOT_PASSWORD,
        secure=settings.MINIO_SECURE,
    )


def ensure_bucket(bucket: str) -> None:
    client = get_minio()
    try:
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)
            logger.info("MinIO bucket created", bucket=bucket)
    except S3Error as e:
        logger.error("MinIO bucket error", bucket=bucket, error=str(e))
        raise


def upload_bytes(bucket: str, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
    ensure_bucket(bucket)
    client = get_minio()
    client.put_object(bucket, key, io.BytesIO(data), length=len(data), content_type=content_type)
    return key


def download_bytes(bucket: str, key: str) -> bytes:
    client = get_minio()
    response = client.get_object(bucket, key)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()


def get_presigned_url(bucket: str, key: str, expires_hours: int = 24) -> str:
    from datetime import timedelta
    client = get_minio()
    return client.presigned_get_object(bucket, key, expires=timedelta(hours=expires_hours))


def delete_object(bucket: str, key: str) -> None:
    client = get_minio()
    try:
        client.remove_object(bucket, key)
    except S3Error as e:
        logger.warning("MinIO delete error", key=key, error=str(e))
