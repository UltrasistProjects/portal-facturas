"""Reglas de Validacion por origen (HU-06, ajustes-finales-configuracion)."""

import html
import re
import secrets

import pytest
from sqlalchemy import func, select, update

from app.core.constants import SupplierOrigin
from app.core.database import SessionLocal
from app.models import AuditLog, CatalogEntry, Invoice, User, ValidationResult, ValidationRule
from app.rules.international_rules import international_rules
from app.rules.xml_rules import DISABLED, XML_NOT_REQUIRED, normalize_name, xml_rules
from app.services import validation_rules_service as rules_service
from app.services.validation_engine import run_validation
from app.services.xml_service import parse_cfdi
from tests.conftest import ROOT, csrf, invoice_by_number, login, migration_module, supplier_by_email

pytestmark = pytest.mark.usefixtures("restore_validation_rules")

URL = "/admin/rules"
NATIONAL, INTERNATIONAL = SupplierOrigin.NATIONAL, SupplierOrigin.INTERNATIONAL
PATHS = {NATIONAL: "national", INTERNATIONAL: "international"}
CFDI = (ROOT / "data" / "demo_documents" / "cfdi_demo_correcto.xml").read_text(encoding="utf-8")
PDF = (ROOT / "data" / "demo_documents" / "factura_demo.pdf").read_bytes()


# --- Utilidades ---------------------------------------------------------------------------------------------------


def rule(origin: SupplierOrigin, code: str) -> ValidationRule:
    with SessionLocal() as db:
        return db.scalar(
            select(ValidationRule).where(ValidationRule.origin == origin, ValidationRule.rule_code == code)
        )


def rule_set(origin: SupplierOrigin = NATIONAL):
    with SessionLocal() as db:
        return rules_service.rule_set(db, origin)


def edit(client, origin: SupplierOrigin, code: str, parameter=None, name=None, version=None, token=True):
    """Edicion de una regla con su version vigente; `parameter` None conserva el valor actual."""
    current = rule(origin, code)
    value = current.parameter if parameter is None else parameter
    data = {
        "name": current.name if name is None else name,
        "parameter": value if value is not None else [],
        "version": current.version if version is None else version,
    }
    if token:
        data["csrf_token"] = csrf(client, "/")
    return client.post(f"{URL}/{PATHS[origin]}/{current.id}", data=data, follow_redirects=False)


def change(client, origin: SupplierOrigin, code: str, action: str):
    current = rule(origin, code)
    return client.post(
        f"{URL}/{PATHS[origin]}/{current.id}/{action}", data={"csrf_token": csrf(client, "/")}, follow_redirects=False
    )


def audit_count() -> int:
    with SessionLocal() as db:
        return db.scalar(select(func.count(AuditLog.id)))


def last_audit(action: str) -> AuditLog:
    with SessionLocal() as db:
        return db.scalar(select(AuditLog).where(AuditLog.action == action).order_by(AuditLog.id.desc()))


def demo_xml(**attributes) -> str:
    """CFDI demo con atributos del Receptor cambiados."""
    xml = CFDI
    for name, value in attributes.items():
        xml = re.sub(rf'(<cfdi:Receptor[^>]*\b{name}=")[^"]*"', rf'\g<1>{value}"', xml)
    return xml


def results_for(xml: str) -> dict:
    return {r.rule_code: r for r in xml_rules(parse_cfdi(xml.encode()), None, rule_set())}


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


def engine_results(invoice_number: str) -> dict:
    """Prevalidacion de una factura sembrada sin confirmar nada: el motor completo con las reglas de su origen."""
    with SessionLocal() as db:
        invoice = db.scalar(select(Invoice).where(Invoice.invoice_number == invoice_number))
        outcome = run_validation(db, invoice)
        db.rollback()
    return {r.rule_code: r for r in outcome["results"]}


