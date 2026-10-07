import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.constants import Role
from app.core.database import get_db
from app.core.middleware import bind_user


def csrf_token(request: Request) -> str:
    token = request.session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf_token"] = token
    return token


async def validate_csrf(request: Request) -> None:
    form = await request.form()
    supplied = str(form.get("csrf_token", ""))
    expected = str(request.session.get("csrf_token", ""))
    if not expected or not secrets.compare_digest(supplied, expected):
        raise HTTPException(status_code=403, detail="Token CSRF invalido")


def get_current_user(request: Request, db: Annotated[Session, Depends(get_db)]):
    """Usuario de la sesion vigente del servidor. La sesion la abre /auth/callback tras validar el ID token de Keycloak;
    cada peticion se valida contra la BD local (sesion, usuario activo), sin llamar a Keycloak."""
    from app.models import User
    from app.services import session_service

    user_session = session_service.resolve(db, request.session.get("sid"))
    user = db.get(User, user_session.user_id) if user_session else None
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Autenticacion requerida")
    if session_service.touch(user_session):
        db.commit()  # renovacion por actividad; no hay otros cambios pendientes a esta altura
    request.state.user_id = user.id
    bind_user(user.id)
    return user


def require_roles(*roles: Role):
    def dependency(user=Depends(get_current_user)):
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="No cuenta con permisos")
        return user

    return dependency
