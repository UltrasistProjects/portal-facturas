"""Pago de la factura y Complemento de Pago (HU Complemento de Pagos; specs pago-facturas, flujo-facturas,
archivos-minimos-factura, cancelacion-facturas y revision-pmo)."""

import hashlib
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select, update

from app.core.config import settings
from app.core.constants import PAYMENT_COMPLEMENT_WINDOW, InvoiceStatus
from app.core.database import SessionLocal
from app.models import Document, Invoice, Supplier, User
from tests.conftest import ROOT, csrf, login
from tests.test_acceso_proveedores import messages
from tests.test_cancelacion import (
    PDF,
    RECEPTION,
    audits,
    business,
    cancel,
    deliveries,
    logout,
    reload,
    smtp_down,  # noqa: F401 - fixture
    stored_files,
    user_id,
)
from tests.test_factura_internacional import INTERNATIONAL
from tests.test_registro_envio import create, own_contract_id

pytestmark = pytest.mark.usefixtures("restore_notification_recipients", "settle_complements")

PMO = "pmo@poc.local"
# Proveedor nacional de estas pruebas. No es proveedor1: sus facturas no deben cargar a ese proveedor demo, cuyo
# listado mide test_postgres (el planificador cambia de indice si concentra casi todas las filas).
PROVIDER = "proveedor2@poc.local"
# Otro proveedor para el aislamiento del bloqueo: el internacional demo, tampoco proveedor1 (ver PROVIDER).
OTHER_PROVIDER = INTERNATIONAL
COMPLEMENT_SOURCE = (ROOT / "data" / "demo_documents" / "complemento_pago_demo.xml").read_text(encoding="utf-8")
DEMO_RELATED = "DEMO0001-0000-4000-8000-000000000001"
NOTICE = "Es importante que adjunte su “Complemento de Pago” a dicha factura pagada antes del"
OVERDUE_PREFIX = "No puede enviar facturas a validación: tiene complementos de pago vencidos de las facturas"


@pytest.fixture()
def settle_complements():
    """La base de la sesion es compartida: al terminar, ningun complemento queda pendiente (bloquearia los envios
    del proveedor demo en otras pruebas)."""
    yield
    with SessionLocal() as db:
        db.execute(
            update(Invoice)
            .where(
                Invoice.status == InvoiceStatus.PAID,
                Invoice.payment_complement_due_at.is_not(None),
                Invoice.payment_complement_received_at.is_(None),
            )
            .values(payment_complement_received_at=Invoice.paid_at)
        )
        db.commit()


# --- Datos de prueba ----------------------------------------------------------------------------------------------


def new_uuid() -> str:
    return str(uuid4()).upper()


def invoice_for(email: str = PROVIDER, status: InvoiceStatus = InvoiceStatus.ACCEPTED, **values) -> Invoice:
    """Factura del proveedor del usuario `email` en `status`, sin documentos."""
    with SessionLocal() as db:
        supplier_id = db.scalar(select(User.supplier_id).where(User.email == email))
        invoice = Invoice(
            internal_folio=f"FAC-P-{uuid4().hex[:10]}",
            supplier_id=supplier_id,
            uploaded_by=user_id(email),
            invoice_number=f"PAGO-{uuid4().hex[:8].upper()}",
            service_period="09/2026",
            project_name="Proyecto pagado",
            subtotal=Decimal("100000.00"),
            tax=Decimal("16000.00"),
            total=Decimal("116000.00"),
            currency="MXN",
            status=status,
            **values,
        )
        db.add(invoice)
        db.commit()
        db.refresh(invoice)
        return invoice


def add_cfdi(invoice: Invoice, payment_method: str | None = "PPD") -> None:
    """XML del CFDI vigente con los datos que extrae el motor, y su archivo (los respaldos lo copian)."""
    stored = f"{uuid4().hex}.xml"
    path = f"invoices/{invoice.id}/{stored}"
    target = settings.storage_path / path
    target.parent.mkdir(parents=True, exist_ok=True)
    content = b'<?xml version="1.0" encoding="UTF-8"?><Comprobante/>'
    target.write_bytes(content)
    with SessionLocal() as db:
        metadata = {"uuid": invoice.uuid, "voucher_type": "I"}
        if payment_method:
            metadata["payment_method"] = payment_method
        db.add(
            Document(
                invoice_id=invoice.id,
                supplier_id=invoice.supplier_id,
                document_type="INVOICE_XML",
                original_filename="cfdi.xml",
                stored_filename=stored,
                path=path,
                mime_type="application/xml",
                file_size=len(content),
                sha256=hashlib.sha256(content).hexdigest(),
                uploaded_by=invoice.uploaded_by,
                metadata_json=metadata,
            )
        )
        db.commit()


