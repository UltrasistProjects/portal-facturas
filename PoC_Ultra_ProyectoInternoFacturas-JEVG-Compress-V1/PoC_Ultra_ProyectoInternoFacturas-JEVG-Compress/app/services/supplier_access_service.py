"""Autorizacion de proveedores y credenciales de acceso al portal (HU-02 y HU-03).

- `authorize()`: pasa proveedores Registrados a Autorizado en una sola transaccion con sus filas bloqueadas, crea el
  usuario Proveedor de cada uno con una contrasena temporal y, despues del commit, envia el correo de credenciales (D3).
- `resend_credentials()`: contrasena nueva mientras el proveedor no haya iniciado sesion (D9).

La contrasena temporal solo existe en claro en memoria, en la entrega al proveedor de identidad (secret_vault) y en el
correo: nunca en la base de datos, la auditoria, la bitacora de envios ni el log (RN-HU03-01, D6).
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
from app.core.passwords import generate_password
from app.core.security import hash_password
from app.models import AuditLog, EmailDelivery, Supplier, User
from app.services import notification_service, secret_vault
from app.services.audit_service import audit
from app.services.invoice_service import violates

logger = logging.getLogger(__name__)

MAX_BATCH = 100
USER_NAME_MAX_LENGTH = 150
ENTITY = "Supplier"
BULK_ACTION = "SUPPLIER_BULK_AUTHORIZED"
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
    db: Session, supplier: Supplier, username: str, password: str, portal_url: str, admin_id: int
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
    conflicts: list[int]
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


def _create_user(db: Session, supplier: Supplier, admin: User, vault: secret_vault.SecretVault) -> Credential:
    password = generate_password()
    user = User(
        name=supplier.business_name[:USER_NAME_MAX_LENGTH],
        email=_email(supplier),
        password_hash=hash_password(password),
        role=Role.PROVEEDOR,
        supplier_id=supplier.id,
        is_active=True,
        must_change_password=True,  # contrasena temporal: se cambia en el primer acceso (HU-10)
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:  # otra transaccion creo un usuario con el mismo correo
        db.rollback()
        if violates(exc, "ix_users_email"):
            raise BusinessRuleError(MSG_RACE) from exc
        raise
    audit(
        db,
        "USER_CREATED",
        "User",
        user.id,
        admin.id,
        new={"role": Role.PROVEEDOR.value, "supplier_id": supplier.id, "origin": USER_ORIGIN},
    )
    vault.store_temporary_password(supplier_id=supplier.id, username=user.email, password=password)
    return Credential(supplier, user.email, password)


def authorize(db: Session, raw_ids: Iterable[str | int], admin: User, portal_url: str) -> AuthorizationResult:
    """Autoriza los proveedores Registrados de la seleccion (D3). Los demas se omiten; los que tienen su correo en uso
    por otro usuario no se autorizan. Confirma la transaccion y despues envia las credenciales."""
    started = time.perf_counter()
    ids = _selection(raw_ids)
    suppliers = list(db.scalars(select(Supplier).where(Supplier.id.in_(ids)).order_by(Supplier.id).with_for_update()))
    if len(suppliers) != len(ids):
        raise NotFoundError(MSG_NOT_FOUND)
    emails = {_email(supplier) for supplier in suppliers}
    users = {user.email.lower(): user for user in db.scalars(select(User).where(func.lower(User.email).in_(emails)))}
    outcome: dict[str, list[int]] = {"authorized": [], "existing_access": [], "skipped": [], "conflicts": []}
    credentials: list[Credential] = []
    vault = secret_vault.get_vault()
    for supplier in suppliers:
        if supplier.status != SupplierStatus.REGISTERED:
            outcome["skipped"].append(supplier.id)
            continue
        existing = users.get(_email(supplier))
        if existing is not None and not (existing.role == Role.PROVEEDOR and existing.supplier_id == supplier.id):
            outcome["conflicts"].append(supplier.id)
            continue
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
        outcome["authorized"].append(supplier.id)
        if existing is not None:
            outcome["existing_access"].append(supplier.id)
            continue
        credentials.append(_create_user(db, supplier, admin, vault))
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
            "conflicts": len(outcome["conflicts"]),
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
class AuthorizationSummary:
    authorized: list[SummaryRow]
    skipped: list[Supplier]
    conflicts: list[Supplier]


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
    return AuthorizationSummary(rows, listed("skipped"), listed("conflicts"))


# --- Reenvio de credenciales (HU-03) ------------------------------------------------------------------------------


def can_resend(supplier: Supplier, user: User | None) -> bool:
    """Mientras el usuario conserve la contrasena temporal (marca de HU-10), haya entrado o no con ella."""
    return (
        supplier.status == SupplierStatus.ACTIVE and user is not None and user.is_active and user.must_change_password
    )


def resend_credentials(db: Session, supplier_id: int, admin: User, portal_url: str) -> EmailDelivery:
    """Contrasena temporal nueva (invalida la anterior) y correo de credenciales (D9)."""
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
    if not user.must_change_password:
        raise BusinessRuleError(MSG_PASSWORD_CHANGED)
    password = generate_password()
    user.password_hash = hash_password(password)
    user.must_change_password = True
    secret_vault.get_vault().store_temporary_password(supplier_id=supplier.id, username=user.email, password=password)
    audit(db, "SUPPLIER_CREDENTIALS_RESENT", ENTITY, supplier.id, admin.id, new={"user_id": user.id})
    db.commit()
    return send_credentials(db, supplier, user.email, password, portal_url, admin.id)
