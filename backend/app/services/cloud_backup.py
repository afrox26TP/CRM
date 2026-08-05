from datetime import UTC, datetime

from ..config import Settings


class CloudBackupError(RuntimeError):
    pass


def _object_name(settings: Settings, stored_name: str) -> str:
    object_prefix = settings.google_cloud_storage_prefix.strip().strip("/")
    return stored_name if not object_prefix else f"{object_prefix}/{stored_name}"


def store_document(settings: Settings, stored_name: str, mime_type: str, content: bytes) -> str:
    """Persist a document in Cloud Storage, or locally when no bucket is configured."""
    bucket_name = settings.google_cloud_storage_bucket.strip()
    if not bucket_name:
        settings.storage_path.mkdir(parents=True, exist_ok=True)
        (settings.storage_path / stored_name).write_bytes(content)
        return str(settings.storage_path / stored_name)

    object_name = _object_name(settings, stored_name)

    try:
        from google.cloud import storage

        client = storage.Client(project=settings.google_cloud_project or None)
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(object_name)
        blob.upload_from_string(content, content_type=mime_type)
    except Exception as exc:
        raise CloudBackupError(f"Uložení do Google Cloud Storage selhalo: {exc}") from exc

    return f"gs://{bucket_name}/{object_name}"


def delete_stored_document(settings: Settings, stored_name: str) -> None:
    bucket_name = settings.google_cloud_storage_bucket.strip()
    if not bucket_name:
        stored_path = settings.storage_path / stored_name
        if stored_path.exists():
            stored_path.unlink()
        return

    try:
        from google.api_core.exceptions import NotFound
        from google.cloud import storage

        client = storage.Client(project=settings.google_cloud_project or None)
        blob = client.bucket(bucket_name).blob(_object_name(settings, stored_name))
        try:
            blob.delete()
        except NotFound:
            pass
    except Exception as exc:
        raise CloudBackupError(f"Smazání z Google Cloud Storage selhalo: {exc}") from exc


def backup_timestamp_iso() -> str:
    return datetime.now(UTC).isoformat()
