import json
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import Role
from app.core.database import get_db
from app.core.security import hash_password, require_roles, validate_csrf
from app.models import AuditLog, Supplier, User
from app.routers.common import templates
from app.services.audit_service import audit

router = APIRouter(prefix="/admin")


@router.get("/users")
def users(request: Request, db: Session = Depends(get_db), user=Depends(require_roles(Role.ADMIN))):
    return templates.TemplateResponse(
        request,
        "admin/users.html",
        {
            "user": user,
            "users": list(db.scalars(select(User).order_by(User.name))),
            "suppliers": list(db.scalars(select(Supplier))),
        },
    )


@router.post("/users")
async def create_user(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    role: Role = Form(...),
    supplier_id: int | None = Form(None),
    db: Session = Depends(get_db),
    user=Depends(require_roles(Role.ADMIN)),
):
    await validate_csrf(request)
    created = User(
        name=name,
        email=email.lower().strip(),
        password_hash=hash_password(password),
        role=role,
        supplier_id=supplier_id if role == Role.PROVIDER else None,
    )
    db.add(created)
    db.flush()
    audit(db, "USER_CREATED", "User", created.id, user.id)
    db.commit()
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/users/{user_id}/toggle")
async def toggle_user(
    user_id: int, request: Request, db: Session = Depends(get_db), user=Depends(require_roles(Role.ADMIN))
):
    await validate_csrf(request)
    target = db.get(User, user_id)
    if target and target.id != user.id:
        old = target.is_active
        target.is_active = not old
        audit(
            db, "USER_STATUS_CHANGED", "User", target.id, user.id, {"is_active": old}, {"is_active": target.is_active}
        )
        db.commit()
    return RedirectResponse("/admin/users", status_code=303)


@router.get("/audit")
def audit_log(request: Request, db: Session = Depends(get_db), user=Depends(require_roles(Role.ADMIN))):
    entries = list(db.scalars(select(AuditLog).order_by(AuditLog.timestamp.desc()).limit(500)))
    return templates.TemplateResponse(request, "admin/audit.html", {"user": user, "entries": entries})


@router.get("/rules")
def rules(request: Request, user=Depends(require_roles(Role.ADMIN))):
    rules_data = json.loads((Path(__file__).parents[1] / "rules" / "business_rules.json").read_text(encoding="utf-8"))
    return templates.TemplateResponse(request, "admin/rules.html", {"user": user, "rules": rules_data})
