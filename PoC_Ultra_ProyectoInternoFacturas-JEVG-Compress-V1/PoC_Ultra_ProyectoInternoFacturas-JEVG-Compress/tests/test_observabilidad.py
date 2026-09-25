import json
import re
from datetime import datetime, timezone
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.core.config import settings
from app.core.constants import NotificationEvent
from app.core.database import SessionLocal
from app.core.demo import DEMO_ACCOUNTS
from app.models import User
from app.services import notification_templates
from tests.conftest import ROOT, TEST_PASSWORDS, csrf, invoice_by_number, login, supplier_by_email

LOG_FILE = settings.log_dir / "app.log"
CFDI = (ROOT / "data" / "demo_documents" / "cfdi_demo_correcto.xml").read_text(encoding="utf-8")
PDF = (ROOT / "data" / "demo_documents" / "factura_demo.pdf").read_bytes()


def log_offset() -> int:
    return LOG_FILE.stat().st_size if LOG_FILE.exists() else 0


def events_since(offset: int) -> list[dict]:
    with LOG_FILE.open(encoding="utf-8") as handle:
        handle.seek(offset)
        return [json.loads(line) for line in handle.read().splitlines() if line.strip()]


def user_id(email: str) -> int:
    with SessionLocal() as db:
        return db.scalar(select(User.id).where(User.email == email))


def upload(client, invoice_id: int, document_type: str, filename: str, content: bytes):
    return client.post(
        f"/invoices/{invoice_id}/documents",
        data={"document_type": document_type, "csrf_token": csrf(client, f"/invoices/{invoice_id}")},
        files={"upload": (filename, content, "application/octet-stream")},
        follow_redirects=False,
    )


def invoice_flow(client, number: str, uuid: str) -> int:
    """Alta, carga de XML y PDF y prevalidacion de una factura nueva del proveedor 1."""
    supplier = supplier_by_email("proveedor1@poc.local")
    data = {
        "supplier_id": supplier.id,
        "contract_id": invoice_by_number("A-CORRECTA").contract_id,
        "invoice_number": number,
        "service_period": "08/2026",
        "project_name": "Automatizacion Operativa 2026",
        "csrf_token": csrf(client, "/invoices/new"),
    }
    assert client.post("/invoices/new", data=data, follow_redirects=False).status_code == 303
    invoice_id = invoice_by_number(number).id
    xml = re.sub(r'UUID="[^"]*"', f'UUID="{uuid}"', CFDI).encode()
    assert upload(client, invoice_id, "INVOICE_XML", "cfdi.xml", xml).status_code == 303
    assert upload(client, invoice_id, "INVOICE_PDF", "factura.pdf", PDF).status_code == 303
    token = csrf(client, f"/invoices/{invoice_id}")
    assert client.post(f"/invoices/{invoice_id}/validation", data={"csrf_token": token}).status_code == 200
    return invoice_id


def test_lineas_json_con_request_id_y_user_id(client):
    login(client, "proveedor1@poc.local")
    offset = log_offset()
    invoice_id = invoice_flow(client, "LOG-001", "LOG00001-0000-4000-8000-000000000001")
    events = events_since(offset)
    provider = user_id("proveedor1@poc.local")
    uploads = [e for e in events if e.get("event") == "document.uploaded"]
    assert len(uploads) == 2
    for entry in uploads:
        assert entry["request_id"] and entry["user_id"] == provider and entry["invoice_id"] == invoice_id
        assert {entry["extension"], entry["document_type"]} <= {".xml", ".pdf", "INVOICE_XML", "INVOICE_PDF"}
        assert entry["size_bytes"] > 0
    started = next(e for e in events if e.get("event") == "validation.started")
    completed = next(e for e in events if e.get("event") == "validation.completed")
    assert started["request_id"] == completed["request_id"]
    assert completed["user_id"] == provider
    assert completed["duration_ms"] >= 0 and "score" in completed and "blockers" in completed
    assert completed["status"] in {"PREVALIDATED", "REQUIRES_CORRECTION"}
    for entry in events:
        assert {"timestamp", "level", "logger", "message", "request_id"} <= set(entry)


