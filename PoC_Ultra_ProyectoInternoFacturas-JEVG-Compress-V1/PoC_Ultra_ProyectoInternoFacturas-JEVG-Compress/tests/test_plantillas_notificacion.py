"""Plantillas de correo de estatus de factura (HU-05, spec plantillas-notificacion)."""

import html
import re
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import delete, func, select, text, update

from app.core.constants import NotificationEvent
from app.core.database import SessionLocal
from app.core.middleware import CONTENT_SECURITY_POLICY, content_security_policy_with_styles
from app.models import AuditLog, NotificationTemplate, User
from app.services import mail_layout
from app.services import notification_templates as nt
from tests.conftest import csrf, login

pytestmark = pytest.mark.usefixtures("restore_notification_templates")

URL = "/admin/notification-templates"
AUTHORIZED = NotificationEvent.INVOICE_AUTHORIZED
REJECTED = NotificationEvent.INVOICE_REJECTED
OBSERVATIONS = NotificationEvent.INVOICE_OBSERVATIONS
CANCELLED = NotificationEvent.INVOICE_CANCELLED
CREDENTIALS = NotificationEvent.SUPPLIER_CREDENTIALS
PAID = NotificationEvent.INVOICE_PAID
COMPLEMENT = NotificationEvent.PAYMENT_COMPLEMENT
SUPPLIER_NAME = "Servicios Digitales del Norte SA de CV"
# Valores completos de un correo; cada prueba cambia solo lo que le interesa.
VALUES = {
    "numero_factura": "A-1024",
    "folio_interno": "FAC-2026-00042",
    "proveedor": SUPPLIER_NAME,
    "monto": Decimal("116000.00"),
    "moneda": "MXN",
    "fecha_estatus": datetime(2026, 9, 25, 16, 30, tzinfo=timezone.utc),
    "observaciones": "El subtotal del XML no coincide con el de la orden de compra.",
    "fecha_limite_cancelacion": datetime(2026, 9, 28, 16, 30, tzinfo=timezone.utc),
    "aviso_complemento": nt.COMPLEMENT_NOTICE.format(fecha="28/09/2026 10:30"),
}


def stored(event: NotificationEvent) -> NotificationTemplate:
    with SessionLocal() as db:
        return db.scalar(select(NotificationTemplate).where(NotificationTemplate.event == event))


def audit_count() -> int:
    with SessionLocal() as db:
        return db.scalar(select(func.count(AuditLog.id)))


def set_template(event: NotificationEvent, **values) -> None:
    with SessionLocal() as db:
        db.execute(update(NotificationTemplate).where(NotificationTemplate.event == event).values(**values))
        db.commit()


def form_data(client, event: NotificationEvent, **fields) -> dict:
    """Formulario con el texto y la version vigentes, y los campos indicados cambiados."""
    current = stored(event)
    data = {"subject": current.subject, "body": current.body, "version": current.version}
    return {**data, "csrf_token": csrf(client, "/"), **fields}


def save(client, event: NotificationEvent, **fields):
    return client.post(f"{URL}/{event}", data=form_data(client, event, **fields), follow_redirects=False)


def preview(client, event: NotificationEvent, **fields):
    return client.post(f"{URL}/{event}/preview", data=form_data(client, event, **fields), follow_redirects=False)


def preview_block(html: str) -> str | None:
    match = re.search(r'<div class="template-preview-body">(.*?)</div>', html, re.DOTALL)
    return match.group(1) if match else None


def preview_email(page: str) -> str | None:
    """HTML del correo de la vista previa, ya sin el escape del atributo srcdoc."""
    match = re.search(r'<iframe class="email-preview"[^>]* srcdoc="([^"]*)"', page)
    return html.unescape(match.group(1)) if match else None


def default_body(event: NotificationEvent) -> str:
    return nt.EVENTS[event].default_body


def admin_name() -> str:
    with SessionLocal() as db:
        return db.scalar(select(User.name).where(User.email == "admin@poc.local"))


def compose(event: NotificationEvent, **overrides):
    with SessionLocal() as db:
        return nt.compose(db, event, **{**VALUES, **overrides})


# --- Una plantilla por evento y acceso ---------------------------------------------------------------------------