# --- Acceso -------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("email", ["pmo@poc.local", "proveedor1@poc.local"])
def test_sin_acceso_para_pmo_ni_proveedor(client, email):
    target = rule(NATIONAL, "XML-009")
    login(client, email)
    token = csrf(client, "/")
    responses = [
        client.get(f"{URL}/national"),
        client.get(f"{URL}/international"),
        client.post(f"{URL}/national/{target.id}", data={"name": "Otra", "version": 1, "csrf_token": token}),
        client.post(f"{URL}/national/{target.id}/delete", data={"csrf_token": token}),
    ]
    assert [r.status_code for r in responses] == [403, 403, 403, 403]
    assert (rule(NATIONAL, "XML-009").version, rule(NATIONAL, "XML-009").is_active) == (1, True)


def test_guardado_sin_token_csrf(client):
    login(client)
    assert edit(client, NATIONAL, "XML-009", "OTRA RAZON", token=False).status_code == 403
    target = rule(NATIONAL, "XML-010")
    assert client.post(f"{URL}/national/{target.id}/delete", data={"csrf_token": "x"}).status_code == 403
    assert rule(NATIONAL, "XML-009").parameter == "ULTRASIST" and rule(NATIONAL, "XML-010").is_active


def test_rutas(client):
    login(client)
    response = client.get(URL, follow_redirects=False)
    assert (response.status_code, response.headers["location"]) == (303, f"{URL}/national")
    assert client.get(f"{URL}/foreign").status_code == 404


def test_opciones_en_el_menu(client):
    login(client)
    page = client.get("/").text
    assert f'href="{URL}/national"' in page and f'href="{URL}/international"' in page
    client.post("/logout", data={"csrf_token": csrf(client, "/")})
    login(client, "pmo@poc.local")
    page = client.get("/").text
    assert f'href="{URL}/national"' not in page and 'href="/admin/catalogs"' not in page


# --- Catalogo y pantallas -----------------------------------------------------------------------------------------


def test_catalogo_inicial():
    with SessionLocal() as db:
        rows = db.execute(select(ValidationRule.origin, ValidationRule.rule_code, ValidationRule.is_active)).all()
    national = {code: active for origin, code, active in rows if origin == NATIONAL}
    international = {code: active for origin, code, active in rows if origin == INTERNATIONAL}
    assert national == {
        "XML-002": True,
        "XML-003": True,
        "XML-004": True,
        "XML-005": True,
        "XML-009": True,
        "XML-010": True,
        "XML-011": False,
    }
    assert international == {"INT-001": True, "INT-002": True, "INT-003": True, "INT-004": False}
    assert (rule(NATIONAL, "XML-005").parameter, rule(NATIONAL, "XML-011").parameter) == (["G03", "I04"], "601")
    assert rule(NATIONAL, "XML-011").deleted_at is not None and rule(INTERNATIONAL, "INT-004").parameter == ""


def test_migracion_de_una_configuracion_modificada():
    """La configuracion unica se convierte en reglas nacionales y siembra las internacionales con los mismos valores."""
    settings = {
        **migration_module("0007_validation_rules_catalogs").SETTINGS,
        "receiver_name": "ULTRASIST SA DE CV",
        "check_receiver_postal_code": False,
        "receiver_address": "Av. Insurgentes Sur 1",
    }
    values = {(o, c): (p, a) for o, c, _, p, a in migration_module("0020_validation_rules").rule_values(settings)}
    assert values["NATIONAL", "XML-009"] == values["INTERNATIONAL", "INT-002"] == ("ULTRASIST SA DE CV", True)
    assert values["NATIONAL", "XML-010"] == values["INTERNATIONAL", "INT-003"] == ("03930", False)
    assert values["INTERNATIONAL", "INT-004"] == ("Av. Insurgentes Sur 1", True)
    assert values["NATIONAL", "XML-011"] == ("601", False)


def test_pagina_nacional(client):
    login(client)
    page = html.unescape(client.get(f"{URL}/national").text)
    for code in ("XML-002", "XML-003", "XML-004", "XML-005", "XML-009", "XML-010"):
        assert f'<td class="mono">{code}</td>' in page
    assert "<td>ULT940623AG0</td>" in page and "<td>G03, I04</td>" in page and "<td>03930</td>" in page
    assert '<td class="mono">XML-011</td>' not in page and "Mostrar eliminados (1)" in page
    assert "XML-007 compara la moneda del CFDI con las monedas activas del catálogo" in page
    assert "INT-00" not in page
    for severity, weight in (("CRITICAL", 35), ("ERROR", 18), ("WARNING", 6), ("INFO", 0)):
        assert f"<dt>{severity}</dt><dd>{weight}</dd>" in page


