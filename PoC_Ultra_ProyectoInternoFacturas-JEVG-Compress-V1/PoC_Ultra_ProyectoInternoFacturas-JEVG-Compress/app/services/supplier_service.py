"""Alta individual, edicion y expediente (Anexo A) del proveedor.

Estas funciones no confirman la transaccion: lo hace el router.
"""

from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.constants import (
    ALTERNATIVE_SUPPLIER_DOCUMENTS,
    DATED_SUPPLIER_DOCUMENTS,
    OPTIONAL_SUPPLIER_DOCUMENTS,
    QUOTATION_DOCUMENT,
    SUPPLIER_DOCUMENT_LABELS,
    SUPPLIER_REQUIREMENTS,
    CatalogType,
    SupplierStatus,
)
from app.core.errors import BusinessRuleError, InvalidInputError
from app.models import CatalogEntry, Supplier, User
from app.schemas import SupplierCreate, SupplierProfile, SupplierUpdate
from app.services.audit_service import audit
from app.services.catalog_service import active_entries

MSG_RFC_IN_USE = "Ya existe un proveedor con ese RFC."
MSG_FOREIGN_TAX_ID_IN_USE = "Ya existe un proveedor con ese identificador fiscal extranjero en ese pais."
MSG_EMAIL_IN_USE = "El correo ya lo usa otro proveedor o usuario."
MSG_ACTIVITY = "Actividad principal: no es una actividad activa del catalogo"
# Campos de SupplierProfile que se guardan tal cual en el proveedor (supplier_type solo decide que se exige).
PROFILE_FIELDS = (
    "business_name",
    "phone",
    "bank_information",
    "confidentiality_agreement",
    "economic_proposal",
    "classification",
    "main_activity",
    "incorporation_date",
    "website",
    "legal_rep_name",
    "legal_rep_phone",
    "contact_name",
    "contact_phone",
)


def supplier_requirement_status(supplier, documents) -> list[dict]:
    """Una fila por documento del expediente. `required` indica si cuenta para el expediente minimo (SUP-003); `note`
    explica por que un documento no es obligatorio o que otro lo sustituye."""
    codes = SUPPLIER_REQUIREMENTS[supplier.supplier_type]
    current = {d.document_type: d for d in documents if d.is_current}
    rows = []
    for code in codes:
        doc = current.get(code)
        expired = bool(
            doc
            and doc.document_date
            and doc.document_date < date.today() - timedelta(days=93)
            and code in DATED_SUPPLIER_DOCUMENTS
        )
        required, note = _requirement(code, codes, current, supplier.economic_proposal)
        rows.append(
            {
                "code": code,
                "label": SUPPLIER_DOCUMENT_LABELS[code],
                "present": bool(doc),
                "expired": expired,
                "document": doc,
                "required": required,
                "note": note,
            }
        )
    return rows


def _requirement(code: str, codes: list[str], current: dict, quotation: bool) -> tuple[bool, str | None]:
    if code in OPTIONAL_SUPPLIER_DOCUMENTS:
        return False, "Opcional"
    if code == QUOTATION_DOCUMENT:
        if quotation:
            return True, "Alta por cotización o licitación"
        return False, "Opcional: el alta no es por cotización o licitación"
    alternative = ALTERNATIVE_SUPPLIER_DOCUMENTS.get(code)
    if alternative in codes:
        label = SUPPLIER_DOCUMENT_LABELS[alternative]
        # Deja de ser obligatorio si falta y el alternativo ya esta cargado; cargado, cumple el requisito.
        return code in current or alternative not in current, f"Basta este o el {label[0].lower()}{label[1:]}"
    return True, None


# --- Actividad principal (catalogo INDUSTRY) ----------------------------------------------------------------------


def activity_options(db: Session, current: str | None = None) -> list[CatalogEntry]:
    """Actividades que ofrece el formulario: las activas y, si ya no lo esta, la que tiene el proveedor."""
    options = active_entries(db, CatalogType.INDUSTRY)
    if current and current not in {entry.code for entry in options}:
        entry = _activity(db, current)
        if entry:
            options.append(entry)
    return options


def activity_name(db: Session, code: str | None) -> str | None:
    entry = _activity(db, code) if code else None
    return entry.name if entry else None


def _activity(db: Session, code: str) -> CatalogEntry | None:
    stmt = select(CatalogEntry).where(CatalogEntry.catalog == CatalogType.INDUSTRY, CatalogEntry.code == code)
    return db.scalar(stmt)


def _check_activity(db: Session, data: SupplierProfile, current: str | None = None) -> None:
    """La actividad debe estar activa; el proveedor conserva la suya aunque despues se haya desactivado."""
    if data.main_activity == current:
        return
    entry = _activity(db, data.main_activity)
    if entry is None or not entry.is_active:
        raise InvalidInputError(MSG_ACTIVITY)


# --- Alta y edicion -----------------------------------------------------------------------------------------------


def create_supplier(db: Session, data: SupplierCreate, user_id: int) -> Supplier:
    _check_activity(db, data)
    # Cada origen se compara solo por su identidad: `rfc == None` seria `IS NULL` y chocaria con los internacionales.
    if data.rfc and db.scalar(select(Supplier.id).where(Supplier.rfc == data.rfc)):
        raise BusinessRuleError(MSG_RFC_IN_USE)
    foreign_identity = (Supplier.country == data.country, Supplier.foreign_tax_id == data.foreign_tax_id)
    if data.foreign_tax_id and db.scalar(select(Supplier.id).where(*foreign_identity)):
        raise BusinessRuleError(MSG_FOREIGN_TAX_ID_IN_USE)
    # Un correo corresponde a un solo proveedor y a su usuario (RD-06 de HU-01): HU-03 lo usa como usuario del portal.
    email_in_use = db.scalar(select(Supplier.id).where(func.lower(Supplier.email) == data.email)) or db.scalar(
        select(User.id).where(func.lower(User.email) == data.email)
    )
    if email_in_use:
        raise BusinessRuleError(MSG_EMAIL_IN_USE)
    # Nace Registrado, como la carga masiva: el acceso al portal llega con la autorizacion (HU-02).
    supplier = Supplier(
        origin=data.origin,
        rfc=data.rfc,
        foreign_tax_id=data.foreign_tax_id,
        country=data.country,
        supplier_type=data.supplier_type,
        email=data.email,
        status=SupplierStatus.REGISTERED,
        **{name: getattr(data, name) for name in PROFILE_FIELDS},
    )
    db.add(supplier)
    db.flush()
    audit(db, "SUPPLIER_CREATED", "Supplier", supplier.id, user_id)
    return supplier


def update_supplier(db: Session, supplier: Supplier, data: SupplierUpdate, user_id: int) -> bool:
    """Guarda los datos editados y audita solo los campos que cambian. True si hubo cambios."""
    _check_activity(db, data, supplier.main_activity)
    old, new = {}, {}
    for name in PROFILE_FIELDS:
        before, after = getattr(supplier, name), getattr(data, name)
        if before != after:
            old[name], new[name] = _json(before), _json(after)
            setattr(supplier, name, after)
    if not new:
        return False
    audit(db, "SUPPLIER_UPDATED", "Supplier", supplier.id, user_id, old, new)
    return True


def _json(value):
    return value.isoformat() if isinstance(value, date) else value
