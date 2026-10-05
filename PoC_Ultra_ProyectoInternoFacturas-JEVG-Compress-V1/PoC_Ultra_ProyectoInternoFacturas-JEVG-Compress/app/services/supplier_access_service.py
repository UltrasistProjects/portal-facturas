"""Autorizacion de proveedores y credenciales de acceso al portal (HU-02 y HU-03, add-keycloak-authentication).

- `authorize()`: pasa proveedores Registrados a Autorizado con sus filas bloqueadas. Un proveedor con requisitos de
  alta exigibles pendientes no se autoriza (HU-21). Cada proveedor se procesa en un punto de guardado: su usuario del
  portal y su cuenta en Keycloak (creada o enlazada, rol Proveedor y contrasena temporal con UPDATE_PASSWORD). Si
  Keycloak falla, solo ese proveedor se revierte y sigue Registrado (D12). Despues del commit se envia el correo de
  credenciales (D1-A).
- `resend_credentials()`: contrasena temporal nueva en Keycloak mientras la cuenta conserve UPDATE_PASSWORD (D14).

La contrasena temporal solo existe en claro en memoria, en la llamada a Keycloak y en el correo: nunca en la base de
datos, la auditoria, la bitacora de envios ni el log (RN-HU03-01). El portal no guarda contrasenas ni hashes.
"""

import logging
import time
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.constants import DeliveryStatus, NotificationEvent, Role, SupplierStatus
from app.core.errors import BusinessRuleError, InvalidInputError, NotFoundError
from app.models import AuditLog, EmailDelivery, Supplier, User
from app.services import identity_service as identity
from app.services import notification_service
from app.services import supplier_requirements_service as requirements
from app.services.audit_service import audit
from app.services.invoice_service import violates
from app.services.keycloak_admin import IdentityAdmin, IdentityProviderError, get_identity_admin

logger = logging.getLogger(__name__)

MAX_BATCH = 100
USER_NAME_MAX_LENGTH = 150
ENTITY = "Supplier"
BULK_ACTION = "SUPPLIER_BULK_AUTHORIZED"
PROVISIONING_FAILED = "SUPPLIER_PROVISIONING_FAILED"
USER_ORIGIN = "SUPPLIER_AUTHORIZATION"
CREDENTIALS = NotificationEvent.SUPPLIER_CREDENTIALS

MSG_EMPTY = "Seleccione al menos un proveedor."
MSG_TOO_MANY = f"Autorice hasta {MAX_BATCH} proveedores por operación."
MSG_INVALID = "La selección de proveedores no es válida."
MSG_NOT_FOUND = "Alguno de los proveedores seleccionados no existe."
MSG_RACE = "Otro proceso usó el correo de un proveedor seleccionado. Intente de nuevo."
MSG_SUPPLIER_NOT_FOUND = "Proveedor no encontrado"
MSG_NOT_AUTHORIZED = "Sólo se reenvían credenciales a proveedores autorizados."
MSG_NO_USER = "El proveedor no tiene usuario del portal."
MSG_USER_DISABLED = "El usuario del proveedor está deshabilitado."
MSG_NOT_LINKED = (
    "El usuario del proveedor no está enlazado al proveedor de identidad: ejecute scripts/link_keycloak_users.py."
)
MSG_PASSWORD_CHANGED = "El proveedor ya cambió su contraseña temporal; no se generan credenciales nuevas."


def _email(supplier: Supplier) -> str:
    return supplier.email.strip().lower()


def provider_user(db: Session, supplier: Supplier, *, lock: bool = False) -> User | None:
    """Usuario Proveedor propio del proveedor: ligado a el y con su correo del catalogo."""
    stmt = select(User).where(
        User.supplier_id == supplier.id, User.role == Role.PROVEEDOR, func.lower(User.email) == _email(supplier)
    )
    if lock:
        stmt = stmt.with_for_update()
    return db.scalar(stmt)


def send_credentials(
    db: Session, supplier: Supplier, username: str, password: str, portal_url: str, admin_id: int | None
) -> EmailDelivery:
    """Correo de credenciales (HU-03) al correo del proveedor, sin copias. Llamar despues del commit."""
    return notification_service.notify(
        db,
        CREDENTIALS,
        supplier_email=username,
        entity=ENTITY,
        entity_id=supplier.id,
        user_id=admin_id,
        proveedor=supplier.business_name,
        usuario=username,
        contrasena_temporal=password,
        url_portal=portal_url,
    )


