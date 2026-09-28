"""Autorizacion masiva de proveedores y credenciales de acceso (HU-02 y HU-03, spec acceso-proveedores)."""

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
from app.core.security import hash_password, verify_password
from app.models import AuditLog, EmailDelivery, Supplier, User
from app.rules.supplier_rules import supplier_rules
from app.services import mail_transport, secret_vault
from app.services import supplier_access_service as access
from tests.conftest import OUTBOX, csrf, login, supplier_by_email

pytestmark = pytest.mark.usefixtures("restore_notification_recipients")

LOG_FILE = settings.log_dir / "app.log"
CREDENTIALS = NotificationEvent.SUPPLIER_CREDENTIALS
PASSWORD_LINE = re.compile(r"Contraseña temporal: (\S+)")


# --- Datos de prueba ----------------------------------------------------------------------------------------------


class RecordingVault:
    """Gestor de secretos de prueba: registra cada resguardo y el estatus que el proveedor tiene en la base de datos
    en ese momento (visto desde otra sesion)."""

    name = "recording"

    def __init__(self, fail_after: int | None = None):
        self.calls: list[dict] = []
        self.fail_after = fail_after

    def store_temporary_password(self, *, supplier_id: int, username: str, password: str) -> None:
        if self.fail_after is not None and len(self.calls) >= self.fail_after:
            raise RuntimeError("Gestor de secretos no disponible")
        with SessionLocal() as other:
            committed = other.scalar(select(Supplier.status).where(Supplier.id == supplier_id))
        self.calls.append({"supplier_id": supplier_id, "username": username, "password": password, "seen": committed})


@pytest.fixture()
def vault(monkeypatch):
    recording = RecordingVault()
    monkeypatch.setattr(secret_vault, "get_vault", lambda: recording)
    return recording


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
        db.add(User(name="Interno", email=registered.email, password_hash="x", role=Role.INTERNAL, is_active=True))
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


def test_fallo_del_resguardo_revierte_la_autorizacion(registered_suppliers, monkeypatch):
    rows = registered_suppliers(2)
    failing = RecordingVault(fail_after=1)
    monkeypatch.setattr(secret_vault, "get_vault", lambda: failing)
    with SessionLocal() as db:
        admin = db.get(User, admin_id())
        with pytest.raises(RuntimeError, match="Gestor de secretos"):
            access.authorize(db, [s.id for s in rows], admin, "http://portal/login")
    for row in rows:
        assert supplier(row.id).status == SupplierStatus.REGISTERED
        assert portal_user(row.id) is None
    assert deliveries() == [] and messages() == []


# --- Usuario y contrasena temporal ---------------------------------------------------------------------------------


def test_usuario_creado_al_autorizar(client, registered_suppliers):
    [registered] = registered_suppliers(email="Contacto.Mixto@Acceso-Proveedor.mx")
    login(client)
    authorize(client, [registered.id])
    user = portal_user(registered.id)
    assert (user.email, user.role, user.is_active) == ("contacto.mixto@acceso-proveedor.mx", Role.PROVIDER, True)
    assert user.name == registered.business_name and user.last_login_at is None
    assert user.must_change_password  # HU-10: la temporal se cambia en el primer acceso
    password = password_for(user.email)
    assert len(password) == 20 and verify_password(password, user.password_hash)


def test_inicio_de_sesion_con_la_contrasena_temporal(client, registered_suppliers):
    [registered] = registered_suppliers()
    login(client)
    authorize(client, [registered.id])
    password = password_for(registered.email)
    client.post("/logout", data={"csrf_token": csrf(client, "/")})
    response = login(client, registered.email, password)
    # HU-10: con la contrasena temporal, el inicio de sesion lleva al cambio obligatorio.
    assert response.status_code == 303 and response.headers["location"] == "/account/password"
    assert registered.email in client.get("/account/password").text


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
    assert all(password not in value for value in user_columns)
    assert password not in audits and user.password_hash not in audits
    assert all(password not in value for value in stored)
    assert password not in log_since(offset)


