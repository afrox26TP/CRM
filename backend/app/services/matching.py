import re
import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import AssignmentRule, Transport


def normalize(value: str | None) -> str:
    if not value:
        return ""
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Z0-9]", "", ascii_value.upper())


def find_transport(db: Session, cmr_number: str | None) -> Transport | None:
    normalized = normalize(cmr_number)
    if not normalized:
        return None
    return db.scalar(select(Transport).where(Transport.cmr_normalized == normalized))


def assign_dispatcher(db: Session, transport: Transport) -> str | None:
    rules = db.scalars(select(AssignmentRule).order_by(AssignmentRule.priority)).all()
    values = {
        "driver_name": transport.driver_name or "",
        "license_plate": transport.license_plate or "",
        "route": transport.route or "",
    }
    for rule in rules:
        if rule.field in values and normalize(rule.pattern) in normalize(values[rule.field]):
            return rule.dispatcher
    return transport.dispatcher
