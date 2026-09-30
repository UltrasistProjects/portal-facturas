"""Autorizacion masiva de proveedores y credenciales de acceso (HU-02 y HU-03, spec acceso-proveedores), con las
cuentas en el Keycloak simulado (add-keycloak-authentication)."""

import json
import re
import socket
from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser

import pytest
from sqlalchemy import delete, func, or_, select, update

from app.core.config import settings
from app.core.constants import DeliveryStatus, NotificationEvent, Role, SupplierStatus
from app.core.database import SessionLocal
from app.core.errors import BusinessRuleError
from app.models import AuditLog, EmailDelivery, Supplier, User
from app.rules.supplier_rules import supplier_rules
from app.services import mail_transport
from app.services import supplier_access_service as access
from app.services.keycloak_admin import UPDATE_PASSWORD
from tests.conftest import OUTBOX, csrf, identity_account, login, supplier_by_email

pytestmark = pytest.mark.usefixtures("restore_notification_recipients")

LOG_FILE = settings.log_dir / "app.log"
CREDENTIALS = NotificationEvent.SUPPLIER_CREDENTIALS
PASSWORD_LINE = re.compile(r"Contraseña temporal: (\S+)")


# --- Datos de prueba ----------------------------------------------------------------------------------------------


def closed_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@pytest.fixture()
def smtp_down(monkeypatch):
    monkeypatch.setattr(settings, "mail_backend", "smtp")
    monkeypatch.setattr(settings, "smtp_host", "127.0.0.1")
    monkeypatch.setattr(settings, "smtp_port", closed_port())
    monkeypatch.setattr(settings, "smtp_timeout", 2)


# --- Utilidades ---------------------------------------------------------------------------------------------------


def authorize(client, ids, token: str | None = None):
    data = {"supplier_ids": [str(i) for i in ids], "csrf_token": token or csrf(client, "/suppliers")}
    return client.post("/suppliers/authorize", data=data, follow_redirects=False)


def resend(client, supplier_id: int):
    token = csrf(client, "/suppliers")
    return client.post(f"/suppliers/{supplier_id}/credentials", data={"csrf_token": token}, follow_redirects=False)


def supplier(supplier_id: int) -> Supplier:
    with SessionLocal() as db:
        return db.get(Supplier, supplier_id)


def portal_user(supplier_id: int) -> User | None:
    with SessionLocal() as db:
        return db.scalar(select(User).where(User.supplier_id == supplier_id))


def deliveries() -> list[EmailDelivery]:
    with SessionLocal() as db:
        return list(db.scalars(select(EmailDelivery).order_by(EmailDelivery.id)))


def messages() -> list:
    files = sorted(OUTBOX.glob("*.eml")) if OUTBOX.exists() else []
    return [BytesParser(policy=policy.default).parsebytes(path.read_bytes()) for path in files]


def password_for(email: str) -> str:
    """Contrasena temporal del ultimo correo de credenciales enviado a `email`."""
    found = [m for m in messages() if m["To"] == email]
    return PASSWORD_LINE.search(found[-1].get_content()).group(1)


def audit_count() -> int:
    with SessionLocal() as db:
        return db.scalar(select(func.count(AuditLog.id)))


def log_offset() -> int:
    return LOG_FILE.stat().st_size if LOG_FILE.exists() else 0


def log_since(offset: int) -> str:
    with LOG_FILE.open(encoding="utf-8") as handle:
        handle.seek(offset)
        return handle.read()


def admin_id() -> int:
    with SessionLocal() as db:
        return db.scalar(select(User.id).where(User.email == "admin@poc.local"))


# --- Estatus y alta individual ------------------------------------------------------------------------------------


def test_etiqueta_autorizado(client):
    login(client)
    page = client.get("/suppliers").text
    assert re.search(r'<span class="status status-supplier-active">Autorizado</span>', page)
    assert ">Activo<" not in page