def test_evento_inexistente(client):
    login(client)
    assert client.get(f"{URL}/INVOICE_ARCHIVED").status_code == 404
    data = {"subject": "x", "body": "y", "version": 1, "csrf_token": csrf(client, "/")}
    assert client.post(f"{URL}/INVOICE_ARCHIVED", data=data).status_code == 404
    assert client.post(f"{URL}/INVOICE_ARCHIVED/preview", data=data).status_code == 404


@pytest.mark.parametrize("email", ["pmo@poc.local", "proveedor1@poc.local"])
def test_sin_acceso_para_pmo_ni_proveedor(client, email):
    login(client, email)
    token = csrf(client, "/")
    data = {"subject": "Otro {{numero_factura}}", "body": "{{numero_factura}} {{observaciones}}", "version": 1}
    responses = [
        client.get(URL),
        client.get(f"{URL}/{REJECTED}"),
        client.post(f"{URL}/{REJECTED}/preview", data={**data, "csrf_token": token}),
        client.post(f"{URL}/{REJECTED}", data={**data, "csrf_token": token}),
    ]
    assert [response.status_code for response in responses] == [403, 403, 403, 403]
    assert (stored(REJECTED).subject, stored(REJECTED).version) == (nt.EVENTS[REJECTED].default_subject, 1)


@pytest.mark.parametrize("token", [None, "token-invalido"])
def test_guardado_sin_token_csrf(client, token):
    login(client)
    data = {"subject": "Otro {{numero_factura}}", "body": default_body(REJECTED), "version": 1}
    if token:
        data["csrf_token"] = token
    assert client.post(f"{URL}/{REJECTED}", data=data, follow_redirects=False).status_code == 403
    assert stored(REJECTED).version == 1


def test_opcion_en_el_menu(client):
    login(client)
    assert f'href="{URL}"' in client.get("/").text and "Plantillas de correo" in client.get("/").text
    client.cookies.clear()
    login(client, "pmo@poc.local")
    assert "Plantillas de correo" not in client.get("/").text


# --- Consulta y variables ----------------------------------------------------------------------------------------


def test_listado_inicial(client):
    login(client)
    response = client.get(URL)
    assert response.status_code == 200
    rows = re.findall(r"<tr><td><strong>(.*?)</strong></td><td>(.*?)</td><td>(.*?)</td><td>(.*?)</td>", response.text)
    reception, supplier = "Recepción de Facturas", "Proveedor (correo del catálogo)"
    assert [(label, recipient) for label, recipient, _, _ in rows] == [
        ("Autorizada", f"{reception} con copia al proveedor"),
        ("Rechazada", supplier),
        ("Observaciones", supplier),
        ("Cancelada", reception),
        ("Pagada", supplier),
        ("Complemento de pago adjuntado", reception),
        ("Credenciales de acceso", supplier),
    ]
    assert [modified for *_, modified in rows] == ["Predeterminada"] * 7
    assert rows[0][2] == "Factura {{numero_factura}} autorizada para pago"


def test_destinatario_de_solo_lectura(client):
    login(client)
    html = client.get(f"{URL}/{REJECTED}").text
    assert "Destinatario: Proveedor (correo del catálogo)" in html
    form = re.search(rf'<form method="post" action="{URL}/{REJECTED}".*?</form>', html, re.DOTALL).group(0)
    assert set(re.findall(r'name="([^"]+)"', form)) == {"csrf_token", "version", "subject", "body"}


def test_variables_de_la_plantilla_cancelada(client):
    login(client)
    html = client.get(f"{URL}/{CANCELLED}").text
    rows = re.findall(r'<span class="mono">\{\{(\w+)\}\}</span>(<small>Obligatoria</small>)?', html)
    assert [name for name, _ in rows] == [
        "numero_factura",
        "folio_interno",
        "proveedor",
        "monto",
        "estatus",
        "fecha_estatus",
        "fecha_limite_cancelacion",
    ]
    assert [name for name, required in rows if required] == ["numero_factura", "proveedor", "fecha_limite_cancelacion"]
    assert "observaciones" not in html


def test_variable_de_otro_evento(client):
    login(client)
    response = save(client, REJECTED, body=default_body(REJECTED) + "\n{{fecha_limite_cancelacion}}")
    assert response.status_code == 400
    assert "Cuerpo: la variable {{fecha_limite_cancelacion}} no existe en esta plantilla" in response.text
    assert stored(REJECTED).body == default_body(REJECTED)