def accepted(email: str = PROVIDER, payment_method: str | None = "PPD") -> Invoice:
    invoice = invoice_for(email, InvoiceStatus.ACCEPTED, uuid=new_uuid())
    add_cfdi(invoice, payment_method)
    return invoice


def paid(email: str = PROVIDER, hours_ago: float = 1, required: bool = True, uuid: bool = True) -> Invoice:
    """Factura "Pagada" hace `hours_ago` horas; con complemento requerido y pendiente si `required`."""
    paid_at = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return invoice_for(
        email,
        InvoiceStatus.PAID,
        uuid=new_uuid() if uuid else None,
        paid_at=paid_at,
        paid_by=user_id(PMO),
        payment_complement_due_at=paid_at + PAYMENT_COMPLEMENT_WINDOW if required else None,
    )


def complement_xml(related: str | None, voucher_type: str = "P") -> bytes:
    xml = COMPLEMENT_SOURCE.replace(DEMO_RELATED, related or "OTRO0000-0000-4000-8000-000000000000")
    return xml.replace('TipoDeComprobante="P"', f'TipoDeComprobante="{voucher_type}"').encode()


def upload(client, invoice_id: int, document_type: str, filename: str, content: bytes):
    return client.post(
        f"/invoices/{invoice_id}/documents",
        data={"document_type": document_type, "csrf_token": csrf(client, "/")},
        files={"upload": (filename, content, "application/octet-stream")},
        follow_redirects=False,
    )


def pay(client, invoice_id: int, confirm: bool = True, token: str | None = None):
    data = {"csrf_token": token if token is not None else csrf(client, f"/invoices/{invoice_id}")}
    if confirm:
        data["confirm"] = "1"
    return client.post(f"/invoices/{invoice_id}/payment", data=data, follow_redirects=False)


def submit(client, invoice_id: int):
    return client.post(f"/invoices/{invoice_id}/submit", data={"csrf_token": csrf(client, "/")}, follow_redirects=False)


def complements(invoice_id: int) -> list[Document]:
    with SessionLocal() as db:
        return list(
            db.scalars(
                select(Document)
                .where(Document.invoice_id == invoice_id, Document.document_type.like("PAYMENT_COMPLEMENT_%"))
                .order_by(Document.id)
            )
        )


def text_of(message) -> str:
    return message.get_body(("plain",)).get_content()


def supplier_name(email: str = PROVIDER) -> str:
    with SessionLocal() as db:
        return db.scalar(
            select(Supplier.business_name).join(User, User.supplier_id == Supplier.id).where(User.email == email)
        )


def supplier_email(email: str = PROVIDER) -> str:
    with SessionLocal() as db:
        return db.scalar(select(Supplier.email).join(User, User.supplier_id == Supplier.id).where(User.email == email))


# --- Marcar como pagada -------------------------------------------------------------------------------------------


def test_panel_de_pago_en_una_factura_autorizada(client):
    invoice = accepted()
    login(client, PMO)
    page = client.get(f"/invoices/{invoice.id}").text
    assert 'id="payment"' in page and f'action="/invoices/{invoice.id}/payment"' in page
    assert f"Confirmo que la factura {invoice.invoice_number} fue pagada. Se notificará al proveedor." in page


def test_sin_panel_de_pago_para_el_proveedor_ni_en_otro_estatus(client):
    invoice = accepted()
    login(client, PROVIDER)
    assert 'id="payment"' not in client.get(f"/invoices/{invoice.id}").text
    logout(client)
    login(client, PMO)
    sent = invoice_for(status=InvoiceStatus.UNDER_REVIEW)
    assert 'id="payment"' not in client.get(f"/invoices/{sent.id}").text


