"""Enlaza los usuarios del portal con sus cuentas de Keycloak (add-keycloak-authentication, D16). Idempotente.

Por cada usuario sin keycloak_sub:
- busca su cuenta en Keycloak por correo y la enlaza (regla D13: ningun otro usuario del portal tiene ese sub y no tiene
  otro rol del portal) o la crea con el rol del usuario; un usuario inactivo queda deshabilitado tambien en Keycloak;
- le fija una contrasena temporal: Keycloak le pedira cambiarla en su primer acceso;
- guarda el sub, vacia password_hash (RN-HU03-01) y audita USER_LINKED_TO_IDP. Confirma usuario por usuario: si
  Keycloak deja de responder, lo enlazado se conserva y otra ejecucion continua donde quedo.

Entrega de la contrasena temporal: a los proveedores activos y autorizados, por el correo de credenciales (HU-03); a los
demas usuarios activos, en consola, una sola vez. Un conflicto se informa y el usuario queda sin enlazar.

Uso: python scripts/link_keycloak_users.py [--dry-run] [--portal-url http://127.0.0.1:8000/login]
"""

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import Role, SupplierStatus
from app.core.database import SessionLocal
from app.models import Supplier, User
from app.services import identity_service as identity
from app.services import supplier_access_service as access
from app.services.audit_service import audit
from app.services.keycloak_admin import IdentityAdmin, IdentityProviderError, get_identity_admin

DEFAULT_PORTAL_URL = "http://127.0.0.1:8000/login"
ACTIONS = {
    "created": "cuenta creada en Keycloak",
    "linked": "enlazado a su cuenta existente de Keycloak",
    "conflict": "CONFLICTO: el correo pertenece a otra cuenta de Keycloak con otro rol del portal; revise Keycloak",
    "would_create": "se creara su cuenta en Keycloak",
    "would_link": "se enlazara a su cuenta existente de Keycloak",
}
DELIVERIES = {"email": "contrasena temporal enviada por correo", "console": "contrasena temporal:", "none": ""}


@dataclass(frozen=True)
class LinkResult:
    email: str
    action: str  # created | linked | conflict | would_create | would_link
    delivery: str = "none"  # email | console | none
    password: str | None = None  # solo con delivery == "console": se imprime una vez y no se guarda


def planned_action(db: Session, idp: IdentityAdmin, user: User) -> str:
    """Lo que haria el enlace, sin escribir en Keycloak ni en la base (--dry-run)."""
    account = idp.find_by_email(user.email.lower())
    if account is None:
        return "would_create"
    linked = db.scalar(select(User.id).where(User.keycloak_sub == account.id))
    if linked is not None or identity.portal_roles(idp.realm_roles(account.id)) - {user.role.value}:
        return "conflict"
    return "would_link"


def _emailable_supplier(db: Session, user: User) -> Supplier | None:
    """Proveedor autorizado cuyo usuario propio es `user`: recibe la contrasena por el correo de credenciales."""
    if not user.is_active or user.role != Role.PROVEEDOR or user.supplier_id is None:
        return None
    supplier = db.get(Supplier, user.supplier_id)
    if supplier is None or supplier.status != SupplierStatus.ACTIVE or access.provider_user(db, supplier) is not user:
        return None
    return supplier


def link_users(
    db: Session, idp: IdentityAdmin, *, dry_run: bool = False, portal_url: str = DEFAULT_PORTAL_URL
) -> list[LinkResult]:
    results = []
    for user in db.scalars(select(User).where(User.keycloak_sub.is_(None)).order_by(User.id)).all():
        email = user.email.lower()
        if dry_run:
            results.append(LinkResult(email, planned_action(db, idp, user)))
            continue
        try:
            account = identity.provision(db, idp, email=email, role=user.role, enabled=user.is_active)
        except identity.AccountConflict:
            results.append(LinkResult(email, "conflict"))
            continue
        user.keycloak_sub = account.sub
        user.password_hash = None
        audit(db, "USER_LINKED_TO_IDP", "User", user.id, None, new={"idp_account": account.origin})
        db.commit()
        supplier = _emailable_supplier(db, user)
        if supplier is not None:
            access.send_credentials(db, supplier, email, account.password, portal_url, None)
            results.append(LinkResult(email, account.origin, "email"))
        elif user.is_active:
            results.append(LinkResult(email, account.origin, "console", account.password))
        else:
            results.append(LinkResult(email, account.origin))
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="solo informa lo que haria, sin escribir nada")
    parser.add_argument("--portal-url", default=DEFAULT_PORTAL_URL, help="direccion de inicio de sesion del correo")
    args = parser.parse_args(argv)
    with SessionLocal() as db:
        try:
            results = link_users(db, get_identity_admin(), dry_run=args.dry_run, portal_url=args.portal_url)
        except IdentityProviderError as exc:
            print(
                f"Keycloak no respondio ({exc.operation}: {exc.code}). Los usuarios enlazados hasta ahora se conservan;"
                " vuelva a ejecutar el script cuando Keycloak este disponible.",
                file=sys.stderr,
            )
            return 1
    if not results:
        print("Todos los usuarios ya estan enlazados con Keycloak.")
    for result in results:
        detail = DELIVERIES[result.delivery]
        line = f"{result.email}: {ACTIONS[result.action]}" + (f"; {detail}" if detail else "")
        print(f"{line} {result.password}" if result.password else line)
    if any(result.password for result in results):
        print("Las contrasenas temporales se muestran una sola vez: entreguelas por un medio seguro.")
    return 1 if any(result.action == "conflict" for result in results) else 0


if __name__ == "__main__":
    sys.exit(main())
