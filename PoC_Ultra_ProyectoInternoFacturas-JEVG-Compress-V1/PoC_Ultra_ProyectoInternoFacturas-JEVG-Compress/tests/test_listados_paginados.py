"""Listados paginados con busqueda y retorno tras altas y acciones (spec listados-paginados; bitacora de
notificaciones-correo).

Cada prueba crea sus registros con un prefijo unico, los busca por ese prefijo (asi no depende del resto de la base
compartida) y los borra al terminar.
"""

import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from app.core.constants import CatalogType, DeliveryStatus, Role, SupplierOrigin, SupplierStatus, SupplierType
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models import CatalogEntry, Contract, EmailDelivery, Supplier, User
from app.repositories.pagination import back_to
from tests.conftest import csrf, login, supplier_by_email
from tests.test_flujo import count_queries

TOTAL = 30  # 25 en la primera pagina y 5 en la segunda


def prefix() -> str:
    return f"PAG{uuid4().hex[:8].upper()}"


def rows(page: str) -> str:
    return page.split("<tbody>", 1)[1].split("</tbody>", 1)[0]


def page_info(page: str) -> str | None:
    match = re.search(r"Página (\d+) de (\d+) · (\d+) registros", page)
    return match.group(0) if match else None


# --- Datos --------------------------------------------------------------------------------------------------------


@pytest.fixture()
def many_users():
    tag = prefix()
    with SessionLocal() as db:
        db.add_all(
            User(
                name=f"{tag} Usuario {index:02d}",
                email=f"{tag.lower()}.{index:02d}@lista.example",
                password_hash=hash_password("Lista#Prueba2026"),
                role=Role.INTERNAL,
            )
            for index in range(TOTAL)
        )
        db.commit()
    yield tag
    with SessionLocal() as db:
        db.execute(delete(User).where(User.name.startswith(tag)))
        db.commit()


@pytest.fixture()
def many_suppliers():
    tag = prefix()
    with SessionLocal() as db:
        db.add_all(
            Supplier(
                business_name=f"{tag} Proveedor {index:02d}",
                supplier_type=SupplierType.PERSONA_MORAL,
                email=f"{tag.lower()}.{index:02d}@proveedor.example",
                origin=SupplierOrigin.INTERNATIONAL,
                rfc=None,
                foreign_tax_id=f"{tag}-{index:02d}",
                country="US",
                status=SupplierStatus.REGISTERED if index % 2 else SupplierStatus.ACTIVE,
            )
            for index in range(TOTAL)
        )
        db.commit()
    yield tag
    with SessionLocal() as db:
        db.execute(delete(Supplier).where(Supplier.business_name.startswith(tag)))
        db.commit()


@pytest.fixture()
def many_contracts():
    tag = prefix()
    supplier = supplier_by_email("proveedor1@poc.local")
    with SessionLocal() as db:
        db.add_all(
            Contract(
                supplier_id=supplier.id,
                project_name=f"{tag} Proyecto {index:02d}",
                project_leader="Lider",
                authorized_technology="Power Platform",
                authorized_amount=Decimal("1000.00"),
                currency="MXN",
                start_date=date(2026, 1, 1),
                end_date=date(2026, 12, 31),
            )
            for index in range(TOTAL)
        )
        db.commit()
    yield tag
    with SessionLocal() as db:
        db.execute(delete(Contract).where(Contract.project_name.startswith(tag)))
        db.commit()


@pytest.fixture()
def many_entries():
    """30 actividades economicas 99xx00..99xx29 (claves de 6 digitos), 2 inactivas."""
    base = f"99{uuid4().int % 90 + 10:02d}"
    with SessionLocal() as db:
        db.add_all(
            CatalogEntry(
                catalog=CatalogType.INDUSTRY,
                code=f"{base}{index:02d}",
                name=f"Actividad de prueba {base}{index:02d}",
                is_active=index >= 2,
            )
            for index in range(TOTAL)
        )
        db.commit()
    yield base
    with SessionLocal() as db:
        db.execute(delete(CatalogEntry).where(CatalogEntry.code.startswith(base)))
        db.commit()


# --- Paginacion y busqueda -----------------------------------------------------------------------------------------