def test_marcar_como_pagada_nacional_ppd(client):
    invoice = accepted()
    login(client, PMO)
    response = pay(client, invoice.id)
    assert response.status_code == 303
    stored = reload(invoice.id)
    assert stored.status == InvoiceStatus.PAID and stored.paid_by == user_id(PMO)
    assert stored.payment_complement_due_at == stored.paid_at + timedelta(hours=72)
    assert stored.payment_complement_received_at is None
    [changed] = [a for a in audits(invoice.id, "STATUS_CHANGED") if a.new_value == {"status": "PAID"}]
    assert changed.old_value == {"status": "ACCEPTED"}
    [entry] = audits(invoice.id, "INVOICE_PAID")
    assert entry.new_value["requires_complement"] is True
    [delivery] = deliveries(invoice.id)
    assert response.headers["location"] == f"/invoices/{invoice.id}?notification={delivery.id}#decision-result"
    [message] = [m for m in messages() if invoice.invoice_number in m["Subject"]]
    assert message["Subject"] == f"Factura {invoice.invoice_number} pagada"
    assert message["To"] == supplier_email()
    body = text_of(message)
    assert f"Su factura número {invoice.invoice_number} ha sido pagada." in body
    assert f"{NOTICE} {business(stored.payment_complement_due_at)}." in body
    page = client.get(response.headers["location"]).text
    assert f"Correo enviado a {supplier_email()}" in page and 'id="payment"' not in page
    assert f"Pagada el {business(stored.paid_at)}" in page
    assert f"Pendiente: adjúntelo antes del {business(stored.payment_complement_due_at)}" in page


@pytest.mark.parametrize(
    ("email", "method"),
    [(PROVIDER, "PUE"), (PROVIDER, None), (INTERNATIONAL, "PPD")],
    ids=["nacional-pue", "nacional-sin-metodo", "internacional"],
)
def test_pagada_sin_complemento(client, email, method):
    invoice = accepted(email, method)
    login(client, PMO)
    assert pay(client, invoice.id).status_code == 303
    stored = reload(invoice.id)
    assert stored.status == InvoiceStatus.PAID and stored.payment_complement_due_at is None
    [message] = [m for m in messages() if invoice.invoice_number in m["Subject"]]
    body = text_of(message)
    assert f"Su factura número {invoice.invoice_number} ha sido pagada." in body
    assert "Complemento de Pago" not in body and "\n\n\n" not in body
    page = client.get(f"/invoices/{invoice.id}").text
    assert "Complemento de pago" in page and "No requerido" in page


def test_sin_confirmacion(client):
    invoice = accepted()
    login(client, PMO)
    response = pay(client, invoice.id, confirm=False)
    assert response.status_code == 400 and "Confirme que la factura fue pagada" in response.text
    assert reload(invoice.id).status == InvoiceStatus.ACCEPTED and deliveries(invoice.id) == []


def test_factura_no_autorizada(client):
    invoice = invoice_for(status=InvoiceStatus.UNDER_REVIEW)
    login(client, "admin@poc.local")
    response = pay(client, invoice.id)
    assert response.status_code == 409
    assert "Sólo una factura autorizada se puede marcar como pagada" in response.text
    assert reload(invoice.id).status == InvoiceStatus.UNDER_REVIEW and deliveries(invoice.id) == []


def test_pago_repetido(client):
    invoice = accepted()
    login(client, PMO)
    assert pay(client, invoice.id).status_code == 303
    response = pay(client, invoice.id, token=csrf(client, "/"))
    assert response.status_code == 409 and "La factura ya fue pagada" in response.text
    assert len(deliveries(invoice.id)) == 1 and len(audits(invoice.id, "INVOICE_PAID")) == 1


def test_proveedor_y_csrf(client):
    invoice = accepted()
    login(client, PROVIDER)
    assert pay(client, invoice.id, token=csrf(client, "/")).status_code == 403
    logout(client)
    login(client, PMO)
    assert pay(client, invoice.id, token="token-invalido").status_code == 403
    assert reload(invoice.id).status == InvoiceStatus.ACCEPTED


@pytest.mark.usefixtures("smtp_down")
def test_servidor_de_correo_caido_y_reenvio(client, monkeypatch):
    invoice = accepted()
    login(client, PMO)
    response = pay(client, invoice.id)
    assert reload(invoice.id).status == InvoiceStatus.PAID
    [failed] = deliveries(invoice.id)
    assert (failed.event, failed.status) == ("INVOICE_PAID", "FAILED")
    page = client.get(response.headers["location"]).text
    assert "No se pudo enviar el correo" in page and "El último correo del pago no se envió." in page
    monkeypatch.setattr(settings, "mail_backend", "file")
    token = csrf(client, f"/invoices/{invoice.id}")
    resent = client.post(f"/invoices/{invoice.id}/notification", data={"csrf_token": token}, follow_redirects=False)
    assert resent.status_code == 303
    _, sent = deliveries(invoice.id)
    assert (sent.event, sent.status) == ("INVOICE_PAID", "SENT")
    [message] = [m for m in messages() if invoice.invoice_number in m["Subject"]]
    due = business(reload(invoice.id).payment_complement_due_at)
    assert f"{NOTICE} {due}." in text_of(message)
    [entry] = audits(invoice.id, "INVOICE_NOTIFICATION_RESENT")
    assert entry.new_value == {"event": "INVOICE_PAID"}


