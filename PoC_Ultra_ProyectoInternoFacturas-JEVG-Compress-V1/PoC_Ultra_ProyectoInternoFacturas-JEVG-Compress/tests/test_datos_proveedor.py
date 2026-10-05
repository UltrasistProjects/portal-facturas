"""Perfil del proveedor (alta individual y edicion) y expediente: requisitos de alta en la pagina, carga y descarga.
Las reglas de los requisitos de alta (HU-21) se prueban en test_requisitos_alta.py."""

import html
import re
from datetime import date

import pytest
from sqlalchemy import delete, select, update

from app.core.constants import SupplierClassification, SupplierOrigin, SupplierType
from app.core.database import SessionLocal
from app.models import AuditLog, CatalogEntry, Document, Supplier
from app.services.file_service import LocalFileStorage
from tests.conftest import SUPPLIER_PROFILE_FORM, csrf, invoice_by_number, login, supplier_by_email

PDF = b"%PDF-1.4\n%demo\n"


def create_supplier(client, **overrides):
    data = {
        "business_name": "Perfil Completo SA de CV",
        "rfc": "PCO260101AB1",
        "supplier_type": "PERSONA_MORAL",
        "email": "contacto@perfilcompleto.mx",
        **SUPPLIER_PROFILE_FORM,
        **overrides,
    }
    return client.post("/suppliers", data={**data, "csrf_token": csrf(client, "/suppliers")}, follow_redirects=False)


def edit_supplier(client, supplier_id: int, **data):
    return client.post(
        f"/suppliers/{supplier_id}/profile", data={**data, "csrf_token": csrf(client, "/")}, follow_redirects=False
    )


def supplier_by_rfc(rfc: str) -> Supplier | None:
    with SessionLocal() as db:
        return db.scalar(select(Supplier).where(Supplier.rfc == rfc))


def delete_supplier(rfc: str) -> None:
    with SessionLocal() as db:
        db.execute(delete(Supplier).where(Supplier.rfc == rfc))
        db.commit()


def updates(supplier_id: int) -> list[AuditLog]:
    with SessionLocal() as db:
        stmt = select(AuditLog).where(AuditLog.action == "SUPPLIER_UPDATED", AuditLog.entity_id == str(supplier_id))
        return list(db.scalars(stmt.order_by(AuditLog.id)))


def set_activity_active(code: str, active: bool) -> None:
    with SessionLocal() as db:
        db.execute(
            update(CatalogEntry)
            .where(CatalogEntry.catalog == "INDUSTRY", CatalogEntry.code == code)
            .values(is_active=active)
        )
        db.commit()


# --- Alta individual ----------------------------------------------------------------------------------------------


def test_alta_con_el_perfil_completo(client):
    login(client)
    try:
        assert create_supplier(client).status_code == 303
        supplier = supplier_by_rfc("PCO260101AB1")
        assert supplier.classification == SupplierClassification.EXTERNAL
        assert supplier.main_activity == "54"
        assert supplier.incorporation_date == date(2026, 1, 1)
        assert supplier.website == "https://www.serviciosnuevos.example"
        assert (supplier.legal_rep_name, supplier.legal_rep_phone) == ("Ana Martinez Ruiz", "55 1234 5678")
        assert (supplier.contact_name, supplier.contact_phone) == ("Luis Gomez Ortiz", "(55) 8765-4321")
        assert supplier.phone == "55 5555 0000"
        # Informacion bancaria opcional; casillas sin marcar.
        assert (supplier.bank_information, supplier.confidentiality_agreement, supplier.economic_proposal) == (
            None,
            False,
            False,
        )
        page = html.unescape(client.get(f"/suppliers/{supplier.id}").text)
        assert "Externo" in page
        assert "54 · Servicios profesionales, científicos y técnicos" in page
        assert "01/01/2026" in page
        assert '<a href="https://www.serviciosnuevos.example" target="_blank" rel="noopener noreferrer">' in page
        assert "Ana Martinez Ruiz" in page and "(55) 8765-4321" in page
    finally:
        delete_supplier("PCO260101AB1")


