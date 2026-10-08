import html
import re
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select

from app.core.constants import SupplierStatus
from app.core.database import SessionLocal
from app.core.passwords import generate_password
from app.models import Contract, EmailDelivery, Invoice, Supplier, User
from app.services.keycloak_admin import UPDATE_PASSWORD
from tests.conftest import SUPPLIER_PROFILE_FORM, csrf, login, supplier_by_email


def create_user(client, email="nuevo@ultrasist.com.mx", **extra):
    data = {"name": "Usuario Nuevo", "email": email, "role": "PMO", **extra}
    return client.post("/admin/users", data={**data, "csrf_token": csrf(client, "/admin/users")})


def user_exists(email: str) -> bool:
    with SessionLocal() as db:
        return db.scalar(select(User.id).where(User.email == email)) is not None


def test_alta_crea_el_usuario_en_keycloak_sin_contrasena_local(client, keycloak):
    login(client)
    response = create_user(client, email="valida@ultrasist.com.mx")
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    with SessionLocal() as db:
        created = db.scalar(select(User).where(User.email == "valida@ultrasist.com.mx"))
    # RN-HU03-01: el portal no guarda la contrasena ni su hash; la cuenta vive en Keycloak, enlazada por sub.
    assert created.password_hash is None and created.keycloak_sub
    account = keycloak.account("valida@ultrasist.com.mx")
    assert (account.id, account.roles, account.required_actions) == (created.keycloak_sub, {"PMO"}, [UPDATE_PASSWORD])
    # La temporal se muestra una sola vez, en esta respuesta (D15). Escapada: puede contener &, < o >.
    assert f"<code>{html.escape(account.password)}</code>" in response.text
    assert html.escape(account.password) not in client.get("/admin/users?q=valida").text


def test_contrasenas_temporales_cumplen_la_politica():
    for _ in range(1000):
        password = generate_password()
        assert len(password) == 20
        assert re.search(r"[A-Za-z]", password) and re.search(r"\d", password) and re.search(r"[^A-Za-z0-9]", password)


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
    assert "Periodo de servicio (MM/AAAA): el mes debe estar entre 01 y 12" in html.unescape(response.text)
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Invoice)) == before


def period_invoice(client, period: str):
    """Alta de una factura del proveedor 1 con el periodo capturado tal cual."""
    supplier = supplier_by_email("proveedor1@poc.local")
    with SessionLocal() as db:
        contract = db.scalar(
            select(Contract)
            .where(Contract.supplier_id == supplier.id, Contract.status == "ACTIVE")
            .order_by(Contract.id)
        )
    login(client, "proveedor1@poc.local")
    number = f"PERIODO-{uuid4().hex[:8]}"
    data = {
        "contract_id": contract.id,
        "invoice_number": number,
        "service_period": period,
        "project_name": contract.project_name,
        "csrf_token": csrf(client, "/invoices/new"),
    }
    return client.post("/invoices/new", data=data, follow_redirects=False), number


@pytest.mark.parametrize(
    ("captured", "stored"),
    [
        ("08/2026", "08/2026"),
        ("8/2026", "08/2026"),
        ("08-2026", "08/2026"),
        (" 08 / 2026 ", "08/2026"),
        ("2026-08", "08/2026"),
    ],
)
def test_periodo_sin_formato_estricto(client, captured, stored):
    """El periodo se acepta con separadores y espacios comunes y se guarda como MM/AAAA."""
    response, number = period_invoice(client, captured)
    assert response.status_code == 303
    with SessionLocal() as db:
        assert db.scalar(select(Invoice.service_period).where(Invoice.invoice_number == number)) == stored


@pytest.mark.parametrize("captured", ["agosto 2026", "2026", "08/26"])
def test_periodo_sin_mes_y_anio(client, captured):
    response, _ = period_invoice(client, captured)
    assert response.status_code == 400
    assert "Periodo de servicio (MM/AAAA): use el formato MM/AAAA, por ejemplo 08/2026" in html.unescape(response.text)
