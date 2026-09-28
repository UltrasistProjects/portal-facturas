"""Perfil del proveedor (alta individual y edicion) y expediente del Anexo A: tipos de documento y descarga."""

import html
import re
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import delete, select, update

from app.core.constants import SupplierClassification, SupplierType
from app.core.database import SessionLocal
from app.models import AuditLog, CatalogEntry, Document, Supplier
from app.rules.supplier_rules import supplier_rules
from app.services.file_service import LocalFileStorage
from app.services.supplier_service import supplier_requirement_status
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


def test_alta_con_actividad_inactiva(client, restore_validation_rules):
    login(client)
    set_activity_active("54", False)
    response = create_supplier(client, rfc="PCO260101INA")
    assert response.status_code == 400
    assert "Actividad principal: no es una actividad activa del catalogo" in html.unescape(response.text)
    assert supplier_by_rfc("PCO260101INA") is None
    assert 'value="54"' not in client.get("/suppliers").text


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


# --- Expediente del Anexo A ---------------------------------------------------------------------------------------


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


def document_rows(page: str) -> dict[str, tuple[bool, str]]:
    """Filas del expediente en la pagina de detalle: etiqueta -> (marcado como obligatorio, estado y nota)."""
    rows = {}
    for label, status in re.findall(r"<strong>(.*?)</strong><small>([^<]+)</small>", html.unescape(page)):
        rows[label.split("<span")[0]] = ("text-danger" in label, status)
    return rows


def test_documentos_del_expediente_por_tipo_de_persona(client):
    moral = supplier_by_email("proveedor1@poc.local")
    physical = supplier_by_email("proveedor2@poc.local")
    login(client)
    moral_rows = document_rows(client.get(f"/suppliers/{moral.id}").text)
    for label in (
        "Cédula fiscal",
        "Acta constitutiva",
        "Opinión de cumplimiento",
        "Identificación del representante legal",
        "Estado de cuenta bancario",
    ):
        assert moral_rows[label][0], label
    for label in ("Contrato", "Debida diligencia", "Ubicación"):
        assert not moral_rows[label][0], label
    physical_rows = document_rows(client.get(f"/suppliers/{physical.id}").text)
    assert physical_rows["Identificación oficial"][0] and physical_rows["Comprobante de domicilio"][0]
    assert not physical_rows["Contrato"][0]
    assert not [label for label in physical_rows if "representante legal" in label]


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
    assert upload(client, moral.id, "SUPPLIER_CONTRACT").status_code == 303
    assert upload(client, moral.id, "LEGAL_REP_ADDRESS_PROOF").status_code == 303
    assert document_row(moral.id, "LEGAL_REP_ADDRESS_PROOF").mime_type == "application/pdf"
    client.cookies.clear()
    login(client, "proveedor2@poc.local")
    assert upload(client, physical.id, "LEGAL_REP_ADDRESS_PROOF").status_code == 400
    assert upload(client, physical.id, "SUPPLIER_CONTRACT").status_code == 303


def test_vigencia_del_comprobante_del_representante_legal():
    supplier = SimpleNamespace(supplier_type=SupplierType.PERSONA_MORAL, economic_proposal=False)
    old = date.today() - timedelta(days=120)
    documents = [
        SimpleNamespace(document_type=code, is_current=True, document_date=old)
        for code in ("LEGAL_REP_ADDRESS_PROOF", "SUPPLIER_CONTRACT")
    ]
    rows = {row["code"]: row for row in supplier_requirement_status(supplier, documents)}
    assert rows["LEGAL_REP_ADDRESS_PROOF"]["expired"] is True
    assert rows["SUPPLIER_CONTRACT"]["expired"] is False
    assert rows["SUPPLIER_CONTRACT"]["label"] == "Contrato"


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


# --- Expediente minimo (SUP-003) ----------------------------------------------------------------------------------

MORAL_REQUIRED = ("INCORPORATION_ACT", "LEGAL_REP_ID", "TAX_STATUS", "SAT_OPINION", "ADDRESS_PROOF", "BANK_STATEMENT")
PHYSICAL_REQUIRED = ("OFFICIAL_ID", "TAX_STATUS", "SAT_OPINION", "ADDRESS_PROOF", "BANK_STATEMENT")