def test_pagada_es_final(client):
    invoice = paid()
    login(client, PROVIDER)
    page = client.get(f"/invoices/{invoice.id}").text
    assert 'id="cancellation"' not in page and "Enviar a validación" not in page
    assert submit(client, invoice.id).status_code == 409
    response = cancel(client, invoice.id)
    assert response.status_code == 409 and "Una factura pagada no se puede cancelar" in response.text
    assert reload(invoice.id).status == InvoiceStatus.PAID and stored_files(invoice.id) == []


def test_pagada_fuera_de_la_bandeja(client):
    invoice = paid()
    login(client, PMO)
    assert invoice.invoice_number not in client.get("/invoices").text
    assert invoice.invoice_number in client.get("/invoices", params={"status": "PAID"}).text


# --- Complemento de Pago ------------------------------------------------------------------------------------------


def test_adjuntar_el_complemento(client):
    invoice = paid()
    login(client, PROVIDER)
    page = client.get(f"/invoices/{invoice.id}/documents").text
    options = re.findall(r'<option value="([A-Z_0-9]+)"', page)
    assert options == ["PAYMENT_COMPLEMENT_XML", "PAYMENT_COMPLEMENT_PDF"]
    assert "archivos obligatorios" not in page.lower() and "Verificar" not in page
    response = upload(client, invoice.id, "PAYMENT_COMPLEMENT_XML", "complemento.xml", complement_xml(invoice.uuid))
    assert response.status_code == 303
    stored = reload(invoice.id)
    assert stored.status == InvoiceStatus.PAID and stored.payment_complement_received_at is not None
    [document] = complements(invoice.id)
    assert document.metadata_json["uuid"] == "DEMOPAGO-0000-4000-8000-000000000001"
    [entry] = audits(invoice.id, "PAYMENT_COMPLEMENT_UPLOADED")
    assert entry.new_value == {"document_id": document.id, "uuid": "DEMOPAGO-0000-4000-8000-000000000001"}
    [delivery] = deliveries(invoice.id)
    assert (delivery.event, delivery.status, delivery.to_addresses) == ("PAYMENT_COMPLEMENT", "SENT", [RECEPTION])
    [message] = [m for m in messages() if invoice.invoice_number in m["Subject"]]
    assert message["Subject"] == f"Complemento de pago de la factura {invoice.invoice_number}"
    assert (
        f"El Complemento de Pago ha sido adjuntado a la factura {invoice.invoice_number} del proveedor "
        f"{supplier_name()}." in text_of(message)
    )
    page = client.get(response.headers["location"]).text
    assert "Se notificó a Recepción de Facturas" in page and RECEPTION not in page
    assert f"Adjuntado el {business(stored.payment_complement_received_at)}" in page


def test_reemplazo_del_complemento(client):
    invoice = paid()
    login(client, PROVIDER)
    upload(client, invoice.id, "PAYMENT_COMPLEMENT_XML", "complemento.xml", complement_xml(invoice.uuid))
    first = reload(invoice.id).payment_complement_received_at
    upload(client, invoice.id, "PAYMENT_COMPLEMENT_XML", "complemento-2.xml", complement_xml(invoice.uuid.lower()))
    assert reload(invoice.id).payment_complement_received_at == first
    assert [d.is_current for d in complements(invoice.id)] == [False, True]
    assert [d.event for d in deliveries(invoice.id)] == ["PAYMENT_COMPLEMENT", "PAYMENT_COMPLEMENT"]


def test_pdf_del_complemento_sin_correo(client):
    invoice = paid()
    login(client, PROVIDER)
    assert upload(client, invoice.id, "PAYMENT_COMPLEMENT_PDF", "complemento.pdf", PDF).status_code == 303
    assert reload(invoice.id).payment_complement_received_at is None and deliveries(invoice.id) == []


