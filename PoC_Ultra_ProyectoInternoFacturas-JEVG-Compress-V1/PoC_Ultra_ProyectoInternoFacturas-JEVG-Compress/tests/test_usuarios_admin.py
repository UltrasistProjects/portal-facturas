"""Alta y habilitacion de usuarios con la regla rol-proveedor (spec administracion-usuarios; changes
usuario-proveedor-vinculado y add-keycloak-authentication: las cuentas viven en el Keycloak simulado)."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from app.core.constants import Role, SupplierStatus
from app.core.database import SessionLocal
from app.core.errors import BusinessRuleError
from app.models import AuditLog, User
from app.routers.invoices import _ensure_supplier_active
from app.services.keycloak_admin import UPDATE_PASSWORD
from tests.conftest import csrf, identity_account, login, supplier_by_email


@pytest.fixture()
def email():
    address = f"alta.{uuid4().hex[:10]}@usuarios.example"
    yield address
    with SessionLocal() as db:
        db.execute(delete(User).where(User.email == address))
        db.commit()


def create(client, email: str, role: str, supplier_id="", name="Joshua Bolaños Hernández"):
    data = {
        "name": name,
        "email": email,
        "role": role,
        "supplier_id": str(supplier_id),
        "csrf_token": csrf(client, "/admin/users"),
    }
    return client.post("/admin/users", data=data, follow_redirects=False)


def stored(email: str) -> User | None:
    with SessionLocal() as db:
        return db.scalar(select(User).where(User.email == email))


def test_proveedor_sin_proveedor_rechazado(client, email):
    login(client)
    response = create(client, email, "Proveedor")
    assert response.status_code == 400 and "Seleccione el proveedor del usuario" in response.text
    assert stored(email) is None
    # El formulario vuelve abierto con lo capturado; no tiene campo de contrasena (la asigna Keycloak).
    page = response.text
    assert '<details class="panel admin-create" open>' in page
    assert f'value="{email}"' in page and 'value="Joshua Bolaños Hernández"' in page
    assert "<option selected>Proveedor</option>" in page and 'name="password"' not in page


def test_proveedor_inexistente(client, email):
    login(client)
    response = create(client, email, "Proveedor", 999999)
    assert response.status_code == 400 and "Proveedor inexistente" in response.text and stored(email) is None


def test_proveedor_con_su_proveedor(client, email, keycloak):
    supplier = supplier_by_email("proveedor1@poc.local")
    login(client)
    response = create(client, email, "Proveedor", supplier.id)
    assert response.status_code == 200 and "Usuario creado" in response.text
    created = stored(email)
    assert (created.role, created.supplier_id, created.is_active) == (Role.PROVEEDOR, supplier.id, True)
    account = keycloak.account(email)
    assert (account.id, account.roles, account.required_actions) == (
        created.keycloak_sub,
        {"Proveedor"},
        [UPDATE_PASSWORD],
    )
    assert account.password in response.text and response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("role", ["PMO", "Administrador"])
def test_pmo_o_administrador_sin_proveedor(client, email, role, keycloak):
    supplier = supplier_by_email("proveedor1@poc.local")
    login(client)
    assert create(client, email, role, supplier.id).status_code == 200
    assert stored(email).supplier_id is None and keycloak.account(email).roles == {role}


def test_alta_con_correo_de_otro_rol_en_keycloak(client, email, keycloak):
    keycloak.add_account(email, "Administrador")
    login(client)
    response = create(client, email, "PMO")
    assert response.status_code == 409 and "otro rol del portal" in response.text
    assert stored(email) is None and keycloak.account(email).password is None


def test_alta_con_keycloak_caido(client, email, keycloak):
    login(client)
    keycloak.unavailable = True
    response = create(client, email, "PMO")
    assert response.status_code == 503
    assert "El servicio de identidad no está disponible. Intente más tarde." in response.text
    assert stored(email) is None


def test_selector_sin_ninguno(client):
    login(client)
    page = client.get("/admin/users").text
    assert '<option value="">Seleccione un proveedor (sólo Proveedor)</option>' in page and ">Ninguno<" not in page


@pytest.fixture()
def orphan():
    """Usuario Proveedor sin proveedor, deshabilitado: como lo deja la migracion 0013."""
    address = f"huerfano.{uuid4().hex[:10]}@usuarios.example"
    with SessionLocal() as db:
        user = User(
            name="Usuario huerfano",
            email=address,
            role=Role.PROVEEDOR,
            supplier_id=None,
            is_active=False,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    yield user
    with SessionLocal() as db:
        db.execute(delete(User).where(User.id == user.id))
        db.commit()


@pytest.fixture()
def linked(email):
    """Usuario PMO activo enlazado a su cuenta del Keycloak simulado."""
    with SessionLocal() as db:
        user = User(name="Usuario enlazado", email=email, role=Role.PMO, keycloak_sub=identity_account(email, Role.PMO))
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def toggle(client, user: User):
    token = csrf(client, "/admin/users")
    return client.post(f"/admin/users/{user.id}/toggle", data={"csrf_token": token}, follow_redirects=False)


def test_deshabilitar_con_keycloak_caido(client, linked, keycloak):
    login(client)
    keycloak.unavailable = True
    response = toggle(client, linked)
    assert response.status_code == 303 and "ok=idp_sync_failed" in response.headers["location"]
    assert stored(linked.email).is_active is False  # el portal le cierra el acceso de todos modos
    assert keycloak.account(linked.email).enabled
    with SessionLocal() as db:
        entry = db.scalar(
            select(AuditLog).where(AuditLog.action == "IDP_SYNC_FAILED", AuditLog.entity_id == str(linked.id))
        )
    assert entry.new_value == {"operation": "update_user", "error": "unavailable"}
    keycloak.unavailable = False
    assert "Keycloak no se actualizó" in client.get(response.headers["location"]).text


def test_habilitar_con_keycloak_caido(client, linked, keycloak):
    login(client)
    toggle(client, linked)  # deshabilitado en el portal y en Keycloak
    keycloak.unavailable = True
    response = toggle(client, linked)
    assert response.status_code == 503 and stored(linked.email).is_active is False
    keycloak.unavailable = False
    assert toggle(client, linked).status_code == 303
    assert stored(linked.email).is_active is True and keycloak.account(linked.email).enabled


def test_habilitar_proveedor_sin_proveedor(client, orphan):
    login(client)
    token = csrf(client, "/admin/users")
    response = client.post(f"/admin/users/{orphan.id}/toggle", data={"csrf_token": token}, follow_redirects=False)
    assert response.status_code == 409
    assert "El usuario no está vinculado a un proveedor: dé de alta uno nuevo con su proveedor" in response.text
    assert stored(orphan.email).is_active is False


@pytest.mark.parametrize(
    ("supplier", "message"),
    [
        (None, "Su usuario no está vinculado a un proveedor. Contacte al Administrador"),
        (SimpleNamespace(status=SupplierStatus.REGISTERED), "Su proveedor no está autorizado para registrar facturas"),
    ],
)
def test_mensaje_al_registrar_factura(supplier, message):
    # Con el CHECK, un Proveedor activo sin proveedor ya no puede existir: el mensaje es la defensa del router.
    with pytest.raises(BusinessRuleError, match=message):
        _ensure_supplier_active(SimpleNamespace(supplier=supplier))
