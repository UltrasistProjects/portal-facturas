"""Factura del proveedor internacional (HU-15 y HU-16): datos del Invoice capturados por el proveedor, duplicado por
nombre de archivo y texto del Invoice para las reglas INT.

Sin commit: el endpoint confirma la transaccion (y con ella libera el bloqueo consultivo por proveedor).
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from pydantic import ValidationError
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.constants import CatalogType, DocumentType, InvoiceStatus, SupplierOrigin
from app.core.errors import BusinessRuleError
from app.core.types import to_money
from app.models import Document, Invoice
from app.schemas import FIELD_LABELS, ForeignInvoiceData, validation_messages
from app.services import catalog_service
from app.services.file_service import LocalFileStorage
from app.services.pdf_service import analyze_pdf

# Bloqueo consultivo de dos enteros (clave, proveedor): serializa las cargas de Invoice de un mismo proveedor, de modo
# que dos cargas concurrentes con el mismo nombre de archivo no pasen ambas el control de duplicados.
FOREIGN_INVOICE_LOCK_KEY = 15_1500_0001
FIELDS = ("invoice_date", "subtotal", "tax", "total", "currency")
MSG_INACTIVE_CURRENCY = f"{FIELD_LABELS['currency']}: la clave no está activa en el catálogo"
MSG_NOT_INTERNATIONAL = "La factura no es de un proveedor internacional"
CURRENCY_CODE = re.compile(r"[A-Z]{3}")


def is_international(invoice: Invoice) -> bool:
    return invoice.supplier.origin == SupplierOrigin.INTERNATIONAL


# --- Datos del Invoice (HU-15) ------------------------------------------------------------------------------------


def form_values(invoice: Invoice) -> dict[str, str]:
    """Valores de la factura para prellenar el formulario de los datos del Invoice."""
    return {
        "invoice_date": invoice.invoice_date.isoformat() if invoice.invoice_date else "",
        "subtotal": f"{invoice.subtotal:.2f}",
        "tax": f"{invoice.tax:.2f}",
        "total": f"{invoice.total:.2f}",
        "currency": invoice.currency,
    }


def parse_data(db: Session, values: Mapping[str, str]) -> tuple[ForeignInvoiceData | None, list[str]]:
    """Datos del Invoice validados, o None y todos los errores juntos: los del esquema y la moneda inactiva."""
    data, errors = None, []
    try:
        data = ForeignInvoiceData(**{field: values.get(field, "") for field in FIELDS})
    except ValidationError as exc:
        errors = validation_messages(exc)
    currency = str(values.get("currency") or "").strip().upper()
    if CURRENCY_CODE.fullmatch(currency) and currency not in catalog_service.active_codes(db, CatalogType.CURRENCY):
        errors.append(MSG_INACTIVE_CURRENCY)
    return (None if errors else data), errors


def _audit_text(value) -> str | None:
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    if isinstance(value, date):
        return value.isoformat()
    return value


def apply_data(invoice: Invoice, data: ForeignInvoiceData) -> tuple[dict, dict]:
    """Asigna los datos a la factura y devuelve (anteriores, nuevos) de los campos que cambiaron, como texto."""
    values = {
        "invoice_date": data.invoice_date,
        "subtotal": to_money(data.subtotal),
        "tax": to_money(data.tax),
        "total": to_money(data.total),
        "currency": data.currency,
    }
    old, new = {}, {}
    for field, value in values.items():
        current = getattr(invoice, field)
        if current != value:
            old[field], new[field] = _audit_text(current), _audit_text(value)
            setattr(invoice, field, value)
    return old, new


# --- Duplicado por nombre de archivo (HU-15) ----------------------------------------------------------------------


def lock_supplier(db: Session, supplier_id: int) -> None:
    db.execute(
        text("SELECT pg_advisory_xact_lock(CAST(:key AS integer), CAST(:supplier AS integer))"),
        {"key": FOREIGN_INVOICE_LOCK_KEY, "supplier": supplier_id},
    )


def duplicate_folios(db: Session, invoice: Invoice, filename: str) -> list[str]:
    """Folios de las otras facturas no canceladas del proveedor con un Invoice vigente del mismo nombre de archivo
    (sin distinguir mayusculas ni espacios de los extremos). Una factura cancelada libera el nombre (HU-14)."""
    return list(
        db.scalars(
            select(Invoice.internal_folio)
            .join(Document, Document.invoice_id == Invoice.id)
            .where(
                Invoice.supplier_id == invoice.supplier_id,
                Invoice.id != invoice.id,
                Invoice.status != InvoiceStatus.CANCELLED,
                Document.document_type == DocumentType.FOREIGN_INVOICE.value,
                Document.is_current.is_(True),
                func.lower(func.trim(Document.original_filename)) == filename.strip().lower(),
            )
            .distinct()
            .order_by(Invoice.internal_folio)
        )
    )


def ensure_unique_filename(db: Session, invoice: Invoice, filename: str) -> None:
    """Antes de escribir el archivo: 409 si otra factura del proveedor ya tiene un Invoice con ese nombre."""
    lock_supplier(db, invoice.supplier_id)
    folios = duplicate_folios(db, invoice, filename)
    if folios:
        name = filename.strip()
        raise BusinessRuleError(f"Ya existe una factura con un Invoice llamado «{name}»: {', '.join(folios)}")


# --- Texto del Invoice (HU-16) ------------------------------------------------------------------------------------


@dataclass(frozen=True)
class InvoiceText:
    document: Document | None
    text: str
    readable: bool


def current_invoice_document(invoice: Invoice) -> Document | None:
    return next(
        (d for d in invoice.documents if d.is_current and d.document_type == DocumentType.FOREIGN_INVOICE.value), None
    )


def invoice_text(invoice: Invoice) -> InvoiceText:
    """Texto completo del Invoice vigente, leido de nuevo: metadata_json solo guarda un extracto (D7)."""
    document = current_invoice_document(invoice)
    if document is None:
        return InvoiceText(None, "", False)
    try:
        pdf = analyze_pdf(LocalFileStorage().resolve(document.path))
    except (ValueError, FileNotFoundError):
        return InvoiceText(document, "", False)
    return InvoiceText(document, pdf["text"], bool(pdf["has_extractable_text"]))