# --- Autorizacion masiva (HU-02) ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Credential:
    """Credencial nueva pendiente de enviar. La contrasena solo vive en memoria hasta el envio."""

    supplier: Supplier
    username: str
    password: str


@dataclass(frozen=True)
class AuthorizationResult:
    audit_id: int
    authorized: list[int]
    existing_access: list[int]
    skipped: list[int]
    requirements_incomplete: list[int]
    conflicts: list[int]
    provisioning_failed: list[int]
    deliveries: list[EmailDelivery]


def _selection(raw_ids: Iterable[str | int]) -> list[int]:
    try:
        ids = list(dict.fromkeys(int(value) for value in raw_ids if str(value).strip()))
    except ValueError:
        raise InvalidInputError(MSG_INVALID) from None
    if not ids:
        raise InvalidInputError(MSG_EMPTY)
    if len(ids) > MAX_BATCH:
        raise InvalidInputError(MSG_TOO_MANY)
    return ids


def _create_user(db: Session, supplier: Supplier, admin: User, idp: IdentityAdmin) -> Credential:
    """Usuario del portal sin contrasena y su cuenta en Keycloak (D12, D13). Dentro del punto de guardado del
    proveedor: si Keycloak falla, el usuario local desaparece con el."""
    email = _email(supplier)
    user = User(
        name=supplier.business_name[:USER_NAME_MAX_LENGTH],
        email=email,
        role=Role.PROVEEDOR,
        supplier_id=supplier.id,
        is_active=True,
    )
    db.add(user)
    try:
        db.flush()  # antes de tocar Keycloak: un correo tomado por otra transaccion no deja cuentas huerfanas
    except IntegrityError as exc:
        if violates(exc, "ix_users_email"):
            raise BusinessRuleError(MSG_RACE) from exc
        raise
    account = identity.provision(db, idp, email=email, role=Role.PROVEEDOR)
    user.keycloak_sub = account.sub
    try:
        db.flush()
    except IntegrityError as exc:  # otra transaccion enlazo la misma cuenta de Keycloak
        if violates(exc, "ix_users_keycloak_sub"):
            raise identity.AccountConflict() from exc
        raise
    audit(
        db,
        "USER_CREATED",
        "User",
        user.id,
        admin.id,
        new={
            "role": Role.PROVEEDOR.value,
            "supplier_id": supplier.id,
            "origin": USER_ORIGIN,
            "idp_account": account.origin,
        },
    )
    return Credential(supplier, email, account.password)


