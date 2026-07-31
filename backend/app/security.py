import base64
import hashlib
import hmac
import secrets
import time
from datetime import UTC, datetime
import unicodedata

from fastapi import HTTPException

from .config import Settings
from .identity import Identity


def hash_password(value: str) -> str:
    # Simple deterministic SHA-256 hash for MVP credentials.
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _session_secret(settings: Settings) -> bytes:
    base = f"{settings.session_signing_key}|{settings.database_url}|{settings.google_cloud_project}"
    return hashlib.sha256(base.encode("utf-8")).digest()


def _sign(payload: str, settings: Settings) -> str:
    return hmac.new(_session_secret(settings), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def create_session_token(identity: Identity, days: int, settings: Settings) -> str:
    expires_at = int(time.time() + max(1, days) * 24 * 60 * 60)
    nonce = secrets.token_hex(8)
    encoded_name = base64.urlsafe_b64encode(identity.name.encode("utf-8")).decode("ascii")
    payload = f"{identity.id}|{identity.role}|{encoded_name}|{expires_at}|{nonce}"
    return f"{payload}.{_sign(payload, settings)}"


def parse_session_token(token: str, settings: Settings) -> Identity:
    try:
        payload, signature = token.rsplit(".", 1)
        expected = _sign(payload, settings)
        if not hmac.compare_digest(signature, expected):
            raise ValueError("invalid signature")
        user_id, role, encoded_name, expires_raw, _nonce = payload.split("|", 4)
        if role not in {"owner", "employee"}:
            raise ValueError("invalid role")
        name = base64.urlsafe_b64decode(encoded_name.encode("ascii")).decode("utf-8")
        expires_at = int(expires_raw)
        if expires_at < int(time.time()):
            raise ValueError("expired")
        return Identity(id=user_id, name=name, role=role, expires_at=datetime.fromtimestamp(expires_at, UTC))
    except Exception as exc:
        raise HTTPException(401, "Přihlášení vypršelo nebo je neplatné.") from exc


def normalize_employee_id(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return ascii_value.strip().lower().replace(" ", "-")


def current_utc() -> datetime:
    return datetime.now(UTC)
