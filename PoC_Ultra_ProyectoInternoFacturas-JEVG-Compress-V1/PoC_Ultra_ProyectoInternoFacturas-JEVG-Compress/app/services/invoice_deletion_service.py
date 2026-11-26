"""Eliminacion de una factura (spec flujo-facturas): la unica excepcion a la prohibicion de borrado fisico de facturas
(spec integridad-datos).

El Administrador elimina cualquier factura en cualquier estatus; el proveedor duenio, solo las suyas en "Borrador" o
"Cancelada"; el PMO, ninguna. Se borran la factura, sus
documentos (tambien su contenido en stored_files), sus resultados de validacion y sus revisiones. La bitacora conserva
las entradas de la factura y agrega INVOICE_DELETED con sus datos; el registro de correos tambien se conserva. El UUID y
el numero quedan libres: la misma factura se puede volver a registrar. El servicio no hace commit: el endpoint confirma
y despues borra los archivos del disco, de modo que un rollback no deja documentos sin archivo.
"""

import logging

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.core.constants import InvoiceStatus, Role
from app.core.errors import BusinessRuleError, InvalidInputError
from app.models import Document, FileContent, Invoice, Review, ValidationResult
from app.services.audit_service import audit
from app.services.invoice_service import lock_invoice

logger = logging.getLogger(__name__)

ENTITY = "Invoice"
# Estatus en que el proveedor elimina su factura; el Administrador no tiene esta restriccion.
DELETABLE_STATUSES = frozenset({InvoiceStatus.DRAFT, InvoiceStatus.CANCELLED})
MSG_NOT_DELETABLE = "Sólo se puede eliminar una factura en Borrador o Cancelada"
MSG_CONFIRM = "Confirme que desea eliminar la factura"


def may_delete(user) -> bool:
    """Roles que eliminan facturas: el Administrador y el proveedor (las suyas; la visibilidad la filtra el router)."""
    return user.role in (Role.ADMINISTRADOR, Role.PROVEEDOR)


def can_delete(user, invoice: Invoice) -> bool:
    """El detalle ofrece "Eliminar" al Administrador, en cualquier estatus, y al proveedor duenio de una factura en
    Borrador o Cancelada."""
    if user.role == Role.ADMINISTRADOR:
        return True
    return (
        user.role == Role.PROVEEDOR and invoice.supplier_id == user.supplier_id and invoice.status in DELETABLE_STATUSES
    )


def delete_invoice(db: Session, invoice: Invoice, user, confirmed: bool) -> list[str]:
    """Borra la factura y lo que depende de ella. Bloquea la fila antes de comprobar el estatus: un envio, una carga o
    una decision simultaneos terminan antes, y si el proveedor ya no puede eliminarla (dejo de estar en Borrador o
    Cancelada) responde 409; sin la confirmacion, 400. Devuelve las rutas relativas de sus archivos, que quien llama
    borra del disco despues del commit."""
    lock_invoice(db, invoice)
    if not can_delete(user, invoice):
        raise BusinessRuleError(MSG_NOT_DELETABLE)
    if not confirmed:
        raise InvalidInputError(MSG_CONFIRM)
    invoice_id = invoice.id
    paths = list(db.scalars(select(Document.path).where(Document.invoice_id == invoice_id)))
    snapshot = {
        "internal_folio": invoice.internal_folio,
        "invoice_number": invoice.invoice_number,
        "uuid": invoice.uuid,
        "status": invoice.status.value,
        "supplier_id": invoice.supplier_id,
        "total": str(invoice.total),
        "currency": invoice.currency,
        "documents": len(paths),
    }
    # Llaves foraneas RESTRICT: primero lo que apunta a la factura y, entre documentos, los reemplazos.
    db.execute(update(Document).where(Document.invoice_id == invoice_id).values(replaced_document_id=None))
    db.execute(delete(ValidationResult).where(ValidationResult.invoice_id == invoice_id))
    db.execute(delete(Review).where(Review.invoice_id == invoice_id))
    db.execute(delete(Document).where(Document.invoice_id == invoice_id))
    if paths:
        db.execute(delete(FileContent).where(FileContent.path.in_(paths)))
    # Sentencia DELETE explicita: el borrado por la unidad de trabajo del ORM sigue prohibido (before_flush).
    db.execute(delete(Invoice).where(Invoice.id == invoice_id), execution_options={"synchronize_session": False})
    db.expunge(invoice)
    audit(db, "INVOICE_DELETED", ENTITY, invoice_id, user.id, old=snapshot)
    logger.info(
        "invoice.deleted", extra={"event": "invoice.deleted", "invoice_id": invoice_id, "status": snapshot["status"]}
    )
    return paths
