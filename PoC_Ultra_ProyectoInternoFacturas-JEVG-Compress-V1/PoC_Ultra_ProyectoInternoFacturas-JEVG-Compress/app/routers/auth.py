from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import validate_csrf, verify_password
from app.models import User
from app.routers.common import templates
from app.services.audit_service import audit

router = APIRouter()


@router.get("/login")
def login_page(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request, "auth/login.html", {})


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
        return templates.TemplateResponse(
            request, "auth/login.html", {"error": "Credenciales invalidas o usuario deshabilitado"}, status_code=400
        )
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
