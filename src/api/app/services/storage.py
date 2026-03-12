import uuid
from datetime import UTC, datetime

import boto3
import structlog
from botocore.config import Config

from app.config import settings

log = structlog.get_logger(__name__)


class StorageService:
    def __init__(self) -> None:
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.STORAGE_ENDPOINT_URL,
            aws_access_key_id=settings.STORAGE_ACCESS_KEY_ID,
            aws_secret_access_key=settings.STORAGE_SECRET_ACCESS_KEY,
            region_name=settings.STORAGE_REGION,
            config=Config(signature_version="s3v4"),
        )
        self.bucket = settings.STORAGE_BUCKET_NAME

    def generate_upload_presigned_url(
        self, key: str, content_type: str
    ) -> tuple[str, str]:
        """Returns (upload_url, download_url)."""
        upload_url: str = self.client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": self.bucket,
                "Key": key,
                "ContentType": content_type,
            },
            ExpiresIn=settings.STORAGE_UPLOAD_URL_TTL_SECONDS,
        )
        download_url, _ = self.generate_download_presigned_url(key)
        return upload_url, download_url

    def generate_download_presigned_url(self, key: str) -> tuple[str, datetime]:
        """Returns (url, expires_at)."""
        url: str = self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=settings.STORAGE_DOWNLOAD_URL_TTL_SECONDS,
        )
        expires_at = datetime.now(UTC).replace(microsecond=0)
        from datetime import timedelta  # noqa: PLC0415

        expires_at = expires_at + timedelta(seconds=settings.STORAGE_DOWNLOAD_URL_TTL_SECONDS)
        return url, expires_at

    def delete_object(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)
        log.info("storage_object_deleted", key=key)

    def build_attachment_key(
        self,
        ticket_id: uuid.UUID,
        attachment_id: uuid.UUID,
        filename: str,
    ) -> str:
        return f"tickets/{ticket_id}/attachments/{attachment_id}/{filename}"

    def build_export_key(self, export_id: uuid.UUID, kind: str, period: str) -> str:
        return f"exports/{kind}/{period}/{export_id}.xlsx"


storage_service = StorageService()