# --- Validacion --------------------------------------------------------------------------------------------------


def test_variable_desconocida(client):
    login(client)
    response = save(client, REJECTED, body=default_body(REJECTED) + "\nRFC: {{rfc_proveedor}}")
    assert response.status_code == 400
    assert (
        "Cuerpo: la variable {{rfc_proveedor}} no existe en esta plantilla. Variables disponibles: {{numero_factura}}, "
        "{{folio_interno}}, {{proveedor}}, {{monto}}, {{estatus}}, {{fecha_estatus}}, {{observaciones}}"
    ) in response.text
    assert "RFC: {{rfc_proveedor}}" in response.text, "el formulario conserva el texto capturado"
    assert (stored(REJECTED).body, stored(REJECTED).version) == (default_body(REJECTED), 1)


def test_variable_obligatoria_ausente(client):
    login(client)
    response = save(client, REJECTED, body="La factura {{numero_factura}} fue rechazada.")
    assert response.status_code == 400
    assert "Cuerpo: debe incluir la variable obligatoria {{observaciones}}" in response.text


def test_variable_obligatoria_solo_en_el_asunto(client):
    login(client)
    body = "La factura {{numero_factura}} de {{proveedor}} fue autorizada."
    response = save(client, AUTHORIZED, subject="Factura {{numero_factura}} por {{monto}}", body=body)
    assert response.status_code == 400
    assert "Cuerpo: debe incluir la variable obligatoria {{monto}}" in response.text


def test_variable_sin_cerrar(client):
    login(client)
    response = save(client, REJECTED, body="Factura {{numero_factura\n{{numero_factura}} {{observaciones}}")
    assert response.status_code == 400
    assert "Cuerpo: hay una variable sin cerrar; falta }}" in response.text


def test_asunto_demasiado_largo(client):
    login(client)
    response = save(client, REJECTED, subject="{{numero_factura}}" + "x" * 183)
    assert response.status_code == 400
    assert "Asunto: admite hasta 200 caracteres" in response.text


def test_espacios_interiores_y_llaves_sencillas(client):
    login(client)
    response = preview(client, REJECTED, body="Factura {{ numero_factura }} {nota}\n{{observaciones}}")
    assert response.status_code == 200
    assert preview_block(response.text).startswith("Factura A-1024 {nota}\n")


def test_varios_errores_a_la_vez(client):
    login(client)
    response = save(client, REJECTED, subject="", body="Sin numero. {{observaciones}}")
    assert response.status_code == 400
    assert "Asunto: es obligatorio" in response.text
    assert "Cuerpo: debe incluir la variable obligatoria {{numero_factura}}" in response.text


def test_reglas_adicionales_de_texto():
    spec = nt.EVENTS[REJECTED]
    assert nt.check_draft(spec, "Factura {{numero_factura}}\notra linea", default_body(REJECTED)).errors == [
        "Asunto: debe ocupar una sola línea"
    ]
    assert nt.check_draft(spec, "Asunto", "{{numero_factura}} {{observaciones}}" + "x" * 5000).errors == [
        "Cuerpo: admite hasta 5000 caracteres"
    ]
    assert nt.check_draft(spec, "Asunto", "   ").errors == ["Cuerpo: es obligatorio"]
    repeated = nt.check_draft(spec, "Asunto", "{{numero_factura}} {{observaciones}} {{x}} {{ x }}").errors
    assert len(repeated) == 1, "una misma variable desconocida se reporta una vez"
    assert nt.check_draft(spec, "Asunto }} suelto", "{{numero_factura}} {{observaciones}} }}").errors == []


def test_normalizacion_al_guardar(client):
    login(client)
    body = "  {{proveedor}}:\r\n\r\nLa factura {{numero_factura}} fue rechazada:\r\n{{observaciones}}  \r\n"
    assert save(client, REJECTED, subject="  Factura {{numero_factura}}  ", body=body).status_code == 303
    template = stored(REJECTED)
    assert template.subject == "Factura {{numero_factura}}"
    assert template.body == "{{proveedor}}:\n\nLa factura {{numero_factura}} fue rechazada:\n{{observaciones}}"


# --- Vista previa ------------------------------------------------------------------------------------------------