def authorize(db: Session, raw_ids: Iterable[str | int], admin: User, portal_url: str) -> AuthorizationResult:
    """Autoriza los proveedores Registrados de la seleccion. Los demas se omiten. No se autorizan los que tienen
    requisitos de alta exigibles pendientes (HU-21), los que tienen su correo en uso por otro usuario (del portal o de
    Keycloak) ni aquellos cuyo aprovisionamiento en Keycloak falla. Confirma la transaccion y despues envia las
    credenciales."""
    started = time.perf_counter()
    ids = _selection(raw_ids)
    suppliers = list(db.scalars(select(Supplier).where(Supplier.id.in_(ids)).order_by(Supplier.id).with_for_update()))
    if len(suppliers) != len(ids):
        raise NotFoundError(MSG_NOT_FOUND)
    emails = {_email(supplier) for supplier in suppliers}
    users = {user.email.lower(): user for user in db.scalars(select(User).where(func.lower(User.email).in_(emails)))}
    # Requisitos de alta con la configuracion vigente, dentro de la transaccion que bloquea a los proveedores: el
    # catalogo y los documentos del expediente de los seleccionados en dos consultas (D5).
    pending = requirements.pending_requirements(db, [s for s in suppliers if s.status == SupplierStatus.REGISTERED])
    outcome: dict[str, list[int]] = {
        "authorized": [],
        "existing_access": [],
        "skipped": [],
        "requirements_incomplete": [],
        "conflicts": [],
        "provisioning_failed": [],
    }
    credentials: list[Credential] = []
    idp = get_identity_admin()
    for supplier in suppliers:
        if supplier.status != SupplierStatus.REGISTERED:
            outcome["skipped"].append(supplier.id)
            continue
        if pending[supplier.id]:
            outcome["requirements_incomplete"].append(supplier.id)
            continue
        existing = users.get(_email(supplier))
        if existing is not None and not (existing.role == Role.PROVEEDOR and existing.supplier_id == supplier.id):
            outcome["conflicts"].append(supplier.id)
            continue
        try:
            with db.begin_nested():
                supplier.status = SupplierStatus.ACTIVE
                audit(
                    db,
                    "SUPPLIER_STATUS_CHANGED",
                    ENTITY,
                    supplier.id,
                    admin.id,
                    {"status": SupplierStatus.REGISTERED.value},
                    {"status": SupplierStatus.ACTIVE.value},
                )
                credential = None if existing is not None else _create_user(db, supplier, admin, idp)
        except identity.AccountConflict:
            outcome["conflicts"].append(supplier.id)
            continue
        except IdentityProviderError as exc:
            audit(
                db,
                PROVISIONING_FAILED,
                ENTITY,
                supplier.id,
                admin.id,
                new={"operation": exc.operation, "error": exc.code},
            )
            outcome["provisioning_failed"].append(supplier.id)
            continue
        outcome["authorized"].append(supplier.id)
        if credential is None:
            outcome["existing_access"].append(supplier.id)
        else:
            credentials.append(credential)
    entry = audit(db, BULK_ACTION, ENTITY, None, admin.id, new=outcome)
    db.commit()
    deliveries = [send_credentials(db, c.supplier, c.username, c.password, portal_url, admin.id) for c in credentials]
    sent = sum(delivery.status == DeliveryStatus.SENT for delivery in deliveries)
    logger.info(
        "supplier.bulk_authorize",
        extra={
            "event": "supplier.bulk_authorize",
            "requested": len(ids),
            "authorized": len(outcome["authorized"]),
            "existing_access": len(outcome["existing_access"]),
            "skipped": len(outcome["skipped"]),
            "requirements_incomplete": len(outcome["requirements_incomplete"]),
            "conflicts": len(outcome["conflicts"]),
            "provisioning_failed": len(outcome["provisioning_failed"]),
            "credentials_sent": sent,
            "credentials_failed": len(deliveries) - sent,
            "duration_ms": round((time.perf_counter() - started) * 1000),
        },
    )
    return AuthorizationResult(audit_id=entry.id, deliveries=deliveries, **outcome)


# --- Consulta -----------------------------------------------------------------------------------------------------


def _credentials_deliveries():
    return select(EmailDelivery).where(EmailDelivery.entity == ENTITY, EmailDelivery.event == CREDENTIALS)


def credentials_status(db: Session, supplier_id: int) -> EmailDelivery | None:
    """Ultimo envio de credenciales del proveedor."""
    stmt = (
        _credentials_deliveries()
        .where(EmailDelivery.entity_id == str(supplier_id))
        .order_by(EmailDelivery.created_at.desc(), EmailDelivery.id.desc())
        .limit(1)
    )
    return db.scalar(stmt)


def failed_credentials(db: Session) -> set[int]:
    """Proveedores cuyo ultimo envio de credenciales fallo."""
    stmt = (
        select(EmailDelivery.entity_id, EmailDelivery.status)
        .where(EmailDelivery.entity == ENTITY, EmailDelivery.event == CREDENTIALS)
        .order_by(EmailDelivery.entity_id, EmailDelivery.created_at.desc(), EmailDelivery.id.desc())
        .distinct(EmailDelivery.entity_id)
    )
    return {int(entity_id) for entity_id, status in db.execute(stmt) if status == DeliveryStatus.FAILED}


@dataclass(frozen=True)
class SummaryRow:
    supplier: Supplier
    state: str  # sent | failed | existing | pending
    delivery: EmailDelivery | None = None


@dataclass(frozen=True)
class IncompleteRow:
    """Proveedor no autorizado por requisitos de alta pendientes, con los nombres pendientes al consultar el resumen."""

    supplier: Supplier
    pending: list[str]


