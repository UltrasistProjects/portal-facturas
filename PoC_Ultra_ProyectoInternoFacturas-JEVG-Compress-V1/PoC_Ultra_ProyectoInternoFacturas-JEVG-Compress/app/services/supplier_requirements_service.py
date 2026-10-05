"""Requisitos de alta del proveedor (HU-21).

Unico acceso al catalogo de requisitos de alta (supplier_document_types): lo usan la pantalla de administracion, el
expediente, el listado de proveedores, la autorizacion y la regla SUP-003. Asi hay una sola definicion del expediente
minimo. La configuracion se lee siempre de la base de datos, sin cache. Toda escritura toma un bloqueo consultivo de
transaccion, de modo que la huella config_version no cambia entre su verificacion y la actualizacion.

Solo cuentan los documentos del expediente: vigentes (is_current) y sin factura (invoice_id nulo). Los documentos de
las facturas tambien guardan supplier_id y no cumplen requisitos de alta.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, timedelta
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.constants import (
    DATED_SUPPLIER_DOCUMENTS,
    FIXED_SUPPLIER_REQUIREMENTS,
    QUOTATION_DOCUMENT,
    REQUIREMENT_PROFILE_PLURALS,
    DocumentRequirement,
    RequirementProfile,
    SupplierOrigin,
    SupplierType,
)
from app.core.errors import BusinessRuleError, InvalidInputError, NotFoundError
from app.models import Document, Supplier, SupplierDocumentType
from app.schemas import (
    INVALID_REQUIREMENT,
    SupplierDocumentTypeCreate,
    SupplierDocumentTypeUpdate,
    document_type_message,
    parse_requirement,
)
from app.services.audit_service import audit
from app.services.invoice_service import violates

# Clave del bloqueo consultivo que serializa las escrituras de la configuracion (pg_advisory_xact_lock).
CONFIG_LOCK_KEY = 21_2100_0001
ENTITY = "SupplierDocumentType"
LEVEL_FIELDS = {profile: f"{profile.value}_requirement" for profile in RequirementProfile}
# Documentos con fecha de mas de tres meses: advertencia de vigencia (SUP-004), sin bloquear la autorizacion.
VALIDITY_DAYS = 93

MSG_CHANGED = "La configuración cambió mientras la editaba. Recargue la página."
MSG_DUPLICATE_NAME = "Ya existe un requisito con ese nombre"
MSG_SYSTEM_TYPE = "Los requisitos del sistema no se pueden editar ni desactivar"
MSG_NOT_FOUND = "Requisito no encontrado"
MSG_SYSTEM_DELETE = "Los elementos del sistema no se pueden eliminar"
MSG_IN_USE = "El tipo ya tiene documentos cargados; desactívelo en su lugar"
MSG_NOT_APPLICABLE = "El documento no aplica a este proveedor"
NOTE_QUOTATION = "Alta por cotización o licitación"
NOTE_QUOTATION_OPTIONAL = "Exigible si el alta es por cotización o licitación"


# --- Lectura ------------------------------------------------------------------------------------------------------


def profile(supplier: Supplier) -> RequirementProfile:
    """El internacional es un tipo propio sin importar su tipo de persona; el nacional, por persona moral o fisica."""
    if supplier.origin == SupplierOrigin.INTERNATIONAL:
        return RequirementProfile.INTERNATIONAL
    if supplier.supplier_type == SupplierType.PERSONA_FISICA:
        return RequirementProfile.PERSONA_FISICA
    return RequirementProfile.PERSONA_MORAL


def sort_key(document_type: SupplierDocumentType) -> tuple:
    """Orden del catalogo: primero los requisitos del sistema, en el orden de su siembra; despues los del
    Administrador, por nombre."""
    if document_type.is_system:
        return (0, document_type.id, "")
    return (1, 0, document_type.name.lower())


def catalog(db: Session) -> list[SupplierDocumentType]:
    return sorted(db.scalars(select(SupplierDocumentType)), key=sort_key)


def requirement(document_type: SupplierDocumentType, target: RequirementProfile) -> DocumentRequirement:
    return getattr(document_type, LEVEL_FIELDS[target])


def fixed_requirement(code: str, target: RequirementProfile) -> DocumentRequirement | None:
    """Nivel que el Administrador no puede cambiar: el Contrato se carga en cada contrato (HU-22)."""
    return FIXED_SUPPLIER_REQUIREMENTS.get(code, {}).get(target)


def applicable(types: Iterable[SupplierDocumentType], target: RequirementProfile) -> list[SupplierDocumentType]:
    """Requisitos que se piden al tipo de proveedor: activos y Obligatorios u Opcionales."""
    return [t for t in types if t.is_active and requirement(t, target) != DocumentRequirement.NOT_APPLICABLE]


def is_exigible(document_type: SupplierDocumentType, supplier: Supplier) -> bool:
    """Obligatorio para su tipo, o la propuesta economica de un alta por cotizacion o licitacion cuando aplica."""
    level = requirement(document_type, profile(supplier))
    if level == DocumentRequirement.REQUIRED:
        return True
    return (
        document_type.code == QUOTATION_DOCUMENT
        and bool(supplier.economic_proposal)
        and level != DocumentRequirement.NOT_APPLICABLE
    )


def config_version(types: Iterable[SupplierDocumentType]) -> str:
    """Huella de la configuracion mostrada: SHA-256 de la clave, los niveles y el estado activo de todos los
    requisitos."""
    rows = sorted([t.code, *(requirement(t, p).value for p in RequirementProfile), t.is_active] for t in types)
    return hashlib.sha256(json.dumps(rows, separators=(",", ":")).encode()).hexdigest()


def expedient_documents(db: Session, supplier_ids: Iterable[int]) -> dict[int, dict[str, Document]]:
    """Documentos vigentes del expediente por proveedor y tipo, en una consulta."""
    ids = list(supplier_ids)
    result: dict[int, dict[str, Document]] = {supplier_id: {} for supplier_id in ids}
    if not ids:
        return result
    stmt = select(Document).where(
        Document.supplier_id.in_(ids), Document.invoice_id.is_(None), Document.is_current.is_(True)
    )
    for document in db.scalars(stmt):
        result[document.supplier_id][document.document_type] = document
    return result


@dataclass
class RequirementRow:
    document_type: SupplierDocumentType
    level: DocumentRequirement
    exigible: bool
    document: Document | None
    expired: bool
    note: str | None


@dataclass
class OtherDocument:
    name: str
    document: Document


@dataclass
class Checklist:
    """Requisitos que aplican al proveedor (exigibles primero, cada grupo en el orden del catalogo) y los documentos
    vigentes de tipos que ya no aplican."""

    profile: RequirementProfile
    rows: list[RequirementRow]
    others: list[OtherDocument] = field(default_factory=list)

    @property
    def pending(self) -> list[RequirementRow]:
        return [row for row in self.rows if row.exigible and row.document is None]

    @property
    def has_exigible(self) -> bool:
        return any(row.exigible for row in self.rows)

    @property
    def label(self) -> str:
        if not self.rows:
            return f"Sin requisitos de alta configurados para {REQUIREMENT_PROFILE_PLURALS[self.profile]}"
        return pending_label(len(self.pending))


def pending_label(pending: int) -> str:
    if pending == 0:
        return "Requisitos de alta completos"
    if pending == 1:
        return "Falta 1 requisito obligatorio"
    return f"Faltan {pending} requisitos obligatorios"


def _expired(code: str, document: Document | None) -> bool:
    return bool(
        document
        and document.document_date
        and code in DATED_SUPPLIER_DOCUMENTS
        and document.document_date < date.today() - timedelta(days=VALIDITY_DAYS)
    )


def _note(document_type: SupplierDocumentType, supplier: Supplier, level: DocumentRequirement) -> str | None:
    if document_type.code != QUOTATION_DOCUMENT or level != DocumentRequirement.OPTIONAL:
        return None
    return NOTE_QUOTATION if supplier.economic_proposal else NOTE_QUOTATION_OPTIONAL


def build_checklist(
    types: list[SupplierDocumentType], supplier: Supplier, current: Mapping[str, Document]
) -> Checklist:
    target = profile(supplier)
    offered = applicable(types, target)
    rows = [
        RequirementRow(
            document_type=t,
            level=requirement(t, target),
            exigible=is_exigible(t, supplier),
            document=current.get(t.code),
            expired=_expired(t.code, current.get(t.code)),
            note=_note(t, supplier, requirement(t, target)),
        )
        for t in offered
    ]
    rows.sort(key=lambda row: not row.exigible)  # estable: conserva el orden del catalogo en cada grupo
    offered_codes = {t.code for t in offered}
    names = {t.code: t.name for t in types}
    others = [
        OtherDocument(names.get(code, code), document)
        for code, document in sorted(current.items(), key=lambda item: item[1].id)
        if code not in offered_codes
    ]
    return Checklist(target, rows, others)


def checklist(db: Session, supplier: Supplier) -> Checklist:
    return build_checklist(catalog(db), supplier, expedient_documents(db, [supplier.id])[supplier.id])


def pending_requirements(db: Session, suppliers: Iterable[Supplier]) -> dict[int, list[SupplierDocumentType]]:
    """Requisitos exigibles sin documento por proveedor: dos consultas para cualquier numero de proveedores."""
    suppliers = list(suppliers)
    types = catalog(db)
    documents = expedient_documents(db, [s.id for s in suppliers])
    return {s.id: [row.document_type for row in build_checklist(types, s, documents[s.id]).pending] for s in suppliers}


def applicable_type(db: Session, supplier: Supplier, code: str) -> SupplierDocumentType:
    """Requisito que se puede cargar en el expediente; 400 si no existe, esta inactivo o no aplica al proveedor."""
    found = next((t for t in applicable(catalog(db), profile(supplier)) if t.code == code), None)
    if found is None:
        raise InvalidInputError(MSG_NOT_APPLICABLE)
    _share_lock(db, SupplierDocumentType, found.id)
    return found


# --- Escritura ----------------------------------------------------------------------------------------------------


def _lock(db: Session) -> None:
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": CONFIG_LOCK_KEY})


def _admin_type(db: Session, type_id: int) -> SupplierDocumentType:
    document_type = db.get(SupplierDocumentType, type_id)
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
    stmt = select(SupplierDocumentType.id).where(func.lower(SupplierDocumentType.name) == name.lower())
    if exclude_id is not None:
        stmt = stmt.where(SupplierDocumentType.id != exclude_id)
    if db.scalar(stmt) is not None:
        raise BusinessRuleError(MSG_DUPLICATE_NAME)


def _flush(db: Session) -> None:
    """flush que traduce la unicidad del nombre a 409 (la BD es la autoridad aunque el servicio ya lo verifico)."""
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        if violates(exc, "uq_supplier_document_types_name_lower"):
            raise BusinessRuleError(MSG_DUPLICATE_NAME) from exc
        raise


def save_requirements(db: Session, form: Mapping[str, str], user_id: int) -> bool:
    """Guarda la matriz de niveles en una sola transaccion. True si hubo cambios; False si no habia nada que cambiar.

    Orden de las verificaciones, como en HU-04: huella (409), niveles recibidos (400) y niveles fijos (409). Una pagina
    vieja puede carecer de un requisito nuevo, y "Recargue la pagina" es mas util que "falta un nivel". Un nivel fijo
    puede faltar: la pagina no tiene selector para el. Los campos de claves desconocidas o de requisitos inactivos se
    ignoran."""
    _lock(db)
    types = catalog(db)
    if form.get("config_version") != config_version(types):
        raise BusinessRuleError(MSG_CHANGED)
    received: dict[tuple[SupplierDocumentType, RequirementProfile], DocumentRequirement] = {}
    for document_type in (t for t in types if t.is_active):
        for target in RequirementProfile:
            value = form.get(f"{target.value}__{document_type.code}")
            if value is None and fixed_requirement(document_type.code, target) is not None:
                continue
            try:
                received[document_type, target] = parse_requirement(value)
            except ValueError:
                raise InvalidInputError(INVALID_REQUIREMENT) from None
    for (document_type, target), level in received.items():
        fixed = fixed_requirement(document_type.code, target)
        if fixed is not None and level != fixed:
            plural = REQUIREMENT_PROFILE_PLURALS[target]
            raise BusinessRuleError(f"{document_type.name} tiene un nivel fijo para {plural}")
    changed = {key: level for key, level in received.items() if requirement(*key) != level}
    if not changed:
        return False
    old: dict[str, dict[str, str]] = {}
    new: dict[str, dict[str, str]] = {}
    for (document_type, target), level in changed.items():
        old.setdefault(document_type.code, {})[target.value] = requirement(document_type, target).value
        new.setdefault(document_type.code, {})[target.value] = level.value
        setattr(document_type, LEVEL_FIELDS[target], level)
    audit(db, "SUPPLIER_REQUIREMENTS_UPDATED", ENTITY, None, user_id, old, new)
    return True


def create_type(db: Session, user_id: int, name: str, description: str | None, **levels: str) -> SupplierDocumentType:
    """Alta de un requisito del Administrador. `levels` recibe `<perfil>_requirement`; los ausentes quedan en "No
    aplica". La clave REQUISITO_<id> se asigna tras el flush, como el folio interno de la factura."""
    try:
        data = SupplierDocumentTypeCreate(name=name, description=description, **levels)
    except ValidationError as exc:
        raise InvalidInputError(document_type_message(exc)) from None
    _lock(db)
    _ensure_unique_name(db, data.name)
    created = SupplierDocumentType(
        code=f"REQUISITO_PENDIENTE_{uuid4().hex}",
        name=data.name,
        description=data.description,
        is_system=False,
        is_active=True,
        **{LEVEL_FIELDS[p]: getattr(data, LEVEL_FIELDS[p]) for p in RequirementProfile},
    )
    db.add(created)
    _flush(db)
    created.code = f"REQUISITO_{created.id}"
    audit(
        db,
        "SUPPLIER_DOCUMENT_TYPE_CREATED",
        ENTITY,
        created.id,
        user_id,
        new={
            "code": created.code,
            "name": created.name,
            **{p.value: requirement(created, p).value for p in RequirementProfile},
        },
    )
    return created