def test_segunda_pagina_de_usuarios(client, many_users):
    login(client)
    first = client.get("/admin/users", params={"q": many_users}).text
    assert rows(first).count("<tr>") == 25 and page_info(first) == f"Página 1 de 2 · {TOTAL} registros"
    assert f'href="?q={many_users}&page=2"' in first
    second = client.get("/admin/users", params={"q": many_users, "page": 2}).text
    names = re.findall(rf"<strong>({many_users} Usuario \d+)</strong>", second)
    assert names == [f"{many_users} Usuario {index:02d}" for index in range(25, TOTAL)]


def test_pagina_fuera_de_rango(client, many_contracts):
    login(client)
    page = client.get("/contracts", params={"q": many_contracts, "page": 99}).text
    assert page_info(page) == f"Página 2 de 2 · {TOTAL} registros"


def test_contratos_del_mas_reciente_al_mas_antiguo(client, many_contracts):
    login(client)
    page = client.get("/contracts", params={"q": many_contracts.lower()}).text
    projects = re.findall(rf"<strong>({many_contracts} Proyecto \d+)</strong>", page)
    assert projects[0] == f"{many_contracts} Proyecto {TOTAL - 1:02d}" and len(projects) == 25


def test_proveedores_con_filtro_y_busqueda(client, many_suppliers):
    login(client)
    page = client.get("/suppliers", params={"q": many_suppliers.lower(), "status": "REGISTERED"}).text
    found = re.findall(rf"<strong>({many_suppliers} Proveedor \d+)</strong>", page)
    assert len(found) == TOTAL // 2 and all(int(name[-2:]) % 2 for name in found)
    assert page_info(page) is None  # 15 registros caben en una pagina
    everything = client.get("/suppliers", params={"q": many_suppliers}).text
    assert f'href="?q={many_suppliers}&page=2"' in everything
    # Busqueda por identificador fiscal.
    by_tax_id = client.get("/suppliers", params={"q": f"{many_suppliers}-07"}).text
    assert re.findall(rf"<strong>({many_suppliers} Proveedor \d+)</strong>", by_tax_id) == [
        f"{many_suppliers} Proveedor 07"
    ]


def test_proveedores_paginados_sin_consultas_por_fila(client, many_suppliers):
    login(client)
    queries = count_queries(lambda: client.get("/suppliers", params={"q": many_suppliers}))
    few = count_queries(lambda: client.get("/suppliers", params={"q": f"{many_suppliers} Proveedor 00"}))
    assert queries == few


def test_comodines_literales(client, many_users):
    login(client)
    page = client.get("/admin/users", params={"q": "%"}).text
    assert "Sin resultados para la búsqueda." in page


def test_claves_paginadas_con_conteo_en_sql(client, many_entries):
    login(client)
    with SessionLocal() as db:
        all_entries = db.scalars(select(CatalogEntry).where(CatalogEntry.catalog == CatalogType.INDUSTRY)).all()
    active = sum(entry.is_active for entry in all_entries)
    page = client.get("/admin/catalogs/INDUSTRY", params={"q": many_entries}).text
    assert f"{active} activas de {len(all_entries)}." in page
    assert rows(page).count('class="mono"') == 25 and page_info(page) == f"Página 1 de 2 · {TOTAL} registros"


def test_bitacora_paginada(client, restore_notification_recipients):
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        db.add_all(
            EmailDelivery(
                event=None,
                status=DeliveryStatus.SENT,
                to_addresses=[f"envio{index:02d}@bitacora.example"],
                transport="file",
                message_id=f"<{index}@bitacora.example>",
                created_at=now - timedelta(minutes=TOTAL - index),
            )
            for index in range(TOTAL)
        )
        db.commit()
    login(client)
    first = client.get("/admin/notifications").text
    shown = re.findall(r"envio(\d+)@bitacora.example", first)
    assert shown == [f"{index:02d}" for index in range(TOTAL - 1, 4, -1)]
    assert page_info(first) == f"Página 1 de 2 · {TOTAL} registros" and "Bitácora de envíos" in first
    second = client.get("/admin/notifications", params={"page": 2}).text
    assert re.findall(r"envio(\d+)@bitacora.example", second) == ["04", "03", "02", "01", "00"]