def test_alta_de_persona_fisica_sin_fecha_de_constitucion(client):
    login(client)
    try:
        # La fecha capturada no se guarda: no aplica a persona fisica.
        response = create_supplier(client, rfc="PCO260101FIS", supplier_type="PERSONA_FISICA", website="")
        assert response.status_code == 303
        supplier = supplier_by_rfc("PCO260101FIS")
        assert (supplier.incorporation_date, supplier.website) == (None, None)
        assert supplier.legal_rep_name == "Ana Martinez Ruiz"
        page = html.unescape(client.get(f"/suppliers/{supplier.id}").text)
        assert "<dt>Fecha de constitución</dt><dd>No aplica</dd>" in page
        assert 'name="incorporation_date"' not in page
        assert "el representante legal puede ser la misma persona" in page
    finally:
        delete_supplier("PCO260101FIS")


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"phone": ""}, "Telefono: es obligatorio"),
        ({"phone": "55-ABC"}, "Telefono: debe tener de 7 a 30 caracteres"),
        ({"legal_rep_name": ""}, "Nombre del representante legal: es obligatorio"),
        (
            {"supplier_type": "PERSONA_FISICA", "legal_rep_phone": ""},
            "Telefono del representante legal: es obligatorio",
        ),
        ({"bank_information": "C" * 256}, "Informacion bancaria: es demasiado largo"),
        ({"incorporation_date": ""}, "Fecha de constitucion: es obligatorio para persona moral"),
        ({"incorporation_date": "2999-01-01"}, "Fecha de constitucion: debe estar entre 1900 y hoy"),
        ({"incorporation_date": "2026-02-30"}, "Fecha de constitucion: no es una fecha valida"),
        ({"website": "ftp://perfil.example"}, "Pagina web: no es una direccion web valida"),
        ({"website": "javascript:alert(1)"}, "Pagina web: no es una direccion web valida"),
        ({"contact_phone": "tel. 55"}, "Telefono del contacto: debe tener de 7 a 30 caracteres"),
        ({"legal_rep_phone": "123"}, "Telefono del representante legal: debe tener de 7 a 30 caracteres"),
        ({"classification": ""}, "Clasificacion: es obligatorio"),
        ({"classification": "OTRA"}, "Clasificacion: no es una opcion valida"),
        ({"contact_name": " "}, "Nombre del contacto: es obligatorio"),
        ({"main_activity": ""}, "Actividad principal: es obligatorio"),
        ({"main_activity": "99"}, "Actividad principal: no es una actividad activa del catalogo"),
    ],
)
def test_alta_invalida(client, overrides, message):
    login(client)
    response = create_supplier(client, rfc="PCO260101INV", **overrides)
    assert response.status_code == 400
    page = html.unescape(response.text)
    assert message in page
    # Lo capturado se conserva para corregirlo.
    assert 'value="Perfil Completo SA de CV"' in page
    assert supplier_by_rfc("PCO260101INV") is None


# Identificadores propios de estas pruebas: el proveedor internacional de la demo ya usa US 98-7654321.
INTERNATIONAL = {"origin": "INTERNATIONAL", "rfc": "", "foreign_tax_id": "PCO-0001", "country": "US"}


def delete_foreign_suppliers(*tax_ids: str) -> None:
    with SessionLocal() as db:
        db.execute(delete(Supplier).where(Supplier.foreign_tax_id.in_(tax_ids)))
        db.commit()


