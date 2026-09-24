import logging

from fastapi.testclient import TestClient

from app.core.constants import InvoiceStatus
from tests.conftest import csrf, invoice_by_number, login


def test_excepcion_no_manejada_no_expone_traza(monkeypatch, caplog):
    import app.routers.dashboard as dashboard
    from app.main import app

    def boom(*_args, **_kwargs):
        raise RuntimeError("detalle-interno-secreto")

    monkeypatch.setattr(dashboard, "status_counts", boom)
    with TestClient(app, raise_server_exceptions=False) as client, caplog.at_level(logging.ERROR):
        login(client)
        response = client.get("/")
    assert response.status_code == 500
    assert "Ocurrio un error interno" in response.text
    assert "Traceback" not in response.text
    assert "detalle-interno-secreto" not in response.text
    assert any(r.exc_info and "detalle-interno-secreto" in str(r.exc_info[1]) for r in caplog.records)


def test_submit_en_borrador_responde_409_sin_cambiar_estado(client):
    invoice = invoice_by_number("BORRADOR-001")
    login(client)
    token = csrf(client, f"/invoices/{invoice.id}")
    response = client.post(f"/invoices/{invoice.id}/submit", data={"csrf_token": token}, follow_redirects=False)
    assert response.status_code == 409
    assert "Transicion no permitida" in response.text
    assert invoice_by_number("BORRADOR-001").status == InvoiceStatus.DRAFT


def test_clickbalance_desde_revision_responde_409(client):
    invoice = invoice_by_number("REVISION-001")
    login(client, "pmo@poc.local")
    token = csrf(client, f"/invoices/{invoice.id}")
    response = client.post(f"/invoices/{invoice.id}/clickbalance", data={"csrf_token": token}, follow_redirects=False)
    assert response.status_code == 409
    assert invoice_by_number("REVISION-001").status == InvoiceStatus.UNDER_REVIEW


def test_error_de_negocio_en_json(client):
    invoice = invoice_by_number("BORRADOR-001")
    login(client)
    token = csrf(client, f"/invoices/{invoice.id}")
    response = client.post(
        f"/invoices/{invoice.id}/submit", data={"csrf_token": token}, headers={"Accept": "application/json"}
    )
    assert response.status_code == 409
    assert response.json() == {"detail": "Transicion no permitida: DRAFT -> UNDER_REVIEW"}
