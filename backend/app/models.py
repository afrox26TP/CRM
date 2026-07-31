from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class Transport(Base):
    __tablename__ = "transports"

    id: Mapped[int] = mapped_column(primary_key=True)
    cmr_number: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    cmr_normalized: Mapped[str] = mapped_column(String(100), index=True)
    transport_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    driver_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    license_plate: Mapped[str | None] = mapped_column(String(30), nullable=True)
    route: Mapped[str | None] = mapped_column(String(255), nullable=True)
    transport_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="CZK")
    dispatcher: Mapped[str | None] = mapped_column(String(30), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    documents: Mapped[list["Document"]] = relationship(back_populates="transport")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    original_name: Mapped[str] = mapped_column(String(255))
    stored_name: Mapped[str] = mapped_column(String(255), unique=True)
    mime_type: Mapped[str] = mapped_column(String(100))
    document_type: Mapped[str] = mapped_column(String(30), default="unknown", index=True)
    status: Mapped[str] = mapped_column(String(30), default="received", index=True)
    cmr_number: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    issue_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    supplier: Mapped[str | None] = mapped_column(String(255), nullable=True)
    net_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    vat_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    vat_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    gross_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    uploaded_by: Mapped[str] = mapped_column(String(120), default="Neznámý zaměstnanec", index=True)
    dispatcher: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    transport_id: Mapped[int | None] = mapped_column(ForeignKey("transports.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    transport: Mapped[Transport | None] = relationship(back_populates="documents")
    audit_events: Mapped[list["AuditEvent"]] = relationship(back_populates="document", cascade="all, delete-orphan")


class AssignmentRule(Base):
    __tablename__ = "assignment_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    field: Mapped[str] = mapped_column(String(30))
    pattern: Mapped[str] = mapped_column(String(120))
    dispatcher: Mapped[str] = mapped_column(String(30))
    priority: Mapped[int] = mapped_column(default=100)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"))
    action: Mapped[str] = mapped_column(String(80))
    actor: Mapped[str] = mapped_column(String(80), default="system")
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    document: Mapped[Document] = relationship(back_populates="audit_events")


class UserAccount(Base):
    __tablename__ = "user_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    role: Mapped[str] = mapped_column(String(20), index=True)
    pin_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
