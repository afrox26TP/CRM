from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Identity:
    id: str
    name: str
    role: str
    expires_at: datetime