def test_pagina_internacional(client):
    login(client)
    page = html.unescape(client.get(f"{URL}/international").text)
    for code in ("INT-001", "INT-002", "INT-003"):
        assert f'<td class="mono">{code}</td>' in page
    assert '<td class="mono">INT-004</td>' not in page and "Mostrar eliminados (1)" in page
    assert "XML-0" not in page


def test_mostrar_eliminados(client):
    login(client)
    page = client.get(f"{URL}/national?eliminados=1").text
    xml011 = rule(NATIONAL, "XML-011")
    assert "Reglas eliminadas" in page and f'action="{URL}/national/{xml011.id}/restore"' in page


# --- Edicion ------------------------------------------------------------------------------------------------------


def test_cambiar_la_forma_de_pago_esperada(client):
    login(client)
    response = edit(client, NATIONAL, "XML-004", "03")
    assert (response.status_code, response.headers["location"]) == (303, f"{URL}/national?ok=updated")
    assert "Regla actualizada" in client.get(response.headers["location"]).text
    current = rule(NATIONAL, "XML-004")
    assert (current.parameter, current.version) == ("03", 2)
    result = results_for(CFDI)["XML-004"]  # el XML demo trae 99
    assert (result.status, result.message, result.expected_value) == ("FAIL", "FormaPago debe ser 03", "03")


def test_regla_de_otro_origen(client):
    login(client)
    int002 = rule(INTERNATIONAL, "INT-002")
    data = {"name": "Otra", "parameter": "OTRA", "version": 1, "csrf_token": csrf(client, "/")}
    assert client.post(f"{URL}/national/{int002.id}", data=data).status_code == 404
    assert rule(INTERNATIONAL, "INT-002").parameter == "ULTRASIST"


def test_editar_una_regla_eliminada(client):
    login(client)
    assert edit(client, INTERNATIONAL, "INT-004", "Av. Insurgentes Sur 1").status_code == 303
    current = rule(INTERNATIONAL, "INT-004")
    assert (current.parameter, current.is_active) == ("Av. Insurgentes Sur 1", False)


def test_varios_errores_conservan_lo_capturado(client):
    login(client)
    response = edit(client, NATIONAL, "XML-002", "ult94", name="R")
    text = html.unescape(response.text)
    assert response.status_code == 400
    assert "RFC: no es un RFC de persona moral válido" in text and "Nombre: debe tener de 3 a 80 caracteres" in text
    assert 'value="ULT94"' in response.text
    assert rule(NATIONAL, "XML-002").version == 1


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
        response = edit(client, NATIONAL, "XML-004", code)
        assert response.status_code == 400
        assert "Forma de pago: la clave no está activa en el catálogo" in html.unescape(response.text)
    response = edit(client, NATIONAL, "XML-005", ["G03", "ZZ99"])
    assert "Usos de CFDI: la clave ZZ99 no está activa en el catálogo" in html.unescape(response.text)
    response = edit(client, NATIONAL, "XML-005", [])
    assert "Usos de CFDI: seleccione al menos uno" in html.unescape(response.text)
    assert rule(NATIONAL, "XML-004").version == rule(NATIONAL, "XML-005").version == 1


def test_edicion_concurrente(client):
    login(client)
    assert edit(client, NATIONAL, "XML-009", "PRIMERO", version=1).status_code == 303
    response = edit(client, NATIONAL, "XML-009", "SEGUNDO", version=1)
    assert response.status_code == 409
    assert "Otro administrador modificó esta regla" in html.unescape(response.text)
    assert (rule(NATIONAL, "XML-009").parameter, rule(NATIONAL, "XML-009").version) == ("PRIMERO", 2)


