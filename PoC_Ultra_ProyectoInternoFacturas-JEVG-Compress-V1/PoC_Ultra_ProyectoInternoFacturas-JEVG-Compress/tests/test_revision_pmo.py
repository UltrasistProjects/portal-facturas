"""Bandeja y detalle del PMO (HU-18 y HU-19, specs revision-pmo, flujo-facturas y almacenamiento-documentos)."""

import re
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.core.constants import InvoiceStatus, ReviewDecision, Role, SupplierStatus, SupplierType
from app.core.database import SessionLocal
from app.models import AuditLog, Document, Invoice, Review, Supplier, User, ValidationResult
from app.repositories.invoice_repository import search_invoices
from app.services import document_view_service
from tests.conftest import csrf, invoice_by_number, login
from tests.test_flujo import count_queries

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


# --- Datos de prueba ----------------------------------------------------------------------------------------------


def user_id(email: str) -> int:
    with SessionLocal() as db:
        return db.scalar(select(User.id).where(User.email == email))


@pytest.fixture(scope="module")
def queue():
    """Proveedor propio con tres facturas "Enviada" en 2001 (las primeras de la bandeja) y un borrador."""
    with SessionLocal() as db:
        supplier = db.scalar(select(Supplier).where(Supplier.email == "bandeja@proveedor.mx"))
        if supplier is None:
            supplier = Supplier(
                business_name="Proveedor Bandeja SA de CV",
                rfc="PBA010101AB1",
                supplier_type=SupplierType.PERSONA_MORAL,
                email="bandeja@proveedor.mx",
                status=SupplierStatus.ACTIVE,
            )
            db.add(supplier)
            db.flush()
            admin = db.scalar(select(User.id).where(User.email == "admin@poc.local"))
            for day, status in ((3, InvoiceStatus.UNDER_REVIEW), (1, InvoiceStatus.UNDER_REVIEW),
                                (2, InvoiceStatus.UNDER_REVIEW), (4, InvoiceStatus.DRAFT)):  # fmt: skip
                db.add(
                    Invoice(
                        internal_folio=f"FAC-BND-{day:05d}",
                        supplier_id=supplier.id,
                        uploaded_by=admin,
                        invoice_number=f"BND-{day}",
                        service_period="01/2001",
                        project_name="Proyecto Bandeja",
                        status=status,
                        submitted_at=datetime(2001, 1, day, 12, tzinfo=timezone.utc)
                        if status == InvoiceStatus.UNDER_REVIEW
                        else None,
                    )
                )
            db.commit()
        return supplier.id


def row(page: str, folio: str) -> str:
    match = re.search(rf"<tr>(?:(?!</tr>).)*{re.escape(folio)}.*?</tr>", page, re.S)
    assert match, folio
    return match.group(0)


def new_invoice_for(supplier_email: str, **values) -> Invoice:
    with SessionLocal() as db:
        supplier_id = db.scalar(select(Supplier.id).where(Supplier.email == supplier_email))
        invoice = Invoice(
            internal_folio=f"FAC-T-{uuid4().hex[:10]}",
            supplier_id=supplier_id,
            uploaded_by=user_id("admin@poc.local"),
            invoice_number=f"RPMO-{uuid4().hex[:8]}",
            service_period="09/2026",
            **{"project_name": "Proyecto de prueba", **values},
        )
        db.add(invoice)
        db.commit()
        db.refresh(invoice)
        return invoice


# --- Bandeja ------------------------------------------------------------------------------------------------------


def test_bandeja_inicial(client, queue):
    login(client, "pmo@poc.local")
    page = client.get("/invoices").text
    assert '<option value="UNDER_REVIEW" selected>' in page and "Bandeja de revisión" in page
    first, second, third = (page.index(f"FAC-BND-{day:05d}") for day in (1, 2, 3))
    assert first < second < third  # enviada el 1, el 2 y el 3 de enero de 2001
    assert third < page.index(invoice_by_number("REVISION-001").internal_folio)
    assert "FAC-BND-00004" not in page  # el borrador no esta en la bandeja


