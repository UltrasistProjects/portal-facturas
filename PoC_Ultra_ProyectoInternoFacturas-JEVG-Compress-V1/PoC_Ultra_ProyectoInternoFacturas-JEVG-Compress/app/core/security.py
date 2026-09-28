import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from app.core.constants import Role
from app.core.database import get_db
from app.core.middleware import bind_user

password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return password_hash.verify(password, hashed)


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


# Unica pagina disponible mientras el usuario conserve una contrasena asignada por otra persona (HU-10).
PASSWORD_CHANGE_URL = "/account/password"


class PasswordChangeRequired(Exception):
    """El usuario debe cambiar la contrasena que le asigno otra persona. app.main la traduce a un 303 hacia
    PASSWORD_CHANGE_URL."""


def get_authenticated_user(request: Request, db: Annotated[Session, Depends(get_db)]):
    """Usuario de la sesion vigente, sin exigir el cambio de contrasena: solo la usan las rutas de ese cambio."""
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


def get_current_user(user=Depends(get_authenticated_user)):
    """Dependencia de toda ruta autenticada: con la marca de contrasena asignada, ninguna se ejecuta (HU-10)."""
    if user.must_change_password:
        raise PasswordChangeRequired()
    return user


def require_roles(*roles: Role):
    def dependency(user=Depends(get_current_user)):
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="No cuenta con permisos")
        return user

    return dependency
