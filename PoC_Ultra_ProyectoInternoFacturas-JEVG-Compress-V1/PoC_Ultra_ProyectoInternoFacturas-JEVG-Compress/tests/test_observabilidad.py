import json
import re
import socket
from datetime import datetime, timezone
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.core.config import settings
from app.core.constants import NotificationEvent
from app.core.database import SessionLocal
from app.core.demo import DEMO_ACCOUNTS
from app.models import Invoice, User
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
    # La validacion ya no cambia el estatus (HU-13): el evento informa cuantas reglas impedirian el envio.
    assert completed["failures"] >= 0 and "status" not in completed
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


def test_sin_datos_sensibles_en_el_log(client, restore_notification_recipients):
    offset = log_offset()
    login(client, "proveedor1@poc.local", "Secreta#Incorrecta1")
    login(client, "proveedor1@poc.local")
    invoice_flow(client, "LOG-002", "LOG00002-0000-4000-8000-000000000002")
    client.post("/logout", data={"csrf_token": csrf(client, "/")})
    login(client, "pmo@poc.local")
    # Decision real del PMO (HU-20) sobre la factura de esta prueba, con su correo al proveedor.
    review = invoice_by_number("LOG-002")
    with SessionLocal() as db:
        db.get(Invoice, review.id).status = "UNDER_REVIEW"
        db.commit()
    token = csrf(client, f"/invoices/{review.id}")
    data = {"decision": "REQUIRES_CORRECTION", "comments": "Corrija el periodo", "csrf_token": token}
    assert client.post(f"/invoices/{review.id}/review", data=data, follow_redirects=False).status_code == 303
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


# --- Notificaciones por correo (HU-08) ----------------------------------------------------------------------------

INVOICE_VALUES = {
    "numero_factura": "LOG-MAIL-1",
    "folio_interno": "FAC-LOG-MAIL",
    "proveedor": "Proveedor del log de correo",
    "monto": Decimal("10.00"),
    "moneda": "MXN",
    "fecha_estatus": datetime(2026, 9, 25, 16, 30, tzinfo=timezone.utc),
}


def closed_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def save_recipients(client, **lists) -> None:
    from app.services import notification_service

    with SessionLocal() as db:
        config = notification_service.load(db)
        data = {item.key: "\n".join(item.addresses) for item in notification_service.recipient_lists(config)}
        data["config_version"] = notification_service.config_version(config)
    response = client.post(
        "/admin/notifications", data={**data, **lists, "csrf_token": csrf(client, "/")}, follow_redirects=False
    )
    assert response.status_code == 303


def test_envio_de_correo_registrado(restore_notification_recipients):
    from app.services import notification_service

    offset = log_offset()
    with SessionLocal() as db:
        delivery = notification_service.notify(db, NotificationEvent.INVOICE_AUTHORIZED, **INVOICE_VALUES)
    events = events_since(offset)
    [sent] = [e for e in events if e.get("event") == "notification.sent"]
    assert sent["event_code"] == "INVOICE_AUTHORIZED" and sent["delivery_id"] == delivery.id
    assert sent["transport"] == "file" and sent["recipients"] == 1 and "duration_ms" in sent
    content = json.dumps(events, ensure_ascii=False)
    for value in ("recepcionfacturas@ultrasist.com.mx", "LOG-MAIL-1", "autorizada para pago", "Proveedor del log"):
        assert value not in content, value


def test_envio_fallido_registrado(client, monkeypatch, restore_notification_recipients):
    monkeypatch.setattr(settings, "mail_backend", "smtp")
    monkeypatch.setattr(settings, "smtp_host", "127.0.0.1")
    monkeypatch.setattr(settings, "smtp_port", closed_port())
    login(client)
    offset = log_offset()
    client.post(
        "/admin/notifications/test", data={"address": "prueba-log@ultrasist.com.mx", "csrf_token": csrf(client, "/")}
    )
    events = events_since(offset)
    [failed] = [e for e in events if e.get("event") == "notification.failed"]
    assert failed["level"] == "WARNING" and failed["event_code"] == "TEST"
    assert failed["error_type"] == "ConnectionRefusedError" and "error" not in failed
    assert "prueba-log@ultrasist.com.mx" not in json.dumps(events)


def test_cambio_de_destinatarios_registrado(client, restore_notification_recipients):
    login(client)
    offset = log_offset()
    save_recipients(client, INVOICE_REJECTED="copia-log@ultrasist.com.mx")
    events = events_since(offset)
    updated = [e for e in events if e.get("event") == "notification_recipients.updated"]
    assert [e["lists"] for e in updated] == [["INVOICE_REJECTED"]]
    assert "copia-log@ultrasist.com.mx" not in json.dumps(events)