def test_proveedor_con_usuario_propio(client, registered_suppliers):
    [registered] = registered_suppliers()
    original = hash_password("Propia#Clave2026")
    with SessionLocal() as db:
        db.add(
            User(
                name="Usuario previo",
                email=registered.email,
                password_hash=original,
                role=Role.PROVIDER,
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
    assert len(users) == 1 and users[0].password_hash == original
    assert deliveries() == []
    assert "Autorizado · Ya tenía usuario" in client.get(response.headers["location"]).text


def test_resguardo_en_el_gestor_de_secretos(client, registered_suppliers, vault):
    [registered] = registered_suppliers()
    login(client)
    authorize(client, [registered.id])
    [call] = vault.calls
    assert call["supplier_id"] == registered.id and call["username"] == registered.email
    assert call["password"] == password_for(registered.email)
    assert call["seen"] == SupplierStatus.REGISTERED  # antes del commit


def test_adaptador_nulo_por_omision():
    assert isinstance(secret_vault.get_vault(), secret_vault.NullSecretVault)
    assert secret_vault.get_vault().store_temporary_password(supplier_id=1, username="a@b.mx", password="x") is None


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


def test_expediente_despues_del_primer_cambio(client, registered_suppliers):
    [registered] = registered_suppliers()
    login(client)
    authorize(client, [registered.id])
    password = password_for(registered.email)
    client.post("/logout", data={"csrf_token": csrf(client, "/")})
    login(client, registered.email, password)
    data = {"current_password": password, "new_password": "Portal#2026x", "confirm_password": "Portal#2026x"}
    response = client.post(
        "/account/password", data={**data, "csrf_token": csrf(client, "/account/password")}, follow_redirects=False
    )
    assert response.status_code == 303
    client.post("/logout", data={"csrf_token": csrf(client, "/")})
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


def test_reenvio_tras_un_envio_fallido(client, registered_suppliers, vault, monkeypatch):
    [registered] = registered_suppliers()
    login(client)
    monkeypatch.setattr(settings, "mail_backend", "smtp")
    monkeypatch.setattr(settings, "smtp_host", "127.0.0.1")
    monkeypatch.setattr(settings, "smtp_port", closed_port())
    authorize(client, [registered.id])
    first_password = vault.calls[0]["password"]
    monkeypatch.setattr(settings, "mail_backend", "file")
    response = resend(client, registered.id)
    delivery = deliveries()[-1]
    assert response.headers["location"] == f"/suppliers/{registered.id}?credentials={delivery.id}"
    page = client.get(response.headers["location"]).text
    assert f"Credenciales enviadas a {registered.email}" in page
    new_password = password_for(registered.email)
    assert new_password == vault.calls[1]["password"] != first_password
    user = portal_user(registered.id)
    assert verify_password(new_password, user.password_hash) and not verify_password(first_password, user.password_hash)
    client.post("/logout", data={"csrf_token": csrf(client, "/")})
    assert login(client, registered.email, first_password).status_code == 400
    assert login(client, registered.email, new_password).status_code == 303


def test_reenvio_a_quien_entro_sin_cambiar_la_contrasena(client, registered_suppliers, vault):
    [registered] = registered_suppliers()
    login(client)
    authorize(client, [registered.id])
    first_password = vault.calls[0]["password"]
    # Entro con la temporal pero no la cambio (HU-10): aun puede recibir credenciales nuevas.
    _set_user(registered.id, last_login_at=datetime.now(timezone.utc))
    assert "Reenviar credenciales</button>" in client.get(f"/suppliers/{registered.id}").text
    response = resend(client, registered.id)
    assert response.status_code == 303
    user = portal_user(registered.id)
    new_password = vault.calls[1]["password"]
    assert new_password != first_password and verify_password(new_password, user.password_hash)
    assert user.must_change_password


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
def test_condiciones_del_reenvio(client, registered_suppliers, setup, message):
    [target] = registered_suppliers(
        status=SupplierStatus.ACTIVE if setup == "without_user" else SupplierStatus.REGISTERED
    )
    login(client)
    if setup in {"disabled", "password_changed"}:
        authorize(client, [target.id])
        values = (
            {"is_active": False}
            if setup == "disabled"
            else {"must_change_password": False, "last_login_at": datetime.now(timezone.utc)}
        )
        _set_user(target.id, **values)
    user = portal_user(target.id)
    before_hash, before_deliveries, before_audit = (
        (user.password_hash if user else None),
        len(deliveries()),
        audit_count(),
    )
    response = resend(client, target.id)
    assert response.status_code == 409 and message in response.text
    after = portal_user(target.id)
    assert (after.password_hash if after else None) == before_hash
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
    assert created.new_value == {"role": "PROVIDER", "supplier_id": registered.id, "origin": "SUPPLIER_AUTHORIZATION"}
    bulk = entries["SUPPLIER_BULK_AUTHORIZED"]
    assert bulk.new_value == {
        "authorized": [registered.id],
        "existing_access": [],
        "skipped": [],
        "conflicts": [],
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