def test_segunda_pagina_conserva_el_orden(queue):
    pmo = SimpleNamespace(role=Role.INTERNAL, supplier_id=None)
    with SessionLocal() as db:
        pages = [search_invoices(db, pmo, status="UNDER_REVIEW", page=n, per_page=2).items for n in (1, 2)]
    sent = [invoice.submitted_at for invoice in pages[0] + pages[1]]
    assert sent == sorted(sent) and [i.internal_folio for i in pages[0]] == ["FAC-BND-00001", "FAC-BND-00002"]
    assert pages[1][0].internal_folio == "FAC-BND-00003"


def test_paginacion_de_la_bandeja_lleva_el_estatus(client, queue):
    login(client, "pmo@poc.local")
    # Pagina fuera de rango: la paginacion muestra la ultima y sus enlaces conservan el estatus efectivo.
    page = client.get("/invoices", params={"status": "UNDER_REVIEW", "page": 2}).text
    assert '<option value="UNDER_REVIEW" selected>' in page
    assert '<option value="">Todos los estados</option>' in page  # "Todos" siempre envia status vacio


def test_todos_los_estados(client, queue):
    login(client, "pmo@poc.local")
    page = client.get("/invoices", params={"status": "", "q": "BND"}).text
    assert '<option value="" selected>Todos los estados</option>' in page
    # Orden por creacion descendente: el borrador se creo al final.
    assert page.index("FAC-BND-00004") < page.index("FAC-BND-00001")


def test_proveedor_sin_bandeja(client):
    draft = new_invoice_for("proveedor1@poc.local")  # la mas reciente: primera en su listado
    login(client, "proveedor1@poc.local")
    page = client.get("/invoices").text
    assert draft.internal_folio in page
    assert "<th>Origen</th>" not in page and 'name="origin"' not in page


@pytest.mark.parametrize("origin", ["INTERNATIONAL", "NATIONAL"])
def test_filtro_por_origen(client, origin):
    # Dos facturas con el mismo proyecto unico, una por origen: la busqueda las aisla del resto de la base.
    project = f"Origen {uuid4().hex[:8]}"
    national = new_invoice_for("proveedor1@poc.local", project_name=project)
    international = new_invoice_for("proveedor3@poc.local", project_name=project)
    present, absent = (international, national) if origin == "INTERNATIONAL" else (national, international)
    login(client, "pmo@poc.local")
    page = client.get("/invoices", params={"status": "", "origin": origin, "q": project}).text
    assert present.internal_folio in page and absent.internal_folio not in page


def test_origen_desconocido_se_ignora(client):
    login(client, "pmo@poc.local")
    page = client.get("/invoices", params={"status": "", "origin": "MARTE", "q": "A-CORRECTA"}).text
    assert invoice_by_number("A-CORRECTA").internal_folio in page


def test_columnas_y_advertencias(client):
    invoice = new_invoice_for(
        "proveedor3@poc.local",
        status=InvoiceStatus.UNDER_REVIEW,
        submitted_at=datetime(2001, 1, 10, 12, tzinfo=timezone.utc),  # 06:00 en la zona de negocio
        subtotal=Decimal("1000.00"),
        tax=Decimal("0.00"),
        total=Decimal("1000.00"),
        currency="USD",
        validation_score=94,
    )
    with SessionLocal() as db:
        for code in ("INT-001", "INT-002"):
            db.add(
                ValidationResult(
                    invoice_id=invoice.id,
                    rule_code=code,
                    category="INT",
                    status="WARNING",
                    severity="WARNING",
                    message="No encontrado",
                )
            )
        db.commit()
    login(client, "pmo@poc.local")
    cells = row(client.get("/invoices").text, invoice.internal_folio)
    assert "Internacional" in cells and "10/01/2001" in cells
    assert "$1,000.00" in cells and "USD" in cells and "2 advertencias" in cells


def test_consultas_constantes(client, queue):
    login(client, "pmo@poc.local")
    full_page = count_queries(lambda: client.get("/invoices", params={"status": ""}))
    single = count_queries(lambda: client.get("/invoices", params={"status": "", "q": "FAC-BND-00001"}))
    assert full_page == single


# --- Visualizacion de documentos ----------------------------------------------------------------------------------