# --- Acceso -------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("email", ["pmo@poc.local", "proveedor1@poc.local"])
def test_sin_acceso_para_pmo_ni_proveedor(client, registered_suppliers, email):
    [registered] = registered_suppliers()
    login(client, email)
    token = csrf(client, "/")
    responses = [
        client.post("/suppliers/authorize", data={"supplier_ids": [registered.id], "csrf_token": token}),
        client.post(f"/suppliers/{registered.id}/credentials", data={"csrf_token": token}),
    ]
    assert [r.status_code for r in responses] == [403, 403]
    assert supplier(registered.id).status == SupplierStatus.REGISTERED
    assert portal_user(registered.id) is None and deliveries() == []


@pytest.mark.parametrize("token", [None, "token-invalido"])
def test_autorizacion_sin_token_csrf(client, registered_suppliers, token):
    [registered] = registered_suppliers()
    login(client)
    data = {"supplier_ids": [registered.id], **({"csrf_token": token} if token else {})}
    assert client.post("/suppliers/authorize", data=data).status_code == 403
    assert supplier(registered.id).status == SupplierStatus.REGISTERED


def test_casillas_solo_para_admin_y_registrados(client, registered_suppliers):
    [registered] = registered_suppliers()
    active = supplier_by_email("proveedor1@poc.local")
    login(client)
    page = client.get("/suppliers").text
    assert f'name="supplier_ids" value="{registered.id}"' in page
    assert f'name="supplier_ids" value="{active.id}"' not in page
    assert 'id="authorize-submit"' in page and "supplier_authorize.js" in page
    client.post("/logout", data={"csrf_token": csrf(client, "/")})
    login(client, "pmo@poc.local")
    page = client.get("/suppliers").text
    assert 'name="supplier_ids"' not in page and 'id="authorize-form"' not in page
    assert "supplier_authorize.js" not in page


def test_filtro_por_estatus(client, registered_suppliers):
    [registered] = registered_suppliers()
    login(client)
    page = client.get("/suppliers?status=REGISTERED").text
    assert registered.business_name in page and "Tecnologia Integral del Centro" not in page
    assert '<option value="REGISTERED" selected>' in page
    unknown = client.get("/suppliers?status=PENDIENTE").text
    assert registered.business_name in unknown and "Tecnologia Integral del Centro" in unknown


# --- Reglas de la autorizacion ------------------------------------------------------------------------------------


def test_autorizacion_de_proveedores_registrados(client, registered_suppliers):
    rows = registered_suppliers(3)
    login(client)
    response = authorize(client, [s.id for s in rows])
    assert response.status_code == 303 and response.headers["location"].startswith("/suppliers?authorization=")
    for row in rows:
        authorized = supplier(row.id)
        assert authorized.status == SupplierStatus.ACTIVE
        sup001 = supplier_rules(authorized, None, [])[0]
        assert (sup001.rule_code, sup001.status) == ("SUP-001", "PASS")
    assert len(messages()) == 3


def test_proveedor_ya_autorizado_se_omite(client, registered_suppliers):
    [registered] = registered_suppliers()
    active = supplier_by_email("proveedor1@poc.local")
    login(client)
    response = authorize(client, [registered.id, active.id])
    assert supplier(registered.id).status == SupplierStatus.ACTIVE
    assert supplier(active.id).status == SupplierStatus.ACTIVE
    assert [m["To"] for m in messages()] == [registered.email]
    page = client.get(response.headers["location"]).text
    assert "Omitido: no estaba en Registrado" in page and active.business_name in page


def test_correo_usado_por_otro_usuario(client, registered_suppliers):
    [registered] = registered_suppliers()
    with SessionLocal() as db:
        db.add(User(name="Interno", email=registered.email, password_hash="x", role=Role.PMO, is_active=True))
        db.commit()
    try:
        login(client)
        response = authorize(client, [registered.id])
        assert supplier(registered.id).status == SupplierStatus.REGISTERED
        assert portal_user(registered.id) is None and deliveries() == []
        page = client.get(response.headers["location"]).text
        assert "No autorizado: el correo lo usa otro usuario" in page
    finally:
        with SessionLocal() as db:
            db.execute(delete(User).where(User.email == registered.email))
            db.commit()


