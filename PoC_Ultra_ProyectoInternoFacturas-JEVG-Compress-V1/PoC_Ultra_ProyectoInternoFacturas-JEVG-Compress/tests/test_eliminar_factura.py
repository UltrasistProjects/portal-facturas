"""Eliminacion de facturas (spec flujo-facturas): la excepcion a la prohibicion de borrado fisico de facturas (spec
integridad-datos). El Administrador elimina cualquiera en cualquier estatus; el proveedor duenio, las suyas en Borrador
o Canceladas; el PMO, ninguna."""

import hashlib
from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select, update

from app.core.constants import InvoiceStatus, ReviewDecision
from app.core.database import SessionLocal
from app.models import AuditLog, Document, FileContent, Invoice, Review, User, ValidationResult
from app.services import invoice_deletion_service as deletion
from app.services.file_service import LocalFileStorage
from tests.cfdi import MORAL_EMAIL, PHYSICAL_EMAIL, SUPPORT, example_cfdi, register_cfdi, upload, verify
from tests.conftest import csrf, login
from tests.test_cancelacion import cancel, stored_files, user_id

PMO, ADMIN = "pmo@poc.local", "admin@poc.local"
BUTTON = "?eliminar=1#deletion"
WARNING = 'class="alert alert-warning deletion-warning"'
# Estatus en que el proveedor ya no elimina su factura y el Administrador si.
OTROS_ESTATUS = [
    InvoiceStatus.UPLOADED,
    InvoiceStatus.UNDER_REVIEW,
    InvoiceStatus.REQUIRES_CORRECTION,
    InvoiceStatus.ACCEPTED,
    InvoiceStatus.REJECTED,
    InvoiceStatus.PAID,
]
# Facturas que crea cada prueba; sin_restos elimina al terminar las que sigan en la base.
CREADAS: list[int] = []


@pytest.fixture(autouse=True)
def sin_restos():
    """La base de la sesion es compartida y otras pruebas cuentan las facturas de proveedor2 (test_flujo): al
    terminar el Administrador elimina, con el propio servicio, las facturas que la prueba dejo, en el estatus que
    hayan quedado."""
    yield
    for invoice_id in CREADAS:
        with SessionLocal() as db:
            if db.get(Invoice, invoice_id) is None:
                continue
            admin = db.scalar(select(User).where(User.email == ADMIN))
            paths = deletion.delete_invoice(db, db.get(Invoice, invoice_id), admin, confirmed=True)
            db.commit()
        LocalFileStorage().discard(paths)
    CREADAS.clear()


def borrador(client):
    """Factura nueva de la proveedora del ejemplo, registrada con su PDF y su XML: queda en "Borrador"."""
    login(client, PHYSICAL_EMAIL)
    data = example_cfdi()
    response, invoice = register_cfdi(client, data)
    assert response.status_code == 303 and invoice.status == InvoiceStatus.DRAFT
    CREADAS.append(invoice.id)
    return invoice, data


def eliminar(client, invoice, confirm: bool = True, token: str | None = None):
    data = {"csrf_token": csrf(client, f"/invoices/{invoice.id}") if token is None else token}
    if confirm:
        data["confirm"] = "1"
    return client.post(f"/invoices/{invoice.id}/delete", data=data, follow_redirects=False)


def restos(invoice_id: int) -> dict:
    """Lo que queda en la base de la factura y de lo que depende de ella."""
    with SessionLocal() as db:

        def count(model):
            return db.scalar(select(func.count()).select_from(model).where(model.invoice_id == invoice_id))

        return {
            "factura": db.get(Invoice, invoice_id) is not None,
            "documentos": count(Document),
            "validaciones": count(ValidationResult),
            "revisiones": count(Review),
        }


NADA = {"factura": False, "documentos": 0, "validaciones": 0, "revisiones": 0}


def cambiar_estatus(invoice_id: int, status: InvoiceStatus) -> None:
    """Lleva la factura al estatus; "Programado para pago" exige fecha y autor del pago (ck_invoices_payment)."""
    values = {"status": status}
    if status == InvoiceStatus.PAID:
        values |= {"paid_at": datetime.now(timezone.utc), "paid_by": user_id(PMO)}
    with SessionLocal() as db:
        db.execute(update(Invoice).where(Invoice.id == invoice_id).values(**values))
        db.commit()


def bitacora(invoice_id: int) -> list[AuditLog]:
    with SessionLocal() as db:
        stmt = select(AuditLog).where(AuditLog.entity == "Invoice", AuditLog.entity_id == str(invoice_id))
        return list(db.scalars(stmt.order_by(AuditLog.id)))


def test_proveedor_elimina_su_borrador(client):
    invoice, data = borrador(client)
    assert verify(client, invoice).status_code == 303
    before = restos(invoice.id)
    assert before["documentos"] == 2 and before["validaciones"] > 0 and stored_files(invoice.id)
    detail = client.get(f"/invoices/{invoice.id}").text
    assert f'href="/invoices/{invoice.id}{BUTTON}"' in detail and 'id="deletion">' in detail
    assert 'id="deletion" open' in client.get(f"/invoices/{invoice.id}?eliminar=1").text

    response = eliminar(client, invoice)
    assert response.status_code == 303
    assert response.headers["location"] == f"/invoices?deleted={invoice.internal_folio}"
    assert f"Factura {invoice.internal_folio} eliminada" in client.get(response.headers["location"]).text
    assert restos(invoice.id) == NADA and stored_files(invoice.id) == []
    # La bitacora conserva lo anterior y agrega la eliminacion con los datos de la factura.
    *previas, eliminada = bitacora(invoice.id)
    assert previas and eliminada.action == "INVOICE_DELETED" and eliminada.user_id == user_id(PHYSICAL_EMAIL)
    assert eliminada.old_value == {
        "internal_folio": invoice.internal_folio,
        "invoice_number": invoice.invoice_number,
        "uuid": data["uuid"],
        "status": "DRAFT",
        "supplier_id": invoice.supplier_id,
        "total": str(invoice.total),
        "currency": "MXN",
        "documents": 2,
    }
    # El UUID y el numero quedan libres: la misma factura se vuelve a registrar.
    response, again = register_cfdi(client, data)
    CREADAS.append(again.id)
    assert response.status_code == 303 and again.id != invoice.id and again.uuid == data["uuid"]


