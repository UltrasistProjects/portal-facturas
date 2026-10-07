from __future__ import annotations

import logging
import time
from datetime import datetime
from decimal import Decimal

from sqlalchemy import and_, delete, select
from sqlalchemy.orm import Session

from app.core.constants import DocumentType, ProcessingStatus, SupplierOrigin
from app.core.types import to_money
from app.models import Invoice, ValidationResult
from app.rules.contract_rules import contract_rules
from app.rules.date_rules import date_rules
from app.rules.document_rules import document_rules
from app.rules.financial_rules import financial_rules
from app.rules.international_rules import international_rules, invoice_duplicate_rule
from app.rules.semantic_rules import semantic_not_evaluated, semantic_outcomes
from app.rules.supplier_rules import supplier_rules
from app.rules.xml_rules import xml_rules
from app.services import (
    contract_requirements_service,
    foreign_invoice_service,
    supplier_requirements_service,
    validation_rules_service,
)
from app.services.ai import get_document_analyzer
from app.services.audit_service import audit
from app.services.document_requirements_service import required_types
from app.services.file_service import LocalFileStorage
from app.services.validation_score_service import calculate_score
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
    """Ejecuta las reglas y guarda sus resultados sin cambiar el estatus: decidir si la factura pasa a "Enviada" le
    corresponde al envio (submission_service). No hace commit: el llamador confirma la transaccion (y traduce una
    carrera sobre uq_invoices_uuid a 409)."""
    audit(db, "VALIDATION_STARTED", "Invoice", invoice.id, user_id)
    started = time.perf_counter()
    logger.info("validation.started", extra={"event": "validation.started", "invoice_id": invoice.id})
    documents = [d for d in invoice.documents if d.is_current]
    types = {d.document_type for d in documents}
    origin = invoice.supplier.origin
    # El Invoice del proveedor internacional no es un CFDI (HU-16): no se busca XML.
    international = origin == SupplierOrigin.INTERNATIONAL
    xml_document = (
        None
        if international
        else next((d for d in documents if d.document_type == DocumentType.INVOICE_XML.value), None)
    )
    xml_data, xml_error, duplicate_uuid = None, None, False
    # Reglas de Validacion del origen del proveedor (sin cache): las nacionales o las internacionales, nunca ambas.
    rules = validation_rules_service.rule_set(db, origin)
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
            # Solo una moneda activa del catalogo llega a la factura; otra la reporta XML-007.
            if xml_data.get("currency") in rules.currencies:
                invoice.currency = xml_data["currency"]
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
    # Requisitos de alta con la configuracion vigente (HU-21): solo los documentos del expediente, sin los de facturas.
    requirements = supplier_requirements_service.checklist(db, invoice.supplier)
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
    # Requisitos del contrato con la configuracion vigente (HU-22): solo los documentos del contrato.
    contract_pending = contract_requirements_service.pending_names(db, contract)
    required = required_types(db, origin)
    results += document_rules(types, required, origin, processable, contract_pending)
    xml_required = any(t.code == DocumentType.INVOICE_XML for t in required)
    results += xml_rules(xml_data, xml_error, rules, international=international, required=xml_required)
    results += supplier_rules(invoice.supplier, contract, requirements)
    results += contract_rules(invoice, contract, descriptions)
    results += date_rules(invoice)
    results += financial_rules(
        invoice, contract, xml_data, duplicate_uuid, duplicate_number, international=international
    )
    if international:
        # Texto del Invoice leido de nuevo (HU-16) y duplicado por nombre de archivo (FIN-007, HU-15).
        text = foreign_invoice_service.invoice_text(invoice)
        results += international_rules(text.text, text.readable, invoice.supplier, rules)
        filename = text.document.original_filename if text.document else None
        folios = foreign_invoice_service.duplicate_folios(db, invoice, filename) if filename else []
        results.append(invoice_duplicate_rule(filename, folios))
        results += semantic_not_evaluated()
    else:
        detected = " | ".join(descriptions)
        technology = contract.authorized_technology if contract else ""
        results += semantic_outcomes(get_document_analyzer().semantic_compare(technology, detected))
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
    return {**summary, "results": results, "xml": xml_data}