def minimum_file(supplier_type: SupplierType, codes, quotation: bool = False) -> str:
    """Resultado de SUP-003 para un expediente con los documentos `codes`."""
    supplier = SimpleNamespace(supplier_type=supplier_type, economic_proposal=quotation, status="ACTIVE")
    documents = [SimpleNamespace(document_type=code, is_current=True, document_date=None) for code in codes]
    outcomes = supplier_rules(supplier, None, supplier_requirement_status(supplier, documents))
    return next(o.status for o in outcomes if o.rule_code == "SUP-003")


def test_expediente_minimo_sin_documentos_opcionales():
    # Contrato, debida diligencia, ubicacion y propuesta economica (sin cotizacion) no cuentan.
    assert minimum_file(SupplierType.PERSONA_MORAL, MORAL_REQUIRED) == "PASS"
    assert minimum_file(SupplierType.PERSONA_FISICA, PHYSICAL_REQUIRED) == "PASS"
    assert minimum_file(SupplierType.PERSONA_MORAL, MORAL_REQUIRED[1:]) == "FAIL"
    assert minimum_file(SupplierType.PERSONA_FISICA, PHYSICAL_REQUIRED[:-1]) == "FAIL"


def test_expediente_minimo_con_cualquier_comprobante_de_domicilio():
    without_address = [code for code in MORAL_REQUIRED if code != "ADDRESS_PROOF"]
    assert minimum_file(SupplierType.PERSONA_MORAL, [*without_address, "LEGAL_REP_ADDRESS_PROOF"]) == "PASS"
    assert minimum_file(SupplierType.PERSONA_MORAL, without_address) == "FAIL"
    # La persona fisica no tiene comprobante del representante legal: el suyo es obligatorio.
    physical = [code for code in PHYSICAL_REQUIRED if code != "ADDRESS_PROOF"]
    assert minimum_file(SupplierType.PERSONA_FISICA, [*physical, "LEGAL_REP_ADDRESS_PROOF"]) == "FAIL"


def test_propuesta_economica_obligatoria_en_alta_por_cotizacion():
    assert minimum_file(SupplierType.PERSONA_MORAL, MORAL_REQUIRED, quotation=True) == "FAIL"
    assert minimum_file(SupplierType.PERSONA_MORAL, [*MORAL_REQUIRED, "ECONOMIC_PROPOSAL"], quotation=True) == "PASS"


def test_notas_de_los_documentos_del_expediente(client):
    moral = supplier_by_email("proveedor1@poc.local")
    login(client)
    page = client.get(f"/suppliers/{moral.id}").text
    rows = {label: status for label, (_, status) in document_rows(page).items()}
    assert "Obligatorio para el expediente mínimo" in html.unescape(page)
    assert rows["Contrato"].endswith("· Opcional")
    assert rows["Debida diligencia"].endswith("· Opcional")
    company, representative = "Comprobante de domicilio", "Comprobante de domicilio del representante legal"
    assert rows[company].endswith("· Basta este o el comprobante de domicilio del representante legal")
    assert rows[representative].endswith("· Basta este o el comprobante de domicilio")
    assert rows["Cédula fiscal"] in ("Disponible", "Pendiente", "Advertencia de vigencia (+3 meses)")


def test_obligatoriedad_de_los_comprobantes_de_domicilio():
    """Sin ninguno, los dos se marcan obligatorios; con uno, solo ese; con ambos, los dos cumplen el requisito."""
    supplier = SimpleNamespace(supplier_type=SupplierType.PERSONA_MORAL, economic_proposal=False)

    def required(*codes):
        documents = [SimpleNamespace(document_type=code, is_current=True, document_date=None) for code in codes]
        rows = supplier_requirement_status(supplier, documents)
        return {r["code"]: r["required"] for r in rows if r["code"] in ("ADDRESS_PROOF", "LEGAL_REP_ADDRESS_PROOF")}

    assert required() == {"ADDRESS_PROOF": True, "LEGAL_REP_ADDRESS_PROOF": True}
    assert required("LEGAL_REP_ADDRESS_PROOF") == {"ADDRESS_PROOF": False, "LEGAL_REP_ADDRESS_PROOF": True}
    assert required("ADDRESS_PROOF", "LEGAL_REP_ADDRESS_PROOF") == {
        "ADDRESS_PROOF": True,
        "LEGAL_REP_ADDRESS_PROOF": True,
    }
