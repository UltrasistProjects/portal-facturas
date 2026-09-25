from __future__ import annotations

import logging
import time
from datetime import datetime
from decimal import Decimal

from sqlalchemy import and_, delete, select
from sqlalchemy.orm import Session

from app.core.constants import DocumentType, InvoiceStatus, ProcessingStatus
from app.core.types import to_money
from app.models import Document, Invoice, ValidationResult
from app.rules.contract_rules import contract_rules
from app.rules.date_rules import date_rules
from app.rules.document_rules import document_rules
from app.rules.financial_rules import financial_rules
from app.rules.semantic_rules import semantic_outcomes
from app.rules.supplier_rules import supplier_rules
from app.rules.xml_rules import xml_rules
from app.services.ai import get_document_analyzer
from app.services.audit_service import audit
from app.services.document_requirements_service import required_types
from app.services.file_service import LocalFileStorage
from app.services.invoice_service import transition_invoice
from app.services.supplier_service import supplier_requirement_status
from app.services.validation_score_service import calculate_score
from app.services.validation_settings_service import rule_parameters
from app.services.xml_service import XMLParseError, parse_cfdi

logger = logging.getLogger(__name__)


def _json_safe(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def uuid_owner(db: Session, uuid: str | None, invoice_id: int) -> int | None:
    """Id de otra factura que ya tiene ese UUID fiscal, si existe."""
    if not uuid:
        return None
    return db.scalar(select(Invoice.id).where(and_(Invoice.uuid == uuid, Invoice.id != invoice_id)))


def run_validation(db: Session, invoice: Invoice, user_id: int | None = None) -> dict:
    """Ejecuta las reglas y deja la factura en PREVALIDATED o REQUIRES_CORRECTION. No hace commit: el llamador
    confirma la transaccion (y traduce una carrera sobre uq_invoices_uuid a 409)."""
    if invoice.status in {InvoiceStatus.DRAFT, InvoiceStatus.REQUIRES_CORRECTION}:
        transition_invoice(db, invoice, InvoiceStatus.UPLOADED, user_id)
    transition_invoice(db, invoice, InvoiceStatus.VALIDATING, user_id)
    audit(db, "VALIDATION_STARTED", "Invoice", invoice.id, user_id)
    started = time.perf_counter()
    logger.info("validation.started", extra={"event": "validation.started", "invoice_id": invoice.id})
    documents = [d for d in invoice.documents if d.is_current]
    types = {d.document_type for d in documents}
    xml_document = next((d for d in documents if d.document_type == DocumentType.INVOICE_XML.value), None)
    xml_data, xml_error, duplicate_uuid = None, None, False
    if xml_document:
        try:
            xml_data = parse_cfdi(LocalFileStorage().resolve(xml_document.path))
            xml_document.processing_status = ProcessingStatus.PROCESSED
            xml_document.metadata_json = _json_safe(xml_data)
            # Se verifica antes de asignar: un UUID ajeno violaria uq_invoices_uuid. El detectado queda en
            # metadata_json del XML y FIN-004 lo reporta como bloqueo.
            duplicate_uuid = uuid_owner(db, xml_data.get("uuid"), invoice.id) is not None
            invoice.uuid = None if duplicate_uuid else xml_data.get("uuid")
            invoice.invoice_date = (
                datetime.fromisoformat(xml_data["date"]).date() if xml_data.get("date") else invoice.invoice_date
            )
            # El XSD admite hasta 6 decimales: se redondea a centavos de forma explicita; metadata_json del
            # documento XML conserva los importes originales.
            invoice.subtotal = to_money(xml_data.get("subtotal") or invoice.subtotal)
            invoice.tax = to_money(xml_data.get("tax") or invoice.tax)
            invoice.total = to_money(xml_data.get("total") or invoice.total)
            invoice.currency = xml_data.get("currency") or invoice.currency
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
            xml_error = str(exc)
            xml_document.processing_status = ProcessingStatus.FAILED
    processable = all(d.processing_status != ProcessingStatus.FAILED for d in documents)
    contract = invoice.contract
    requirements = supplier_requirement_status(
        invoice.supplier, [d for d in db.scalars(select(Document).where(Document.supplier_id == invoice.supplier_id))]
    )
    descriptions = [c.get("description") or "" for c in (xml_data or {}).get("concepts", [])]
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
    origin = invoice.supplier.origin
    results += document_rules(types, required_types(db, origin), origin, processable, bool(contract))
    # Reglas de Validacion vigentes (HU-06) y monedas activas (HU-07), sin cache, como los archivos minimos.
    results += xml_rules(xml_data, xml_error, rule_parameters(db))
    results += supplier_rules(invoice.supplier, contract, requirements)
    results += contract_rules(invoice, contract, descriptions)
    results += date_rules(invoice)
    results += financial_rules(invoice, contract, xml_data, duplicate_uuid, duplicate_number)
    detected = " | ".join(descriptions)
    semantic = get_document_analyzer().semantic_compare(contract.authorized_technology if contract else "", detected)
    results += semantic_outcomes(semantic)
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
                evidence_json=result.evidence,
            )
        )
    summary = calculate_score(results)
    invoice.validation_score = summary["score"]
    target = (
        InvoiceStatus.REQUIRES_CORRECTION if summary["blockers"] or summary["errors"] else InvoiceStatus.PREVALIDATED
    )
    transition_invoice(db, invoice, target, user_id)
    audit(db, "VALIDATION_COMPLETED", "Invoice", invoice.id, user_id, new=summary)
    logger.info(
        "validation.completed",
        extra={
            "event": "validation.completed",
            "invoice_id": invoice.id,
            "duration_ms": round((time.perf_counter() - started) * 1000, 1),
            "score": summary["score"],
            "blockers": summary["blockers"],
            "status": target.value,
        },
    )
    return {**summary, "results": results, "xml": xml_data}