def document_of(number: str, document_type: str) -> tuple[int, int]:
    invoice = invoice_by_number(number)
    with SessionLocal() as db:
        document_id = db.scalar(
            select(Document.id).where(
                Document.invoice_id == invoice.id,
                Document.document_type == document_type,
                Document.is_current.is_(True),
            )
        )
    return invoice.id, document_id


def test_ver_pdf_como_imagenes(client):
    invoice_id, document_id = document_of("A-CORRECTA", "INVOICE_PDF")
    login(client, "pmo@poc.local")
    base = f"/invoices/{invoice_id}/documents/{document_id}"
    view = client.get(f"{base}/view")
    assert view.status_code == 200 and f'src="{base}/pages/1"' in view.text
    assert view.headers["cache-control"] == "private, max-age=300"
    page = client.get(f"{base}/pages/1")
    assert page.status_code == 200 and page.headers["content-type"] == "image/png"
    assert page.content.startswith(b"\x89PNG")


@pytest.mark.parametrize("number", [0, 99])
def test_pagina_inexistente(client, number):
    invoice_id, document_id = document_of("A-CORRECTA", "INVOICE_PDF")
    login(client, "pmo@poc.local")
    assert client.get(f"/invoices/{invoice_id}/documents/{document_id}/pages/{number}").status_code == 404


def test_xml_escapado(client):
    invoice_id, document_id = document_of("A-CORRECTA", "INVOICE_XML")
    login(client, "pmo@poc.local")
    response = client.get(f"/invoices/{invoice_id}/documents/{document_id}/view")
    assert response.headers["content-type"].startswith("text/html")
    assert "&lt;cfdi:Comprobante" in response.text and "<cfdi:Comprobante" not in response.text
    assert client.get(f"/invoices/{invoice_id}/documents/{document_id}/pages/1").status_code == 404
    assert client.get(f"/invoices/{invoice_id}/documents/{document_id}/image").status_code == 404


def test_texto_truncado(client, monkeypatch):
    monkeypatch.setattr(document_view_service, "TEXT_LIMIT", 10)
    invoice_id, document_id = document_of("A-CORRECTA", "PURCHASE_ORDER")
    login(client, "pmo@poc.local")
    page = client.get(f"/invoices/{invoice_id}/documents/{document_id}/view").text
    assert "Se muestran los primeros 10 caracteres." in page


def test_imagen_inline(client):
    login(client, "proveedor1@poc.local")
    base = invoice_by_number("A-CORRECTA")
    number = f"IMG-{uuid4().hex[:8]}"
    data = {
        "contract_id": base.contract_id,
        "invoice_number": number,
        "service_period": "08/2026",
        "project_name": base.project_name,
        "csrf_token": csrf(client, "/invoices/new"),
    }
    assert client.post("/invoices/new", data=data, follow_redirects=False).status_code == 303
    invoice = invoice_by_number(number)
    upload = client.post(
        f"/invoices/{invoice.id}/documents",
        data={"document_type": "PURCHASE_ORDER", "csrf_token": csrf(client, f"/invoices/{invoice.id}")},
        files={"upload": ("orden.png", PNG, "application/octet-stream")},
        follow_redirects=False,
    )
    assert upload.status_code == 303
    _, document_id = document_of(number, "PURCHASE_ORDER")
    base_url = f"/invoices/{invoice.id}/documents/{document_id}"
    assert f'src="{base_url}/image"' in client.get(f"{base_url}/view").text
    image = client.get(f"{base_url}/image")
    assert image.headers["content-type"] == "image/png"
    assert image.headers["content-disposition"].startswith("inline")


@pytest.mark.parametrize("suffix", ["view", "pages/1", "image", "download"])
def test_documento_de_otro_proveedor(client, suffix):
    invoice_id, document_id = document_of("A-CORRECTA", "INVOICE_PDF")
    login(client, "proveedor2@poc.local")
    assert client.get(f"/invoices/{invoice_id}/documents/{document_id}/{suffix}").status_code == 404


def test_documento_de_otra_factura(client):
    _, document_id = document_of("A-CORRECTA", "INVOICE_PDF")
    other = invoice_by_number("REVISION-001")
    login(client, "pmo@poc.local")
    assert client.get(f"/invoices/{other.id}/documents/{document_id}/view").status_code == 404