def test_alta_de_proveedor_internacional(client):
    login(client)
    try:
        response = create_supplier(client, **{**INTERNATIONAL, "foreign_tax_id": " pco-00  01 ", "country": "us"})
        assert response.status_code == 303
        supplier = supplier_by_email("contacto@perfilcompleto.mx")
        assert supplier.origin == SupplierOrigin.INTERNATIONAL
        assert (supplier.rfc, supplier.foreign_tax_id, supplier.country) == (None, "PCO-00 01", "US")
        page = html.unescape(client.get(f"/suppliers/{supplier.id}").text)
        assert "US PCO-00 01 · Internacional" in page
        # Sin RFC no hay conflicto con otro internacional; el par (pais, identificador) si es unico.
        second = {**INTERNATIONAL, "email": "billing@segundo.example"}
        assert create_supplier(client, **second).status_code == 303
        repeated = create_supplier(client, **{**second, "email": "otro@segundo.example"})
        assert repeated.status_code == 409
        assert "Ya existe un proveedor con ese identificador fiscal extranjero en ese pais." in repeated.text
        # El mismo identificador en otro pais es otro proveedor.
        other_country = create_supplier(client, **{**second, "country": "CA", "email": "canada@segundo.example"})
        assert other_country.status_code == 303
    finally:
        delete_foreign_suppliers("PCO-00 01", "PCO-0001")


def test_alta_nacional_por_omision(client):
    """Sin origen, el alta es nacional: su pais es MX."""
    login(client)
    try:
        assert create_supplier(client).status_code == 303
        supplier = supplier_by_rfc("PCO260101AB1")
        assert (supplier.origin, supplier.country, supplier.foreign_tax_id) == (SupplierOrigin.NATIONAL, "MX", None)
    finally:
        delete_supplier("PCO260101AB1")


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"rfc": ""}, "RFC: es obligatorio para proveedores nacionales"),
        (
            {"foreign_tax_id": "PCO-0001"},
            "Identificador fiscal extranjero: debe quedar vacio para proveedores nacionales",
        ),
        ({"country": "US"}, "Pais: debe quedar vacio o ser MX para proveedores nacionales"),
        ({**INTERNATIONAL, "rfc": "PCO260101INV"}, "RFC: debe quedar vacio para proveedores internacionales"),
        (
            {**INTERNATIONAL, "foreign_tax_id": ""},
            "Identificador fiscal extranjero: es obligatorio para proveedores internacionales",
        ),
        ({**INTERNATIONAL, "foreign_tax_id": "98_765"}, "Identificador fiscal extranjero: use hasta 40 caracteres"),
        ({**INTERNATIONAL, "foreign_tax_id": "9" * 41}, "Identificador fiscal extranjero: use hasta 40 caracteres"),
        ({**INTERNATIONAL, "country": ""}, "Pais: es obligatorio para proveedores internacionales"),
        ({**INTERNATIONAL, "country": "MX"}, "Pais: un proveedor internacional no puede tener pais MX"),
        ({**INTERNATIONAL, "country": "USA"}, "Pais: use el codigo ISO de dos letras"),
        ({"origin": "EXTRANJERO"}, "Origen: no es una opcion valida"),
    ],
)
def test_alta_con_identidad_fiscal_incongruente(client, overrides, message):
    login(client)
    response = create_supplier(client, **overrides)
    assert response.status_code == 400
    page = html.unescape(response.text)
    assert message in page
    assert supplier_by_email("contacto@perfilcompleto.mx") is None


def test_alta_internacional_invalida_conserva_lo_capturado(client):
    login(client)
    response = create_supplier(client, **{**INTERNATIONAL, "country": "CA", "foreign_tax_id": ""})
    assert response.status_code == 400
    page = response.text
    assert '<option value="INTERNATIONAL" selected>' in page
    assert '<option value="CA" selected>' in page
    # Mexico corresponde al origen Nacional: no se ofrece como pais del internacional.
    countries = re.search(r'<select[^>]*name="country".*?</select>', page, re.S).group(0)
    assert 'value="MX"' not in countries and 'value="US"' in countries


# --- Campos condicionados (supplier_form.js) ----------------------------------------------------------------------

FIELD = re.compile(
    r'<div class="field[^"]*"(?: data-depends-on="(\w+)" data-applies-when="([\w ]+)")?>(.*?)</div>', re.S
)
REQUIRED = re.compile(r"\srequired\b")


