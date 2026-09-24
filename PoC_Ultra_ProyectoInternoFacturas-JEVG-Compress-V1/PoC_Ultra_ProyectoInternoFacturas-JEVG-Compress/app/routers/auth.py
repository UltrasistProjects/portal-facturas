from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.demo import quick_access_accounts
from app.core.security import validate_csrf, verify_password
from app.models import User
from app.routers.common import templates
from app.services.audit_service import audit

router = APIRouter()


def render_login(request: Request, status_code: int = 200, **context):
    context["demo_accounts"] = quick_access_accounts(settings.app_env)
    return templates.TemplateResponse(request, "auth/login.html", context, status_code=status_code)


@router.get("/login")
def login_page(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse("/", status_code=303)
    return render_login(request)


@router.post("/login")
async def login(request: Request, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    await validate_csrf(request)
    user = db.scalar(select(User).where(User.email == email.lower().strip()))
    if not user or not user.is_active or not verify_password(password, user.password_hash):
        audit(
            db,
            "LOGIN_FAILED",
            "User",
            user.id if user else None,
            new={"email": email.lower().strip()},
            ip=request.client.host if request.client else None,
        )
        db.commit()
        return render_login(request, 400, error="Credenciales invalidas o usuario deshabilitado")
    request.session.clear()
    request.session["user_id"] = user.id
    user.last_login_at = datetime.now(timezone.utc)
    audit(db, "LOGIN_SUCCESS", "User", user.id, user.id, ip=request.client.host if request.client else None)
    db.commit()
    return RedirectResponse("/", status_code=303)


@router.post("/logout")
async def logout(request: Request, db: Session = Depends(get_db)):
    await validate_csrf(request)
    user_id = request.session.get("user_id")
    if user_id:
        audit(db, "LOGOUT", "User", user_id, user_id)
        db.commit()
    request.session.clear()
    return RedirectResponse("/login", status_code=303)