@pytest.mark.parametrize(
    ("voucher_type", "related", "message"),
    [
        ("I", "self", "El XML no es un Complemento de Pago (CFDI de tipo P)"),
        ("P", None, "El Complemento de Pago no relaciona la factura {uuid}"),
    ],
    ids=["ingreso", "otra-factura"],
)
def test_complemento_invalido(client, voucher_type, related, message):
    invoice = paid()
    login(client, PROVIDER)
    content = complement_xml(invoice.uuid if related == "self" else None, voucher_type)
    response = upload(client, invoice.id, "PAYMENT_COMPLEMENT_XML", "complemento.xml", content)
    assert response.status_code == 400 and message.format(uuid=invoice.uuid) in response.text
    assert stored_files(invoice.id) == [] and reload(invoice.id).payment_complement_received_at is None


def test_xml_ilegible_como_complemento(client):
    invoice = paid()
    login(client, PROVIDER)
    response = upload(client, invoice.id, "PAYMENT_COMPLEMENT_XML", "complemento.xml", b"<?xml version='1.0'?><roto")
    assert response.status_code == 400 and "El XML no es un Complemento de Pago" in response.text
    assert stored_files(invoice.id) == []


def test_factura_pagada_sin_uuid(client):
    invoice = paid(uuid=False)
    login(client, PROVIDER)
    response = upload(client, invoice.id, "PAYMENT_COMPLEMENT_XML", "complemento.xml", complement_xml(None))
    assert response.status_code == 400 and "la factura aún no tiene el UUID de su CFDI" in response.text


def test_otro_tipo_en_una_factura_pagada(client):
    invoice = paid()
    login(client, PROVIDER)
    response = upload(client, invoice.id, "PURCHASE_ORDER", "oc.pdf", PDF)
    assert response.status_code == 409
    assert "En una factura pagada sólo se puede cargar el Complemento de Pago" in response.text
    assert stored_files(invoice.id) == []


def test_factura_pagada_sin_complemento_requerido(client):
    invoice = paid(required=False)
    login(client, PROVIDER)
    response = client.get(f"/invoices/{invoice.id}/documents")
    assert response.status_code == 409 and "La factura no requiere Complemento de Pago" in response.text
    content = complement_xml(invoice.uuid)
    assert upload(client, invoice.id, "PAYMENT_COMPLEMENT_XML", "c.xml", content).status_code == 409


def test_complemento_antes_del_pago(client):
    invoice = invoice_for(status=InvoiceStatus.DRAFT, uuid=new_uuid())
    login(client, PROVIDER)
    bad = upload(client, invoice.id, "PAYMENT_COMPLEMENT_XML", "c.xml", complement_xml(invoice.uuid, "I"))
    assert bad.status_code == 400 and stored_files(invoice.id) == []
    good = upload(client, invoice.id, "PAYMENT_COMPLEMENT_XML", "c.xml", complement_xml(invoice.uuid))
    assert good.status_code == 303 and deliveries(invoice.id) == []


def test_complemento_previo_cuenta_al_pagar(client):
    invoice = accepted()
    with SessionLocal() as db:
        db.execute(update(Invoice).where(Invoice.id == invoice.id).values(status=InvoiceStatus.DRAFT))
        db.commit()
    login(client, PROVIDER)
    upload(client, invoice.id, "PAYMENT_COMPLEMENT_XML", "c.xml", complement_xml(invoice.uuid))
    with SessionLocal() as db:
        db.execute(update(Invoice).where(Invoice.id == invoice.id).values(status=InvoiceStatus.ACCEPTED))
        db.commit()
    logout(client)
    login(client, PMO)
    pay(client, invoice.id)
    stored = reload(invoice.id)
    [document] = complements(invoice.id)
    assert stored.payment_complement_due_at is not None
    assert stored.payment_complement_received_at == document.uploaded_at
    [message] = [m for m in messages() if invoice.invoice_number in m["Subject"]]
    # Ya adjuntado: el correo no lo pide.
    assert "Complemento de Pago" not in text_of(message)


# --- Pendientes y bloqueo -----------------------------------------------------------------------------------------


def test_envio_bloqueado_por_complemento_vencido(client):
    overdue = paid(hours_ago=73)
    invoice = invoice_for(status=InvoiceStatus.UPLOADED)
    login(client, PROVIDER)
    response = submit(client, invoice.id)
    assert response.status_code == 409
    assert f"{OVERDUE_PREFIX} {overdue.invoice_number}. Adjúntelos para continuar." in response.text
    assert reload(invoice.id).status == InvoiceStatus.UPLOADED
    page = client.get(f"/invoices/{overdue.id}").text
    assert "Vencido desde el" in page and "Adjuntar Complemento de Pago" in page