@pytest.mark.parametrize(
    ("ids", "status", "message"),
    [
        ([], 400, "Seleccione al menos un proveedor."),
        (list(range(1, 102)), 400, "Autorice hasta 100 proveedores por operación."),
        (["abc"], 400, "La selección de proveedores no es válida."),
    ],
)
def test_seleccion_invalida(client, ids, status, message):
    login(client)
    before = audit_count()
    response = authorize(client, ids)
    assert response.status_code == status and message in response.text
    assert audit_count() == before


def test_proveedor_inexistente_no_autoriza_a_nadie(client, registered_suppliers):
    [registered] = registered_suppliers()
    login(client)
    response = authorize(client, [registered.id, 99_999_999])
    assert response.status_code == 404
    assert "Alguno de los proveedores seleccionados no existe." in response.text
    assert supplier(registered.id).status == SupplierStatus.REGISTERED


def test_fallo_parcial_al_aprovisionar(client, registered_suppliers, keycloak):
    first, rejected, third = registered_suppliers(3)
    keycloak.rejected_emails.add(rejected.email)
    login(client)
    response = authorize(client, [first.id, rejected.id, third.id])
    assert [supplier(row.id).status for row in (first, rejected, third)] == [
        SupplierStatus.ACTIVE,
        SupplierStatus.REGISTERED,
        SupplierStatus.ACTIVE,
    ]
    assert portal_user(rejected.id) is None and portal_user(first.id).keycloak_sub
    assert sorted(m["To"] for m in messages()) == sorted([first.email, third.email])
    with SessionLocal() as db:
        failed = db.scalar(
            select(AuditLog).where(
                AuditLog.action == access.PROVISIONING_FAILED, AuditLog.entity_id == str(rejected.id)
            )
        )
        other = db.scalars(select(AuditLog.action).where(AuditLog.entity_id == str(rejected.id))).all()
    assert failed.new_value == {"operation": "create_user", "error": "http_400"} and failed.user_id == admin_id()
    assert "SUPPLIER_STATUS_CHANGED" not in other
    page = client.get(response.headers["location"]).text
    assert "2 autorizados · 0 omitidos · 1 no autorizados" in page
    row = re.search(rf"{re.escape(rejected.business_name)}.*?</tr>", page, re.DOTALL).group(0)
    assert "No autorizado: el servicio de identidad no pudo crear su cuenta" in row


def test_keycloak_caido_no_autoriza_a_nadie(client, registered_suppliers, keycloak):
    rows = registered_suppliers(2)
    login(client)
    keycloak.unavailable = True
    response = authorize(client, [s.id for s in rows])
    assert response.status_code == 303
    for row in rows:
        assert supplier(row.id).status == SupplierStatus.REGISTERED and portal_user(row.id) is None
    assert deliveries() == [] and messages() == []
    assert "0 autorizados · 0 omitidos · 2 no autorizados" in client.get(response.headers["location"]).text


# --- Usuario y contrasena temporal ---------------------------------------------------------------------------------


def test_usuario_creado_al_autorizar(client, registered_suppliers, keycloak):
    [registered] = registered_suppliers(email="Contacto.Mixto@Acceso-Proveedor.mx")
    login(client)
    authorize(client, [registered.id])
    user = portal_user(registered.id)
    assert (user.email, user.role, user.is_active) == ("contacto.mixto@acceso-proveedor.mx", Role.PROVEEDOR, True)
    assert user.name == registered.business_name and user.last_login_at is None
    # RN-HU03-01: sin contrasena ni hash en el portal; la credencial vive en Keycloak, enlazada por sub.
    assert user.password_hash is None and user.keycloak_sub
    account = keycloak.account(user.email)
    assert (account.id, account.enabled, account.roles) == (user.keycloak_sub, True, {"Proveedor"})
    password = password_for(user.email)
    assert len(password) == 20 and account.password == password
    assert account.required_actions == [UPDATE_PASSWORD]  # Keycloak exige cambiarla en el primer acceso