def test_pdf_danado(client):
    invoice = new_invoice_for("proveedor1@poc.local")
    folder = settings.storage_path / "invoices" / str(invoice.id)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "danado.pdf").write_bytes(b"esto no es un PDF")
    with SessionLocal() as db:
        document = Document(
            invoice_id=invoice.id,
            supplier_id=invoice.supplier_id,
            document_type="INVOICE_PDF",
            original_filename="danado.pdf",
            stored_filename="danado.pdf",
            path=f"invoices/{invoice.id}/danado.pdf",
            mime_type="application/pdf",
            file_size=17,
            sha256="0" * 64,
            uploaded_by=invoice.uploaded_by,
        )
        db.add(document)
        db.commit()
        document_id = document.id
    login(client, "pmo@poc.local")
    base = f"/invoices/{invoice.id}/documents/{document_id}"
    assert "No se pudo mostrar el documento" in client.get(f"{base}/view").text
    assert client.get(f"{base}/pages/1").status_code == 404


def test_enlace_ver_en_el_detalle(client):
    invoice_id, document_id = document_of("A-CORRECTA", "INVOICE_PDF")
    login(client, "pmo@poc.local")
    page = client.get(f"/invoices/{invoice_id}").text
    assert f'href="/invoices/{invoice_id}/documents/{document_id}/view" target="_blank" rel="noopener"' in page


# --- Detalle para la revision -------------------------------------------------------------------------------------


def test_bloque_del_proveedor(client):
    login(client, "pmo@poc.local")
    page = client.get(f"/invoices/{invoice_by_number('INV-2026-0042').id}").text
    block = re.search(r'<section class="panel" id="supplier">.*?</section>', page, re.S).group(0)
    for text in ("Global Data Services Inc. (DEMO)", "Internacional", "US 98-7654321", "proveedor3@poc.local"):
        assert text in block
    assert "Autorizado" in block


def test_historial_de_una_factura_devuelta_y_reenviada(client, queue):
    invoice = new_invoice_for("bandeja@proveedor.mx", status=InvoiceStatus.UNDER_REVIEW)
    admin, pmo = user_id("admin@poc.local"), user_id("pmo@poc.local")
    with SessionLocal() as db:
        for day in (1, 3):
            db.add(
                AuditLog(
                    user_id=admin,
                    action="INVOICE_SUBMITTED",
                    entity="Invoice",
                    entity_id=str(invoice.id),
                    timestamp=datetime(2026, 9, day, 15, tzinfo=timezone.utc),
                )
            )
        db.add(
            Review(
                invoice_id=invoice.id,
                reviewer_id=pmo,
                decision=ReviewDecision.REQUIRES_CORRECTION,
                comments="Falta el Vo.Bo.",
                created_at=datetime(2026, 9, 2, 15, tzinfo=timezone.utc),
            )
        )
        db.commit()
        pmo_name = db.get(User, pmo).name
    login(client, "pmo@poc.local")
    page = client.get(f"/invoices/{invoice.id}").text
    history = re.search(r'<section class="panel" id="history">.*?</section>', page, re.S).group(0)
    first = history.index("Enviada a validación")
    observations = history.index("Observaciones")
    second = history.index("Enviada a validación", observations)
    assert first < observations < second
    assert "Falta el Vo.Bo." in history and pmo_name in history
    assert "01/09/2026 09:00" in history  # 15:00 UTC en America/Mexico_City


def test_historial_vacio(client):
    login(client, "pmo@poc.local")
    page = client.get(f"/invoices/{invoice_by_number('BORRADOR-001').id}").text
    assert "Sin envíos ni revisiones" in page


def test_proveedor_con_seguimiento_sin_bloque_proveedor(client):
    # HU-17: el proveedor ve el historial como "Seguimiento"; el bloque "Proveedor" sigue siendo del PMO.
    login(client, "proveedor1@poc.local")
    page = client.get(f"/invoices/{invoice_by_number('A-CORRECTA').id}").text
    assert "<h2>Seguimiento</h2>" in page and "<h2>Historial</h2>" not in page and 'id="supplier"' not in page
