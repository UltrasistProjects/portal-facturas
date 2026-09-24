from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.constants import BUSINESS_RULES, Role
from app.core.database import get_db
from app.core.security import hash_password, require_roles, validate_csrf
from app.models import AuditLog, Supplier, User
from app.repositories.pagination import paginate
from app.routers.common import templates
from app.schemas import UserCreate, validation_message
from app.services import session_service
from app.services.audit_service import audit

router = APIRouter(prefix="/admin")


def _users_page(request: Request, db: Session, user, error: str | None = None, status_code: int = 200):
    context = {
        "user": user,
        "users": list(db.scalars(select(User).order_by(User.name))),
        "suppliers": list(db.scalars(select(Supplier))),
        "error": error,
    }
    return templates.TemplateResponse(request, "admin/users.html", context, status_code=status_code)


@router.get("/users")
def users(request: Request, db: Session = Depends(get_db), user=Depends(require_roles(Role.ADMIN))):
    return _users_page(request, db, user)


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
    try:
        data = UserCreate(name=name, email=email, password=password, role=role, supplier_id=supplier_id)
    except ValidationError as exc:
        return _users_page(request, db, user, validation_message(exc), 400)
    if db.scalar(select(User.id).where(User.email == data.email)):
        return _users_page(request, db, user, "Ya existe un usuario con ese correo.", 409)
    created = User(
        name=data.name,
        email=data.email,
        password_hash=hash_password(data.password),
        role=data.role,
        supplier_id=data.supplier_id if data.role == Role.PROVIDER else None,
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
        if not target.is_active:
            session_service.revoke_all_for_user(db, target.id)
        audit(
            db, "USER_STATUS_CHANGED", "User", target.id, user.id, {"is_active": old}, {"is_active": target.is_active}
        )
        db.commit()
    return RedirectResponse("/admin/users", status_code=303)


AUDIT_ENTRIES_PER_PAGE = 50


@router.get("/audit")
def audit_log(request: Request, page: int = 1, db: Session = Depends(get_db), user=Depends(require_roles(Role.ADMIN))):
    stmt = select(AuditLog).options(joinedload(AuditLog.user)).order_by(AuditLog.timestamp.desc(), AuditLog.id.desc())
    result = paginate(db, stmt, page, AUDIT_ENTRIES_PER_PAGE)
    context = {"user": user, "entries": result.items, "page": result, "base_query": ""}
    return templates.TemplateResponse(request, "admin/audit.html", context)


@router.get("/rules")
def rules(request: Request, user=Depends(require_roles(Role.ADMIN))):
    # Fuente unica: los mismos valores que aplica el motor de validacion (AUDITORIA COD-04).
    rules_data = BUSINESS_RULES
    return templates.TemplateResponse(request, "admin/rules.html", {"user": user, "rules": rules_data})
