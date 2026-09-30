"""Alta y habilitacion de usuarios con la regla rol-proveedor (spec administracion-usuarios; change
usuario-proveedor-vinculado)."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from app.core.constants import Role, SupplierStatus
from app.core.database import SessionLocal
from app.core.errors import BusinessRuleError
from app.core.security import hash_password
from app.models import User
from app.routers.invoices import _ensure_supplier_active
from tests.conftest import csrf, login, supplier_by_email

PASSWORD = "Temporal#2026"


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
        "password": PASSWORD,
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
    response = create(client, email, "PROVIDER")
    assert response.status_code == 400 and "Seleccione el proveedor del usuario" in response.text
    assert stored(email) is None
    # El formulario vuelve abierto con lo capturado, sin la contrasena.
    page = response.text
    assert '<details class="panel admin-create" open>' in page
    assert f'value="{email}"' in page and 'value="Joshua Bolaños Hernández"' in page
    assert "<option selected>PROVIDER</option>" in page and PASSWORD not in page


def test_proveedor_inexistente(client, email):
    login(client)
    response = create(client, email, "PROVIDER", 999999)
    assert response.status_code == 400 and "Proveedor inexistente" in response.text and stored(email) is None


def test_proveedor_con_su_proveedor(client, email):
    supplier = supplier_by_email("proveedor1@poc.local")
    login(client)
    assert create(client, email, "PROVIDER", supplier.id).status_code == 303
    created = stored(email)
    assert (created.role, created.supplier_id, created.is_active) == (Role.PROVIDER, supplier.id, True)


@pytest.mark.parametrize("role", ["INTERNAL", "ADMIN"])
def test_interno_o_administrador_sin_proveedor(client, email, role):
    supplier = supplier_by_email("proveedor1@poc.local")
    login(client)
    assert create(client, email, role, supplier.id).status_code == 303
    assert stored(email).supplier_id is None


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
            password_hash=hash_password(PASSWORD),
            role=Role.PROVIDER,
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
