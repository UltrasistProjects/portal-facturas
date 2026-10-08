"""Cuentas del portal en Keycloak: crear o enlazar, rol y contrasena temporal (add-keycloak-authentication, D13-D16).

Lo usan la autorizacion de proveedores, el alta de usuarios, el seed y scripts/link_keycloak_users.py.

Regla de enlace (D13): si Keycloak ya tiene una cuenta con el correo, se enlaza en lugar de crear otra siempre que
ningun usuario del portal tenga su `sub` y que sus roles del portal sean ninguno o solo el rol pedido. En otro caso el
correo esta en uso (AccountConflict). Enlazar fija una contrasena nueva: el portal no conoce la anterior.

La contrasena en claro solo existe en memoria y en la llamada a Keycloak; quien la recibe decide si la entrega por
correo o en pantalla. Nunca se guarda ni se escribe en el log (RN-HU03-01).
"""

from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import Role
from app.core.errors import BusinessRuleError
from app.core.passwords import generate_password
from app.models import User
from app.services.keycloak_admin import IdentityAdmin, IdentityProviderError

PORTAL_ROLES = frozenset(role.value for role in Role)
MSG_ACCOUNT_IN_USE = "El correo ya lo usa otra cuenta del proveedor de identidad con otro rol del portal."

# Estado de la contrasena de un usuario, leido de Keycloak (D14).
TEMPORARY = "temporary"
CHANGED = "changed"
UNAVAILABLE = "unavailable"
UNLINKED = "unlinked"


class AccountConflict(BusinessRuleError):
    """La cuenta de Keycloak con ese correo pertenece a otro usuario del portal o tiene otro rol del portal."""

    status_code = 409

    def __init__(self):
        super().__init__(MSG_ACCOUNT_IN_USE)


@dataclass(frozen=True)
class Provisioned:
    sub: str
    origin: str  # created | linked
    password: str


def portal_roles(roles: Iterable[str]) -> set[str]:
    """Roles del portal entre los de una cuenta; offline_access, default-roles-..., etc. se ignoran."""
    return set(roles) & PORTAL_ROLES


def provision(
    db: Session,
    idp: IdentityAdmin,
    *,
    email: str,
    role: Role,
    password: str | None = None,
    temporary: bool = True,
    enabled: bool = True,
) -> Provisioned:
    """Crea o enlaza la cuenta de `email` en Keycloak con el realm role `role` y una contrasena (temporal por omision:
    Keycloak exigira cambiarla en el primer acceso). No modifica la base de datos: quien llama guarda el `sub`."""
    password = password or generate_password()
    account = idp.find_by_email(email)
    if account is None:
        sub, origin = idp.create_user(email, enabled=enabled), "created"
    else:
        linked = db.scalar(select(User.id).where(User.keycloak_sub == account.id))
        if linked is not None or portal_roles(idp.realm_roles(account.id)) - {role.value}:
            raise AccountConflict()
        sub, origin = account.id, "linked"
        if account.enabled != enabled:
            idp.set_enabled(sub, enabled)
    idp.assign_realm_role(sub, role.value)
    idp.set_password(sub, password, temporary=temporary)
    return Provisioned(sub, origin, password)


def reset_temporary_password(idp: IdentityAdmin, sub: str) -> str:
    """Contrasena temporal nueva (invalida la anterior); Keycloak mantiene UPDATE_PASSWORD."""
    password = generate_password()
    idp.set_password(sub, password, temporary=True)
    return password


def password_state(idp: IdentityAdmin, sub: str | None) -> str:
    """temporary, changed, unlinked (sin cuenta en Keycloak) o unavailable (Keycloak no respondio): la pagina que lo
    muestra no falla por ello."""
    if not sub:
        return UNLINKED
    try:
        account = idp.get_user(sub)
    except IdentityProviderError:
        return UNAVAILABLE
    if account is None:
        return UNLINKED
    return TEMPORARY if account.password_pending else CHANGED
