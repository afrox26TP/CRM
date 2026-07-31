from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException


@dataclass(frozen=True)
class Identity:
    name: str
    role: str


def current_identity(
    x_user_id: Annotated[str | None, Header()] = None,
    x_user_role: Annotated[str | None, Header()] = None,
) -> Identity:
    """Development identity boundary; replace headers with verified OIDC claims in production."""
    names = {"vratislav": "Vratislav", "petr-novak": "Petr Novák", "milan-dvorak": "Milan Dvořák", "jan-svoboda": "Jan Svoboda"}
    if not x_user_id or x_user_id not in names or x_user_role not in {"owner", "employee"}:
        raise HTTPException(401, "Pro tuto operaci je nutné přihlášení.")
    return Identity(name=names[x_user_id], role=x_user_role)


def owner_only(identity: Identity = Depends(current_identity)) -> Identity:
    if identity.role != "owner" or identity.name.casefold() != "vratislav":
        raise HTTPException(403, "Tato část je přístupná pouze jednateli Vratislavovi.")
    return identity