# --- Alta visible y retorno ----------------------------------------------------------------------------------------


def test_alta_de_usuario_visible(client, many_users):
    login(client)
    email = f"{many_users.lower()}.nuevo@lista.example"
    data = {
        "name": "Joshua Bolaños Hernández",
        "email": email,
        "password": "Temporal#2026",
        "role": "INTERNAL",
        "supplier_id": "",
        "csrf_token": csrf(client, "/admin/users"),
    }
    try:
        response = client.post("/admin/users", data=data, follow_redirects=False)
        assert response.headers["location"] == f"/admin/users?q={email.replace('@', '%40')}&ok=created"
        page = client.get(response.headers["location"]).text
        assert "Usuario creado" in page and rows(page).count("<tr>") == 1 and "Joshua Bolaños Hernández" in page
    finally:
        with SessionLocal() as db:
            db.execute(delete(User).where(User.email == email))
            db.commit()


def test_alta_de_contrato_visible(client, many_contracts):
    login(client)
    supplier = supplier_by_email("proveedor1@poc.local")
    project = f"{many_contracts} Nuevo"
    data = {
        "supplier_id": supplier.id,
        "project_name": project,
        "project_leader": "Lider",
        "authorized_technology": "Power Platform",
        "authorized_amount": "1000.00",
        "currency": "MXN",
        "start_date": "2026-01-01",
        "end_date": "2026-12-31",
        "csrf_token": csrf(client, "/contracts"),
    }
    response = client.post("/contracts", data=data, follow_redirects=False)
    page = client.get(response.headers["location"]).text
    assert "Contrato creado" in page and re.findall(r"<strong>([^<]+)</strong><small>Lider", page)[0] == project


def test_alta_de_clave_visible(client, many_entries):
    login(client)
    code = f"{many_entries}99"
    data = {"entry_code": code, "name": "Actividad nueva", "csrf_token": csrf(client, "/admin/catalogs/INDUSTRY")}
    response = client.post("/admin/catalogs/INDUSTRY", data=data, follow_redirects=False)
    assert response.headers["location"] == f"/admin/catalogs/INDUSTRY?q={code}&ok=created"
    page = client.get(response.headers["location"]).text
    assert "Clave agregada" in page and code in rows(page)


def test_deshabilitar_regresa_a_la_misma_pagina(client, many_users):
    login(client)
    with SessionLocal() as db:
        target = db.scalar(select(User).where(User.name == f"{many_users} Usuario 27"))
    data = {"q": many_users, "page": "2", "csrf_token": csrf(client, "/admin/users")}
    response = client.post(f"/admin/users/{target.id}/toggle", data=data, follow_redirects=False)
    assert response.headers["location"] == f"/admin/users?q={many_users}&page=2"


def test_editar_clave_regresa_a_la_misma_pagina(client, many_entries):
    login(client)
    with SessionLocal() as db:
        entry = db.scalar(select(CatalogEntry).where(CatalogEntry.code == f"{many_entries}27"))
    data = {"name": "Otra descripción", "q": many_entries, "page": "2", "csrf_token": csrf(client, "/")}
    response = client.post(f"/admin/catalogs/INDUSTRY/{entry.id}", data=data, follow_redirects=False)
    assert response.headers["location"] == f"/admin/catalogs/INDUSTRY?q={many_entries}&page=2&ok=updated"


@pytest.mark.parametrize(
    ("form", "expected"),
    [
        ({}, "/admin/users"),
        ({"page": "1"}, "/admin/users"),
        ({"page": "abc", "q": " demo "}, "/admin/users?q=demo"),
        ({"q": "a&b", "status": "ACTIVE", "page": "3"}, "/admin/users?q=a%26b&status=ACTIVE&page=3"),
        # Solo q, status y page: otra clave (p. ej. un destino) se ignora.
        ({"next": "https://evil.example", "url": "//evil.example"}, "/admin/users"),
    ],
)
def test_back_to_solo_conserva_busqueda_filtro_y_pagina(form, expected):
    assert back_to("/admin/users", form) == expected