def test_vista_previa_del_texto_predeterminado(client):
    login(client)
    response = preview(client, AUTHORIZED)
    assert response.status_code == 200
    assert "<dt>Asunto</dt><dd>Factura A-1024 autorizada para pago</dd>" in response.text
    assert (
        "La factura número A-1024 del proveedor Servicios Digitales del Norte SA de CV por el monto $116,000.00 MXN "
        "ha sido Autorizada para su pago."
    ) in preview_block(response.text)


def test_la_vista_previa_no_guarda(client):
    login(client)
    before = audit_count()
    response = preview(client, REJECTED, body="Nuevo texto {{numero_factura}}: {{observaciones}}")
    assert response.status_code == 200
    assert preview_block(response.text) == f"Nuevo texto A-1024: {VALUES['observaciones']}"
    assert "Nuevo texto {{numero_factura}}" not in client.get(f"{URL}/{REJECTED}").text
    assert (stored(REJECTED).body, stored(REJECTED).version) == (default_body(REJECTED), 1)
    assert audit_count() == before


def test_vista_previa_escapada(client):
    login(client)
    response = preview(client, REJECTED, body="<b>Urgente</b> {{numero_factura}} {{observaciones}}")
    assert response.status_code == 200
    assert "&lt;b&gt;Urgente&lt;/b&gt;" in preview_block(response.text)
    assert "<b>Urgente</b>" not in response.text
    email = preview_email(response.text)
    assert "&lt;b&gt;Urgente&lt;/b&gt;" in email and "<b>" not in email


def test_vista_previa_como_el_correo(client):
    login(client)
    response = preview(client, CREDENTIALS)
    assert response.status_code == 200
    assert '<iframe class="email-preview" title="Vista previa del correo" sandbox="allow-same-origin"' in response.text
    email = preview_email(response.text)
    body = html.unescape(preview_block(response.text))
    assert email == mail_layout.render_preview("Acceso al Portal de Proveedores ULTRASIST", body)
    assert f'src="{mail_layout.logo_data_uri()}"' in email
    assert ">Contraseña temporal</div>" in email and ">Ejemplo#Temporal2026</div>" in email
    # La pagina admite exactamente los atributos style del correo; la CSP del resto no cambia.
    policy = response.headers["content-security-policy"]
    assert policy == content_security_policy_with_styles(mail_layout.style_hashes(email))
    assert policy.startswith(f"{CONTENT_SECURITY_POLICY}; style-src 'self' 'unsafe-hashes' 'sha256-")
    assert "'unsafe-inline'" not in policy
    assert client.get(f"{URL}/{CREDENTIALS}").headers["content-security-policy"] == CONTENT_SECURITY_POLICY


def test_hashes_de_los_estilos_del_correo():
    document = '<p style="color:red">a</p><p style="color:red">b</p><td style="font:12px &#39;A&#39;">c</td>'
    # sha256 en base64 de "color:red" y de "font:12px 'A'" (el valor ya sin entidades)
    assert mail_layout.style_hashes(document) == [
        "'sha256-8f935d27GvUutRyY9yWScUMiFUk4WTdZURISiYfPOeQ='",
        "'sha256-HBlOXrEvV5o1r9ZLA3tWTkYU+SgPh66oZrPcfpTz7Eg='",
    ]
    assert mail_layout.style_hashes("<p>sin estilos</p>") == []


def test_vista_previa_de_un_borrador_invalido(client):
    login(client)
    response = preview(client, REJECTED, body="Sin la causa {{numero_factura}}")
    assert response.status_code == 400
    assert "Cuerpo: debe incluir la variable obligatoria {{observaciones}}" in response.text
    assert preview_block(response.text) is None


# --- Guardado ----------------------------------------------------------------------------------------------------


def test_guardado_exitoso(client):
    login(client)
    response = save(client, REJECTED, subject="Su factura {{numero_factura}} fue rechazada", version=1)
    assert response.status_code == 303
    assert response.headers["location"] == f"{URL}?updated=INVOICE_REJECTED"
    template = stored(REJECTED)
    assert template.version == 2
    listing = client.get(response.headers["location"]).text
    assert "Plantilla actualizada: Rechazada." in listing
    row = re.search(r"<td><strong>Rechazada</strong></td>.*?</tr>", listing, re.DOTALL).group(0)
    assert "Su factura {{numero_factura}} fue rechazada" in row
    assert f"{nt.format_datetime(template.updated_at)}<small>{admin_name()}</small>" in row