def test_sin_datos_sensibles_al_enviar_correos(client, monkeypatch, restore_notification_recipients):
    from pydantic import SecretStr

    from app.services import notification_service

    monkeypatch.setattr(settings, "smtp_password", SecretStr("Clave#Smtp#DelLog"))
    login(client)
    offset = log_offset()
    save_recipients(client, INVOICE_RECEPTION="buzon-log@ultrasist.com.mx")
    client.post(
        "/admin/notifications/test", data={"address": "prueba-log@ultrasist.com.mx", "csrf_token": csrf(client, "/")}
    )
    with SessionLocal() as db:
        notification_service.notify(db, NotificationEvent.INVOICE_AUTHORIZED, **INVOICE_VALUES)
    content = json.dumps(events_since(offset), ensure_ascii=False)
    for value in (
        "Clave#Smtp#DelLog",
        "buzon-log@ultrasist.com.mx",
        "prueba-log@ultrasist.com.mx",
        "Correo de prueba del Portal",
        "Factura LOG-MAIL-1 autorizada para pago",
    ):
        assert value not in content, value


# --- Autorizacion de proveedores (HU-02, HU-03) -------------------------------------------------------------------


def test_autorizacion_masiva_registrada(client, registered_suppliers, restore_notification_recipients):
    rows = registered_suppliers(3)
    active = supplier_by_email("proveedor1@poc.local")
    login(client)
    offset = log_offset()
    ids = [str(s.id) for s in rows] + [str(active.id)]
    response = client.post(
        "/suppliers/authorize",
        data={"supplier_ids": ids, "csrf_token": csrf(client, "/suppliers")},
        follow_redirects=False,
    )
    assert response.status_code == 303
    events = events_since(offset)
    [event] = [e for e in events if e.get("event") == "supplier.bulk_authorize"]
    counts = {key: event[key] for key in ("requested", "authorized", "existing_access", "skipped", "conflicts")}
    assert counts == {"requested": 4, "authorized": 3, "existing_access": 0, "skipped": 1, "conflicts": 0}
    assert (event["credentials_sent"], event["credentials_failed"]) == (3, 0) and "duration_ms" in event
    content = json.dumps(events, ensure_ascii=False)
    for supplier in rows:
        assert supplier.email not in content and supplier.business_name not in content
    assert "Contraseña" not in content and "contrasena" not in content


# --- Reglas de Validacion y catalogos (HU-06, HU-07) --------------------------------------------------------------


def test_cambio_de_reglas_de_validacion_registrado(client, restore_validation_rules):
    from app.models import ValidationSettings
    from app.services.validation_settings_service import CHECK_FIELDS, LABELS

    with SessionLocal() as db:
        current = db.get(ValidationSettings, 1)
        data = {name: getattr(current, name) for name in LABELS} | {"version": current.version}
        data |= {name: "on" for name in CHECK_FIELDS}
    login(client)
    offset = log_offset()
    data |= {"receiver_name": "RAZON SOCIAL DEL LOG", "payment_form": "03", "csrf_token": csrf(client, "/")}
    assert client.post("/admin/rules", data=data, follow_redirects=False).status_code == 303
    events = events_since(offset)
    [updated] = [e for e in events if e.get("event") == "validation_settings.updated"]
    assert (updated["fields"], updated["version"]) == (["receiver_name", "payment_form"], 2)
    assert "RAZON SOCIAL DEL LOG" not in json.dumps(events, ensure_ascii=False)


def test_carga_de_catalogo_registrada(client, restore_validation_rules):
    from io import BytesIO

    from openpyxl import Workbook

    book = Workbook()
    book.active.title = "Catalogo"
    for row in (("Clave", "Descripción", "Activo"), ("USD", "Dólar estadounidense", "Sí"), ("JPY", "Yen", "Sí")):
        book.active.append(row)
    content = BytesIO()
    book.save(content)
    login(client)
    offset = log_offset()
    response = client.post(
        "/admin/catalogs/CURRENCY/import",
        data={"csrf_token": csrf(client, "/")},
        files={"upload": ("monedas.xlsx", content.getvalue(), "application/octet-stream")},
    )
    assert response.status_code == 200
    [event] = [e for e in events_since(offset) if e.get("event") == "catalog.import"]
    counts = {key: event[key] for key in ("catalog", "result", "rows", "added", "updated", "unchanged", "invalid")}
    assert counts == {
        "catalog": "CURRENCY",
        "result": "imported",
        "rows": 2,
        "added": 1,
        "updated": 1,
        "unchanged": 0,
        "invalid": 0,
    }
    assert event["size_bytes"] == len(content.getvalue()) and "duration_ms" in event
