from __future__ import annotations

import logging
import time
from datetime import datetime
from decimal import Decimal

from sqlalchemy import and_, delete, select
from sqlalchemy.orm import Session

from app.core.constants import DocumentType, ProcessingStatus, SupplierOrigin
from app.core.types import to_money
from app.models import Document, Invoice, ValidationResult
from app.rules.date_rules import date_rules
from app.rules.document_rules import document_rules
from app.rules.financial_rules import financial_rules
from app.rules.international_rules import international_rules, invoice_duplicate_rule
from app.rules.purchase_order_rules import (
    captured_reference,
    detect_order_number,
    international_facts,
    national_facts,
    purchase_order_rules,
)
from app.rules.supplier_identity_rules import supplier_identity_rules
from app.rules.supplier_rules import supplier_rules
from app.rules.xml_rules import xml_rules
from app.services import (
    foreign_invoice_service,
    purchase_order_service,
    supplier_requirements_service,
    validation_rules_service,
)
from app.services import invoice_extraction_service as extraction
from app.services.audit_service import audit
from app.services.document_requirements_service import offered_types, required_types
from app.services.file_service import LocalFileStorage
from app.services.validation_score_service import calculate_score
from app.services.xml_service import XMLParseError, parse_cfdi

logger = logging.getLogger(__name__)
MSG_PDF_UNREADABLE = "No se pudieron leer los datos de la factura en el PDF. Adjunte el XML."
# Compatibilidad: la carga documental lo importaba de aqui.
_json_safe = extraction.json_safe


def uuid_owner(db: Session, uuid: str | None, invoice_id: int) -> int | None:
    """Id de otra factura que ya tiene ese UUID fiscal, si existe."""
    if not uuid:
        return None
    return db.scalar(select(Invoice.id).where(and_(Invoice.uuid == uuid, Invoice.id != invoice_id)))


def _current(invoice: Invoice, document_type: DocumentType) -> Document | None:
    return next((d for d in invoice.documents if d.is_current and d.document_type == document_type.value), None)