def test_aviso_solo_para_un_evento_del_catalogo(client):
    login(client)
    assert "Plantilla actualizada" not in client.get(URL, params={"updated": "<script>"}).text


def test_edicion_concurrente(client):
    login(client)
    second = form_data(client, REJECTED, subject="Segundo {{numero_factura}}")  # abrio el formulario en la version 1
    assert save(client, REJECTED, subject="Primero {{numero_factura}}", version=1).status_code == 303
    before = audit_count()
    response = client.post(f"{URL}/{REJECTED}", data=second, follow_redirects=False)
    assert response.status_code == 409
    assert (
        "Otro administrador modificó esta plantilla mientras usted la editaba. Revise la versión vigente y vuelva a "
        "aplicar sus cambios."
    ) in response.text
    assert 'value="Segundo {{numero_factura}}"' in response.text, "el formulario conserva el texto capturado"
    assert (stored(REJECTED).subject, stored(REJECTED).version) == ("Primero {{numero_factura}}", 2)
    assert audit_count() == before


def test_edicion_concurrente_entre_la_lectura_y_la_escritura():
    """El UPDATE va condicionado a la version: si otro guardado ocurre despues de leer la plantilla, no afecta filas."""
    spec = nt.EVENTS[REJECTED]
    with SessionLocal() as db:
        admin = db.scalar(select(User).where(User.email == "admin@poc.local"))
        # La referencia mantiene la plantilla en el mapa de identidad (debil) de la sesion: la lectura de
        # save_template la ve en la version 1 y la version se detecta en el UPDATE condicionado.
        loaded = nt.get_template(db, spec)
        assert loaded.version == 1
        set_template(REJECTED, subject="De otra sesion {{numero_factura}}", version=2)
        with pytest.raises(nt.ConcurrentEditError):
            nt.save_template(db, spec, "Mio {{numero_factura}}", default_body(REJECTED), 1, admin)
    assert (stored(REJECTED).subject, stored(REJECTED).version) == ("De otra sesion {{numero_factura}}", 2)


def test_guardado_sin_cambios(client):
    login(client)
    before = audit_count()
    current = stored(REJECTED)
    body = " " + current.body.replace("\n", "\r\n") + "\r\n"  # mismo texto una vez normalizado
    response = save(client, REJECTED, body=body)
    assert response.status_code == 303
    assert stored(REJECTED).version == 1
    assert stored(REJECTED).updated_by is None
    assert audit_count() == before


def test_version_ausente_es_edicion_concurrente(client):
    login(client)
    data = form_data(client, REJECTED, subject="Otro {{numero_factura}}")
    del data["version"]
    assert client.post(f"{URL}/{REJECTED}", data=data).status_code == 409


def test_cargar_y_guardar_el_texto_predeterminado(client):
    login(client)
    modified = "{{numero_factura}} rechazada: {{observaciones}}"
    set_template(REJECTED, body=modified, version=3)
    html = client.get(f"{URL}/{REJECTED}", params={"default": 1}).text
    assert "Se cargó el texto predeterminado. Pulse Guardar para aplicarlo." in html
    assert 'name="version" value="3"' in html
    assert "ha sido “Rechazada” por la siguiente causa:" in html
    assert (stored(REJECTED).body, stored(REJECTED).version) == (modified, 3)
    assert save(client, REJECTED, body=default_body(REJECTED), version=3).status_code == 303
    assert (stored(REJECTED).body, stored(REJECTED).version) == (default_body(REJECTED), 4)


# --- Textos predeterminados y composicion ------------------------------------------------------------------------


def test_textos_predeterminados_validos():
    for spec in nt.EVENTS.values():
        assert nt.check_draft(spec, spec.default_subject, spec.default_body).errors == [], spec.event