def conditional_control(page: str, name: str) -> tuple[str, str, str] | None:
    """(selector del que depende, valores con los que aplica, etiqueta del control) del campo `name`; None si aplica
    siempre."""
    for depends_on, applies_when, content in FIELD.findall(page):
        control = re.search(rf'<(?:input|select)[^>]*name="{name}"[^>]*>', content)
        if control:
            return (depends_on, applies_when, control.group(0)) if depends_on else None
    raise AssertionError(f"El formulario no tiene el campo {name}")


@pytest.mark.parametrize(
    ("name", "rule"),
    [
        ("rfc", ("origin", "NATIONAL")),
        ("foreign_tax_id", ("origin", "INTERNATIONAL")),
        ("country", ("origin", "INTERNATIONAL")),
        ("incorporation_date", ("supplier_type", "PERSONA_MORAL")),
    ],
)
def test_alta_declara_los_campos_condicionados(client, name, rule):
    login(client)
    depends_on, applies_when, control = conditional_control(client.get("/suppliers").text, name)
    assert (depends_on, applies_when) == rule
    # Obligatorio solo cuando aplica: lo activa supplier_form.js; sin JavaScript, el servidor valida la combinacion.
    assert "data-required" in control and not REQUIRED.search(control)


def test_alta_sin_dependencias_en_los_demas_campos(client):
    login(client)
    page = client.get("/suppliers").text
    assert "/static/js/supplier_form.js" in page
    always = ("origin", "business_name", "supplier_type", "email", "phone", "classification", "main_activity")
    always += ("website", "contact_name", "contact_phone", "legal_rep_name", "legal_rep_phone", "bank_information")
    for name in (*always, "confidentiality_agreement", "economic_proposal"):
        assert conditional_control(page, name) is None, name
    hint = 'data-depends-on="supplier_type" data-applies-when="PERSONA_FISICA">En persona física, el representante'
    assert hint in html.unescape(page)


def test_alta_sin_los_campos_que_no_aplican(client):
    """El navegador no envia los campos deshabilitados: el pais del nacional es MX y la persona fisica no necesita
    fecha de constitucion."""
    login(client)
    try:
        response = create_supplier(
            client, origin="NATIONAL", rfc="PCO260101PAY", supplier_type="PERSONA_FISICA", incorporation_date=""
        )
        assert response.status_code == 303
        supplier = supplier_by_rfc("PCO260101PAY")
        assert (supplier.country, supplier.foreign_tax_id, supplier.incorporation_date) == ("MX", None, None)
    finally:
        delete_supplier("PCO260101PAY")


def test_edicion_sin_selectores_de_identidad(client, registered_suppliers):
    """En la edicion el origen y el tipo de persona no cambian: no hay selectores y el servidor decide los campos. La
    fecha de constitucion de la persona moral es obligatoria sin depender del script."""
    (supplier,) = registered_suppliers()
    login(client)
    page = client.get(f"/suppliers/{supplier.id}").text
    assert 'name="supplier_type"' not in page and 'name="origin"' not in page
    _, _, control = conditional_control(page, "incorporation_date")
    assert REQUIRED.search(control)


def test_alta_con_actividad_inactiva(client, restore_validation_rules):
    login(client)
    set_activity_active("54", False)
    response = create_supplier(client, rfc="PCO260101INA")
    assert response.status_code == 400
    assert "Actividad principal: no es una actividad activa del catalogo" in html.unescape(response.text)
    assert supplier_by_rfc("PCO260101INA") is None
    # Solo el selector de actividad: la pagina tambien trae value="<id>" en las casillas de los proveedores.
    activities = re.search(r'<select[^>]*name="main_activity".*?</select>', client.get("/suppliers").text, re.S)
    assert 'value="54"' not in activities.group(0)


# --- Edicion ------------------------------------------------------------------------------------------------------


