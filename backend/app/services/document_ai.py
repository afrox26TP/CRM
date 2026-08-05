import hashlib
import re
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from ..config import Settings


@dataclass
class ExtractionResult:
    document_type: str
    confidence: Decimal
    cmr_number: str | None = None
    issue_date: date | None = None
    supplier: str | None = None
    net_amount: Decimal | None = None
    vat_amount: Decimal | None = None
    vat_rate: Decimal | None = None
    gross_amount: Decimal | None = None


class DocumentExtractionError(RuntimeError):
    pass


def _decimal(value: str | None) -> Decimal | None:
    if not value:
        return None
    cleaned = re.sub(r"[^0-9,.-]", "", value).replace(" ", "").replace(",", ".")
    try:
        return Decimal(cleaned)
    except Exception:
        return None


def _cmr_number_from_text(value: str) -> str | None:
    match = re.search(r"\bCMR\s*(?:NO\.?|NUMBER|ČÍSLO|CISLO|Č\.)?\s*[:#-]?\s*([A-Z0-9][A-Z0-9./-]{3,})", value, re.IGNORECASE)
    return match.group(1).strip(".-/") if match else None


def _mock_extract(filename: str, content: bytes) -> ExtractionResult:
    """Deterministic local demo; never presented as real OCR."""
    fingerprint = int(hashlib.sha256(content or filename.encode()).hexdigest()[:6], 16)
    lower = filename.lower()
    is_tax = any(word in lower for word in ("uct", "receipt", "fakt", "phm", "invoice", "tax"))
    if is_tax:
        gross = Decimal(500 + fingerprint % 9500).quantize(Decimal("0.01"))
        net = (gross / Decimal("1.21")).quantize(Decimal("0.01"))
        return ExtractionResult(
            document_type="tax",
            confidence=Decimal("0.91"),
            issue_date=date.today() - timedelta(days=fingerprint % 30),
            supplier="Čerpací stanice DEMO",
            net_amount=net,
            vat_amount=gross - net,
            vat_rate=Decimal("21"),
            gross_amount=gross,
        )
    match = re.search(r"(?:cmr[-_ ]*)?([0-9]{4})[-_ ]?([0-9]{3})", lower)
    cmr = f"CMR-{match.group(1)}-{match.group(2)}" if match else f"CMR-2026-{fingerprint % 6 + 1:03d}"
    return ExtractionResult(document_type="cmr", confidence=Decimal("0.94"), cmr_number=cmr)


def _google_extract(settings: Settings, mime_type: str, content: bytes) -> ExtractionResult:
    if not all((settings.google_cloud_project, settings.google_document_ai_processor_id)):
        raise DocumentExtractionError("Chybí GOOGLE_CLOUD_PROJECT nebo GOOGLE_DOCUMENT_AI_PROCESSOR_ID.")
    try:
        from google.api_core.client_options import ClientOptions
        from google.cloud import documentai

        endpoint = f"{settings.google_cloud_location}-documentai.googleapis.com"
        client = documentai.DocumentProcessorServiceClient(
            client_options=ClientOptions(api_endpoint=endpoint)
        )
        name = client.processor_path(
            settings.google_cloud_project,
            settings.google_cloud_location,
            settings.google_document_ai_processor_id,
        )
        request = documentai.ProcessRequest(
            name=name,
            raw_document=documentai.RawDocument(content=content, mime_type=mime_type),
        )
        document = client.process_document(request=request).document
    except Exception as exc:
        raise DocumentExtractionError(f"Google Document AI zpracování selhalo: {exc}") from exc

    entities = {entity.type_.lower(): entity for entity in document.entities}

    def text(*keys: str) -> str | None:
        entity = next((entities[key] for key in keys if key in entities), None)
        return entity.mention_text.strip() if entity and entity.mention_text else None

    def confidence(*keys: str) -> Decimal:
        entity = next((entities[key] for key in keys if key in entities), None)
        return Decimal(str(entity.confidence if entity else 0.5))

    cmr = text("cmr_number", "cmr", "document_number")
    has_tax_fields = any(key in entities for key in ("total_amount", "net_amount", "supplier_name"))
    if cmr and not has_tax_fields:
        return ExtractionResult(document_type="cmr", confidence=confidence("cmr_number", "cmr"), cmr_number=cmr)
    if not has_tax_fields:
        cmr = _cmr_number_from_text(document.text or "")
        if cmr:
            return ExtractionResult(document_type="cmr", confidence=Decimal("0.75"), cmr_number=cmr)

    gross = _decimal(text("total_amount", "gross_amount"))
    net = _decimal(text("net_amount", "subtotal"))
    vat = _decimal(text("vat_amount", "total_tax_amount"))
    parsed_date = None
    raw_date = text("invoice_date", "issue_date", "receipt_date")
    if raw_date:
        try:
            from dateutil.parser import parse
            parsed_date = parse(raw_date, dayfirst=True).date()
        except ValueError:
            pass
    return ExtractionResult(
        document_type="tax",
        confidence=confidence("total_amount", "gross_amount"),
        issue_date=parsed_date,
        supplier=text("supplier_name", "vendor_name"),
        net_amount=net,
        vat_amount=vat,
        vat_rate=_decimal(text("vat_rate", "tax_rate")),
        gross_amount=gross,
    )


def extract_document(settings: Settings, filename: str, mime_type: str, content: bytes) -> ExtractionResult:
    if settings.document_ai_provider.lower() == "google":
        return _google_extract(settings, mime_type, content)
    return _mock_extract(filename, content)
