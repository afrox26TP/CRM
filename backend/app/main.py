import csv
import io
import json
import mimetypes
import uuid
from contextlib import asynccontextmanager
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd
from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy import func, inspect, select, text
from sqlalchemy.orm import Session

from .auth import Identity, current_identity, owner_only
from .config import get_settings
from .database import Base, SessionLocal, engine, get_db
from .models import AuditEvent, Document, Transport, UserAccount
from .schemas import (
    DocumentOut,
    DocumentUpdate,
    EmployeeCreateRequest,
    EmployeeOut,
    EmployeeDocumentOut,
    LoginRequest,
    SessionOut,
    TransportOut,
)
from .security import create_session_token, current_utc, hash_password, normalize_employee_id
from .services.cloud_backup import CloudBackupError, backup_timestamp_iso, upload_document_backup
from .services.document_ai import DocumentExtractionError, extract_document
from .services.matching import assign_dispatcher, find_transport, normalize

settings = get_settings()
ALLOWED_DOCUMENT_TYPES = {"image/jpeg", "image/png", "image/webp", "application/pdf"}
MAX_DOCUMENT_SIZE = 15 * 1024 * 1024


def _seed(db: Session) -> None:
    owner_id = normalize_employee_id(settings.owner_name)
    owner = db.scalar(select(UserAccount).where(UserAccount.user_id == owner_id))
    if not owner:
        db.add(UserAccount(user_id=owner_id, name=settings.owner_name, role="owner", pin_hash=hash_password(settings.owner_pin)))
    else:
        owner.name = settings.owner_name
        owner.pin_hash = hash_password(settings.owner_pin)
        owner.role = "owner"
        owner.is_active = True

    db.commit()


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)
    if "uploaded_by" not in {column["name"] for column in inspect(engine).get_columns("documents")}:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE documents ADD COLUMN uploaded_by VARCHAR(120) NOT NULL DEFAULT 'Neznámý zaměstnanec'"))
    settings.storage_path.mkdir(parents=True, exist_ok=True)
    with SessionLocal() as db:
        _seed(db)
    yield


app = FastAPI(title="Conpath CRM API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _audit(db: Session, document: Document, action: str, actor: str = "system", details: dict | None = None) -> None:
    db.add(AuditEvent(document=document, action=action, actor=actor, details=json.dumps(details, ensure_ascii=False, default=str) if details else None))


def _transport_out(item: Transport) -> TransportOut:
    data = TransportOut.model_validate(item)
    data.document_count = len(item.documents)
    return data


def _set_session_cookie(response: Response, identity: Identity, days: int) -> SessionOut:
    token = create_session_token(identity, days, settings)
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=days * 24 * 60 * 60,
        httponly=True,
        secure=settings.session_secure,
        samesite="lax",
        path="/",
    )
    expires_at = current_utc() + timedelta(days=days)
    return SessionOut(user_id=identity.id, name=identity.name, role=identity.role, expires_at=expires_at)


@app.get("/api/health")
def health():
    return {"status": "ok", "provider": settings.document_ai_provider}


@app.get("/api/auth/session", response_model=SessionOut)
def auth_session(identity: Identity = Depends(current_identity)):
    return SessionOut(user_id=identity.id, name=identity.name, role=identity.role, expires_at=identity.expires_at)


@app.post("/api/auth/login", response_model=SessionOut)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    pin = payload.pin.strip()
    pin_hash = hash_password(pin)
    matches = db.scalars(select(UserAccount).where(UserAccount.pin_hash == pin_hash, UserAccount.is_active.is_(True))).all()
    if len(matches) == 0:
        raise HTTPException(401, "Neplatný PIN.")
    if len(matches) > 1:
        raise HTTPException(409, "PIN není jednoznačný. Kontaktujte správce systému.")

    user = matches[0]
    if user.role == "owner" and len(pin) < 6:
        raise HTTPException(500, "PIN jednatele je v konfiguraci neplatný.")
    if user.role == "employee" and len(pin) != 4:
        raise HTTPException(500, "PIN řidiče je v konfiguraci neplatný.")

    identity = Identity(id=user.user_id, name=user.name, role=user.role, expires_at=current_utc())
    days = settings.owner_session_days if user.role == "owner" else settings.employee_session_days
    response.headers["Cache-Control"] = "no-store"
    return _set_session_cookie(response, identity, days)


@app.post("/api/auth/logout")
def logout(response: Response):
    response.delete_cookie(key=settings.session_cookie_name, path="/")
    return {"status": "ok"}