def update_type(db: Session, type_id: int, user_id: int, name: str, description: str | None) -> bool:
    """Edita nombre y descripcion de un requisito del Administrador. True si hubo cambios."""
    _lock(db)
    document_type = _admin_type(db, type_id)
    try:
        data = SupplierDocumentTypeUpdate(name=name, description=description)
    except ValidationError as exc:
        raise InvalidInputError(document_type_message(exc)) from None
    _ensure_unique_name(db, data.name, exclude_id=document_type.id)
    old, new = {}, {}
    for attr in ("name", "description"):
        before, after = getattr(document_type, attr), getattr(data, attr)
        if before != after:
            old[attr], new[attr] = before, after
    if not new:
        return False
    for attr, value in new.items():
        setattr(document_type, attr, value)
    _flush(db)
    audit(db, "SUPPLIER_DOCUMENT_TYPE_UPDATED", ENTITY, document_type.id, user_id, old, new)
    return True


def set_active(db: Session, type_id: int, user_id: int, active: bool) -> bool:
    """Desactiva o reactiva un requisito del Administrador con un estado destino explicito. Conserva sus niveles."""
    _lock(db)
    document_type = _admin_type(db, type_id)
    if document_type.is_active == active:
        return False
    document_type.is_active = active
    audit(
        db,
        "SUPPLIER_DOCUMENT_TYPE_STATUS_CHANGED",
        ENTITY,
        document_type.id,
        user_id,
        {"is_active": not active},
        {"is_active": active},
    )
    return True


def delete_type(db: Session, type_id: int, user_id: int) -> None:
    """Elimina un requisito del Administrador sin documentos. La fila se bloquea FOR UPDATE: una carga concurrente la
    tiene FOR KEY SHARE, asi que no queda un documento con la clave de un tipo eliminado. Con documentos (vigentes o
    reemplazados) responde 409 y sugiere desactivarlo."""
    _lock(db)
    document_type = db.get(SupplierDocumentType, type_id, with_for_update=True)
    if document_type is None:
        raise NotFoundError(MSG_NOT_FOUND)
    if document_type.is_system:
        raise BusinessRuleError(MSG_SYSTEM_DELETE)
    if _in_use(db, document_type.code):
        raise BusinessRuleError(MSG_IN_USE)
    audit(
        db,
        "SUPPLIER_DOCUMENT_TYPE_DELETED",
        ENTITY,
        document_type.id,
        user_id,
        old={
            "code": document_type.code,
            "name": document_type.name,
            "description": document_type.description,
            "is_active": document_type.is_active,
            "persona_moral": document_type.persona_moral_requirement.value,
            "persona_fisica": document_type.persona_fisica_requirement.value,
            "international": document_type.international_requirement.value,
        },
    )
    db.delete(document_type)
    db.flush()
