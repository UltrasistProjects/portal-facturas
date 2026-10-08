"""Inicio y cierre de sesion con Keycloak (OIDC) y cambio de contrasena en Keycloak (add-keycloak-authentication).

El portal no recibe contrasenas: /login redirige a Keycloak, /auth/callback valida el ID token (app.services.oidc),
enlaza al usuario local por su `sub` (D7), exige un rol del portal igual al local (D8) y abre la sesion del servidor
(D9). El logout revoca la sesion local y termina la de Keycloak (D10).
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user, validate_csrf
from app.models import User
from app.services import oidc, session_service
from app.services.audit_service import audit
from app.services.identity_service import portal_roles

router = APIRouter()

PASSWORD_CHANGE_URL = "/account/password"
UPDATE_PASSWORD = "UPDATE_PASSWORD"
MSG_REJECTED = "No se pudo completar el inicio de sesión. Vuelva a intentarlo."
MSG_ACCOUNT_DISABLED = "Su cuenta no está habilitada en el portal."
MSG_ROLE = "Su cuenta no tiene un rol válido para el portal. Solicite al Administrador que revise su acceso."
MSG_UNAVAILABLE = "El servicio de autenticación no está disponible."


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _callback_url(request: Request) -> str:
    return str(request.url_for("auth_callback"))


def denial_reason(user: User | None, claims: dict) -> str | None:
    """Motivo por el que un ID token valido no abre sesion (D7, D8), o None."""
    if user is None:
        return "unknown_account"
    if not user.is_active:
        return "inactive"
    realm_access = claims.get("realm_access")
    roles = portal_roles(realm_access.get("roles") or []) if isinstance(realm_access, dict) else set()
    if not roles:
        return "role_missing"
    if roles != {user.role.value}:
        return "role_mismatch"
    return None


@router.get("/login")
async def login_page(request: Request, db: Session = Depends(get_db)):
    if session_service.resolve(db, request.session.get("sid")):
        return RedirectResponse("/", status_code=303)
    request.session.pop("sid", None)  # sesion vencida o revocada: evita el ciclo / <-> /login
    try:
        return await oidc.authorize_redirect(request, _callback_url(request))
    except oidc.IdentityUnavailable:
        raise HTTPException(503, MSG_UNAVAILABLE) from None


@router.get("/auth/callback", name="auth_callback")
async def auth_callback(request: Request, db: Session = Depends(get_db)):
    ip = _ip(request)
    try:
        claims, id_token = await oidc.complete_login(request)
    except oidc.LoginRejected as exc:
        audit(db, "LOGIN_FAILED", "User", None, new={"reason": exc.reason}, ip=ip)
        db.commit()
        raise HTTPException(400, MSG_REJECTED) from None
    except oidc.IdentityUnavailable:
        raise HTTPException(503, MSG_UNAVAILABLE) from None
    user = db.scalar(select(User).where(User.keycloak_sub == claims["sub"]))
    reason = denial_reason(user, claims)
    if reason:
        details = {"reason": reason} if user else {"reason": reason, "email": claims.get("email")}
        audit(db, "LOGIN_DENIED", "User", user.id if user else None, new=details, ip=ip)
        db.commit()
        raise HTTPException(403, MSG_ROLE if reason.startswith("role_") else MSG_ACCOUNT_DISABLED)
    # Identificador y token CSRF nuevos en cada inicio de sesion (antifijacion); el anterior deja de autenticar.
    session_service.revoke(db, request.session.get("sid"))
    request.session.clear()
    user_agent = request.headers.get("user-agent")
    request.session["sid"] = session_service.create(db, user.id, ip, user_agent, id_token_hint=id_token)
    user.last_login_at = datetime.now(timezone.utc)
    audit(db, "LOGIN_SUCCESS", "User", user.id, user.id, ip=ip)
    target = "/"
    # Regreso de "Cambiar contrasena" (kc_action=UPDATE_PASSWORD): Keycloak informa el resultado de la accion.
    if request.query_params.get("kc_action_status") == "success":
        audit(db, "PASSWORD_CHANGED", "User", user.id, user.id, new={"forced": False}, ip=ip)
        target = "/?notice=password_changed"
    db.commit()
    return RedirectResponse(target, status_code=303)


@router.post("/logout")
async def logout(request: Request, db: Session = Depends(get_db)):
    await validate_csrf(request)
    sid = request.session.get("sid")
    user_session = session_service.resolve(db, sid)
    id_token_hint = session_service.id_token_hint(db, sid)
    if user_session:
        audit(db, "LOGOUT", "User", user_session.user_id, user_session.user_id)
    session_service.revoke(db, sid)
    db.commit()
    request.session.clear()
    # Termina tambien la sesion SSO de Keycloak; sin Keycloak, al menos la local ya quedo revocada.
    end_session = await oidc.logout_url(id_token_hint, str(request.base_url))
    return RedirectResponse(end_session or "/", status_code=303)


@router.get(PASSWORD_CHANGE_URL, dependencies=[Depends(get_current_user)])
async def password_page(request: Request):
    """Cambio de contrasena en Keycloak (accion iniciada por la aplicacion); el portal no muestra formularios de
    contrasena. El primer acceso lo exige Keycloak con la accion requerida UPDATE_PASSWORD."""
    try:
        return await oidc.authorize_redirect(request, _callback_url(request), kc_action=UPDATE_PASSWORD)
    except oidc.IdentityUnavailable:
        raise HTTPException(503, MSG_UNAVAILABLE) from None
