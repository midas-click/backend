"""S3 service — pre-signed upload/download URLs."""

from typing import Any

import boto3
from botocore.config import Config

from app.config import settings

_s3_client: Any = None


def _get_client():
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client(
            "s3",
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_REGION,
            config=Config(signature_version="s3v4"),
        )
    return _s3_client


def generate_presigned_upload_url(key: str, content_type: str = "application/pdf", expires: int = 300) -> str:
    """Generate a pre-signed URL for client-side upload."""
    client = _get_client()
    return client.generate_presigned_url(
        "put_object",
        Params={
            "Bucket": settings.S3_BUCKET_NAME,
            "Key": key,
            "ContentType": content_type,
        },
        ExpiresIn=expires,
    )


def generate_presigned_download_url(key: str, expires: int = 3600) -> str:
    """Generate a pre-signed URL for viewing a stored file."""
    client = _get_client()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.S3_BUCKET_NAME, "Key": key},
        ExpiresIn=expires,
    )


async def upload_to_s3(key: str, body: bytes, content_type: str = "application/pdf") -> str:
    """Upload bytes to S3 directly and return a pre-signed download URL."""
    client = _get_client()
    client.put_object(
        Bucket=settings.S3_BUCKET_NAME,
        Key=key,
        Body=body,
        ContentType=content_type,
    )
    return generate_presigned_download_url(key)
