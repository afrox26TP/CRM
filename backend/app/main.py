import csv
import io
import json
import mimetypes
import uuid
from contextlib import asynccontextmanager
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd
from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy import func, inspect, select, text
from sqlalchemy.orm import Session

from .auth import Identity, current_identity, owner_only
from .config import get_settings
from .database import Base, SessionLocal, engine, get_db
from .models import AssignmentRule, AuditEvent, Document, Transport
from .schemas import DocumentOut, DocumentUpdate, EmployeeDocumentOut, TransportOut
from .services.document_ai import DocumentExtractionError, extract_document
from .services.matching import assign_dispatcher, find_transport, normalize

settings = get_settings()
ALLOWED_DOCUMENT_TYPES = {"image/jpeg", "image/png", "image/webp", "application/pdf"}
MAX_DOCUMENT_SIZE = 15 * 1024 * 1024


def _seed(db: Session) -> None:
    if not db.scalar(select(func.count(Transport.id))):
        transports = [
            Transport(cmr_number="CMR-2026-001", cmr_normalized=normalize("CMR-2026-001"), transport_date=date(2026, 7, 28), driver_name="Petr Novák", license_plate="8AB 1234", route="Praha → Hamburg", transport_price=Decimal("28500"), currency="CZK", dispatcher="Tonda"),
            Transport(cmr_number="CMR-2026-002", cmr_normalized=normalize("CMR-2026-002"), transport_date=date(2026, 7, 29), driver_name="Milan Dvořák", license_plate="5AX 7788", route="Brno → Vídeň", transport_price=Decimal("920"), currency="EUR", dispatcher="Karel"),
            Transport(cmr_number="CMR-2026-003", cmr_normalized=normalize("CMR-2026-003"), transport_date=date(2026, 7, 30), driver_name="Jan Svoboda", license_plate="9AC 4210", route="Ostrava → Katovice", transport_price=Decimal("14600"), currency="CZK", dispatcher="Jarda"),
            Transport(cmr_number="CMR-2026-004", cmr_normalized=normalize("CMR-2026-004"), transport_date=date(2026, 7, 31), driver_name="Petr Novák", license_plate="8AB 1234", route="Hamburg → Praha", transport_price=Decimal("30100"), currency="CZK", dispatcher="Tonda"),
            Transport(cmr_number="CMR-2026-005", cmr_normalized=normalize("CMR-2026-005"), transport_date=date(2026, 8, 1), driver_name="Milan Dvořák", license_plate="5AX 7788", route="Brno → Bratislava", transport_price=Decimal("17800"), currency="CZK", dispatcher="Karel"),
            Transport(cmr_number="CMR-2026-006", cmr_normalized=normalize("CMR-2026-006"), transport_date=date(2026, 8, 2), driver_name="Jan Svoboda", license_plate="9AC 4210", route="Praha → Drážďany", transport_price=Decimal("795"), currency="EUR", dispatcher="Jarda"),
        ]
        db.add_all(transports)
        db.flush()
        demo_documents = [
            Document(original_name="CMR_2026_001.jpg", stored_name="demo-cmr-001.jpg", mime_type="image/jpeg", document_type="cmr", status="matched", cmr_number="CMR-2026-001", confidence=Decimal("0.97"), uploaded_by="Petr Novák", dispatcher="Tonda", transport_id=transports[0].id),
            Document(original_name="PHM_Benzina_28-07.jpg", stored_name="demo-phm-001.jpg", mime_type="image/jpeg", document_type="tax", status="needs_review", issue_date=date(2026, 7, 28), supplier="ORLEN Unipetrol RPA s.r.o.", net_amount=Decimal("4049.59"), vat_amount=Decimal("850.41"), vat_rate=Decimal("21"), gross_amount=Decimal("4900"), confidence=Decimal("0.88"), uploaded_by="Petr Novák", dispatcher="Tonda"),
            Document(original_name="CMR_2026_002.pdf", stored_name="demo-cmr-002.pdf", mime_type="application/pdf", document_type="cmr", status="approved", cmr_number="CMR-2026-002", confidence=Decimal("0.98"), uploaded_by="Milan Dvořák", dispatcher="Karel", transport_id=transports[1].id),
            Document(original_name="Uctenka_Shell.jpg", stored_name="demo-phm-002.jpg", mime_type="image/jpeg", document_type="tax", status="approved", issue_date=date(2026, 7, 29), supplier="Shell Czech Republic a.s.", net_amount=Decimal("2578.51"), vat_amount=Decimal("541.49"), vat_rate=Decimal("21"), gross_amount=Decimal("3120"), confidence=Decimal("0.95"), uploaded_by="Milan Dvořák", dispatcher="Karel"),
            Document(original_name="CMR_necitelne.jpg", stored_name="demo-cmr-review.jpg", mime_type="image/jpeg", document_type="cmr", status="needs_review", cmr_number="CMR-2026-099", confidence=Decimal("0.61"), uploaded_by="Jan Svoboda", dispatcher="Jarda"),
        ]
        db.add_all(demo_documents)
    if not db.scalar(select(func.count(AssignmentRule.id))):
        db.add_all([
            AssignmentRule(field="license_plate", pattern="8AB1234", dispatcher="Tonda", priority=10),
            AssignmentRule(field="license_plate", pattern="5AX7788", dispatcher="Karel", priority=10),
            AssignmentRule(field="license_plate", pattern="9AC4210", dispatcher="Jarda", priority=10),
        ])
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
        legacy_uploaders = {
            "demo-cmr-001.jpg": "Petr Novák", "demo-phm-001.jpg": "Petr Novák",
            "demo-cmr-002.pdf": "Milan Dvořák", "demo-phm-002.jpg": "Milan Dvořák",
            "demo-cmr-review.jpg": "Jan Svoboda",
        }
        for stored_name, employee in legacy_uploaders.items():
            document = db.scalar(select(Document).where(Document.stored_name == stored_name))
            if document and document.uploaded_by == "Neznámý zaměstnanec":
                document.uploaded_by = employee
        db.commit()
    yield


app = FastAPI(title="DokladFlow API", version="0.1.0", lifespan=lifespan)
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


@app.get("/api/health")
def health():
    return {"status": "ok", "provider": settings.document_ai_provider}


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
        assigned_dispatcher = dispatcher if identity.role == "owner" else None
        document = Document(original_name=upload.filename or stored_name, stored_name=stored_name, mime_type=content_type, status="processing", dispatcher=assigned_dispatcher, uploaded_by=identity.name)
        db.add(document)
        db.flush()
        _audit(db, document, "uploaded", identity.name)
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