def test_edicion_guarda_y_audita_solo_los_cambios(client, registered_suppliers):
    (supplier,) = registered_suppliers()
    login(client)
    form = {"business_name": "Nombre Editado SA de CV", **SUPPLIER_PROFILE_FORM}
    assert edit_supplier(client, supplier.id, **form).status_code == 303
    with SessionLocal() as db:
        saved = db.get(Supplier, supplier.id)
    assert saved.business_name == "Nombre Editado SA de CV"
    assert saved.classification == SupplierClassification.EXTERNAL
    assert saved.incorporation_date == date(2026, 1, 1)
    (entry,) = updates(supplier.id)
    assert entry.old_value["business_name"] == supplier.business_name
    assert entry.old_value["contact_name"] is None
    assert entry.new_value["incorporation_date"] == "2026-01-01"
    assert entry.new_value["website"] == "https://www.serviciosnuevos.example"

    # Sin cambios no se audita; un cambio solo registra ese campo.
    assert edit_supplier(client, supplier.id, **form).status_code == 303
    assert edit_supplier(client, supplier.id, **{**form, "contact_phone": "55 0000 1111"}).status_code == 303
    changes = updates(supplier.id)
    assert len(changes) == 2
    assert changes[-1].old_value == {"contact_phone": "(55) 8765-4321"}
    assert changes[-1].new_value == {"contact_phone": "55 0000 1111"}


def test_edicion_no_cambia_la_identidad_fiscal_ni_el_correo(client, registered_suppliers):
    (supplier,) = registered_suppliers()
    login(client)
    form = {
        "business_name": supplier.business_name,
        **SUPPLIER_PROFILE_FORM,
        "rfc": "XAXX010101000",
        "email": "otro@proveedor.mx",
        "supplier_type": "PERSONA_FISICA",
        "origin": "INTERNATIONAL",
    }
    assert edit_supplier(client, supplier.id, **form).status_code == 303
    with SessionLocal() as db:
        saved = db.get(Supplier, supplier.id)
    assert (saved.rfc, saved.email, saved.supplier_type) == (supplier.rfc, supplier.email, SupplierType.PERSONA_MORAL)


def test_edicion_invalida_conserva_lo_capturado(client, registered_suppliers):
    (supplier,) = registered_suppliers()
    login(client)
    form = {"business_name": supplier.business_name, **SUPPLIER_PROFILE_FORM, "legal_rep_phone": ""}
    response = edit_supplier(client, supplier.id, **{**form, "contact_name": "Contacto Capturado"})
    assert response.status_code == 400
    page = html.unescape(response.text)
    assert "Telefono del representante legal: es obligatorio" in page
    assert 'value="Contacto Capturado"' in page
    assert supplier_by_rfc(supplier.rfc).contact_name is None
    assert updates(supplier.id) == []


def test_edicion_exclusiva_del_administrador(client, registered_suppliers):
    (supplier,) = registered_suppliers()
    own = supplier_by_email("proveedor1@poc.local")
    form = {"business_name": "Intento", **SUPPLIER_PROFILE_FORM}
    login(client, "pmo@poc.local")
    assert edit_supplier(client, supplier.id, **form).status_code == 403
    client.cookies.clear()
    login(client, "proveedor1@poc.local")
    assert edit_supplier(client, own.id, **form).status_code == 403
    client.cookies.clear()
    login(client)
    response = client.post(f"/suppliers/{supplier.id}/profile", data=form, follow_redirects=False)
    assert response.status_code == 403
    assert edit_supplier(client, 999999, **form).status_code == 404
    assert supplier_by_rfc(supplier.rfc).business_name == supplier.business_name
    assert supplier_by_email("proveedor1@poc.local").business_name == own.business_name