@app.get("/api/employees", response_model=list[EmployeeOut])
def list_employees(_identity: Identity = Depends(owner_only), db: Session = Depends(get_db)):
    query = select(UserAccount).where(UserAccount.role == "employee", UserAccount.is_active.is_(True)).order_by(UserAccount.created_at.desc())
    return db.scalars(query).all()


@app.post("/api/employees", response_model=EmployeeOut, status_code=201)
def create_employee(payload: EmployeeCreateRequest, _identity: Identity = Depends(owner_only), db: Session = Depends(get_db)):
    pin_hash = hash_password(payload.pin)
    existing_pin = db.scalar(select(UserAccount).where(UserAccount.pin_hash == pin_hash, UserAccount.is_active.is_(True)))
    if existing_pin:
        raise HTTPException(409, "Tento PIN už používá jiný účet.")

    base_id = normalize_employee_id(payload.name) or "ridic"
    candidate = base_id
    suffix = 2
    while db.scalar(select(UserAccount.id).where(UserAccount.user_id == candidate)):
        candidate = f"{base_id}-{suffix}"
        suffix += 1

    employee = UserAccount(user_id=candidate, name=payload.name.strip(), role="employee", pin_hash=pin_hash, is_active=True)
    db.add(employee)
    db.commit()
    db.refresh(employee)
    return employee


@app.delete("/api/employees/{user_id}", status_code=204)
def delete_employee(user_id: str, _identity: Identity = Depends(owner_only), db: Session = Depends(get_db)):
    employee = db.scalar(select(UserAccount).where(UserAccount.user_id == user_id, UserAccount.role == "employee", UserAccount.is_active.is_(True)))
    if not employee:
        raise HTTPException(404, "Řidič nebyl nalezen.")
    employee.is_active = False
    db.commit()
    return Response(status_code=204)


@app.get("/api/dashboard")
def dashboard(_identity: Identity = Depends(owner_only), db: Session = Depends(get_db)):
    statuses = dict(db.execute(select(Document.status, func.count(Document.id)).group_by(Document.status)).all())
    dispatchers = dict(db.execute(select(Document.dispatcher, func.count(Document.id)).where(Document.dispatcher.is_not(None)).group_by(Document.dispatcher)).all())
    tax_total = db.scalar(select(func.coalesce(func.sum(Document.gross_amount), 0)).where(Document.document_type == "tax", Document.status.in_(["approved", "exported"])))
    return {
        "documents_total": db.scalar(select(func.count(Document.id))),
        "matched": statuses.get("matched", 0) + statuses.get("approved", 0) + statuses.get("exported", 0),
        "needs_review": statuses.get("needs_review", 0),
        "approved_tax_total": float(tax_total or 0),
        "by_dispatcher": dispatchers,
        "automation_rate": round(100 * (statuses.get("matched", 0) + statuses.get("approved", 0) + statuses.get("exported", 0)) / max(sum(statuses.values()), 1)),
    }


@app.get("/api/documents", response_model=list[DocumentOut])
def list_documents(
    dispatcher: str | None = None,
    status: str | None = None,
    document_type: str | None = Query(default=None, alias="type"),
    search: str | None = None,
    _identity: Identity = Depends(owner_only),
    db: Session = Depends(get_db),
):
    query = select(Document).order_by(Document.created_at.desc())
    if dispatcher:
        query = query.where(Document.dispatcher == dispatcher)
    if status:
        query = query.where(Document.status == status)
    if document_type:
        query = query.where(Document.document_type == document_type)
    if search:
        term = f"%{search.strip()}%"
        query = query.where((Document.original_name.ilike(term)) | (Document.cmr_number.ilike(term)) | (Document.supplier.ilike(term)))
    return db.scalars(query).all()


@app.get("/api/me/documents", response_model=list[EmployeeDocumentOut])
def my_documents(
    date_from: date | None = None,
    date_to: date | None = None,
    identity: Identity = Depends(current_identity),
    db: Session = Depends(get_db),
):
    query = select(Document).where(Document.uploaded_by == identity.name).order_by(Document.created_at.desc())
    if date_from:
        query = query.where(func.date(Document.created_at) >= date_from)
    if date_to:
        query = query.where(func.date(Document.created_at) <= date_to)
    return db.scalars(query).all()


@app.get("/api/documents/{document_id}")
def get_document(document_id: int, _identity: Identity = Depends(owner_only), db: Session = Depends(get_db)):
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(404, "Doklad nebyl nalezen.")
    result = DocumentOut.model_validate(document).model_dump(mode="json")
    result["transport"] = _transport_out(document.transport).model_dump(mode="json") if document.transport else None
    result["audit_events"] = [{"action": event.action, "actor": event.actor, "details": event.details, "created_at": event.created_at} for event in document.audit_events]
    return result


