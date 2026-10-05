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
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.constants import FIXED_REQUIREMENTS, FORMAT_EXTENSIONS, DocumentRequirement, SupplierOrigin
from app.core.errors import BusinessRuleError, InvalidInputError, NotFoundError
from app.models import Document, Invoice, InvoiceDocumentType
from app.schemas import (
    INVALID_REQUIREMENT,
    DocumentTypeCreate,
    DocumentTypeUpdate,
    document_type_message,
    parse_requirement,
)
from app.services.audit_service import audit
from app.services.invoice_service import violates

# Clave del bloqueo consultivo que serializa las escrituras de la configuracion (pg_advisory_xact_lock).
CONFIG_LOCK_KEY = 4_0400_0001
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
MSG_SYSTEM_TYPE = "Los tipos de documento del sistema no se pueden editar ni desactivar"
MSG_NOT_FOUND = "Tipo de documento no encontrado"
MSG_SYSTEM_DELETE = "Los elementos del sistema no se pueden eliminar"
MSG_IN_USE = "El tipo ya tiene documentos cargados; desactívelo en su lugar"
MSG_NOT_OFFERED = "El tipo de documento no aplica a esta factura"


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


def fixed_requirement(code: str, origin: SupplierOrigin) -> DocumentRequirement | None:
    return FIXED_REQUIREMENTS.get(code, {}).get(origin)


def offered_types(db: Session, origin: SupplierOrigin) -> list[InvoiceDocumentType]:
    """Tipos que se ofrecen en la carga documental: activos y Obligatorios u Opcionales para el origen."""
    return [t for t in catalog(db) if t.is_active and requirement(t, origin) != DocumentRequirement.NOT_APPLICABLE]


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
    items = [ChecklistItem(t, requirement(t, origin), current.get(t.code)) for t in offered_types(db, origin)]
    return sorted(items, key=lambda item: item.level != DocumentRequirement.REQUIRED)


def pending_required(items: Iterable[ChecklistItem]) -> int:
    return sum(item.level == DocumentRequirement.REQUIRED and item.document is None for item in items)


def pending_label(pending: int) -> str:
    if pending == 0:
        return "Archivos obligatorios completos"
    if pending == 1:
        return "Falta 1 archivo obligatorio"
    return f"Faltan {pending} archivos obligatorios"


def offered_type(db: Session, invoice: Invoice, code: str) -> InvoiceDocumentType:
    """Tipo que se puede cargar en la factura; 400 si no existe, esta inactivo o no aplica al origen del proveedor."""
    offered = next((t for t in offered_types(db, invoice.supplier.origin) if t.code == code), None)
    if offered is None:
        raise InvalidInputError(MSG_NOT_OFFERED)
    _share_lock(db, InvoiceDocumentType, offered.id)
    return offered


def ensure_format(document_type: InvoiceDocumentType, filename: str | None) -> None:
    if not extension_allowed(document_type, filename):
        raise InvalidInputError(
            f"Formato no admitido para {document_type.name}. Formatos admitidos: {formats_label(document_type)}"
        )


# --- Escritura ----------------------------------------------------------------------------------------------------


def _lock(db: Session) -> None:
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": CONFIG_LOCK_KEY})


def _support_type(db: Session, type_id: int) -> InvoiceDocumentType:
    document_type = db.get(InvoiceDocumentType, type_id)
    if document_type is None:
        raise NotFoundError(MSG_NOT_FOUND)
    if document_type.is_system:
        raise BusinessRuleError(MSG_SYSTEM_TYPE)
    return document_type


def _in_use(db: Session, code: str) -> bool:
    return db.scalar(select(Document.id).where(Document.document_type == code).limit(1)) is not None


def _share_lock(db: Session, model, type_id: int) -> None:
    """Bloqueo compartido de la fila del tipo durante la carga: impide su eliminacion hasta el commit."""
    db.execute(select(model.id).where(model.id == type_id).with_for_update(key_share=True, read=True))


def _ensure_unique_name(db: Session, name: str, exclude_id: int | None = None) -> None:
    stmt = select(InvoiceDocumentType.id).where(func.lower(InvoiceDocumentType.name) == name.lower())
    if exclude_id is not None:
        stmt = stmt.where(InvoiceDocumentType.id != exclude_id)
    if db.scalar(stmt) is not None:
        raise BusinessRuleError(MSG_DUPLICATE_NAME)