def test_edicion_conserva_una_actividad_desactivada(client, registered_suppliers, restore_validation_rules):
    (supplier,) = registered_suppliers(main_activity="54")
    (other,) = registered_suppliers(main_activity="31")
    set_activity_active("54", False)
    login(client)
    page = html.unescape(client.get(f"/suppliers/{supplier.id}").text)
    option = '<option value="54" selected>54 · Servicios profesionales, científicos y técnicos (inactiva)</option>'
    assert option in page
    form = {"business_name": supplier.business_name, **SUPPLIER_PROFILE_FORM}
    assert edit_supplier(client, supplier.id, **form).status_code == 303
    # Elegirla de nuevo en otro proveedor no se permite.
    response = edit_supplier(client, other.id, **{**form, "business_name": other.business_name})
    assert response.status_code == 400
    assert "Actividad principal: no es una actividad activa del catalogo" in html.unescape(response.text)
    assert supplier_by_rfc(other.rfc).main_activity == "31"


def test_detalle_de_proveedor_sin_perfil(client, registered_suppliers):
    (supplier,) = registered_suppliers()
    login(client, "pmo@poc.local")
    page = client.get(f"/suppliers/{supplier.id}").text
    assert "Sin clasificar" in page
    assert "Editar datos del proveedor" not in page


# --- Expediente: requisitos de alta ----------------------------------------------------------------------------


def document_row(supplier_id: int, document_type: str) -> Document:
    with SessionLocal() as db:
        return db.scalar(
            select(Document).where(
                Document.supplier_id == supplier_id,
                Document.invoice_id.is_(None),
                Document.document_type == document_type,
                Document.is_current.is_(True),
            )
        )


def requirement_rows(page: str) -> dict[str, str]:
    """Panel "Requisitos de alta" del expediente: nombre -> "<nivel> · <estado>[ · <nota>]"."""
    pattern = r'<strong>([^<]+)</strong><small class="requirement-status">([^<]+)</small>'
    return dict(re.findall(pattern, html.unescape(page)))


def test_requisitos_del_expediente_por_tipo_de_persona(client):
    moral = supplier_by_email("proveedor1@poc.local")
    physical = supplier_by_email("proveedor2@poc.local")
    login(client)
    page = html.unescape(client.get(f"/suppliers/{moral.id}").text)
    assert "<h2>Requisitos de alta</h2>" in page and "Requisitos de alta completos" in page
    moral_rows = requirement_rows(page)
    for label in (
        "Acta constitutiva",
        "Poderes",
        "Cédula fiscal",
        "Identificación del representante legal",
        "Comprobante de domicilio del representante legal",
        "Comprobante de domicilio",
        "Estado de cuenta bancario",
    ):
        assert moral_rows[label].startswith("Obligatorio · "), label
    for label in ("Opinión de cumplimiento", "Debida diligencia", "Ubicación"):
        assert moral_rows[label].startswith("Opcional · "), label
    # El Contrato se carga en cada contrato (HU-22).
    assert "Identificación oficial" not in moral_rows and "Contrato" not in moral_rows
    physical_rows = requirement_rows(client.get(f"/suppliers/{physical.id}").text)
    assert physical_rows["Identificación oficial"].startswith("Obligatorio · ")
    assert physical_rows["Comprobante de domicilio"].startswith("Obligatorio · ")
    assert physical_rows["Ubicación"].startswith("Opcional · ") and "Contrato" not in physical_rows
    assert not [label for label in physical_rows if "representante legal" in label or label == "Poderes"]


def test_notas_de_los_requisitos_del_expediente(client):
    moral = supplier_by_email("proveedor1@poc.local")
    login(client)
    rows = requirement_rows(client.get(f"/suppliers/{moral.id}").text)
    # El proveedor demo se dio de alta por cotizacion: la propuesta economica es exigible.
    assert rows["Propuesta económica"].startswith("Obligatorio · ")
    assert rows["Propuesta económica"].endswith(" · Alta por cotización o licitación")
    # Cargado: nombre del archivo vigente y fecha del documento (otras pruebas pueden reemplazarlo).
    assert re.fullmatch(r"Obligatorio · \S+ \(\d{2}/\d{2}/\d{4}\)", rows["Cédula fiscal"])


