from datetime import UTC, datetime

from ..config import Settings


class CloudBackupError(RuntimeError):
    pass


def upload_document_backup(settings: Settings, stored_name: str, mime_type: str, content: bytes) -> str | None:
    """Upload the raw document to Google Cloud Storage when bucket is configured."""
    bucket_name = settings.google_cloud_storage_bucket.strip()
    if not bucket_name:
        return None

    object_prefix = settings.google_cloud_storage_prefix.strip().strip("/")
    object_name = stored_name if not object_prefix else f"{object_prefix}/{stored_name}"

    try:
        from google.cloud import storage

        client = storage.Client(project=settings.google_cloud_project or None)
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(object_name)
        blob.upload_from_string(content, content_type=mime_type)
    except Exception as exc:
        raise CloudBackupError(f"Záloha do Google Cloud Storage selhala: {exc}") from exc

    return f"gs://{bucket_name}/{object_name}"


def backup_timestamp_iso() -> str:
    return datetime.now(UTC).isoformat()