def test_proveedor_elimina_su_factura_cancelada(client):
    invoice, _ = borrador(client)
    # Un Vo.Bo. reemplazado (documents.replaced_document_id), la cancelacion con su acuse y una revision previa.
    assert upload(client, invoice, "APPROVAL", "vobo.txt", SUPPORT).status_code == 303
    assert upload(client, invoice, "APPROVAL", "vobo-2.txt", SUPPORT + b" corregido").status_code == 303
    assert cancel(client, invoice.id).status_code == 303
    with SessionLocal() as db:
        db.add(Review(invoice_id=invoice.id, reviewer_id=user_id(PMO), decision=ReviewDecision.REQUIRES_CORRECTION))
        paths = list(db.scalars(select(Document.path).where(Document.invoice_id == invoice.id)))
        # Con STORAGE_BACKEND=database el contenido tambien vive en stored_files.
        db.add_all(FileContent(path=p, content=b"x", size=1, sha256=hashlib.sha256(b"x").hexdigest()) for p in paths)
        db.commit()
        assert db.get(Invoice, invoice.id).status == InvoiceStatus.CANCELLED
    assert len(paths) == 5 and restos(invoice.id)["revisiones"] == 1

    assert eliminar(client, invoice).status_code == 303
    assert restos(invoice.id) == NADA and stored_files(invoice.id) == []
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(FileContent).where(FileContent.path.in_(paths))) == 0
    assert bitacora(invoice.id)[-1].old_value["status"] == "CANCELLED"


def test_administrador_elimina_la_de_un_proveedor(client):
    invoice, _ = borrador(client)
    login(client, ADMIN)
    detail = client.get(f"/invoices/{invoice.id}").text
    # En Borrador no hay advertencia: la factura no ha seguido su curso.
    assert BUTTON in detail and WARNING not in detail
    assert eliminar(client, invoice).status_code == 303
    assert restos(invoice.id) == NADA
    assert bitacora(invoice.id)[-1].user_id == user_id(ADMIN)


@pytest.mark.parametrize("status", OTROS_ESTATUS)
def test_administrador_elimina_en_cualquier_estatus(client, status):
    invoice, _ = borrador(client)
    assert verify(client, invoice).status_code == 303
    cambiar_estatus(invoice.id, status)
    with SessionLocal() as db:
        db.add(Review(invoice_id=invoice.id, reviewer_id=user_id(PMO), decision=ReviewDecision.ACCEPTED))
        db.commit()
    login(client, ADMIN)
    detail = client.get(f"/invoices/{invoice.id}").text
    assert BUTTON in detail and 'id="deletion">' in detail and WARNING in detail
    before = restos(invoice.id)
    assert before["documentos"] == 2 and before["validaciones"] > 0 and before["revisiones"] == 1

    response = eliminar(client, invoice)
    assert response.status_code == 303
    assert response.headers["location"] == f"/invoices?deleted={invoice.internal_folio}"
    assert restos(invoice.id) == NADA and stored_files(invoice.id) == []
    eliminada = bitacora(invoice.id)[-1]
    assert eliminada.action == "INVOICE_DELETED" and eliminada.user_id == user_id(ADMIN)
    assert eliminada.old_value["status"] == status.value


def test_pmo_no_elimina(client):
    invoice, _ = borrador(client)
    login(client, PMO)
    detail = client.get(f"/invoices/{invoice.id}").text
    assert BUTTON not in detail and 'id="deletion"' not in detail
    assert eliminar(client, invoice).status_code == 403
    assert restos(invoice.id)["factura"]


def test_otro_proveedor_no_la_encuentra(client):
    invoice, _ = borrador(client)
    login(client, MORAL_EMAIL)
    token = csrf(client, "/invoices")
    assert eliminar(client, invoice, token=token).status_code == 404
    assert restos(invoice.id)["factura"]


@pytest.mark.parametrize("status", OTROS_ESTATUS)
def test_el_proveedor_no_elimina_en_otro_estatus(client, status):
    invoice, _ = borrador(client)
    cambiar_estatus(invoice.id, status)
    detail = client.get(f"/invoices/{invoice.id}").text
    assert BUTTON not in detail and 'id="deletion"' not in detail
    response = eliminar(client, invoice)
    assert response.status_code == 409 and "Sólo se puede eliminar una factura en Borrador o Cancelada" in response.text
    assert restos(invoice.id)["factura"] and restos(invoice.id)["documentos"] == 2


def test_sin_confirmacion(client):
    invoice, _ = borrador(client)
    response = eliminar(client, invoice, confirm=False)
    assert response.status_code == 400 and "Confirme que desea eliminar la factura" in response.text
    assert 'id="deletion" open' in response.text
    assert restos(invoice.id)["factura"] and stored_files(invoice.id)


def test_sin_token_csrf(client):
    invoice, _ = borrador(client)
    assert eliminar(client, invoice, token="").status_code == 403
    assert restos(invoice.id)["factura"]


def test_el_aviso_del_listado_solo_acepta_un_folio(client):
    login(client, PHYSICAL_EMAIL)
    page = client.get("/invoices", params={"deleted": "<b>cualquier texto</b>"}).text
    assert 'id="invoice-notice"' not in page