def test_textos_predeterminados_conforme_a_las_reglas_de_negocio():
    subjects = {event: spec.default_subject for event, spec in nt.EVENTS.items()}
    assert subjects == {
        AUTHORIZED: "Factura {{numero_factura}} autorizada para pago",
        REJECTED: "Factura {{numero_factura}} rechazada",
        OBSERVATIONS: "Factura {{numero_factura}} con observaciones",
        CANCELLED: "Cancelación de la factura {{numero_factura}} de {{proveedor}}",
        PAID: "Factura {{numero_factura}} pagada",
        COMPLEMENT: "Complemento de pago de la factura {{numero_factura}}",
        CREDENTIALS: "Acceso al Portal de Proveedores ULTRASIST",
    }
    assert "Su factura número {{numero_factura}} ha sido pagada.\n\n{{aviso_complemento}}\n\n" in default_body(PAID)
    assert (
        "El Complemento de Pago ha sido adjuntado a la factura {{numero_factura}} del proveedor {{proveedor}}."
        in default_body(COMPLEMENT)
    )
    for line in ("Portal: {{url_portal}}", "Usuario: {{usuario}}", "Contraseña temporal: {{contrasena_temporal}}"):
        assert f"\n{line}\n" in default_body(CREDENTIALS), line
    assert (
        "La factura número {{numero_factura}} del proveedor {{proveedor}} por el monto {{monto}} ha sido Autorizada "
        "para su pago."
    ) in default_body(AUTHORIZED)
    assert (
        "La factura número {{numero_factura}} ha sido “Rechazada” por la siguiente causa:\n\n{{observaciones}}"
        in default_body(REJECTED)
    )
    assert (
        "La factura número {{numero_factura}} tiene “Observaciones” por la siguiente causa:\n\n{{observaciones}}"
        in default_body(OBSERVATIONS)
    )


def test_texto_predeterminado_de_cancelada():
    email = compose(CANCELLED)
    assert (
        "La factura número A-1024 del proveedor Servicios Digitales del Norte SA de CV ha sido cancelada. Por favor "
        "acepte la “Cancelación” antes del 28/09/2026 10:30."
    ) in email.body
    assert email.subject == "Cancelación de la factura A-1024 de Servicios Digitales del Norte SA de CV"


def test_composicion_con_la_plantilla_vigente(client):
    login(client)
    assert save(client, REJECTED, subject="Su factura {{numero_factura}} fue rechazada").status_code == 303
    assert compose(REJECTED).subject == "Su factura A-1024 fue rechazada"


def test_formato_de_montos_y_fechas():
    body = compose(CANCELLED).body
    assert "antes del 28/09/2026 10:30" in body
    assert "Monto: $116,000.00 MXN" in body
    assert "Fecha de la solicitud: 25/09/2026 10:30" in body


def test_estatus_toma_el_nombre_del_evento():
    set_template(AUTHORIZED, subject="{{estatus}}: {{numero_factura}}")
    assert compose(AUTHORIZED).subject == "Autorizada: A-1024"


def test_valor_con_llaves():
    body = compose(OBSERVATIONS, observaciones="Corrija el campo {{monto}}").body
    assert "Corrija el campo {{monto}}" in body


def test_asunto_en_una_sola_linea():
    set_template(OBSERVATIONS, subject="Observaciones: {{observaciones}}")
    assert compose(OBSERVATIONS, observaciones="Línea 1\nLínea 2").subject == "Observaciones: Línea 1 Línea 2"
    assert len(compose(OBSERVATIONS, observaciones="x" * 300).subject) == 255


@pytest.mark.parametrize("value", ["", "   "])
def test_variable_obligatoria_vacia(value):
    with pytest.raises(nt.NotificationDataError, match="observaciones"):
        compose(REJECTED, observaciones=value)


@pytest.mark.parametrize(
    ("event", "missing", "variable"),
    [
        (REJECTED, "observaciones", "observaciones"),
        (CANCELLED, "fecha_limite_cancelacion", "fecha_limite_cancelacion"),
        (AUTHORIZED, "moneda", "monto"),
        (AUTHORIZED, "folio_interno", "folio_interno"),
    ],
)
def test_variable_sin_valor(event, missing, variable):
    with pytest.raises(nt.NotificationDataError, match=variable):
        compose(event, **{missing: None})


def test_variables_que_el_evento_no_admite_se_ignoran():
    assert "A-1024" in compose(AUTHORIZED, observaciones="", fecha_limite_cancelacion=None).body


