"""scripts/link_keycloak_users.py: enlace de los usuarios existentes con Keycloak (add-keycloak-authentication, D16)."""

from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from app.core.constants import Role, SupplierStatus
from app.core.database import SessionLocal
from app.models import AuditLog, EmailDelivery, User
from app.services.keycloak_admin import UPDATE_PASSWORD
from scripts import link_keycloak_users as link
from tests.test_acceso_proveedores import messages, password_for

pytestmark = pytest.mark.usefixtures("restore_notification_recipients")


@pytest.fixture()
def legacy(registered_suppliers):
    """Usuarios previos a Keycloak (con hash local y sin sub): uno interno, un proveedor autorizado y uno inactivo.
    Otros usuarios sin enlazar que dejen pruebas anteriores tambien se procesan: las pruebas miran solo los suyos."""
    tag = uuid4().hex[:8]
    [supplier] = registered_suppliers(status=SupplierStatus.ACTIVE)
    users = {
        "internal": User(
            name="Interno previo", email=f"interno.{tag}@ultrasist.mx", password_hash="hash", role=Role.PMO
        ),
        "provider": User(
            name="Proveedor previo",
            email=supplier.email,
            password_hash="hash",
            role=Role.PROVEEDOR,
            supplier_id=supplier.id,
        ),
        "inactive": User(
            name="Inactivo previo",
            email=f"inactivo.{tag}@ultrasist.mx",
            password_hash="hash",
            role=Role.ADMINISTRADOR,
            is_active=False,
        ),
    }
    with SessionLocal() as db:
        db.add_all(users.values())
        db.commit()
        emails = {key: user.email for key, user in users.items()}
    yield emails
    with SessionLocal() as db:
        ids = list(db.scalars(select(User.id).where(User.email.in_([emails["internal"], emails["inactive"]]))))
        db.execute(delete(AuditLog).where(AuditLog.entity == "User", AuditLog.entity_id.in_([str(i) for i in ids])))
        db.execute(delete(User).where(User.id.in_(ids)))
        db.commit()


def user(email: str) -> User:
    with SessionLocal() as db:
        return db.scalar(select(User).where(User.email == email))


def mine(results, emails: dict[str, str]) -> dict[str, link.LinkResult]:
    by_email = {result.email: result for result in results}
    return {key: by_email[email] for key, email in emails.items()}


def test_enlace_de_usuarios_existentes(legacy, keycloak):
    with SessionLocal() as db:
        results = mine(link.link_users(db, keycloak, portal_url="http://portal/login"), legacy)
    for key, email in legacy.items():
        linked = user(email)
        assert linked.keycloak_sub == keycloak.account(email).id and linked.password_hash is None, key
        assert keycloak.account(email).required_actions == [UPDATE_PASSWORD]
    # Entrega de la temporal: el proveedor por correo, el interno en consola y el inactivo ninguna.
    assert (results["provider"].delivery, results["internal"].delivery, results["inactive"].delivery) == (
        "email",
        "console",
        "none",
    )
    assert results["internal"].password == keycloak.account(legacy["internal"]).password
    assert password_for(legacy["provider"]) == keycloak.account(legacy["provider"]).password
    assert keycloak.account(legacy["inactive"]).enabled is False
    assert keycloak.account(legacy["provider"]).roles == {"Proveedor"}
    with SessionLocal() as db:
        audits = db.scalars(
            select(AuditLog).where(
                AuditLog.action == "USER_LINKED_TO_IDP", AuditLog.entity_id == str(user(legacy["internal"]).id)
            )
        ).all()
    assert [entry.new_value for entry in audits] == [{"idp_account": "created"}]


def test_segunda_ejecucion_no_toca_a_los_enlazados(legacy, keycloak):
    with SessionLocal() as db:
        link.link_users(db, keycloak)
        passwords = {email: keycloak.account(email).password for email in legacy.values()}
        again = link.link_users(db, keycloak)
    assert not set(legacy.values()) & {result.email for result in again}
    assert {email: keycloak.account(email).password for email in legacy.values()} == passwords


def test_simulacion_sin_escrituras(legacy, keycloak):
    keycloak.add_account(legacy["internal"], "PMO")  # ya tenia cuenta en Keycloak
    with SessionLocal() as db:
        results = mine(link.link_users(db, keycloak, dry_run=True), legacy)
        deliveries_before = len(db.scalars(select(EmailDelivery)).all())
    assert (results["internal"].action, results["provider"].action) == ("would_link", "would_create")
    assert all(user(email).keycloak_sub is None for email in legacy.values())
    assert keycloak._find(legacy["provider"]) is None and deliveries_before == len(messages())


def test_conflicto_con_otra_cuenta_de_keycloak(legacy, keycloak):
    keycloak.add_account(legacy["internal"], "Administrador")  # el interno previo es PMO
    with SessionLocal() as db:
        results = mine(link.link_users(db, keycloak), legacy)
    assert results["internal"].action == "conflict" and user(legacy["internal"]).keycloak_sub is None
    assert results["provider"].action == "created"


def test_consola(legacy, keycloak, capsys):
    assert link.main(["--dry-run"]) == 0
    assert f"{legacy['internal']}: se creara su cuenta en Keycloak" in capsys.readouterr().out
    assert link.main([]) == 0
    output = capsys.readouterr().out
    internal_password = keycloak.account(legacy["internal"]).password
    assert f"{legacy['internal']}: cuenta creada en Keycloak; contrasena temporal: {internal_password}" in output
    assert f"{legacy['provider']}: cuenta creada en Keycloak; contrasena temporal enviada por correo" in output
    assert output.count(internal_password) == 1 and "se muestran una sola vez" in output
    assert link.main([]) == 0
    assert "Todos los usuarios ya estan enlazados con Keycloak." in capsys.readouterr().out


def test_consola_con_conflicto_y_keycloak_caido(legacy, keycloak, capsys):
    keycloak.add_account(legacy["internal"], "Administrador")
    assert link.main([]) == 1  # un conflicto termina con codigo 1
    assert "CONFLICTO" in capsys.readouterr().out
    keycloak.unavailable = True
    assert link.main([]) == 1
    assert "Keycloak no respondio" in capsys.readouterr().err
