from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.constants import LoginResult
from app.core.database import get_db
from app.core.demo import quick_access_accounts
from app.core.passwords import MAX_LENGTH, MIN_LENGTH, password_problems
from app.core.security import (
    PASSWORD_CHANGE_URL,
    get_authenticated_user,
    hash_password,
    validate_csrf,
    verify_password,
)
from app.models import User
from app.routers.common import templates
from app.services import login_throttle, session_service
from app.services.audit_service import audit

router = APIRouter()

MSG_THROTTLED = "Demasiados intentos fallidos. Espere unos minutos e intente de nuevo."
MSG_WRONG_CURRENT = "La contraseña actual no es correcta."
MSG_MISMATCH = "La confirmación no coincide con la nueva contraseña."
MSG_SAME = "La nueva contraseña debe ser distinta de la actual."
PASSWORD_POLICY = (
    f"Entre {MIN_LENGTH} y {MAX_LENGTH} caracteres, con al menos una letra, un número y un carácter especial. "
    "No se aceptan contraseñas comunes."
)


def render_login(request: Request, status_code: int = 200, **context):
    context["demo_accounts"] = quick_access_accounts(settings.app_env)
    return templates.TemplateResponse(request, "auth/login.html", context, status_code=status_code)


@router.get("/login")
def login_page(request: Request, db: Session = Depends(get_db)):
    if session_service.resolve(db, request.session.get("sid")):
        return RedirectResponse("/", status_code=303)
    request.session.pop("sid", None)  # sesion vencida o revocada: evita el ciclo / <-> /login
    return render_login(request)


@router.post("/login")
async def login(request: Request, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    await validate_csrf(request)
    email = email.lower().strip()
    ip = request.client.host if request.client else None
    # Antes de verificar la contrasena: un intento bloqueado no consume Argon2 y no revela si el correo existe.
    decision = login_throttle.check(db, email, ip)
    if not decision.allowed:
        login_throttle.record(db, email, ip, LoginResult.THROTTLED)
        db.commit()
        response = render_login(request, 429, error=MSG_THROTTLED)
        response.headers["Retry-After"] = str(decision.retry_after_seconds)
        return response
    user = db.scalar(select(User).where(User.email == email))
    if not user or not user.is_active or not verify_password(password, user.password_hash):
        audit(db, "LOGIN_FAILED", "User", user.id if user else None, new={"email": email}, ip=ip)
        login_throttle.record(db, email, ip, LoginResult.FAILURE)
        db.commit()
        return render_login(request, 400, error="Credenciales invalidas o usuario deshabilitado")
    login_throttle.record(db, email, ip, LoginResult.SUCCESS)
    # Identificador nuevo en cada login (antifijacion); el que traia la cookie deja de autenticar.
    session_service.revoke(db, request.session.get("sid"))
    request.session.clear()
    request.session["sid"] = session_service.create(db, user.id, ip, request.headers.get("user-agent"))
    user.last_login_at = datetime.now(timezone.utc)
    audit(db, "LOGIN_SUCCESS", "User", user.id, user.id, ip=ip)
    db.commit()
    # Con una contrasena asignada por otra persona, directo al cambio (HU-10); desde / tambien llegaria ahi.
    return RedirectResponse(PASSWORD_CHANGE_URL if user.must_change_password else "/", status_code=303)


@router.post("/logout")
async def logout(request: Request, db: Session = Depends(get_db)):
    await validate_csrf(request)
    sid = request.session.get("sid")
    user_session = session_service.resolve(db, sid)
    if user_session:
        audit(db, "LOGOUT", "User", user_session.user_id, user_session.user_id)
    session_service.revoke(db, sid)
    db.commit()
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


# --- Cambio de contrasena (HU-10) ----------------------------------------------------------------------------------


def render_password_page(request: Request, account: User, status_code: int = 200, errors: list[str] | None = None):
    """Con la marca activa la pagina se muestra sin menu (bloque anonymous): sus enlaces solo devolverian aqui."""
    context = {
        "account": account,
        "forced": account.must_change_password,
        "user": None if account.must_change_password else account,
        "errors": errors or [],
        "policy": PASSWORD_POLICY,
        "min_length": MIN_LENGTH,
        "max_length": MAX_LENGTH,
    }
    return templates.TemplateResponse(request, "auth/change_password.html", context, status_code=status_code)


@router.get(PASSWORD_CHANGE_URL)
def password_page(request: Request, user: User = Depends(get_authenticated_user)):
    return render_password_page(request, user)


@router.post(PASSWORD_CHANGE_URL)
async def change_password(
    request: Request,
    current_password: str = Form(""),
    new_password: str = Form(""),
    confirm_password: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(get_authenticated_user),
):
    await validate_csrf(request)
    ip = request.client.host if request.client else None
    # Verifica el mismo secreto que el login: comparte su limitacion de intentos (D4).
    decision = login_throttle.check(db, user.email, ip)
    if not decision.allowed:
        login_throttle.record(db, user.email, ip, LoginResult.THROTTLED)
        db.commit()
        response = render_password_page(request, user, 429, [MSG_THROTTLED])
        response.headers["Retry-After"] = str(decision.retry_after_seconds)
        return response
    if len(current_password) > MAX_LENGTH or not verify_password(current_password, user.password_hash):
        login_throttle.record(db, user.email, ip, LoginResult.FAILURE)
        db.commit()
        return render_password_page(request, user, 400, [MSG_WRONG_CURRENT])
    errors = password_problems(new_password)
    if new_password != confirm_password:
        errors.append(MSG_MISMATCH)
    if new_password == current_password:
        errors.append(MSG_SAME)
    if errors:
        return render_password_page(request, user, 400, errors)
    forced = user.must_change_password
    user.password_hash = hash_password(new_password)
    user.must_change_password = False
    login_throttle.record(db, user.email, ip, LoginResult.SUCCESS)
    # Todas las sesiones del usuario, incluida esta, se revocan: quien entro con la contrasena anterior queda fuera.
    session_service.revoke_all_for_user(db, user.id)
    request.session.clear()
    request.session["sid"] = session_service.create(db, user.id, ip, request.headers.get("user-agent"))
    audit(db, "PASSWORD_CHANGED", "User", user.id, user.id, new={"forced": forced}, ip=ip)
    db.commit()
    return RedirectResponse("/?notice=password_changed", status_code=303)
