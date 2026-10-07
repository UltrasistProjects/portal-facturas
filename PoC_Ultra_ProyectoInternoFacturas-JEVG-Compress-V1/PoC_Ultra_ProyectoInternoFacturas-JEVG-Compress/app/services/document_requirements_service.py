"""Archivos minimos por tipo de proveedor (HU-04).

Unico acceso al catalogo de tipos de documento de factura: lo usan la pantalla de administracion, la carga documental
y el motor de validacion. La configuracion se lee siempre de la base de datos, sin cache (RD-08). Toda escritura toma
un bloqueo consultivo de transaccion, de modo que la huella config_version no cambia entre su verificacion y la
actualizacion.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import (
    FORMAT_EXTENSIONS,
    PAYMENT_COMPLEMENT_TYPES,
    DocumentRequirement,
    InvoiceStatus,
    SupplierOrigin,
)
from app.core.errors import BusinessRuleError, InvalidInputError
from app.models import Document, Invoice, InvoiceDocumentType
from app.schemas import (
    INVALID_REQUIREMENT,
    DocumentTypeCreate,
    DocumentTypeUpdate,
    document_type_message,
    parse_requirement,
)
from app.services.audit_service import audit
from app.services.type_catalog import TypeCatalog, share_lock

ENTITY = "InvoiceDocumentType"
LEVEL_FIELDS = {
    SupplierOrigin.NATIONAL: "national_requirement",
    SupplierOrigin.INTERNATIONAL: "international_requirement",
}
# Prefijo de los campos de la matriz y clave del origen en la auditoria.
ORIGIN_KEYS = {SupplierOrigin.NATIONAL: "national", SupplierOrigin.INTERNATIONAL: "international"}
ORIGIN_PLURALS = {SupplierOrigin.NATIONAL: "nacionales", SupplierOrigin.INTERNATIONAL: "internacionales"}

MSG_CHANGED = "La configuración cambió mientras la editaba. Recargue la página."
MSG_DUPLICATE_NAME = "Ya existe un tipo de documento con ese nombre"
MSG_NOT_FOUND = "Tipo de documento no encontrado"
MSG_NOT_OFFERED = "El tipo de documento no aplica a esta factura"
# Bloqueo consultivo 4_0400_0001: serializa las escrituras de la configuracion (pg_advisory_xact_lock).
CATALOG = TypeCatalog(
    model=InvoiceDocumentType,
    entity=ENTITY,
    action_prefix="INVOICE_DOCUMENT_TYPE",
    lock_key=4_0400_0001,
    name_index="uq_invoice_document_types_name_lower",
    duplicate_message=MSG_DUPLICATE_NAME,
    not_found_message=MSG_NOT_FOUND,
)


# --- Lectura ------------------------------------------------------------------------------------------------------


def sort_key(document_type: InvoiceDocumentType) -> tuple:
    """Orden del catalogo: primero los tipos del sistema, en el orden de su siembra; despues los del Administrador,
    por nombre."""
    if document_type.is_system:
        return (0, document_type.id, "")
    return (1, 0, document_type.name.lower())


def catalog(db: Session) -> list[InvoiceDocumentType]:
    return sorted(db.scalars(select(InvoiceDocumentType)), key=sort_key)


def requirement(document_type: InvoiceDocumentType, origin: SupplierOrigin) -> DocumentRequirement:
    return getattr(document_type, LEVEL_FIELDS[origin])


def offered_types(db: Session, origin: SupplierOrigin) -> list[InvoiceDocumentType]:
    """Tipos que se ofrecen en la carga documental: activos y Obligatorios u Opcionales para el origen."""
    return [t for t in catalog(db) if t.is_active and requirement(t, origin) != DocumentRequirement.NOT_APPLICABLE]


def invoice_types(db: Session, invoice: Invoice) -> list[InvoiceDocumentType]:
    """Tipos que se ofrecen en la carga documental de la factura. Una factura "Pagada" solo admite su Complemento de
    Pago (HU Complemento de Pagos)."""
    types = offered_types(db, invoice.supplier.origin)
    if invoice.status == InvoiceStatus.PAID:
        return [t for t in types if t.code in PAYMENT_COMPLEMENT_TYPES]
    return types


def required_types(db: Session, origin: SupplierOrigin) -> list[InvoiceDocumentType]:
    """Tipos que exige la prevalidacion: activos y Obligatorios para el origen."""
    return [t for t in catalog(db) if t.is_active and requirement(t, origin) == DocumentRequirement.REQUIRED]


def type_names(db: Session) -> dict[str, str]:
    return {code: name for code, name in db.execute(select(InvoiceDocumentType.code, InvoiceDocumentType.name))}


def config_version(types: Iterable[InvoiceDocumentType]) -> str:
    """Huella de la configuracion mostrada: SHA-256 de la clave, los niveles y el estado activo de todos los tipos."""
    rows = sorted([t.code, t.national_requirement.value, t.international_requirement.value, t.is_active] for t in types)
    return hashlib.sha256(json.dumps(rows, separators=(",", ":")).encode()).hexdigest()


def formats_label(document_type: InvoiceDocumentType) -> str:
    return ", ".join(name for name in FORMAT_EXTENSIONS if name in document_type.formats)


def extensions(document_type: InvoiceDocumentType) -> list[str]:
    return [ext for name in FORMAT_EXTENSIONS if name in document_type.formats for ext in FORMAT_EXTENSIONS[name]]


def extension_allowed(document_type: InvoiceDocumentType, filename: str | None) -> bool:
    return Path(filename or "").suffix.lower() in extensions(document_type)


@dataclass
class ChecklistItem:
    document_type: InvoiceDocumentType
    level: DocumentRequirement
    document: Document | None


def checklist(db: Session, invoice: Invoice) -> list[ChecklistItem]:
    """Tipos ofrecidos a la factura con su documento vigente: primero los obligatorios, cada grupo en el orden del
    catalogo. Los documentos de tipos que ya no se ofrecen no aparecen (siguen en el detalle de la factura)."""
    origin = invoice.supplier.origin
    current = {d.document_type: d for d in invoice.documents if d.is_current}
    items = [ChecklistItem(t, requirement(t, origin), current.get(t.code)) for t in invoice_types(db, invoice)]
    return sorted(items, key=lambda item: item.level != DocumentRequirement.REQUIRED)


def pending_required(items: Iterable[ChecklistItem]) -> int:
    return sum(item.level == DocumentRequirement.REQUIRED and item.document is None for item in items)


def missing_required(db: Session, invoice: Invoice) -> list[InvoiceDocumentType]:
    """Tipos activos y Obligatorios para el origen del proveedor sin documento vigente, en el orden del catalogo: lo
    que impide enviar la factura a validacion. Un tipo eliminado no se exige."""
    present = {document.document_type for document in invoice.documents if document.is_current}
    return [t for t in required_types(db, invoice.supplier.origin) if t.code not in present]


def missing_message(types: Iterable[InvoiceDocumentType]) -> str:
    return f"Faltan archivos obligatorios: {', '.join(t.name for t in types)}. Cárguelos antes de enviar"


def pending_label(pending: int) -> str:
    if pending == 0:
        return "Archivos obligatorios completos"
    if pending == 1:
        return "Falta 1 archivo obligatorio"
    return f"Faltan {pending} archivos obligatorios"


def offered_type(db: Session, invoice: Invoice, code: str) -> InvoiceDocumentType:
    """Tipo que se puede cargar en la factura; 400 si no existe, esta inactivo o no aplica al origen del proveedor."""
    offered = next((t for t in invoice_types(db, invoice) if t.code == code), None)
    if offered is None:
        raise InvalidInputError(MSG_NOT_OFFERED)
    share_lock(db, InvoiceDocumentType, offered.id)
    return offered


def ensure_format(document_type: InvoiceDocumentType, filename: str | None) -> None:
    if not extension_allowed(document_type, filename):
        raise InvalidInputError(
            f"Formato no admitido para {document_type.name}. Formatos admitidos: {formats_label(document_type)}"
        )


# --- Escritura ----------------------------------------------------------------------------------------------------


def save_requirements(db: Session, form: Mapping[str, str], user_id: int) -> bool:
    """Guarda la matriz de niveles en una sola transaccion. True si hubo cambios; False si no habia nada que cambiar.

    Orden de las verificaciones: huella (409) y niveles recibidos (400). Una pagina vieja puede carecer de un tipo
    nuevo, y "Recargue la pagina" es mas util que "falta un nivel". Los campos de claves desconocidas o de tipos
    eliminados se ignoran: no se escriben."""
    CATALOG.lock(db)
    types = catalog(db)
    if form.get("config_version") != config_version(types):
        raise BusinessRuleError(MSG_CHANGED)
    received: dict[tuple[InvoiceDocumentType, SupplierOrigin], DocumentRequirement] = {}
    for document_type in (t for t in types if t.is_active):
        for origin in SupplierOrigin:
            try:
                received[document_type, origin] = parse_requirement(
                    form.get(f"{ORIGIN_KEYS[origin]}__{document_type.code}")
                )
            except ValueError:
                raise InvalidInputError(INVALID_REQUIREMENT) from None
    changed = {key: level for key, level in received.items() if requirement(*key) != level}
    if not changed:
        return False
    old: dict[str, dict[str, str]] = {}
    new: dict[str, dict[str, str]] = {}
    for (document_type, origin), level in changed.items():
        old.setdefault(document_type.code, {})[ORIGIN_KEYS[origin]] = requirement(document_type, origin).value
        new.setdefault(document_type.code, {})[ORIGIN_KEYS[origin]] = level.value
        setattr(document_type, LEVEL_FIELDS[origin], level)
    audit(db, "INVOICE_DOCUMENT_REQUIREMENTS_UPDATED", ENTITY, None, user_id, old, new)
    return True


def create_type(
    db: Session,
    user_id: int,
    name: str,
    description: str | None,
    formats: list[str],
    national_requirement: str,
    international_requirement: str,
) -> InvoiceDocumentType:
    """Alta de un tipo soporte. La clave SOPORTE_<id> se asigna tras el flush, como el folio interno de la factura."""
    try:
        data = DocumentTypeCreate(
            name=name,
            description=description,
            formats=formats,
            national_requirement=national_requirement,
            international_requirement=international_requirement,
        )
    except ValidationError as exc:
        raise InvalidInputError(document_type_message(exc)) from None
    CATALOG.lock(db)
    CATALOG.ensure_unique_name(db, data.name)
    created = InvoiceDocumentType(
        code=f"SOPORTE_PENDIENTE_{uuid4().hex}",
        name=data.name,
        description=data.description,
        formats=data.formats,
        is_system=False,
        is_active=True,
        national_requirement=data.national_requirement,
        international_requirement=data.international_requirement,
    )
    db.add(created)
    CATALOG.flush(db)
    created.code = f"SOPORTE_{created.id}"
    audit(
        db,
        "INVOICE_DOCUMENT_TYPE_CREATED",
        ENTITY,
        created.id,
        user_id,
        new={
            "code": created.code,
            "name": created.name,
            "formats": created.formats,
            "national": created.national_requirement.value,
            "international": created.international_requirement.value,
        },
    )
    return created


def update_type(
    db: Session, type_id: int, user_id: int, name: str, description: str | None, formats: list[str]
) -> bool:
    """Edita nombre, descripcion y formatos de cualquier tipo, del sistema o soporte. True si hubo cambios. La clave
    y los documentos ya cargados no cambian."""
    try:
        data = DocumentTypeUpdate(name=name, description=description, formats=formats)
    except ValidationError as exc:
        raise InvalidInputError(document_type_message(exc)) from None
    return CATALOG.update(db, type_id, user_id, data.model_dump())


def delete_type(db: Session, type_id: int, user_id: int) -> bool:
    """Baja logica de cualquier tipo, aunque tenga documentos: deja de ofrecerse y de exigirse."""
    return CATALOG.delete(db, type_id, user_id)


def restore_type(db: Session, type_id: int, user_id: int) -> bool:
    return CATALOG.restore(db, type_id, user_id)
