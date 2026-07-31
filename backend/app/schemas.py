from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class DocumentUpdate(BaseModel):
    document_type: str | None = Field(default=None, pattern="^(cmr|tax|unknown)$")
    status: str | None = Field(default=None, pattern="^(received|processing|matched|needs_review|approved|exported)$")
    cmr_number: str | None = None
    issue_date: date | None = None
    supplier: str | None = None
    net_amount: Decimal | None = Field(default=None, ge=0)
    vat_amount: Decimal | None = Field(default=None, ge=0)
    vat_rate: Decimal | None = Field(default=None, ge=0, le=100)
    gross_amount: Decimal | None = Field(default=None, ge=0)
    dispatcher: str | None = Field(default=None, pattern="^(Tonda|Karel|Jarda)$")
    note: str | None = None


class DocumentOut(BaseModel):
    id: int
    original_name: str
    document_type: str
    status: str
    cmr_number: str | None
    issue_date: date | None
    supplier: str | None
    net_amount: Decimal | None
    vat_amount: Decimal | None
    vat_rate: Decimal | None
    gross_amount: Decimal | None
    confidence: Decimal | None
    uploaded_by: str
    dispatcher: str | None
    note: str | None
    transport_id: int | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EmployeeDocumentOut(BaseModel):
    id: int
    original_name: str
    document_type: str
    status: str
    cmr_number: str | None
    issue_date: date | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TransportOut(BaseModel):
    id: int
    cmr_number: str
    transport_date: date | None
    driver_name: str | None
    license_plate: str | None
    route: str | None
    transport_price: Decimal | None
    currency: str
    dispatcher: str | None
    document_count: int = 0

    model_config = ConfigDict(from_attributes=True)
