from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.constants import LoginResult
from app.core.database import get_db
from app.core.demo import quick_access_accounts
from app.core.security import validate_csrf, verify_password
from app.models import User
from app.routers.common import templates
from app.services import login_throttle, session_service
from app.services.audit_service import audit

router = APIRouter()


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
        response = render_login(
            request, 429, error="Demasiados intentos fallidos. Espere unos minutos e intente de nuevo."
        )
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
    return RedirectResponse("/", status_code=303)


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