def _flush(db: Session) -> None:
    """flush que traduce la unicidad del nombre a 409 (la BD es la autoridad aunque el servicio ya lo verifico)."""
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        if violates(exc, "uq_invoice_document_types_name_lower"):
            raise BusinessRuleError(MSG_DUPLICATE_NAME) from exc
        raise


def save_requirements(db: Session, form: Mapping[str, str], user_id: int) -> bool:
    """Guarda la matriz de niveles en una sola transaccion. True si hubo cambios; False si no habia nada que cambiar.

    Orden de las verificaciones: huella (409), niveles recibidos (400) y niveles fijos (409). Una pagina vieja puede
    carecer de un tipo nuevo, y "Recargue la pagina" es mas util que "falta un nivel". Los campos de claves
    desconocidas o de tipos inactivos se ignoran: no se escriben."""
    _lock(db)
    types = catalog(db)
    if form.get("config_version") != config_version(types):
        raise BusinessRuleError(MSG_CHANGED)
    received: dict[tuple[InvoiceDocumentType, SupplierOrigin], DocumentRequirement] = {}
    for document_type in (t for t in types if t.is_active):
        for origin in SupplierOrigin:
            value = form.get(f"{ORIGIN_KEYS[origin]}__{document_type.code}")
            if value is None:
                if fixed_requirement(document_type.code, origin) is None:
                    raise InvalidInputError(INVALID_REQUIREMENT)
                continue
            try:
                received[document_type, origin] = parse_requirement(value)
            except ValueError:
                raise InvalidInputError(INVALID_REQUIREMENT) from None
    for (document_type, origin), level in received.items():
        fixed = fixed_requirement(document_type.code, origin)
        if fixed is not None and level != fixed:
            plural = ORIGIN_PLURALS[origin]
            raise BusinessRuleError(f"{document_type.name} tiene un nivel fijo para proveedores {plural}")
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
    _lock(db)
    _ensure_unique_name(db, data.name)
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
    _flush(db)
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
    """Edita nombre, descripcion y formatos de un tipo soporte. True si hubo cambios. Los documentos ya cargados no
    cambian."""
    _lock(db)
    document_type = _support_type(db, type_id)
    try:
        data = DocumentTypeUpdate(name=name, description=description, formats=formats)
    except ValidationError as exc:
        raise InvalidInputError(document_type_message(exc)) from None
    _ensure_unique_name(db, data.name, exclude_id=document_type.id)
    old, new = {}, {}
    for field in ("name", "description", "formats"):
        before, after = getattr(document_type, field), getattr(data, field)
        if before != after:
            old[field], new[field] = before, after
    if not new:
        return False
    for field, value in new.items():
        setattr(document_type, field, value)
    _flush(db)
    audit(db, "INVOICE_DOCUMENT_TYPE_UPDATED", ENTITY, document_type.id, user_id, old, new)
    return True


def set_active(db: Session, type_id: int, user_id: int, active: bool) -> bool:
    """Desactiva o reactiva un tipo soporte con un estado destino explicito (no un conmutador). Conserva sus niveles."""
    _lock(db)
    document_type = _support_type(db, type_id)
    if document_type.is_active == active:
        return False
    document_type.is_active = active
    audit(
        db,
        "INVOICE_DOCUMENT_TYPE_STATUS_CHANGED",
        ENTITY,
        document_type.id,
        user_id,
        {"is_active": not active},
        {"is_active": active},
    )
    return True


def delete_type(db: Session, type_id: int, user_id: int) -> None:
    """Elimina un tipo soporte sin documentos. La fila se bloquea FOR UPDATE: una carga concurrente la
    tiene FOR KEY SHARE, asi que no queda un documento con la clave de un tipo eliminado. Con documentos (vigentes o
    reemplazados) responde 409 y sugiere desactivarlo."""
    _lock(db)
    document_type = db.get(InvoiceDocumentType, type_id, with_for_update=True)
    if document_type is None:
        raise NotFoundError(MSG_NOT_FOUND)
    if document_type.is_system:
        raise BusinessRuleError(MSG_SYSTEM_DELETE)
    if _in_use(db, document_type.code):
        raise BusinessRuleError(MSG_IN_USE)
    audit(
        db,
        "INVOICE_DOCUMENT_TYPE_DELETED",
        ENTITY,
        document_type.id,
        user_id,
        old={
            "code": document_type.code,
            "name": document_type.name,
            "description": document_type.description,
            "formats": document_type.formats,
            "is_active": document_type.is_active,
            "national": document_type.national_requirement.value,
            "international": document_type.international_requirement.value,
        },
    )
    db.delete(document_type)
    db.flush()
