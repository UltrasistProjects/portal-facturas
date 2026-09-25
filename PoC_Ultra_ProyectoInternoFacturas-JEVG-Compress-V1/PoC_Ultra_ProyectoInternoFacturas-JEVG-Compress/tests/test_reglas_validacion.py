"""Reglas de Validacion (HU-06, specs reglas-validacion y motor-validacion)."""

import html
import re
import secrets

import pytest
from sqlalchemy import func, select, update

from app.core.database import SessionLocal
from app.models import AuditLog, CatalogEntry, Invoice, User, ValidationResult, ValidationSettings
from app.rules.xml_rules import DISABLED, xml_rules
from app.services import validation_settings_service as vs
from app.services.xml_service import parse_cfdi
from tests.conftest import ROOT, csrf, invoice_by_number, login, supplier_by_email

pytestmark = pytest.mark.usefixtures("restore_validation_rules")

URL = "/admin/rules"
CFDI = (ROOT / "data" / "demo_documents" / "cfdi_demo_correcto.xml").read_text(encoding="utf-8")
PDF = (ROOT / "data" / "demo_documents" / "factura_demo.pdf").read_bytes()


# --- Utilidades ---------------------------------------------------------------------------------------------------


def settings() -> ValidationSettings:
    with SessionLocal() as db:
        return db.get(ValidationSettings, 1)


def params() -> vs.RuleParameters:
    with SessionLocal() as db:
        return vs.rule_parameters(db)


def form_data(client, **fields) -> dict:
    """Formulario con la configuracion y la version vigentes, y los campos indicados cambiados."""
    current = settings()
    data = {name: getattr(current, name) for name in vs.LABELS if name != "allowed_cfdi_uses"}
    data["allowed_cfdi_uses"] = list(current.allowed_cfdi_uses)
    data.update({name: "on" for name in vs.CHECK_FIELDS if getattr(current, name)})
    data.update({"version": current.version, "csrf_token": csrf(client, "/")})
    for name, value in fields.items():
        if value is None:
            data.pop(name, None)
        else:
            data[name] = value
    return data


def save(client, **fields):
    return client.post(URL, data=form_data(client, **fields), follow_redirects=False)


def audit_count() -> int:
    with SessionLocal() as db:
        return db.scalar(select(func.count(AuditLog.id)))


def demo_xml(**attributes) -> str:
    """CFDI demo con atributos del Receptor cambiados."""
    xml = CFDI
    for name, value in attributes.items():
        xml = re.sub(rf'(<cfdi:Receptor[^>]*\b{name}=")[^"]*"', rf'\g<1>{value}"', xml)
    return xml


def results_for(xml: str) -> dict:
    return {r.rule_code: r for r in xml_rules(parse_cfdi(xml.encode()), None, params())}


def validate_invoice(client, xml: str) -> Invoice:
    """Alta, carga de XML y PDF y prevalidacion de una factura nueva del proveedor 1."""
    number = f"REGLAS-{secrets.token_hex(4).upper()}"
    uuid = f"{secrets.token_hex(4)}-0000-4000-8000-{secrets.token_hex(6)}".upper()
    supplier = supplier_by_email("proveedor1@poc.local")
    login(client, "proveedor1@poc.local")
    data = {
        "supplier_id": supplier.id,
        "contract_id": invoice_by_number("A-CORRECTA").contract_id,
        "invoice_number": number,
        "service_period": "08/2026",
        "project_name": "Automatizacion Operativa 2026",
        "csrf_token": csrf(client, "/invoices/new"),
    }
    assert client.post("/invoices/new", data=data, follow_redirects=False).status_code == 303
    invoice = invoice_by_number(number)
    xml = re.sub(r'UUID="[^"]*"', f'UUID="{uuid}"', xml)
    for doc_type, filename, content in (("INVOICE_XML", "cfdi.xml", xml.encode()), ("INVOICE_PDF", "f.pdf", PDF)):
        response = client.post(
            f"/invoices/{invoice.id}/documents",
            data={"document_type": doc_type, "csrf_token": csrf(client, f"/invoices/{invoice.id}")},
            files={"upload": (filename, content, "application/octet-stream")},
            follow_redirects=False,
        )
        assert response.status_code == 303
    token = csrf(client, f"/invoices/{invoice.id}")
    assert client.post(f"/invoices/{invoice.id}/validation", data={"csrf_token": token}).status_code == 200
    return invoice_by_number(number)