def test_plantilla_guardada_invalida():
    with SessionLocal() as db:
        db.execute(text("UPDATE notification_templates SET body = 'Sin variables' WHERE event = 'INVOICE_REJECTED'"))
        db.commit()
    email = compose(REJECTED)
    assert email.body.startswith(f"{SUPPLIER_NAME}:\n\nLa factura número A-1024 ha sido “Rechazada”")
    assert email.subject == "Factura A-1024 rechazada"


def test_plantilla_ausente():
    with SessionLocal() as db:
        db.execute(delete(NotificationTemplate).where(NotificationTemplate.event == REJECTED))
        email = nt.compose(db, REJECTED, **VALUES)
        db.rollback()
    assert email.subject == "Factura A-1024 rechazada"
    assert stored(REJECTED) is not None


def test_plantilla_ausente_en_la_interfaz(client):
    """Una plantilla borrada por SQL no rompe el listado y su edicion responde 404."""
    login(client)
    with SessionLocal() as db:
        original = db.scalar(select(NotificationTemplate).where(NotificationTemplate.event == REJECTED))
        values = {"event": original.event, "subject": original.subject, "body": original.body, "version": 1}
        db.execute(delete(NotificationTemplate).where(NotificationTemplate.event == REJECTED))
        db.commit()
    try:
        assert "<strong>Rechazada</strong>" not in client.get(URL).text
        assert client.get(f"{URL}/{REJECTED}").status_code == 404
    finally:
        with SessionLocal() as db:
            db.add(NotificationTemplate(**values))
            db.commit()


# --- Auditoria ---------------------------------------------------------------------------------------------------


def test_auditoria_de_un_cambio(client):
    login(client)
    assert save(client, REJECTED, subject="Su factura {{numero_factura}} fue rechazada").status_code == 303
    with SessionLocal() as db:
        entry = db.scalar(select(AuditLog).order_by(AuditLog.id.desc()).limit(1))
        admin_id = db.scalar(select(User.id).where(User.email == "admin@poc.local"))
    assert (entry.action, entry.entity, entry.entity_id, entry.user_id) == (
        "NOTIFICATION_TEMPLATE_UPDATED",
        "NotificationTemplate",
        "INVOICE_REJECTED",
        admin_id,
    )
    spec = nt.EVENTS[REJECTED]
    assert entry.old_value == {"subject": spec.default_subject, "body": spec.default_body, "version": 1}
    assert entry.new_value == {
        "subject": "Su factura {{numero_factura}} fue rechazada",
        "body": spec.default_body,
        "version": 2,
    }


def test_acciones_sin_auditoria(client):
    login(client)
    stale = form_data(client, REJECTED, subject="Tarde {{numero_factura}}")
    assert save(client, REJECTED, subject="Primero {{numero_factura}}").status_code == 303
    before = audit_count()
    assert preview(client, REJECTED).status_code == 200
    assert client.get(f"{URL}/{REJECTED}", params={"default": 1}).status_code == 200
    assert save(client, REJECTED, body="Sin variables").status_code == 400
    assert client.post(f"{URL}/{REJECTED}", data=stale, follow_redirects=False).status_code == 409
    assert audit_count() == before


# --- Plantilla de credenciales de acceso (HU-03) -------------------------------------------------------------------

CREDENTIAL_VALUES = {
    "proveedor": SUPPLIER_NAME,
    "usuario": "contacto@serviciosdelnorte.mx",
    "contrasena_temporal": "Clave#Temporal#Real1",
    "url_portal": "https://portal.ultrasist.local/login",
}


def test_variables_de_la_plantilla_de_credenciales(client):
    login(client)
    html = client.get(f"{URL}/{CREDENTIALS}").text
    assert "Destinatario: Proveedor (correo del catálogo)" in html
    rows = re.findall(r'<span class="mono">\{\{(\w+)\}\}</span>(<small>Obligatoria</small>)?', html)
    assert rows == [
        ("proveedor", ""),
        ("usuario", "<small>Obligatoria</small>"),
        ("contrasena_temporal", "<small>Obligatoria</small>"),
        ("url_portal", "<small>Obligatoria</small>"),
    ]