def test_sin_cambios(client):
    login(client)
    before = audit_count()
    response = edit(client, NATIONAL, "XML-009")
    assert response.headers["location"] == f"{URL}/national?ok=unchanged"
    assert rule(NATIONAL, "XML-009").version == 1 and audit_count() == before


def test_auditoria_de_un_cambio(client):
    login(client)
    edit(client, NATIONAL, "XML-004", "03")
    entry = last_audit("VALIDATION_RULE_UPDATED")
    with SessionLocal() as db:
        admin = db.scalar(select(User.id).where(User.email == "admin@poc.local"))
    assert (entry.user_id, entry.entity, entry.entity_id) == (
        admin,
        "ValidationRule",
        str(rule(NATIONAL, "XML-004").id),
    )
    assert (entry.old_value, entry.new_value) == ({"parameter": "99", "version": 1}, {"parameter": "03", "version": 2})


# --- Eliminacion y restauracion -----------------------------------------------------------------------------------


def test_eliminar_una_regla(client):
    login(client)
    response = change(client, NATIONAL, "XML-010", "delete")
    assert response.headers["location"] == f"{URL}/national?ok=deleted"
    current = rule(NATIONAL, "XML-010")
    assert (current.is_active, current.deleted_at is not None, current.version) == (False, True, 2)
    assert '<td class="mono">XML-010</td>' not in client.get(f"{URL}/national").text
    result = results_for(demo_xml(DomicilioFiscalReceptor="06600"))["XML-010"]
    assert (result.status, result.severity, result.message) == ("NOT_APPLICABLE", "ERROR", DISABLED)
    entry = last_audit("VALIDATION_RULE_DELETED")
    assert (entry.old_value, entry.new_value) == ({"is_active": True}, {"is_active": False})
    before = audit_count()
    assert change(client, NATIONAL, "XML-010", "delete").headers["location"] == f"{URL}/national?ok=unchanged"
    assert audit_count() == before


def test_restaurar_una_regla(client):
    login(client)
    change(client, NATIONAL, "XML-010", "delete")
    assert change(client, NATIONAL, "XML-010", "restore").headers["location"] == f"{URL}/national?ok=restored"
    current = rule(NATIONAL, "XML-010")
    assert (current.is_active, current.deleted_at, current.deleted_by) == (True, None, None)
    assert last_audit("VALIDATION_RULE_RESTORED").new_value == {"is_active": True}


def test_restaurar_sin_parametro_valido(client):
    login(client)
    response = change(client, INTERNATIONAL, "INT-004", "restore")
    assert response.status_code == 400 and "Dirección: es obligatoria" in html.unescape(response.text)
    assert not rule(INTERNATIONAL, "INT-004").is_active


def test_restaurar_con_una_clave_desactivada(client):
    with SessionLocal() as db:
        db.execute(
            update(CatalogEntry)
            .where(CatalogEntry.catalog == "TAX_REGIME", CatalogEntry.code == "601")
            .values(is_active=False)
        )
        db.commit()
    login(client)
    response = change(client, NATIONAL, "XML-011", "restore")
    assert response.status_code == 400
    assert "Régimen fiscal: la clave no está activa en el catálogo" in html.unescape(response.text)
    assert not rule(NATIONAL, "XML-011").is_active


def test_accion_desconocida(client):
    login(client)
    assert change(client, NATIONAL, "XML-010", "status").status_code == 404


# --- Motor --------------------------------------------------------------------------------------------------------


def test_razon_social_con_otro_formato():
    assert results_for(demo_xml(Nombre="Últrasist  "))["XML-009"].status == "PASS"
    assert normalize_name(" Últra   SIST ") == "ultra sist"


def test_codigo_postal_distinto_en_una_factura(client):
    invoice = validate_invoice(client, demo_xml(DomicilioFiscalReceptor="06600"))
    xml010 = stored_results(invoice.id)["XML-010"]
    assert (xml010.status, xml010.severity) == ("FAIL", "ERROR")
    assert (xml010.expected_value, xml010.detected_value) == ("03930", "06600")
    # Verificar no cambia el estatus: la factura sin orden de compra ni Vo.Bo. sigue en "Borrador".
    assert invoice.status.value == "DRAFT"