def _xml_data(invoice: Invoice, document: Document) -> tuple[dict | None, str | None]:
    """El XML vigente se lee de nuevo en cada validacion (como antes de HU-24)."""
    try:
        data = parse_cfdi(LocalFileStorage().resolve(document.path))
    except (XMLParseError, ValueError) as exc:
        logger.warning(
            "xml.parse_failed",
            extra={
                "event": "xml.parse_failed",
                "invoice_id": invoice.id,
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
        )
        document.processing_status = ProcessingStatus.FAILED
        return None, str(exc)
    document.processing_status = ProcessingStatus.PROCESSED
    document.metadata_json = extraction.xml_metadata(data)
    return data, None


def _pdf_data(document: Document) -> dict | None:
    """Datos del PDF guardados al registrarlo; un PDF cargado antes de HU-24 se lee ahora y se guardan."""
    metadata = document.metadata_json or {}
    if "invoice" not in metadata:
        try:
            analysis, data, source = extraction.read_pdf(LocalFileStorage().resolve(document.path))
        except (ValueError, FileNotFoundError):
            return None
        document.metadata_json = extraction.pdf_metadata(analysis, data, source)
        metadata = document.metadata_json
    data = metadata.get("invoice")
    return data if extraction.is_complete(data) else None


def invoice_data(invoice: Invoice) -> tuple[dict | None, str | None, str | None]:
    """(datos del comprobante, error, fuente) de una factura nacional: el XML vigente o, sin XML, los datos de su PDF
    (HU-24, D5)."""
    xml_document = _current(invoice, DocumentType.INVOICE_XML)
    if xml_document is not None:
        data, error = _xml_data(invoice, xml_document)
        return data, error, extraction.SOURCE_XML
    pdf_document = _current(invoice, DocumentType.INVOICE_PDF)
    if pdf_document is None:
        return None, None, None
    data = _pdf_data(pdf_document)
    if data is None:
        return None, MSG_PDF_UNREADABLE, None
    return data, None, data.get("source") or extraction.SOURCE_PDF_TEXT


def _money(value, default: Decimal) -> Decimal:
    # El XSD admite hasta 6 decimales: se redondea a centavos de forma explicita; metadata_json del documento conserva
    # los importes originales.
    return to_money(Decimal(str(value))) if value is not None else default


def apply_data(invoice: Invoice, data: dict, duplicate_uuid: bool, currencies) -> None:
    """Copia a la factura el UUID (si no es de otra factura), la fecha, los importes y la moneda del comprobante. Solo
    una moneda activa del catalogo llega a la factura; otra la reporta XML-007."""
    invoice.uuid = None if duplicate_uuid else data.get("uuid")
    if data.get("date"):
        invoice.invoice_date = datetime.fromisoformat(data["date"]).date()
    invoice.subtotal = _money(data.get("subtotal"), invoice.subtotal)
    invoice.tax = _money(data.get("tax"), invoice.tax)
    invoice.total = _money(data.get("total"), invoice.total)
    if data.get("currency") in currencies:
        invoice.currency = data["currency"]


def _xml_offered(db: Session, origin: SupplierOrigin) -> bool:
    return any(t.code == DocumentType.INVOICE_XML for t in offered_types(db, origin))


def identity_checks(db: Session, invoice: Invoice, stored: extraction.StoredData | None) -> list:
    """Validacion 1 del Paso 2 (HU-24, D6): PRV-001 a PRV-003 y las reglas del CFDI sobre los datos guardados, con las
    Reglas de Validacion y los catalogos vigentes. No guarda nada ni cambia el estatus."""
    origin = invoice.supplier.origin
    rules = validation_rules_service.rule_set(db, origin)
    data = stored.data if stored else None
    source = stored.source if stored else None
    document = "CFDI.xml" if source == extraction.SOURCE_XML else "CFDI.pdf"
    return supplier_identity_rules(data, invoice.supplier, rules.tax_regimes, source_document=document) + xml_rules(
        data, None, rules, required=_xml_offered(db, origin), source=source
    )


def _order_rules(db: Session, invoice: Invoice, data: dict | None, international: bool):
    """Validacion 2 (HU-24): la orden de compra citada en los conceptos (nacional) o capturada (internacional), leida
    con bloqueo de fila, y las otras facturas que la ocupan."""
    supplier = invoice.supplier
    if international:
        reference = captured_reference(invoice.purchase_order_number)
        facts = international_facts(invoice, supplier)
    else:
        concepts = (data or {}).get("concepts") or []
        reference = detect_order_number(c.get("description") for c in concepts)
        facts = national_facts(data)
        if reference.number:
            invoice.purchase_order_number = reference.number
    order = purchase_order_service.find(db, reference.number, supplier)
    invoiced = purchase_order_service.active_invoices(db, order.id, invoice.id) if order else []
    view = purchase_order_service.view(order) if order else None
    return purchase_order_rules(facts, reference, view, invoiced, international), order


def run_validation(db: Session, invoice: Invoice, user_id: int | None = None) -> dict:
    """Ejecuta las reglas y guarda sus resultados sin cambiar el estatus: decidir si la factura pasa a "Enviada" le
    corresponde al envio (submission_service), que tambien liga la orden de compra que se devuelve en
    `purchase_order`. No hace commit: el llamador confirma la transaccion (y traduce una carrera sobre
    uq_invoices_uuid a 409)."""
    audit(db, "VALIDATION_STARTED", "Invoice", invoice.id, user_id)
    started = time.perf_counter()
    logger.info("validation.started", extra={"event": "validation.started", "invoice_id": invoice.id})
    documents = [d for d in invoice.documents if d.is_current]
    types = {d.document_type for d in documents}
    origin = invoice.supplier.origin
    # El Invoice del proveedor internacional no es un CFDI (HU-16): no se busca XML ni se leen datos del PDF.
    international = origin == SupplierOrigin.INTERNATIONAL
    # Reglas de Validacion del origen del proveedor (sin cache): las nacionales o las internacionales, nunca ambas.
    rules = validation_rules_service.rule_set(db, origin)
    data, error, source = (None, None, None) if international else invoice_data(invoice)
    xml_offered = not international and _xml_offered(db, origin)
    if error and source is None and not xml_offered:
        # PDF sin datos y el XML del CFDI fuera de los archivos ofrecidos: las reglas del CFDI no aplican.
        error = None
    duplicate_uuid = False
    if data is not None:
        # Se verifica antes de asignar: un UUID ajeno violaria uq_invoices_uuid. El detectado queda en metadata_json
        # del documento y FIN-004 lo reporta como bloqueo.
        duplicate_uuid = uuid_owner(db, data.get("uuid"), invoice.id) is not None
        apply_data(invoice, data, duplicate_uuid, rules.currencies)
    processable = all(d.processing_status != ProcessingStatus.FAILED for d in documents)
    # Requisitos de alta con la configuracion vigente (HU-21): solo los documentos del expediente, sin los de facturas.
    requirements = supplier_requirements_service.checklist(db, invoice.supplier)
    duplicate_number = bool(
        db.scalar(
            select(Invoice.id).where(
                and_(
                    Invoice.supplier_id == invoice.supplier_id,
                    Invoice.invoice_number == invoice.invoice_number,
                    Invoice.id != invoice.id,
                )
            )
        )
    )
    results = []
    # Configuracion vigente de archivos minimos, sin cache: la leida en esta prevalidacion queda en sus resultados.
    required = required_types(db, origin)
    results += document_rules(types, required, origin, processable)
    results += xml_rules(data, error, rules, international=international, required=xml_offered, source=source)
    document = "CFDI.xml" if source == extraction.SOURCE_XML else "CFDI.pdf"
    results += supplier_identity_rules(data, invoice.supplier, rules.tax_regimes, international, document)
    results += supplier_rules(invoice.supplier, requirements)
    results += date_rules(invoice)
    results += financial_rules(invoice, data, duplicate_uuid, duplicate_number, international=international)
    if international:
        # Texto del Invoice leido de nuevo (HU-16) y duplicado por nombre de archivo (FIN-007, HU-15).
        text = foreign_invoice_service.invoice_text(invoice)
        results += international_rules(text.text, text.readable, invoice.supplier, rules)
        filename = text.document.original_filename if text.document else None
        folios = foreign_invoice_service.duplicate_folios(db, invoice, filename) if filename else []
        results.append(invoice_duplicate_rule(filename, folios))
    order_results, order = _order_rules(db, invoice, data, international)
    results += order_results
    db.execute(delete(ValidationResult).where(ValidationResult.invoice_id == invoice.id))
    for result in results:
        db.add(
            ValidationResult(
                invoice_id=invoice.id,
                rule_code=result.rule_code,
                category=result.category,
                status=result.status,
                severity=result.severity,
                expected_value=result.expected_value,
                detected_value=result.detected_value,
                confidence=result.confidence,
                message=result.message,
                source_document=result.source_document,
                source_reference=result.source_reference,
                evidence_json=extraction.json_safe(result.evidence),
            )
        )
    summary = calculate_score(results)
    invoice.validation_score = summary["score"]
    audit(db, "VALIDATION_COMPLETED", "Invoice", invoice.id, user_id, new=summary)
    logger.info(
        "validation.completed",
        extra={
            "event": "validation.completed",
            "invoice_id": invoice.id,
            "duration_ms": round((time.perf_counter() - started) * 1000, 1),
            "score": summary["score"],
            "blockers": summary["blockers"],
            "failures": summary["errors"],
        },
    )
    return {**summary, "results": results, "xml": data, "purchase_order": order}