def stored_results(invoice_id: int) -> dict:
    with SessionLocal() as db:
        rows = db.scalars(select(ValidationResult).where(ValidationResult.invoice_id == invoice_id))
        return {r.rule_code: r for r in rows}


# --- Acceso -------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("email", ["pmo@poc.local", "proveedor1@poc.local"])
def test_sin_acceso_para_pmo_ni_proveedor(client, email):
    login(client, email)
    token = csrf(client, "/")
    responses = [client.get(URL), client.post(URL, data={"receiver_name": "OTRA", "version": 1, "csrf_token": token})]
    assert [r.status_code for r in responses] == [403, 403]
    assert settings().version == 1


@pytest.mark.parametrize("token", [None, "token-invalido"])
def test_guardado_sin_token_csrf(client, token):
    login(client)
    data = form_data(client, receiver_name="OTRA RAZON")
    data.pop("csrf_token")
    if token:
        data["csrf_token"] = token
    assert client.post(URL, data=data).status_code == 403
    assert settings().receiver_name == "ULTRASIST"


def test_opciones_en_el_menu(client):
    login(client)
    page = client.get("/").text
    assert "Reglas de validación</a>" in page and 'href="/admin/catalogs"' in page
    client.post("/logout", data={"csrf_token": csrf(client, "/")})
    login(client, "pmo@poc.local")
    page = client.get("/").text
    assert 'href="/admin/rules"' not in page and 'href="/admin/catalogs"' not in page


# --- Configuracion ------------------------------------------------------------------------------------------------


def test_valores_iniciales(client):
    login(client)
    page = client.get(URL).text
    assert 'name="receiver_rfc" class="form-control mono" value="ULT940623AG0"' in page
    assert 'value="ULTRASIST"' in page and 'value="03930"' in page
    assert '<option value="PPD" selected>' in page and '<option value="99" selected>' in page
    assert re.search(r'value="G03" checked', page) and re.search(r'value="I04" checked', page)
    assert not re.search(r'value="G01" checked', page)
    for severity, weight in (("CRITICAL", 35), ("ERROR", 18), ("WARNING", 6), ("INFO", 0)):
        assert f"<dt>{severity}</dt><dd>{weight}</dd>" in page
    assert page.count("checked> Comparar") == 6


def test_cambio_de_razon_social_y_direccion(client):
    login(client)
    response = save(
        client, receiver_name="  ULTRASIST   SA DE CV ", receiver_address="Av. Insurgentes Sur 1, Ciudad de México"
    )
    assert response.status_code == 303 and response.headers["location"] == f"{URL}?ok=saved"
    assert "Reglas de validación guardadas" in client.get(response.headers["location"]).text
    current = settings()
    assert (current.receiver_name, current.version) == ("ULTRASIST SA DE CV", 2)
    assert current.receiver_address == "Av. Insurgentes Sur 1, Ciudad de México"
    assert results_for(CFDI)["XML-009"].status == "FAIL"  # el XML demo trae "ULTRASIST"


def test_desactivar_una_comparacion(client):
    login(client)
    assert save(client, check_receiver_postal_code=None).status_code == 303
    page = client.get(URL).text
    assert re.search(
        r"XML-010</td><td>Código postal del receptor</td><td>ERROR</td><td><span class=\"status\">Desactivada", page
    )
    result = results_for(demo_xml(DomicilioFiscalReceptor="06600"))["XML-010"]
    assert (result.status, result.severity, result.message) == ("NOT_APPLICABLE", "ERROR", DISABLED)


def test_varios_errores_conservan_lo_capturado(client):
    login(client)
    response = save(client, receiver_rfc="ult94", receiver_postal_code="0393", allowed_cfdi_uses=[])
    assert response.status_code == 400
    for message in (
        "RFC: no es un RFC de persona moral válido",
        "Código postal: debe tener 5 dígitos",
        "Usos de CFDI: seleccione al menos uno",
    ):
        assert message in html.unescape(response.text)
    assert 'value="ULT94"' in response.text
    assert settings().version == 1


def test_rfc_con_fecha_invalida(client):
    login(client)
    response = save(client, receiver_rfc="ULT941323AG0")
    assert response.status_code == 400 and "RFC: no es un RFC de persona moral válido" in html.unescape(response.text)