def test_linea_de_arranque_sin_request_id():
    from app.main import app

    offset = log_offset()
    with TestClient(app):
        pass
    startup = next(e for e in events_since(offset) if e["message"].startswith("Starting"))
    assert startup["request_id"] is None
    assert "user_id" not in startup


def test_pdf_danado(client):
    invoice = invoice_by_number("BORRADOR-001")
    login(client, "proveedor1@poc.local")
    offset = log_offset()
    response = upload(client, invoice.id, "ADDITIONAL", "roto.pdf", b"%PDF-1.7\nesto no es un pdf valido")
    assert response.status_code == 400
    assert "El PDF no puede abrirse o esta danado" in response.text
    failure = next(e for e in events_since(offset) if e.get("event") == "pdf.analysis_failed")
    assert failure["level"] == "WARNING" and failure["error_type"] and failure["error"]


def test_sin_datos_sensibles_en_el_log(client):
    offset = log_offset()
    login(client, "proveedor1@poc.local", "Secreta#Incorrecta1")
    login(client, "proveedor1@poc.local")
    invoice_flow(client, "LOG-002", "LOG00002-0000-4000-8000-000000000002")
    client.post("/logout", data={"csrf_token": csrf(client, "/")})
    login(client, "pmo@poc.local")
    review = invoice_by_number("REVISION-001")
    token = csrf(client, f"/invoices/{review.id}")
    client.post(f"/invoices/{review.id}/review", data={"decision": "COMMENT", "comments": "ok", "csrf_token": token})
    events = events_since(offset)
    assert any(e.get("event") == "review.decided" for e in events)
    content = json.dumps(events)
    forbidden = [
        "password",
        "csrf",
        "Secreta#Incorrecta1",
        "TIC210101ABC",
        "ULT940623AG0",
        "cfdi.xml",
        "factura.pdf",
        *TEST_PASSWORDS.values(),
        *(account.password for account in DEMO_ACCOUNTS),
    ]
    for value in forbidden:
        assert value not in content, value


def test_cambio_de_plantilla_registrado(client, restore_notification_templates):
    login(client)
    offset = log_offset()
    rejected = notification_templates.EVENTS[NotificationEvent.INVOICE_REJECTED]
    data = {
        "subject": "Asunto de prueba {{numero_factura}}",
        "body": rejected.default_body,
        "version": 1,
        "csrf_token": csrf(client, "/"),
    }
    response = client.post("/admin/notification-templates/INVOICE_REJECTED", data=data, follow_redirects=False)
    assert response.status_code == 303
    events = events_since(offset)
    updated = [e for e in events if e.get("event") == "notification_template.updated"]
    assert [(e["event_code"], e["version"]) for e in updated] == [("INVOICE_REJECTED", 2)]
    content = json.dumps(events, ensure_ascii=False)
    assert "Asunto de prueba" not in content and "por la siguiente causa" not in content


def test_plantilla_invalida_registrada(client, restore_notification_templates):
    with SessionLocal() as db:
        db.execute(
            text(
                "UPDATE notification_templates SET body = 'Texto dañado {{rfc_secreto}}'"
                " WHERE event = 'INVOICE_REJECTED'"
            )
        )
        db.commit()
    offset = log_offset()
    with SessionLocal() as db:
        notification_templates.compose(
            db,
            NotificationEvent.INVOICE_REJECTED,
            numero_factura="LOG-NOTIF-1",
            folio_interno="FAC-LOG-NOTIF",
            proveedor="Proveedor del log",
            monto=Decimal("10.00"),
            moneda="MXN",
            fecha_estatus=datetime(2026, 9, 25, 16, 30, tzinfo=timezone.utc),
            observaciones="Causa confidencial",
        )
    events = events_since(offset)
    fallback = [e for e in events if e.get("event") == "notification.template_fallback"]
    assert [(e["event_code"], e["reason"]) for e in fallback] == [("INVOICE_REJECTED", "invalid")]
    content = json.dumps(events, ensure_ascii=False)
    for value in ("Texto dañado", "rfc_secreto", "LOG-NOTIF-1", "FAC-LOG-NOTIF", "Proveedor del log", "confidencial"):
        assert value not in content, value