def upload(client, supplier_id: int, document_type: str):
    return client.post(
        f"/suppliers/{supplier_id}/documents",
        data={"document_type": document_type, "document_date": "2026-09-01", "csrf_token": csrf(client, "/")},
        files={"upload": ("documento.pdf", PDF, "application/octet-stream")},
        follow_redirects=False,
    )


def test_carga_de_los_documentos_nuevos(client):
    moral = supplier_by_email("proveedor1@poc.local")
    physical = supplier_by_email("proveedor2@poc.local")
    login(client, "proveedor1@poc.local")
    assert upload(client, moral.id, "LOCATION").status_code == 303
    assert upload(client, moral.id, "LEGAL_REP_ADDRESS_PROOF").status_code == 303
    assert document_row(moral.id, "LEGAL_REP_ADDRESS_PROOF").mime_type == "application/pdf"
    client.cookies.clear()
    login(client, "proveedor2@poc.local")
    rejected = upload(client, physical.id, "LEGAL_REP_ADDRESS_PROOF")
    assert rejected.status_code == 400 and "El documento no aplica a este proveedor" in rejected.text
    assert upload(client, physical.id, "LOCATION").status_code == 303
    # El Contrato ya no es requisito de alta: se carga en cada contrato (HU-22).
    assert upload(client, physical.id, "SUPPLIER_CONTRACT").status_code == 400


def download(client, supplier_id: int, document_id: int):
    return client.get(f"/suppliers/{supplier_id}/documents/{document_id}/download")


def test_descarga_de_documentos_del_expediente(client):
    moral = supplier_by_email("proveedor1@poc.local")
    physical = supplier_by_email("proveedor2@poc.local")
    document = document_row(moral.id, "TAX_STATUS")
    content = LocalFileStorage().resolve(document.path).read_bytes()

    login(client, "proveedor1@poc.local")
    page = client.get(f"/suppliers/{moral.id}").text
    assert f"/suppliers/{moral.id}/documents/{document.id}/download" in page
    response = download(client, moral.id, document.id)
    assert response.status_code == 200
    assert response.content == content
    assert response.headers["content-type"] == "application/octet-stream"
    assert response.headers["content-disposition"].startswith("attachment;")

    client.cookies.clear()
    login(client, "proveedor2@poc.local")
    assert download(client, moral.id, document.id).status_code == 403

    client.cookies.clear()
    login(client, "pmo@poc.local")
    assert download(client, moral.id, document.id).status_code == 200
    # El documento debe pertenecer al expediente del proveedor de la ruta, y no a una factura.
    assert download(client, physical.id, document.id).status_code == 404
    invoice_document = invoice_by_number("A-CORRECTA").id
    with SessionLocal() as db:
        invoice_doc_id = db.scalar(select(Document.id).where(Document.invoice_id == invoice_document))
    assert download(client, moral.id, invoice_doc_id).status_code == 404
    assert download(client, moral.id, 999999).status_code == 404


def test_edicion_de_las_casillas_y_la_informacion_bancaria(client, registered_suppliers):
    (supplier,) = registered_suppliers()
    login(client)
    form = {"business_name": supplier.business_name, **SUPPLIER_PROFILE_FORM}
    checked = {**form, "confidentiality_agreement": "true", "economic_proposal": "true", "bank_information": "CLABE 01"}
    assert edit_supplier(client, supplier.id, **checked).status_code == 303
    saved = supplier_by_rfc(supplier.rfc)
    flags = (saved.confidentiality_agreement, saved.economic_proposal, saved.bank_information)
    assert flags == (True, True, "CLABE 01")
    page = html.unescape(client.get(f"/suppliers/{supplier.id}").text)
    assert 'name="confidentiality_agreement" value="true" class="form-check-input" checked' in page
    assert "Requerida: alta por cotización o licitación" in page
    # Una casilla sin marcar no se envia: queda en falso.
    assert edit_supplier(client, supplier.id, **form).status_code == 303
    saved = supplier_by_rfc(supplier.rfc)
    assert (saved.confidentiality_agreement, saved.economic_proposal, saved.bank_information) == (False, False, None)