def test_primer_acceso_del_proveedor_autorizado(client, registered_suppliers, keycloak):
    [registered] = registered_suppliers()
    login(client)
    authorize(client, [registered.id])
    # Keycloak pide la contrasena nueva antes de volver al portal; el callback enlaza la cuenta por su sub.
    response = login(client, registered.email)
    assert response.status_code == 303 and response.headers["location"] == "/"
    assert "Proveedor" in client.get("/").text and portal_user(registered.id).last_login_at is not None


def test_contrasena_temporal_fuera_de_registros(client, registered_suppliers):
    [registered] = registered_suppliers()
    login(client)
    offset = log_offset()
    authorize(client, [registered.id])
    password = password_for(registered.email)
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.supplier_id == registered.id))
        user_columns = [str(getattr(user, column.key)) for column in User.__table__.columns]
        audits = json.dumps(
            [[a.old_value, a.new_value] for a in db.scalars(select(AuditLog))], ensure_ascii=False, default=str
        )
        stored = [
            str(getattr(d, column.key))
            for d in db.scalars(select(EmailDelivery))
            for column in EmailDelivery.__table__.columns
        ]
    assert all(password not in value for value in user_columns) and user.password_hash is None
    assert password not in audits
    assert all(password not in value for value in stored)
    assert password not in log_since(offset)


def test_proveedor_con_usuario_propio(client, registered_suppliers, keycloak):
    [registered] = registered_suppliers()
    sub = identity_account(registered.email, Role.PROVEEDOR)
    keycloak.change_password(registered.email, "Propia#Clave2026")
    with SessionLocal() as db:
        db.add(
            User(
                name="Usuario previo",
                email=registered.email,
                keycloak_sub=sub,
                role=Role.PROVEEDOR,
                supplier_id=registered.id,
                is_active=True,
            )
        )
        db.commit()
    login(client)
    response = authorize(client, [registered.id])
    assert supplier(registered.id).status == SupplierStatus.ACTIVE
    with SessionLocal() as db:
        users = list(db.scalars(select(User).where(User.supplier_id == registered.id)))
    assert len(users) == 1 and users[0].keycloak_sub == sub
    assert keycloak.account(registered.email).password == "Propia#Clave2026"  # su contrasena no cambia
    assert deliveries() == []
    assert "Autorizado · Ya tenía usuario" in client.get(response.headers["location"]).text


def test_proveedor_ya_existente_en_keycloak(client, registered_suppliers, keycloak):
    [registered] = registered_suppliers()
    existing = keycloak.add_account(registered.email, enabled=False)
    login(client)
    authorize(client, [registered.id])
    user = portal_user(registered.id)
    assert user.keycloak_sub == existing.id  # se enlaza, no se duplica
    assert sum(account.email == registered.email for account in keycloak.accounts.values()) == 1
    assert existing.enabled and existing.roles == {"Proveedor"}
    assert existing.password == password_for(registered.email) and existing.required_actions == [UPDATE_PASSWORD]
    with SessionLocal() as db:
        created = db.scalar(
            select(AuditLog).where(AuditLog.action == "USER_CREATED", AuditLog.entity_id == str(user.id))
        )
    assert created.new_value["idp_account"] == "linked"


def test_correo_de_un_usuario_interno_en_keycloak(client, registered_suppliers, keycloak):
    [registered] = registered_suppliers()
    internal = keycloak.add_account(registered.email, "PMO")
    login(client)
    response = authorize(client, [registered.id])
    assert supplier(registered.id).status == SupplierStatus.REGISTERED and portal_user(registered.id) is None
    assert internal.roles == {"PMO"} and internal.password is None and deliveries() == []
    assert "No autorizado: el correo lo usa otro usuario" in client.get(response.headers["location"]).text


# --- Correo de credenciales ---------------------------------------------------------------------------------------


