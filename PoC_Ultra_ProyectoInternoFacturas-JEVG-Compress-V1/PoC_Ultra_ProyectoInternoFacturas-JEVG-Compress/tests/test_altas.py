import pytest
from sqlalchemy import delete, func, select

from app.core.constants import SupplierStatus
from app.core.database import SessionLocal
from app.core.demo import DEMO_ACCOUNTS
from app.core.passwords import generate_password, password_problems
from app.core.security import verify_password
from app.models import Contract, EmailDelivery, Invoice, Supplier, User
from tests.conftest import SUPPLIER_PROFILE_FORM, csrf, login, supplier_by_email


def create_user(client, email="nuevo@ultrasist.com.mx", password="Portal#2026x", **extra):
    data = {"name": "Usuario Nuevo", "email": email, "password": password, "role": "INTERNAL", **extra}
    return client.post("/admin/users", data={**data, "csrf_token": csrf(client, "/admin/users")})


def user_exists(email: str) -> bool:
    with SessionLocal() as db:
        return db.scalar(select(User.id).where(User.email == email)) is not None


@pytest.mark.parametrize(
    ("password", "reason"),
    [
        ("Ab1!", "al menos 8"),
        ("Password123", "caracter especial"),
        ("Password1!", "demasiado comun"),
        ("sinnumeros#", "numero"),
        ("12345678#", "letra"),
    ],
)
def test_contrasena_invalida_rechazada(client, password, reason):
    login(client)
    response = create_user(client, email="debil@ultrasist.com.mx", password=password)
    assert response.status_code == 400
    assert reason in response.text
    assert not user_exists("debil@ultrasist.com.mx")


def test_contrasena_excesiva_rechazada_sin_calcular_hash(client, monkeypatch):
    import app.routers.admin as admin

    def never(_password):
        raise AssertionError("no debe calcular el hash")

    monkeypatch.setattr(admin, "hash_password", never)
    login(client)
    response = create_user(client, email="larga@ultrasist.com.mx", password="Ab1#" + "x" * 125)
    assert response.status_code == 400
    assert "128" in response.text


def test_contrasena_valida_crea_usuario(client):
    login(client)
    response = create_user(client, email="valida@ultrasist.com.mx", password="Portal#2026x")
    assert response.status_code == 200  # sigue la redireccion al listado
    with SessionLocal() as db:
        created = db.scalar(select(User).where(User.email == "valida@ultrasist.com.mx"))
    assert verify_password("Portal#2026x", created.password_hash)


def test_contrasenas_demo_y_generadas_cumplen_la_politica():
    for account in DEMO_ACCOUNTS:
        assert password_problems(account.password) == [], account.email
    for _ in range(50):
        assert password_problems(generate_password()) == []


def test_correo_invalido_en_alta_de_usuario(client):
    login(client)
    response = create_user(client, email="no-es-correo")
    assert response.status_code == 400
    assert "Correo: no es un correo valido" in response.text


def test_correo_duplicado_responde_409(client):
    login(client)
    assert create_user(client, email="duplicado@ultrasist.com.mx").status_code == 200
    response = create_user(client, email="Duplicado@Ultrasist.com.mx")
    assert response.status_code == 409
    assert "Ya existe un usuario" in response.text


def create_supplier(client, **overrides):
    data = {
        "business_name": "Servicios Nuevos SA de CV",
        "rfc": "SNU260101AB1",
        "supplier_type": "PERSONA_MORAL",
        "email": "contacto@serviciosnuevos.mx",
        **SUPPLIER_PROFILE_FORM,
        **overrides,
    }
    return client.post("/suppliers", data={**data, "csrf_token": csrf(client, "/suppliers")})


def test_correo_invalido_en_alta_de_proveedor(client):
    login(client)
    response = create_supplier(client, email="proveedor@", rfc="SNU260101AB2")
    assert response.status_code == 400
    assert "no es un correo valido" in response.text
    with SessionLocal() as db:
        assert db.scalar(select(Supplier.id).where(Supplier.rfc == "SNU260101AB2")) is None


def test_rfc_duplicado_responde_409(client):
    login(client)
    response = create_supplier(client, rfc="tic210101abc")
    assert response.status_code == 409
    assert "Ya existe un proveedor" in response.text


def test_alta_individual_queda_registrada(client, restore_notification_recipients):
    login(client)
    response = create_supplier(client, rfc="SNU260101RG1", email="Registro.Individual@ServiciosNuevos.mx")
    assert response.status_code == 200
    with SessionLocal() as db:
        supplier = db.scalar(select(Supplier).where(Supplier.rfc == "SNU260101RG1"))
        try:
            assert supplier.status == SupplierStatus.REGISTERED
            assert supplier.email == "registro.individual@serviciosnuevos.mx"
            assert db.scalar(select(User.id).where(User.supplier_id == supplier.id)) is None
            assert db.scalar(select(func.count(EmailDelivery.id))) == 0
            assert "Registrado" in client.get(f"/suppliers/{supplier.id}").text
        finally:
            db.delete(supplier)
            db.commit()


def test_alta_individual_con_correo_en_uso(client):
    login(client)
    assert create_supplier(client, rfc="SNU260101CU1", email="compartido@serviciosnuevos.mx").status_code == 200
    assert create_user(client, email="usuario.existente@ultrasist.com.mx").status_code == 200
    try:
        for email in ("Compartido@ServiciosNuevos.mx", "usuario.existente@ultrasist.com.mx"):
            response = create_supplier(client, rfc="SNU260101CU2", email=email)
            assert response.status_code == 409
            assert "El correo ya lo usa otro proveedor o usuario." in response.text
        with SessionLocal() as db:
            assert db.scalar(select(Supplier.id).where(Supplier.rfc == "SNU260101CU2")) is None
    finally:
        with SessionLocal() as db:
            supplier_id = db.scalar(select(Supplier.id).where(Supplier.rfc == "SNU260101CU1"))
            user_id = db.scalar(select(User.id).where(User.email == "usuario.existente@ultrasist.com.mx"))
            db.execute(delete(User).where(User.id == user_id))
            db.execute(delete(Supplier).where(Supplier.id == supplier_id))
            db.commit()


def test_periodo_invalido_en_alta_de_factura(client):
    supplier = supplier_by_email("proveedor1@poc.local")
    with SessionLocal() as db:
        contract = db.scalar(select(Contract).where(Contract.supplier_id == supplier.id))
        before = db.scalar(select(func.count()).select_from(Invoice))
    login(client, "proveedor1@poc.local")
    data = {
        "supplier_id": supplier.id,
        "contract_id": contract.id,
        "invoice_number": "PERIODO-INVALIDO",
        "service_period": "13/2026",
        "project_name": contract.project_name,
        "csrf_token": csrf(client, "/invoices/new"),
    }
    response = client.post("/invoices/new", data=data, follow_redirects=False)
    assert response.status_code == 400
    assert "Periodo de servicio" in response.text
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Invoice)) == before