@app.patch("/api/documents/{document_id}", response_model=DocumentOut)
def update_document(document_id: int, update: DocumentUpdate, identity: Identity = Depends(owner_only), db: Session = Depends(get_db)):
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(404, "Doklad nebyl nalezen.")
    changes = update.model_dump(exclude_unset=True)
    if "gross_amount" in changes and "net_amount" in changes and changes.get("gross_amount") is not None and changes.get("net_amount") is not None:
        if changes["gross_amount"] < changes["net_amount"]:
            raise HTTPException(422, "Částka s DPH nesmí být nižší než základ daně.")
    for field, value in changes.items():
        setattr(document, field, value)
    if document.document_type == "cmr" and "cmr_number" in changes:
        transport = find_transport(db, document.cmr_number)
        document.transport = transport
        if transport:
            document.dispatcher = assign_dispatcher(db, transport)
            if document.status in {"received", "processing", "needs_review"}:
                document.status = "matched"
    _audit(db, document, "document_updated", identity.name, changes)
    db.commit()
    db.refresh(document)
    return document


@app.delete("/api/documents/{document_id}", status_code=204)
def delete_document(document_id: int, _identity: Identity = Depends(owner_only), db: Session = Depends(get_db)):
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(404, "Doklad nebyl nalezen.")

    stored_path = settings.storage_path / document.stored_name
    if stored_path.exists():
        stored_path.unlink()

    db.delete(document)
    db.commit()
    return Response(status_code=204)


@app.post("/api/documents/upload", response_model=list[DocumentOut], status_code=201)
async def upload_documents(
    files: list[UploadFile] = File(...),
    dispatcher: str | None = Form(default=None),
    identity: Identity = Depends(current_identity),
    db: Session = Depends(get_db),
):
    if not files or len(files) > 20:
        raise HTTPException(400, "Nahrajte 1 až 20 souborů.")
    created: list[Document] = []
    for upload in files:
        content_type = upload.content_type or mimetypes.guess_type(upload.filename or "")[0] or "application/octet-stream"
        if content_type not in ALLOWED_DOCUMENT_TYPES:
            raise HTTPException(415, f"Soubor {upload.filename} nemá podporovaný formát.")
        content = await upload.read(MAX_DOCUMENT_SIZE + 1)
        if len(content) > MAX_DOCUMENT_SIZE:
            raise HTTPException(413, f"Soubor {upload.filename} překračuje limit 15 MB.")
        suffix = Path(upload.filename or "document").suffix.lower()
        stored_name = f"{uuid.uuid4().hex}{suffix}"
        (settings.storage_path / stored_name).write_bytes(content)
        try:
            backup_uri = upload_document_backup(settings, stored_name, content_type, content)
        except CloudBackupError as exc:
            if settings.google_cloud_storage_backup_required:
                raise HTTPException(502, str(exc)) from exc
            backup_uri = None
        assigned_dispatcher = dispatcher if identity.role == "owner" else identity.name
        document = Document(original_name=upload.filename or stored_name, stored_name=stored_name, mime_type=content_type, status="processing", dispatcher=assigned_dispatcher, uploaded_by=identity.name)
        db.add(document)
        db.flush()
        _audit(
            db,
            document,
            "uploaded",
            identity.name,
            {
                "backup_uri": backup_uri,
                "backup_required": settings.google_cloud_storage_backup_required,
                "backup_timestamp": backup_timestamp_iso() if backup_uri else None,
            },
        )
        try:
            result = extract_document(settings, document.original_name, content_type, content)
            for field in ("document_type", "confidence", "cmr_number", "issue_date", "supplier", "net_amount", "vat_amount", "vat_rate", "gross_amount"):
                setattr(document, field, getattr(result, field))
            if result.document_type == "cmr":
                transport = find_transport(db, result.cmr_number)
                document.transport = transport
                if transport:
                    document.dispatcher = assign_dispatcher(db, transport) or assigned_dispatcher
                    document.status = "matched" if result.confidence >= Decimal("0.80") else "needs_review"
                else:
                    document.status = "needs_review"
            else:
                document.status = "needs_review" if result.confidence < Decimal("0.93") else "approved"
            _audit(db, document, "ai_extracted", details={"provider": settings.document_ai_provider, "confidence": result.confidence})
        except DocumentExtractionError as exc:
            document.status = "needs_review"
            document.note = str(exc)
            _audit(db, document, "ai_failed", details={"error": str(exc)})
        created.append(document)
    db.commit()
    for document in created:
        db.refresh(document)
    return created