def test_credenciales_enviadas(client, registered_suppliers):
    [registered] = registered_suppliers()
    login(client)
    authorize(client, [registered.id])
    [message] = messages()
    assert message["To"] == registered.email and message["Cc"] is None
    assert message["Subject"] == "Acceso al Portal de Proveedores ULTRASIST"
    body = message.get_content()
    assert f"Usuario: {registered.email}" in body and "Portal: http://testserver/login" in body
    assert PASSWORD_LINE.search(body)
    [delivery] = deliveries()
    assert (delivery.event, delivery.entity, delivery.entity_id) == (CREDENTIALS, "Supplier", str(registered.id))
    assert (delivery.status, delivery.requested_by) == (DeliveryStatus.SENT, admin_id())


def test_servidor_de_correo_caido_conserva_la_autorizacion(client, registered_suppliers, smtp_down):
    [registered] = registered_suppliers()
    login(client)
    response = authorize(client, [registered.id])
    assert supplier(registered.id).status == SupplierStatus.ACTIVE and portal_user(registered.id) is not None
    [delivery] = deliveries()
    assert delivery.status == DeliveryStatus.FAILED and delivery.error.startswith("ConnectionRefusedError")
    summary = client.get(response.headers["location"]).text
    assert "Autorizado · Envío fallido" in summary and "ConnectionRefusedError" in summary
    listing = client.get("/suppliers").text
    row = re.search(rf"{re.escape(registered.business_name)}.*?</tr>", listing, re.DOTALL).group(0)
    assert "Credenciales no enviadas" in row


# --- Resumen ------------------------------------------------------------------------------------------------------


def test_resumen_con_un_envio_fallido(client, registered_suppliers, monkeypatch):
    ok, broken = registered_suppliers(2)
    original = mail_transport.FileTransport.send

    def send(self, message):
        if message["To"] == broken.email:
            raise OSError("Buzón del proveedor lleno")
        original(self, message)

    monkeypatch.setattr(mail_transport.FileTransport, "send", send)
    login(client)
    response = authorize(client, [ok.id, broken.id])
    page = client.get(response.headers["location"]).text
    assert "2 autorizados · 0 omitidos · 0 no autorizados" in page
    ok_row = re.search(rf"{re.escape(ok.business_name)}.*?</tr>", page, re.DOTALL).group(0)
    broken_row = re.search(rf"{re.escape(broken.business_name)}.*?</tr>", page, re.DOTALL).group(0)
    assert "Credenciales enviadas" in ok_row
    assert "Envío fallido" in broken_row and "OSError: Buzón del proveedor lleno" in broken_row


def test_parametro_que_no_es_una_autorizacion(client):
    login(client)
    with SessionLocal() as db:
        other = db.scalar(select(AuditLog.id).where(AuditLog.action != access.BULK_ACTION).limit(1))
    for value in (other, 99_999_999):
        assert "Resultado de la autorización" not in client.get(f"/suppliers?authorization={value}").text


# --- Expediente y reenvio -----------------------------------------------------------------------------------------


def test_expediente_de_un_proveedor_recien_autorizado(client, registered_suppliers):
    [registered] = registered_suppliers()
    login(client)
    authorize(client, [registered.id])
    page = client.get(f"/suppliers/{registered.id}").text
    assert "Acceso al portal" in page and registered.email in page
    assert "<dt>Último acceso</dt><dd>Nunca</dd>" in page
    assert "<dt>Contraseña</dt><dd>Temporal, pendiente de cambio</dd>" in page
    assert "Credenciales enviadas el " in page and "Reenviar credenciales" in page


def test_expediente_despues_del_primer_cambio(client, registered_suppliers, keycloak):
    [registered] = registered_suppliers()
    login(client)
    authorize(client, [registered.id])
    # Primer acceso: Keycloak exige la contrasena nueva y el proveedor entra al portal.
    keycloak.change_password(registered.email, "Portal#2026x")
    login(client, registered.email)
    login(client)
    page = client.get(f"/suppliers/{registered.id}").text
    assert "<dt>Contraseña</dt><dd>Cambiada por el proveedor</dd>" in page
    assert "<dt>Último acceso</dt><dd>Nunca</dd>" not in page and "Reenviar credenciales" not in page