def test_dentro_del_plazo_no_bloquea(client):
    paid(hours_ago=71)
    invoice = invoice_for(status=InvoiceStatus.UPLOADED)
    login(client, PROVIDER)
    response = submit(client, invoice.id)
    # Sin documentos el envio no procede, pero por los archivos obligatorios, no por el complemento.
    assert response.status_code == 409 and OVERDUE_PREFIX not in response.text
    assert "Faltan archivos obligatorios" in response.text


def test_bloqueo_levantado_al_adjuntar(client):
    overdue = paid(hours_ago=73)
    invoice = invoice_for(status=InvoiceStatus.UPLOADED)
    login(client, PROVIDER)
    assert OVERDUE_PREFIX in submit(client, invoice.id).text
    upload(client, overdue.id, "PAYMENT_COMPLEMENT_XML", "c.xml", complement_xml(overdue.uuid))
    assert OVERDUE_PREFIX not in submit(client, invoice.id).text


def test_reenvio_desde_observaciones_bloqueado(client):
    paid(hours_ago=80)
    invoice = invoice_for(status=InvoiceStatus.REQUIRES_CORRECTION)
    login(client, PROVIDER)
    response = submit(client, invoice.id)
    assert response.status_code == 409 and OVERDUE_PREFIX in response.text
    assert reload(invoice.id).status == InvoiceStatus.REQUIRES_CORRECTION


def test_solo_los_complementos_del_proveedor(client):
    paid(hours_ago=73)
    invoice = invoice_for(OTHER_PROVIDER, InvoiceStatus.UPLOADED)
    login(client, OTHER_PROVIDER)
    assert OVERDUE_PREFIX not in submit(client, invoice.id).text


def test_alta_permitida_con_complemento_vencido(client):
    paid(hours_ago=73)
    login(client, PROVIDER)
    response, _ = create(client, contract_id=own_contract_id(PROVIDER))
    assert response.status_code == 303 and response.headers["location"].endswith("/documents")


def test_aviso_en_el_tablero_y_el_listado(client):
    pending = paid(hours_ago=10)
    overdue = paid(hours_ago=75)
    login(client, PROVIDER)
    for url in ("/", "/invoices"):
        page = client.get(url).text
        notice = re.search(r'<div class="alert alert-danger complement-notice".*?</div>', page, re.DOTALL).group(0)
        assert "Tiene complementos de pago pendientes" in notice
        assert notice.index(overdue.invoice_number) < notice.index(pending.invoice_number)
        assert f'href="/invoices/{pending.id}/documents"' in notice
        assert "no podrá enviar facturas a validación" in notice


def test_aviso_sin_complementos_vencidos(client):
    pending = paid(hours_ago=10)
    login(client, PROVIDER)
    page = client.get("/").text
    assert 'class="alert alert-warning complement-notice"' in page and pending.invoice_number in page
    assert "no podrá enviar facturas a validación" not in page


def test_sin_aviso_para_el_pmo(client):
    paid(hours_ago=75)
    login(client, PMO)
    assert "Tiene complementos de pago pendientes" not in client.get("/").text


def test_indicador_de_pagadas(client):
    invoice = accepted()
    login(client, PMO)
    before = client.get("/").text
    count = int(re.search(r'id="kpi-paid"><span>Pagadas</span><strong>(\d+)</strong>', before).group(1))
    pay(client, invoice.id)
    after = client.get("/").text
    assert re.search(r'id="kpi-paid"><span>Pagadas</span><strong>(\d+)</strong>', after).group(1) == str(count + 1)


# --- Historial ----------------------------------------------------------------------------------------------------


def test_pago_y_complemento_en_el_historial(client):
    invoice = accepted()
    login(client, PMO)
    pay(client, invoice.id)
    logout(client)
    login(client, PROVIDER)
    upload(client, invoice.id, "PAYMENT_COMPLEMENT_XML", "c.xml", complement_xml(invoice.uuid))
    due = business(reload(invoice.id).payment_complement_due_at)
    page = client.get(f"/invoices/{invoice.id}").text
    history = re.search(r'<section class="panel" id="history">.*?</section>', page, re.DOTALL).group(0)
    assert f"Fecha límite del complemento: {due}" in history
    assert history.index("Pagada") < history.index("Complemento de pago adjuntado")
    with SessionLocal() as db:
        pmo_name = db.scalar(select(User.name).where(User.email == PMO))
    assert pmo_name not in history and "<small>PMO</small>" in history
    logout(client)
    login(client, PMO)
    history = client.get(f"/invoices/{invoice.id}").text
    assert pmo_name in history and "Complemento de pago adjuntado" in history
