"""Requisitos de alta del contrato (HU-22).

Unico acceso al catalogo de requisitos del contrato (contract_document_types): lo usan la pantalla de administracion,
el expediente y el listado de contratos, la carga de documentos, la activacion y la regla DOC-005. Asi hay una sola
definicion del contrato completo. La configuracion se lee siempre de la base de datos, sin cache. Toda escritura de la
configuracion toma un bloqueo consultivo de transaccion, de modo que la huella config_version no cambia entre su
verificacion y la actualizacion.

Solo cuentan los documentos del contrato: vigentes (is_current) y con contract_id. No llevan supplier_id ni
invoice_id, asi que no cuentan en el expediente del proveedor ni en la factura, y los de esos no cuentan aqui.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import (
    ContractStatus,
    DocumentRequirement,
    ProcessingStatus,
    SupplierStatus,
)
from app.core.errors import BusinessRuleError, InvalidInputError, NotFoundError
from app.models import Contract, ContractDocumentType, Document
from app.schemas import (
    INVALID_REQUIREMENT,
    ContractDocumentTypeCreate,
    ContractDocumentTypeUpdate,
    document_type_message,
    parse_requirement,
)
from app.services.audit_service import audit
from app.services.file_service import StoredFile
from app.services.type_catalog import TypeCatalog, share_lock

ENTITY = "ContractDocumentType"
FIELD_PREFIX = "requirement__"
UPLOAD_STATUSES = {ContractStatus.REGISTERED, ContractStatus.ACTIVE}

MSG_CHANGED = "La configuración cambió mientras la editaba. Recargue la página."
MSG_DUPLICATE_NAME = "Ya existe un requisito con ese nombre"
MSG_NOT_FOUND = "Requisito no encontrado"
MSG_CONTRACT_NOT_FOUND = "Contrato no encontrado"
MSG_NOT_APPLICABLE = "El documento no aplica a este contrato"
MSG_BAD_REPLACEMENT = "El documento a reemplazar no corresponde a este requisito"
MSG_UPLOAD_STATUS = "Sólo se cargan documentos en un contrato Registrado o Activo"
MSG_NOT_REGISTERED = "Sólo se puede activar un contrato Registrado"
MSG_SUPPLIER_NOT_AUTHORIZED = "No se activó el contrato: el proveedor no está autorizado"
MSG_PENDING = "No se activó el contrato: faltan requisitos obligatorios ({names})"
# Bloqueo consultivo 22_2200_0001: serializa las escrituras de la configuracion (pg_advisory_xact_lock).
CATALOG = TypeCatalog(
    model=ContractDocumentType,
    entity=ENTITY,
    action_prefix="CONTRACT_DOCUMENT_TYPE",
    lock_key=22_2200_0001,
    name_index="uq_contract_document_types_name_lower",
    duplicate_message=MSG_DUPLICATE_NAME,
    not_found_message=MSG_NOT_FOUND,
)


# --- Lectura ------------------------------------------------------------------------------------------------------


def sort_key(document_type: ContractDocumentType) -> tuple:
    """Orden del catalogo: primero los requisitos del sistema, en el orden de su siembra; despues los del
    Administrador, por nombre."""
    if document_type.is_system:
        return (0, document_type.id, "")
    return (1, 0, document_type.name.lower())


def catalog(db: Session) -> list[ContractDocumentType]:
    return sorted(db.scalars(select(ContractDocumentType)), key=sort_key)


def applicable(types: Iterable[ContractDocumentType]) -> list[ContractDocumentType]:
    """Requisitos que se piden en todo contrato: activos y Obligatorios u Opcionales."""
    return [t for t in types if t.is_active and t.requirement != DocumentRequirement.NOT_APPLICABLE]


def config_version(types: Iterable[ContractDocumentType]) -> str:
    """Huella de la configuracion mostrada: SHA-256 de la clave, el nivel y el estado activo de todos los
    requisitos."""
    rows = sorted([t.code, t.requirement.value, t.is_active] for t in types)
    return hashlib.sha256(json.dumps(rows, separators=(",", ":")).encode()).hexdigest()


def contract_documents(db: Session, contract_ids: Iterable[int]) -> dict[int, dict[str, list[Document]]]:
    """Documentos vigentes por contrato y por tipo, en orden de carga, en una consulta. Un requisito con varios
    archivos tiene varios vigentes."""
    ids = list(contract_ids)
    result: dict[int, dict[str, list[Document]]] = {contract_id: {} for contract_id in ids}
    if not ids:
        return result
    stmt = select(Document).where(Document.contract_id.in_(ids), Document.is_current.is_(True)).order_by(Document.id)
    for document in db.scalars(stmt):
        result[document.contract_id].setdefault(document.document_type, []).append(document)
    return result


@dataclass
class RequirementRow:
    document_type: ContractDocumentType
    documents: list[Document]

    @property
    def required(self) -> bool:
        return self.document_type.requirement == DocumentRequirement.REQUIRED

    @property
    def pending(self) -> bool:
        return not self.documents


@dataclass
class OtherDocument:
    name: str
    document: Document


@dataclass
class Checklist:
    """Requisitos que aplican (obligatorios primero, cada grupo en el orden del catalogo) y los documentos vigentes
    de tipos que ya no aplican."""

    rows: list[RequirementRow]
    others: list[OtherDocument] = field(default_factory=list)

    @property
    def pending(self) -> list[RequirementRow]:
        return [row for row in self.rows if row.required and row.pending]

    @property
    def label(self) -> str:
        return pending_label(len(self.pending))


def pending_label(pending: int) -> str:
    if pending == 0:
        return "Requisitos del contrato completos"
    if pending == 1:
        return "Falta 1 requisito obligatorio"
    return f"Faltan {pending} requisitos obligatorios"


def build_checklist(types: list[ContractDocumentType], current: Mapping[str, list[Document]]) -> Checklist:
    offered = applicable(types)
    rows = [RequirementRow(t, current.get(t.code, [])) for t in offered]
    rows.sort(key=lambda row: not row.required)  # estable: conserva el orden del catalogo en cada grupo
    offered_codes = {t.code for t in offered}
    names = {t.code: t.name for t in types}
    others = [
        OtherDocument(names.get(document.document_type, document.document_type), document)
        for code, documents in current.items()
        if code not in offered_codes
        for document in documents
    ]
    others.sort(key=lambda other: other.document.id)
    return Checklist(rows, others)


def checklist(db: Session, contract: Contract) -> Checklist:
    return build_checklist(catalog(db), contract_documents(db, [contract.id])[contract.id])


def pending_requirements(db: Session, contracts: Iterable[Contract]) -> dict[int, list[ContractDocumentType]]:
    """Requisitos obligatorios sin documento por contrato: dos consultas para cualquier numero de contratos."""
    contracts = list(contracts)
    types = catalog(db)
    documents = contract_documents(db, [c.id for c in contracts])
    return {c.id: [row.document_type for row in build_checklist(types, documents[c.id]).pending] for c in contracts}


def pending_names(db: Session, contract: Contract | None) -> list[str] | None:
    """Nombres de los requisitos obligatorios pendientes del contrato, en el orden del catalogo (DOC-005); None si no
    hay contrato."""
    if contract is None:
        return None
    return [row.document_type.name for row in checklist(db, contract).pending]


def applicable_type(db: Session, code: str) -> ContractDocumentType:
    """Requisito que se puede cargar en un contrato; 400 si no existe, esta inactivo o es "No aplica"."""
    found = next((t for t in applicable(catalog(db)) if t.code == code), None)
    if found is None:
        raise InvalidInputError(MSG_NOT_APPLICABLE)
    share_lock(db, ContractDocumentType, found.id)
    return found


def get_contract(db: Session, contract_id: int, lock: bool = False) -> Contract:
    stmt = select(Contract).where(Contract.id == contract_id)
    if lock:
        stmt = stmt.with_for_update(of=Contract)
    contract = db.scalar(stmt)
    if contract is None:
        raise NotFoundError(MSG_CONTRACT_NOT_FOUND)
    return contract


# --- Documentos del contrato --------------------------------------------------------------------------------------


def prepare_upload(
    db: Session, contract: Contract, code: str, replaces_document_id: int | None
) -> tuple[ContractDocumentType, list[Document]]:
    """Verificaciones previas a escribir el archivo: estatus del contrato (409), requisito que aplica (400) y documento
    a reemplazar (400). Devuelve el requisito y los documentos que el nuevo reemplaza: con un archivo, el vigente de
    su tipo; con varios, solo el indicado."""
    if contract.status not in UPLOAD_STATUSES:
        raise BusinessRuleError(MSG_UPLOAD_STATUS)
    document_type = applicable_type(db, code)
    current = contract_documents(db, [contract.id])[contract.id].get(code, [])
    if not document_type.allows_multiple:
        return document_type, current
    if replaces_document_id is None:
        return document_type, []
    replaced = next((d for d in current if d.id == replaces_document_id), None)
    if replaced is None:
        raise InvalidInputError(MSG_BAD_REPLACEMENT)
    return document_type, [replaced]


def record_upload(
    db: Session,
    contract: Contract,
    document_type: ContractDocumentType,
    replaced: list[Document],
    stored: StoredFile,
    user_id: int,
) -> Document:
    """Registra el documento ya escrito en storage/. Los reemplazados quedan no vigentes; nada se borra."""
    for previous in replaced:
        previous.is_current = False
    document = Document(
        contract_id=contract.id,
        document_type=document_type.code,
        original_filename=stored.original_filename,
        stored_filename=stored.stored_filename,
        path=stored.relative_path,
        mime_type=stored.mime_type,
        file_size=stored.file_size,
        sha256=stored.sha256,
        uploaded_by=user_id,
        processing_status=ProcessingStatus.PROCESSED,
        metadata_json={"scope": "contract"},
        replaced_document_id=replaced[-1].id if replaced else None,
    )
    db.add(document)
    db.flush()
    audit(
        db,
        "CONTRACT_DOCUMENT_REPLACED" if replaced else "CONTRACT_DOCUMENT_UPLOADED",
        "Document",
        document.id,
        user_id,
        new={"type": document_type.code, "contract_id": contract.id},
    )
    return document


# --- Activacion ---------------------------------------------------------------------------------------------------


def activation_blocker(db: Session, contract: Contract) -> str | None:
    """Motivo por el que un contrato Registrado no puede activarse todavia, para el boton del expediente."""
    if contract.supplier.status != SupplierStatus.ACTIVE:
        return "Autorice al proveedor para activar el contrato"
    if checklist(db, contract).pending:
        return "Cargue los requisitos obligatorios para activar"
    return None


def activate(db: Session, contract_id: int, user_id: int) -> Contract:
    """Pasa un contrato Registrado a Activo. Con la fila del contrato bloqueada y la configuracion leida en la misma
    transaccion: contrato Registrado, proveedor Autorizado y requisitos obligatorios completos (409 si no)."""
    contract = get_contract(db, contract_id, lock=True)
    if contract.status != ContractStatus.REGISTERED:
        raise BusinessRuleError(MSG_NOT_REGISTERED)
    if contract.supplier.status != SupplierStatus.ACTIVE:
        raise BusinessRuleError(MSG_SUPPLIER_NOT_AUTHORIZED)
    pending = pending_names(db, contract)
    if pending:
        raise BusinessRuleError(MSG_PENDING.format(names=", ".join(pending)))
    contract.status = ContractStatus.ACTIVE
    contract.updated_by = user_id
    audit(
        db,
        "CONTRACT_STATUS_CHANGED",
        "Contract",
        contract.id,
        user_id,
        {"status": ContractStatus.REGISTERED.value},
        {"status": ContractStatus.ACTIVE.value},
    )
    return contract


# --- Configuracion ------------------------------------------------------------------------------------------------


def save_requirements(db: Session, form: Mapping[str, str], user_id: int) -> bool:
    """Guarda los niveles en una sola transaccion. True si hubo cambios; False si no habia nada que cambiar.

    Orden de las verificaciones, como en HU-04: huella (409) y niveles recibidos (400). Los campos de claves
    desconocidas o de requisitos eliminados se ignoran."""
    CATALOG.lock(db)
    types = catalog(db)
    if form.get("config_version") != config_version(types):
        raise BusinessRuleError(MSG_CHANGED)
    received: dict[ContractDocumentType, DocumentRequirement] = {}
    for document_type in (t for t in types if t.is_active):
        try:
            received[document_type] = parse_requirement(form.get(f"{FIELD_PREFIX}{document_type.code}"))
        except ValueError:
            raise InvalidInputError(INVALID_REQUIREMENT) from None
    changed = {document_type: level for document_type, level in received.items() if document_type.requirement != level}
    if not changed:
        return False
    old = {document_type.code: document_type.requirement.value for document_type in changed}
    new = {document_type.code: level.value for document_type, level in changed.items()}
    for document_type, level in changed.items():
        document_type.requirement = level
    audit(db, "CONTRACT_REQUIREMENTS_UPDATED", ENTITY, None, user_id, old, new)
    return True


def create_type(
    db: Session,
    user_id: int,
    name: str,
    description: str | None,
    requirement: str = DocumentRequirement.NOT_APPLICABLE.value,
    allows_multiple: bool = False,
) -> ContractDocumentType:
    """Alta de un requisito del Administrador. La clave REQ_CONTRATO_<id> se asigna tras el flush, como el folio
    interno de la factura."""
    try:
        data = ContractDocumentTypeCreate(
            name=name, description=description, requirement=requirement, allows_multiple=allows_multiple
        )
    except ValidationError as exc:
        raise InvalidInputError(document_type_message(exc)) from None
    CATALOG.lock(db)
    CATALOG.ensure_unique_name(db, data.name)
    created = ContractDocumentType(
        code=f"REQ_CONTRATO_PENDIENTE_{uuid4().hex}",
        name=data.name,
        description=data.description,
        is_system=False,
        is_active=True,
        requirement=data.requirement,
        allows_multiple=data.allows_multiple,
    )
    db.add(created)
    CATALOG.flush(db)
    created.code = f"REQ_CONTRATO_{created.id}"
    audit(
        db,
        "CONTRACT_DOCUMENT_TYPE_CREATED",
        ENTITY,
        created.id,
        user_id,
        new={
            "code": created.code,
            "name": created.name,
            "requirement": created.requirement.value,
            "allows_multiple": created.allows_multiple,
        },
    )
    return created


def update_type(db: Session, type_id: int, user_id: int, name: str, description: str | None) -> bool:
    """Edita nombre y descripcion de cualquier requisito, del sistema o del Administrador. True si hubo cambios. Si
    admite varios archivos no cambia."""
    try:
        data = ContractDocumentTypeUpdate(name=name, description=description)
    except ValidationError as exc:
        raise InvalidInputError(document_type_message(exc)) from None
    return CATALOG.update(db, type_id, user_id, data.model_dump())


def delete_type(db: Session, type_id: int, user_id: int) -> bool:
    """Baja logica de cualquier requisito, aunque tenga documentos: deja de pedirse y de exigirse al activar. Ningun
    contrato cambia de estatus."""
    return CATALOG.delete(db, type_id, user_id)


def restore_type(db: Session, type_id: int, user_id: int) -> bool:
    return CATALOG.restore(db, type_id, user_id)