def test_expediente_de_un_proveedor_registrado(client, registered_suppliers):
    [registered] = registered_suppliers()
    login(client)
    page = client.get(f"/suppliers/{registered.id}").text
    assert "Sin usuario del portal" in page and "Sin envío registrado" in page
    assert "El proveedor aún no está autorizado" in page and "Reenviar credenciales" not in page
    client.post("/logout", data={"csrf_token": csrf(client, "/")})
    login(client, "pmo@poc.local")
    assert "Acceso al portal" not in client.get(f"/suppliers/{registered.id}").text


def test_expediente_con_keycloak_caido(client, registered_suppliers, keycloak):
    [registered] = registered_suppliers()
    login(client)
    authorize(client, [registered.id])
    keycloak.unavailable = True
    response = client.get(f"/suppliers/{registered.id}")
    assert response.status_code == 200
    assert "<dt>Contraseña</dt><dd>No disponible</dd>" in response.text and "Reenviar credenciales" not in response.text


def test_reenvio_tras_un_envio_fallido(client, registered_suppliers, keycloak, monkeypatch):
    [registered] = registered_suppliers()
    login(client)
    monkeypatch.setattr(settings, "mail_backend", "smtp")
    monkeypatch.setattr(settings, "smtp_host", "127.0.0.1")
    monkeypatch.setattr(settings, "smtp_port", closed_port())
    authorize(client, [registered.id])
    first_password = keycloak.account(registered.email).password
    monkeypatch.setattr(settings, "mail_backend", "file")
    response = resend(client, registered.id)
    delivery = deliveries()[-1]
    assert response.headers["location"] == f"/suppliers/{registered.id}?credentials={delivery.id}"
    page = client.get(response.headers["location"]).text
    assert f"Credenciales enviadas a {registered.email}" in page
    new_password = password_for(registered.email)
    # Keycloak solo acepta la nueva: la temporal anterior deja de funcionar.
    assert keycloak.account(registered.email).password == new_password != first_password


def test_reenvio_a_quien_entro_sin_cambiar_la_contrasena(client, registered_suppliers, keycloak):
    [registered] = registered_suppliers()
    login(client)
    authorize(client, [registered.id])
    first_password = keycloak.account(registered.email).password
    # Entro con la temporal pero no la cambio: aun puede recibir credenciales nuevas.
    _set_user(registered.id, last_login_at=datetime.now(timezone.utc))
    assert "Reenviar credenciales</button>" in client.get(f"/suppliers/{registered.id}").text
    response = resend(client, registered.id)
    assert response.status_code == 303
    account = keycloak.account(registered.email)
    assert account.password != first_password and account.required_actions == [UPDATE_PASSWORD]


def test_reenvio_con_keycloak_caido(client, registered_suppliers, keycloak):
    [registered] = registered_suppliers()
    login(client)
    authorize(client, [registered.id])
    password = keycloak.account(registered.email).password
    before_deliveries, before_audit = len(deliveries()), audit_count()
    keycloak.unavailable = True
    response = resend(client, registered.id)
    assert response.status_code == 503
    assert "El servicio de identidad no está disponible. Intente más tarde." in response.text
    assert len(deliveries()) == before_deliveries and audit_count() == before_audit
    assert keycloak.account(registered.email).password == password


def test_reenvio_a_un_usuario_sin_enlazar(client, registered_suppliers):
    [target] = registered_suppliers(status=SupplierStatus.ACTIVE)
    with SessionLocal() as db:
        db.add(User(name="Previo", email=target.email, role=Role.PROVEEDOR, supplier_id=target.id, is_active=True))
        db.commit()
    login(client)
    response = resend(client, target.id)
    assert response.status_code == 409 and access.MSG_NOT_LINKED in response.text


def _set_user(supplier_id: int, **values) -> None:
    with SessionLocal() as db:
        db.execute(update(User).where(User.supplier_id == supplier_id).values(**values))
        db.commit()


