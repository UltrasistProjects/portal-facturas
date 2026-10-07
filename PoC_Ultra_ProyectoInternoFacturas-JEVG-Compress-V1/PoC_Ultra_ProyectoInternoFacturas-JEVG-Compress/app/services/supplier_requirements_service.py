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
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import (
    DATED_SUPPLIER_DOCUMENTS,
    QUOTATION_DOCUMENT,
    REQUIREMENT_PROFILE_PLURALS,
    DocumentRequirement,
    RequirementProfile,
    SupplierOrigin,
    SupplierType,
)
from app.core.errors import BusinessRuleError, InvalidInputError
from app.models import Document, Supplier, SupplierDocumentType
from app.schemas import (
    INVALID_REQUIREMENT,
    SupplierDocumentTypeCreate,
    SupplierDocumentTypeUpdate,
    document_type_message,
    parse_requirement,
)
from app.services.audit_service import audit
from app.services.type_catalog import TypeCatalog, share_lock

ENTITY = "SupplierDocumentType"
LEVEL_FIELDS = {profile: f"{profile.value}_requirement" for profile in RequirementProfile}
# Documentos con fecha de mas de tres meses: advertencia de vigencia (SUP-004), sin bloquear la autorizacion.
VALIDITY_DAYS = 93

MSG_CHANGED = "La configuración cambió mientras la editaba. Recargue la página."
MSG_DUPLICATE_NAME = "Ya existe un requisito con ese nombre"
MSG_NOT_FOUND = "Requisito no encontrado"
MSG_NOT_APPLICABLE = "El documento no aplica a este proveedor"
NOTE_QUOTATION = "Alta por cotización o licitación"
NOTE_QUOTATION_OPTIONAL = "Exigible si el alta es por cotización o licitación"
# Bloqueo consultivo 21_2100_0001: serializa las escrituras de la configuracion (pg_advisory_xact_lock).
CATALOG = TypeCatalog(
    model=SupplierDocumentType,
    entity=ENTITY,
    action_prefix="SUPPLIER_DOCUMENT_TYPE",
    lock_key=21_2100_0001,
    name_index="uq_supplier_document_types_name_lower",
    duplicate_message=MSG_DUPLICATE_NAME,
    not_found_message=MSG_NOT_FOUND,
)


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
    share_lock(db, SupplierDocumentType, found.id)
    return found


# --- Escritura ----------------------------------------------------------------------------------------------------


def save_requirements(db: Session, form: Mapping[str, str], user_id: int) -> bool:
    """Guarda la matriz de niveles en una sola transaccion. True si hubo cambios; False si no habia nada que cambiar.

    Orden de las verificaciones, como en HU-04: huella (409) y niveles recibidos (400). Una pagina vieja puede carecer
    de un requisito nuevo, y "Recargue la pagina" es mas util que "falta un nivel". Los campos de claves desconocidas o
    de requisitos eliminados se ignoran."""
    CATALOG.lock(db)
    types = catalog(db)
    if form.get("config_version") != config_version(types):
        raise BusinessRuleError(MSG_CHANGED)
    received: dict[tuple[SupplierDocumentType, RequirementProfile], DocumentRequirement] = {}
    for document_type in (t for t in types if t.is_active):
        for target in RequirementProfile:
            try:
                received[document_type, target] = parse_requirement(form.get(f"{target.value}__{document_type.code}"))
            except ValueError:
                raise InvalidInputError(INVALID_REQUIREMENT) from None
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
    CATALOG.lock(db)
    CATALOG.ensure_unique_name(db, data.name)
    created = SupplierDocumentType(
        code=f"REQUISITO_PENDIENTE_{uuid4().hex}",
        name=data.name,
        description=data.description,
        is_system=False,
        is_active=True,
        **{LEVEL_FIELDS[p]: getattr(data, LEVEL_FIELDS[p]) for p in RequirementProfile},
    )
    db.add(created)
    CATALOG.flush(db)
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
    """Edita nombre y descripcion de cualquier requisito, del sistema o del Administrador. True si hubo cambios."""
    try:
        data = SupplierDocumentTypeUpdate(name=name, description=description)
    except ValidationError as exc:
        raise InvalidInputError(document_type_message(exc)) from None
    return CATALOG.update(db, type_id, user_id, data.model_dump())


def delete_type(db: Session, type_id: int, user_id: int) -> bool:
    """Baja logica de cualquier requisito, aunque tenga documentos: deja de pedirse y de exigirse al autorizar. Ningun
    proveedor cambia de estatus."""
    return CATALOG.delete(db, type_id, user_id)


def restore_type(db: Session, type_id: int, user_id: int) -> bool:
    return CATALOG.restore(db, type_id, user_id)
