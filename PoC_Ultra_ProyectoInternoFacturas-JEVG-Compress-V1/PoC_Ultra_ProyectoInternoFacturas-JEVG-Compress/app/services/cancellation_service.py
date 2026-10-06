"""Cancelacion de la factura por el proveedor con su acuse (HU-14, RF-09; EP-01 DT-10).

Ningun servicio hace commit: el endpoint confirma la cancelacion y despues envia el correo a Recepcion de Facturas
(review_service.send_notification), de modo que un envio fallido no la revierte.
"""

import logging

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import DocumentType, InvoiceStatus, ProcessingStatus
from app.core.errors import BusinessRuleError, InvalidInputError
from app.models import Document, Invoice, InvoiceDocumentType
from app.services import document_requirements_service as requirements
from app.services.audit_service import audit
from app.services.file_service import LocalFileStorage, log_upload
from app.services.invoice_service import lock_invoice, transition_invoice

logger = logging.getLogger(__name__)

MSG_CONFIRM = "Confirme la cancelación"
MSG_ALREADY_CANCELLED = "La factura ya está cancelada"
MSG_PAID = "Una factura pagada no se puede cancelar"
ENTITY = "Invoice"


def acknowledgment_type(db: Session) -> InvoiceDocumentType:
    """Tipo del sistema "Acuse de cancelacion": su nombre y formatos viven en el catalogo (HU-04)."""
    return db.scalar(select(InvoiceDocumentType).where(InvoiceDocumentType.code == DocumentType.CANCELLATION_ACK))


def ensure_cancellable(invoice: Invoice) -> None:
    """Cancelada y Pagada son finales (409): una factura pagada no se cancela en el portal."""
    if invoice.status == InvoiceStatus.CANCELLED:
        raise BusinessRuleError(MSG_ALREADY_CANCELLED)
    if invoice.status == InvoiceStatus.PAID:
        raise BusinessRuleError(MSG_PAID)


def check_request(db: Session, invoice: Invoice, confirmed: bool, filename: str | None) -> None:
    """Antes de leer o escribir el archivo: confirmacion, acuse y formato, en ese orden (400). Un formulario viejo
    sobre una factura ya cancelada o pagada responde 409 (cancel lo vuelve a comprobar con la fila bloqueada)."""
    ensure_cancellable(invoice)
    if not confirmed:
        raise InvalidInputError(MSG_CONFIRM)
    ack = acknowledgment_type(db)
    if not filename:
        raise InvalidInputError(f"Cargue el {ack.name}")
    requirements.ensure_format(ack, filename)


async def cancel(db: Session, invoice: Invoice, upload: UploadFile, user_id: int) -> Document:
    """Cancela la factura con su acuse. Bloquea la fila antes de comprobar el estatus: de dos cancelaciones
    simultaneas, la segunda encuentra la factura cancelada (409) sin escribir su archivo. Un archivo vacio, demasiado
    grande o cuyo contenido no corresponde a la extension es InvalidInputError (400) y nada cambia."""
    lock_invoice(db, invoice)
    ensure_cancellable(invoice)
    previous_status = invoice.status
    try:
        stored = await LocalFileStorage().save_invoice_file(invoice.id, upload)
    except ValueError as exc:
        raise InvalidInputError(str(exc)) from None
    # El acuse XML del SAT no es un CFDI: no se procesa ni se extraen metadatos.
    document = Document(
        invoice_id=invoice.id,
        supplier_id=invoice.supplier_id,
        document_type=DocumentType.CANCELLATION_ACK.value,
        original_filename=stored.original_filename,
        stored_filename=stored.stored_filename,
        path=stored.relative_path,
        mime_type=stored.mime_type,
        file_size=stored.file_size,
        sha256=stored.sha256,
        uploaded_by=user_id,
        processing_status=ProcessingStatus.PROCESSED,
        metadata_json={},
    )
    db.add(document)
    transition_invoice(db, invoice, InvoiceStatus.CANCELLED, user_id)
    db.flush()
    log_upload(DocumentType.CANCELLATION_ACK.value, stored, invoice_id=invoice.id)
    audit(
        db,
        "INVOICE_CANCELLED",
        ENTITY,
        invoice.id,
        user_id,
        old={"status": previous_status.value},
        new={"document_id": document.id, "deadline": invoice.cancellation_deadline.isoformat()},
    )
    logger.info("invoice.cancelled", extra={"event": "invoice.cancelled", "invoice_id": invoice.id})
    return document
