"""S3/R2 storage helpers for audio files."""
from __future__ import annotations

import os
from typing import Optional

import boto3


def _get_s3_env() -> dict:
    return {
        "access_key": os.getenv("S3_ACCESS_KEY_ID", "").strip(),
        "secret_key": os.getenv("S3_SECRET_ACCESS_KEY", "").strip(),
        "endpoint_url": os.getenv("S3_ENDPOINT_URL", "").strip(),
        "bucket": os.getenv("S3_BUCKET_NAME", "").strip(),
        "region": os.getenv("S3_REGION", "auto").strip(),
    }


def s3_enabled() -> bool:
    env = _get_s3_env()
    return all([env["access_key"], env["secret_key"], env["endpoint_url"], env["bucket"]])


def create_s3_client():
    env = _get_s3_env()
    return boto3.client(
        "s3",
        aws_access_key_id=env["access_key"],
        aws_secret_access_key=env["secret_key"],
        endpoint_url=env["endpoint_url"],
        region_name=env["region"] or "auto",
    )


def get_audio_object_key(lesson_id: int, filename: str) -> str:
    return f"{lesson_id}_{filename}"


def create_presigned_audio_url(key: str, expires_seconds: int = 3600) -> Optional[str]:
    if not s3_enabled():
        return None
    env = _get_s3_env()
    client = create_s3_client()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": env["bucket"], "Key": key},
        ExpiresIn=expires_seconds,
    )


def upload_audio_fileobj(fileobj, key: str) -> None:
    env = _get_s3_env()
    client = create_s3_client()
    client.upload_fileobj(fileobj, env["bucket"], key)


def rename_audio_object(source_key: str, dest_key: str) -> None:
    env = _get_s3_env()
    client = create_s3_client()
    client.copy_object(
        Bucket=env["bucket"],
        CopySource={"Bucket": env["bucket"], "Key": source_key},
        Key=dest_key,
    )
    client.delete_object(Bucket=env["bucket"], Key=source_key)


def download_audio_bytes(key: str) -> bytes:
    env = _get_s3_env()
    client = create_s3_client()
    response = client.get_object(Bucket=env["bucket"], Key=key)
    return response["Body"].read()