def test_clave_inexistente_o_inactiva(client):
    with SessionLocal() as db:
        db.execute(
            update(CatalogEntry)
            .where(CatalogEntry.catalog == "PAYMENT_FORM", CatalogEntry.code == "01")
            .values(is_active=False)
        )
        db.commit()
    login(client)
    for code in ("98", "01"):
        response = save(client, payment_form=code)
        assert response.status_code == 400
        assert "Forma de pago: la clave no está activa en el catálogo" in html.unescape(response.text)
    response = save(client, allowed_cfdi_uses=["G03", "ZZ99"])
    assert "Usos de CFDI: la clave ZZ99 no está activa en el catálogo" in html.unescape(response.text)
    assert settings().version == 1


def test_edicion_concurrente(client):
    login(client)
    stale = form_data(client)
    assert save(client, payment_form="03").status_code == 303
    response = client.post(URL, data={**stale, "payment_form": "04"}, follow_redirects=False)
    assert response.status_code == 409
    assert "Otro administrador modificó las Reglas de Validación" in html.unescape(response.text)
    assert (settings().payment_form, settings().version) == ("03", 2)


def test_sin_cambios(client):
    login(client)
    before = audit_count()
    response = save(client)
    assert response.headers["location"] == f"{URL}?ok=unchanged"
    assert "Sin cambios" in client.get(response.headers["location"]).text
    assert settings().version == 1 and audit_count() == before


def test_auditoria_de_un_cambio(client):
    login(client)
    save(client, payment_form="03")
    with SessionLocal() as db:
        entry = db.scalar(
            select(AuditLog).where(AuditLog.action == "VALIDATION_SETTINGS_UPDATED").order_by(AuditLog.id.desc())
        )
        admin = db.scalar(select(User.id).where(User.email == "admin@poc.local"))
    assert entry.user_id == admin
    assert (entry.old_value, entry.new_value) == (
        {"payment_form": "99", "version": 1},
        {"payment_form": "03", "version": 2},
    )


# --- Motor --------------------------------------------------------------------------------------------------------


def test_razon_social_con_otro_formato():
    assert results_for(demo_xml(Nombre="Últrasist  "))["XML-009"].status == "PASS"
    assert vs.normalize_name(" Últra   SIST ") == "ultra sist"


def test_codigo_postal_distinto_en_una_factura(client):
    invoice = validate_invoice(client, demo_xml(DomicilioFiscalReceptor="06600"))
    xml010 = stored_results(invoice.id)["XML-010"]
    assert (xml010.status, xml010.severity) == ("FAIL", "ERROR")
    assert (xml010.expected_value, xml010.detected_value) == ("03930", "06600")
    assert invoice.status.value == "REQUIRES_CORRECTION"


def test_factura_demo_correcta(client):
    invoice = validate_invoice(client, CFDI)
    results = stored_results(invoice.id)
    assert (results["XML-009"].status, results["XML-010"].status) == ("PASS", "PASS")
    assert results["XML-009"].source_reference == "Receptor.Nombre"


def test_comparacion_de_razon_social_desactivada(client):
    login(client)
    save(client, check_receiver_name=None)
    result = results_for(demo_xml(Nombre="OTRA EMPRESA"))["XML-009"]
    assert (result.status, result.message) == ("NOT_APPLICABLE", DISABLED)


def test_mensajes_con_el_valor_esperado(client):
    login(client)
    save(client, payment_method="PUE", payment_form="03")
    results = results_for(CFDI)  # el XML demo trae PPD y 99
    assert results["XML-003"].message == "MetodoPago debe ser PUE" and results["XML-003"].expected_value == "PUE"
    assert results["XML-004"].message == "FormaPago debe ser 03"


def test_todas_las_comparaciones_desactivables(client):
    login(client)
    save(client, **{field: None for field in vs.CHECK_FIELDS})
    wrong = demo_xml(Rfc="XXX010101XXX", Nombre="OTRA", DomicilioFiscalReceptor="06600", UsoCFDI="S01")
    results = results_for(wrong)
    for code in ("XML-002", "XML-003", "XML-004", "XML-005", "XML-009", "XML-010"):
        assert results[code].status == "NOT_APPLICABLE", code
    assert results["XML-001"].status == "PASS" and results["XML-007"].status == "PASS"