def test_factura_demo_correcta(client):
    invoice = validate_invoice(client, CFDI)
    results = stored_results(invoice.id)
    assert (results["XML-009"].status, results["XML-010"].status) == ("PASS", "PASS")
    assert (results["XML-011"].status, results["XML-011"].message) == ("NOT_APPLICABLE", DISABLED)
    assert results["XML-009"].source_reference == "Receptor.Nombre"


def test_regimen_fiscal_restaurado(client):
    login(client)
    assert change(client, NATIONAL, "XML-011", "restore").status_code == 303
    result = results_for(demo_xml(RegimenFiscalReceptor="603"))["XML-011"]
    assert (result.status, result.expected_value, result.detected_value) == ("FAIL", "601", "603")


def test_mensajes_con_el_valor_esperado(client):
    login(client)
    edit(client, NATIONAL, "XML-003", "PUE")
    results = results_for(CFDI)  # el XML demo trae PPD
    assert results["XML-003"].message == "MetodoPago debe ser PUE" and results["XML-003"].expected_value == "PUE"


def test_todas_las_reglas_eliminables(client):
    login(client)
    for code in ("XML-002", "XML-003", "XML-004", "XML-005", "XML-009", "XML-010"):
        assert change(client, NATIONAL, code, "delete").status_code == 303
    wrong = demo_xml(Rfc="XXX010101XXX", Nombre="OTRA", DomicilioFiscalReceptor="06600", UsoCFDI="S01")
    results = results_for(wrong)
    for code in ("XML-002", "XML-003", "XML-004", "XML-005", "XML-009", "XML-010", "XML-011"):
        assert results[code].status == "NOT_APPLICABLE", code
    assert results["XML-001"].status == "PASS" and results["XML-007"].status == "PASS"


def test_xml_no_exigido_y_ausente():
    results = xml_rules(None, None, rule_set(), required=False)
    assert {r.rule_code for r in results} == {f"XML-{n:03d}" for n in range(1, 12)}
    assert {(r.status, r.message) for r in results} == {("NOT_APPLICABLE", XML_NOT_REQUIRED)}
    assert [r.status for r in xml_rules(None, "XML roto", rule_set(), required=False)] == ["FAIL"]


def test_factura_internacional_con_reglas_internacionales(client):
    """Una factura internacional se valida solo con las reglas internacionales; la nacional, solo con las nacionales."""
    login(client)
    edit(client, INTERNATIONAL, "INT-002", "ULTRASIST SA DE CV")
    edit(client, INTERNATIONAL, "INT-003", "06600")
    supplier = supplier_by_email("proveedor3@poc.local")
    text = "Tax ID 98-7654321. Bill to: ULTRASIST, S.A. de C.V., C.P. 03930"
    results = {r.rule_code: r for r in international_rules(text, True, supplier, rule_set(INTERNATIONAL))}
    assert (results["INT-002"].status, results["INT-002"].expected_value) == ("PASS", "ULTRASIST SA DE CV")
    assert (results["INT-003"].status, results["INT-003"].expected_value) == ("WARNING", "06600")
    national = engine_results("A-CORRECTA")
    assert (national["XML-009"].expected_value, national["XML-010"].expected_value) == ("ULTRASIST", "03930")
    assert not any(code.startswith("INT-") for code in national)
    international = engine_results("INV-2026-0042")
    assert (international["INT-002"].expected_value, international["INT-003"].expected_value) == (
        "ULTRASIST SA DE CV",
        "06600",
    )
    assert international["XML-009"].status == "NOT_APPLICABLE"


def test_regla_eliminada_en_un_solo_origen(client):
    login(client)
    change(client, INTERNATIONAL, "INT-002", "delete")
    supplier = supplier_by_email("proveedor3@poc.local")
    results = {r.rule_code: r for r in international_rules("ULTRASIST", True, supplier, rule_set(INTERNATIONAL))}
    assert (results["INT-002"].status, results["INT-002"].message) == ("NOT_APPLICABLE", DISABLED)
    assert results_for(demo_xml(Nombre="OTRA"))["XML-009"].status == "FAIL"
