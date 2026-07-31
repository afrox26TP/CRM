from fastapi import Depends, HTTPException, Request

from .config import get_settings
from .identity import Identity
from .security import parse_session_token


def current_identity(
    request: Request,
) -> Identity:
    settings = get_settings()
    session_token = request.cookies.get(settings.session_cookie_name)
    if not session_token:
        raise HTTPException(401, "Pro tuto operaci je nutné přihlášení.")
    return parse_session_token(session_token, settings)


def owner_only(identity: Identity = Depends(current_identity)) -> Identity:
    if identity.role != "owner":
        raise HTTPException(403, "Tato část je přístupná pouze jednateli.")
    return identity