@dataclass(frozen=True)
class AuthorizationSummary:
    authorized: list[SummaryRow]
    skipped: list[Supplier]
    requirements_incomplete: list[IncompleteRow]
    conflicts: list[Supplier]
    provisioning_failed: list[Supplier]


def authorization_summary(db: Session, audit_id: int) -> AuthorizationSummary | None:
    """Resumen de una autorizacion reconstruido con su registro de auditoria y la bitacora (D5). None si el id no es
    el de una autorizacion masiva."""
    entry = db.get(AuditLog, audit_id)
    if entry is None or entry.action != BULK_ACTION or not isinstance(entry.new_value, dict):
        return None
    data = {key: [int(value) for value in values] for key, values in entry.new_value.items()}
    ids = {value for values in data.values() for value in values}
    suppliers = {s.id: s for s in db.scalars(select(Supplier).where(Supplier.id.in_(ids)))}

    def listed(key: str) -> list[Supplier]:
        return [suppliers[value] for value in data.get(key, []) if value in suppliers]

    existing = set(data.get("existing_access", []))
    rows = []
    for supplier in listed("authorized"):
        if supplier.id in existing:
            rows.append(SummaryRow(supplier, "existing"))
            continue
        delivery = credentials_status(db, supplier.id)
        state = "pending" if delivery is None else ("sent" if delivery.status == DeliveryStatus.SENT else "failed")
        rows.append(SummaryRow(supplier, state, delivery))
    # Los requisitos pendientes se recalculan al mostrar el resumen, como el estado del correo (D6 de HU-21).
    incomplete = listed("requirements_incomplete")
    pending = requirements.pending_requirements(db, incomplete)
    incomplete_rows = [IncompleteRow(s, [t.name for t in pending[s.id]]) for s in incomplete]
    return AuthorizationSummary(
        rows, listed("skipped"), incomplete_rows, listed("conflicts"), listed("provisioning_failed")
    )


def password_state(user: User | None) -> str | None:
    """Estado de la contrasena del usuario del proveedor, leido de Keycloak (D14); None sin usuario."""
    if user is None:
        return None
    return identity.password_state(get_identity_admin(), user.keycloak_sub)


# --- Reenvio de credenciales (HU-03) ------------------------------------------------------------------------------


def can_resend(supplier: Supplier, user: User | None, state: str | None) -> bool:
    """Mientras la cuenta de Keycloak conserve la contrasena temporal (UPDATE_PASSWORD), haya entrado o no con ella."""
    return (
        supplier.status == SupplierStatus.ACTIVE and user is not None and user.is_active and state == identity.TEMPORARY
    )


def resend_credentials(db: Session, supplier_id: int, admin: User, portal_url: str) -> EmailDelivery:
    """Contrasena temporal nueva en Keycloak (invalida la anterior) y correo de credenciales (D14)."""
    supplier = db.scalar(select(Supplier).where(Supplier.id == supplier_id).with_for_update())
    if supplier is None:
        raise NotFoundError(MSG_SUPPLIER_NOT_FOUND)
    if supplier.status != SupplierStatus.ACTIVE:
        raise BusinessRuleError(MSG_NOT_AUTHORIZED)
    user = provider_user(db, supplier, lock=True)
    if user is None:
        raise BusinessRuleError(MSG_NO_USER)
    if not user.is_active:
        raise BusinessRuleError(MSG_USER_DISABLED)
    if not user.keycloak_sub:
        raise BusinessRuleError(MSG_NOT_LINKED)
    idp = get_identity_admin()
    account = idp.get_user(user.keycloak_sub)
    if account is None:
        raise BusinessRuleError(MSG_NOT_LINKED)
    if not account.password_pending:
        raise BusinessRuleError(MSG_PASSWORD_CHANGED)
    password = identity.reset_temporary_password(idp, user.keycloak_sub)
    audit(db, "SUPPLIER_CREDENTIALS_RESENT", ENTITY, supplier.id, admin.id, new={"user_id": user.id})
    db.commit()
    return send_credentials(db, supplier, user.email, password, portal_url, admin.id)