@pytest.mark.parametrize(
    ("setup", "message"),
    [
        ("registered", "Sólo se reenvían credenciales a proveedores autorizados."),
        ("without_user", "El proveedor no tiene usuario del portal."),
        ("disabled", "El usuario del proveedor está deshabilitado."),
        ("password_changed", "El proveedor ya cambió su contraseña temporal; no se generan credenciales nuevas."),
    ],
)
def test_condiciones_del_reenvio(client, registered_suppliers, keycloak, setup, message):
    [target] = registered_suppliers(
        status=SupplierStatus.ACTIVE if setup == "without_user" else SupplierStatus.REGISTERED
    )
    login(client)
    if setup == "disabled":
        authorize(client, [target.id])
        _set_user(target.id, is_active=False)
    elif setup == "password_changed":
        authorize(client, [target.id])
        keycloak.change_password(target.email, "Portal#2026x")
        _set_user(target.id, last_login_at=datetime.now(timezone.utc))

    def password() -> str | None:
        return keycloak.account(target.email).password if portal_user(target.id) else None

    before_password, before_deliveries, before_audit = password(), len(deliveries()), audit_count()
    response = resend(client, target.id)
    assert response.status_code == 409 and message in response.text
    assert password() == before_password
    assert len(deliveries()) == before_deliveries and audit_count() == before_audit
    assert "Reenviar credenciales</button>" not in client.get(f"/suppliers/{target.id}").text


def test_reenvio_de_un_proveedor_inexistente(client):
    login(client)
    assert resend(client, 99_999_999).status_code == 404


def test_resultado_de_reenvio_de_otro_proveedor(client, registered_suppliers):
    first, second = registered_suppliers(2)
    login(client)
    authorize(client, [first.id, second.id])
    other = next(d for d in deliveries() if d.entity_id == str(second.id))
    page = client.get(f"/suppliers/{first.id}?credentials={other.id}").text
    assert "Credenciales enviadas a" not in page


# --- Auditoria ----------------------------------------------------------------------------------------------------


def test_auditoria_de_la_autorizacion(client, registered_suppliers):
    [registered] = registered_suppliers()
    login(client)
    response = authorize(client, [registered.id])
    audit_id = int(response.headers["location"].rsplit("=", 1)[1])
    user = portal_user(registered.id)
    with SessionLocal() as db:
        entries = {
            a.action: a
            for a in db.scalars(
                select(AuditLog).where(
                    or_(
                        AuditLog.id == audit_id,
                        (AuditLog.entity == "Supplier") & (AuditLog.entity_id == str(registered.id)),
                        (AuditLog.entity == "User") & (AuditLog.entity_id == str(user.id)),
                    )
                )
            )
        }
    status = entries["SUPPLIER_STATUS_CHANGED"]
    assert (status.old_value, status.new_value) == ({"status": "REGISTERED"}, {"status": "ACTIVE"})
    created = entries["USER_CREATED"]
    assert created.new_value == {
        "role": "Proveedor",
        "supplier_id": registered.id,
        "origin": "SUPPLIER_AUTHORIZATION",
        "idp_account": "created",
    }
    bulk = entries["SUPPLIER_BULK_AUTHORIZED"]
    assert bulk.new_value == {
        "authorized": [registered.id],
        "existing_access": [],
        "skipped": [],
        "conflicts": [],
        "provisioning_failed": [],
    }
    assert {e.user_id for e in entries.values()} == {admin_id()}
    password = password_for(registered.email)
    assert password not in json.dumps([e.new_value for e in entries.values()], default=str)


def test_auditoria_del_reenvio(client, registered_suppliers):
    [registered] = registered_suppliers()
    login(client)
    authorize(client, [registered.id])
    resend(client, registered.id)
    with SessionLocal() as db:
        entry = db.scalar(
            select(AuditLog).where(
                AuditLog.action == "SUPPLIER_CREDENTIALS_RESENT", AuditLog.entity_id == str(registered.id)
            )
        )
    assert entry.user_id == admin_id() and entry.new_value == {"user_id": portal_user(registered.id).id}


def test_servicio_rechaza_seleccion_sin_cambios():
    with SessionLocal() as db:
        admin = db.get(User, admin_id())
        with pytest.raises(BusinessRuleError, match="Seleccione al menos un proveedor"):
            access.authorize(db, ["", " "], admin, "http://portal/login")