COLUMN_ALIASES = {
    "cmr_number": {"cmr", "cislo cmr", "číslo cmr", "cmr number"},
    "transport_date": {"datum", "datum prepravy", "datum přepravy", "date"},
    "driver_name": {"ridic", "řidič", "jmeno ridice", "driver"},
    "license_plate": {"spz", "rz", "license plate"},
    "route": {"trasa", "route"},
    "transport_price": {"cena", "cena prepravy", "cena přepravy", "price"},
    "currency": {"mena", "měna", "currency"},
    "dispatcher": {"dispecer", "dispečer", "dispatcher"},
}


def _column_map(columns) -> dict[str, str]:
    normalized = {str(column).strip().lower(): str(column) for column in columns}
    return {target: normalized[alias] for target, aliases in COLUMN_ALIASES.items() for alias in aliases if alias in normalized}


@app.post("/api/transports/import")
async def import_transports(file: UploadFile = File(...), _identity: Identity = Depends(owner_only), db: Session = Depends(get_db)):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".xlsx", ".xls", ".csv"}:
        raise HTTPException(415, "Použijte Excel (.xlsx/.xls) nebo CSV soubor.")
    content = await file.read(25 * 1024 * 1024 + 1)
    if len(content) > 25 * 1024 * 1024:
        raise HTTPException(413, "Soubor překračuje limit 25 MB.")
    try:
        frame = pd.read_csv(io.BytesIO(content), sep=None, engine="python") if suffix == ".csv" else pd.read_excel(io.BytesIO(content))
    except Exception as exc:
        raise HTTPException(422, f"Tabulku nelze načíst: {exc}") from exc
    columns = _column_map(frame.columns)
    if "cmr_number" not in columns:
        raise HTTPException(422, "Tabulka musí obsahovat sloupec CMR / Číslo CMR.")
    imported = updated = skipped = 0
    for _, row in frame.iterrows():
        raw_cmr = row.get(columns["cmr_number"])
        if pd.isna(raw_cmr) or not normalize(str(raw_cmr)):
            skipped += 1
            continue
        cmr_number = str(raw_cmr).strip()
        transport = find_transport(db, cmr_number)
        if transport:
            updated += 1
        else:
            transport = Transport(cmr_number=cmr_number, cmr_normalized=normalize(cmr_number))
            db.add(transport)
            imported += 1
        for field in ("driver_name", "license_plate", "route", "currency", "dispatcher"):
            if field in columns and not pd.isna(row.get(columns[field])):
                setattr(transport, field, str(row.get(columns[field])).strip())
        if "transport_date" in columns and not pd.isna(row.get(columns["transport_date"])):
            transport.transport_date = pd.to_datetime(row.get(columns["transport_date"]), dayfirst=True).date()
        if "transport_price" in columns and not pd.isna(row.get(columns["transport_price"])):
            try:
                transport.transport_price = Decimal(str(row.get(columns["transport_price"])).replace(" ", "").replace(",", "."))
            except InvalidOperation:
                pass
    db.commit()
    return {"imported": imported, "updated": updated, "skipped": skipped}


@app.get("/api/transports", response_model=list[TransportOut])
def list_transports(search: str | None = None, _identity: Identity = Depends(owner_only), db: Session = Depends(get_db)):
    query = select(Transport).order_by(Transport.transport_date.desc())
    if search:
        term = f"%{search.strip()}%"
        query = query.where((Transport.cmr_number.ilike(term)) | (Transport.driver_name.ilike(term)) | (Transport.license_plate.ilike(term)) | (Transport.route.ilike(term)))
    return [_transport_out(item) for item in db.scalars(query).unique().all()]


@app.get("/api/accounting/export.csv")
def accounting_export(identity: Identity = Depends(owner_only), db: Session = Depends(get_db)):
    documents = db.scalars(select(Document).where(Document.document_type == "tax", Document.status == "approved").order_by(Document.issue_date)).all()
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(["ID", "Datum vystavení", "Dodavatel", "Základ DPH", "DPH", "Sazba DPH", "Celkem", "Dispečer"])
    for item in documents:
        writer.writerow([item.id, item.issue_date or "", item.supplier or "", item.net_amount or "", item.vat_amount or "", item.vat_rate or "", item.gross_amount or "", item.dispatcher or ""])
        item.status = "exported"
        _audit(db, item, "accounting_exported", identity.name)
    db.commit()
    payload = "\ufeff" + output.getvalue()
    headers = {"Content-Disposition": f'attachment; filename="ucetnictvi-{date.today().isoformat()}.csv"'}
    return StreamingResponse(iter([payload.encode("utf-8")]), media_type="text/csv; charset=utf-8", headers=headers)