def test_credenciales_sin_variable_obligatoria_o_ajena(client):
    login(client)
    body = default_body(CREDENTIALS)
    missing = save(client, CREDENTIALS, body=body.replace("{{contrasena_temporal}}", "********"))
    assert missing.status_code == 400
    assert "Cuerpo: debe incluir la variable obligatoria {{contrasena_temporal}}" in missing.text
    foreign = save(client, CREDENTIALS, body=body + "\n{{numero_factura}}")
    assert foreign.status_code == 400
    assert "Cuerpo: la variable {{numero_factura}} no existe en esta plantilla" in foreign.text
    assert stored(CREDENTIALS).version == 1


def test_vista_previa_de_las_credenciales(client):
    login(client)
    response = preview(client, CREDENTIALS)
    assert response.status_code == 200
    block = preview_block(response.text)
    assert "Usuario: contacto@serviciosdelnorte.mx" in block
    assert "Contraseña temporal: Ejemplo#Temporal2026" in block
    assert "Portal: https://proveedores.ultrasist.com.mx/login" in block


def test_composicion_de_las_credenciales():
    with SessionLocal() as db:
        email = nt.compose(db, CREDENTIALS, **CREDENTIAL_VALUES)
        assert email.subject == "Acceso al Portal de Proveedores ULTRASIST"
        assert email.body.startswith(f"{SUPPLIER_NAME}:\n\n")
        for line in (
            "Portal: https://portal.ultrasist.local/login",
            "Usuario: contacto@serviciosdelnorte.mx",
            "Contraseña temporal: Clave#Temporal#Real1",
        ):
            assert line in email.body
        with pytest.raises(nt.NotificationDataError, match="contrasena_temporal"):
            nt.compose(db, CREDENTIALS, **{**CREDENTIAL_VALUES, "contrasena_temporal": " "})


# --- Pagada y Complemento de pago adjuntado (HU Complemento de Pagos) --------------------------------------------


def test_variables_de_la_plantilla_pagada(client):
    login(client)
    html = client.get(f"{URL}/{PAID}").text
    rows = re.findall(r'<span class="mono">\{\{(\w+)\}\}</span>(<small>Obligatoria</small>)?', html)
    assert [name for name, _ in rows] == [
        "numero_factura",
        "folio_interno",
        "proveedor",
        "monto",
        "estatus",
        "fecha_estatus",
        "aviso_complemento",
    ]
    assert {name for name, required in rows if required} == {"numero_factura", "aviso_complemento"}
    assert "PPD" in html


def test_aviso_del_complemento_obligatorio_en_el_cuerpo(client):
    login(client)
    body = default_body(PAID).replace("{{aviso_complemento}}", "")
    response = save(client, PAID, body=body)
    assert response.status_code == 400
    assert "Cuerpo: debe incluir la variable obligatoria {{aviso_complemento}}" in response.text
    assert stored(PAID).version == 1


def test_vista_previa_de_pagada(client):
    login(client)
    response = preview(client, PAID)
    assert response.status_code == 200
    block = html.unescape(preview_block(response.text))
    assert "Factura A-1024 pagada" in response.text
    assert "Su factura número A-1024 ha sido pagada." in block
    notice = "Es importante que adjunte su “Complemento de Pago” a dicha factura pagada antes del 28/09/2026 10:30."
    assert notice in block


def test_aviso_del_complemento_vacio():
    email = compose(PAID, aviso_complemento="")
    assert email.subject == "Factura A-1024 pagada"
    assert "Su factura número A-1024 ha sido pagada.\n\nFolio interno: FAC-2026-00042" in email.body
    assert "Complemento de Pago" not in email.body
    assert "\n\n\n" not in email.body


def test_aviso_del_complemento_con_valor():
    email = compose(PAID)
    assert "ha sido pagada.\n\nEs importante que adjunte su “Complemento de Pago”" in email.body


def test_aviso_del_complemento_ausente_falla():
    with pytest.raises(nt.NotificationDataError, match="aviso_complemento"):
        compose(PAID, aviso_complemento=None)


def test_otras_variables_obligatorias_siguen_sin_admitir_vacio():
    with pytest.raises(nt.NotificationDataError, match="numero_factura"):
        compose(PAID, numero_factura=" ")


def test_texto_predeterminado_de_complemento_adjuntado():
    email = compose(COMPLEMENT)
    assert email.subject == "Complemento de pago de la factura A-1024"
    assert (
        "El Complemento de Pago ha sido adjuntado a la factura A-1024 del proveedor Servicios Digitales del Norte SA "
        "de CV."
    ) in email.body
