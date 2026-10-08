"""Sesiones revocables del lado del servidor (AUDITORIA SEC-07).

La cookie firmada solo transporta un identificador aleatorio opaco (y el token CSRF); la BD guarda su SHA-256.
Una sesion expira tras 60 minutos sin actividad u 8 horas desde el login, y se revoca al cerrar sesion o al
deshabilitar al usuario. El reloj es inyectable para las pruebas.

Con Keycloak (add-keycloak-authentication, D9) la sesion la abre /auth/callback y guarda el ID token como
id_token_hint del cierre de sesion en Keycloak: solo en la BD, nunca en la cookie, y se borra al revocar la sesion.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, or_, select, update
from sqlalchemy.orm import Session

from app.models import UserSession

IDLE_TIMEOUT = timedelta(minutes=60)
ABSOLUTE_TIMEOUT = timedelta(hours=8)
# last_seen_at se actualiza a lo sumo una vez por minuto: evita convertir cada GET en una escritura.
TOUCH_INTERVAL = timedelta(minutes=1)
PURGE_AFTER = timedelta(days=7)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def hash_sid(sid: str) -> str:
    return hashlib.sha256(sid.encode()).hexdigest()


def create(
    db: Session,
    user_id: int,
    ip: str | None,
    user_agent: str | None,
    now: datetime | None = None,
    id_token_hint: str | None = None,
) -> str:
    now = now or utcnow()
    sid = secrets.token_urlsafe(32)
    db.add(
        UserSession(
            user_id=user_id,
            sid_hash=hash_sid(sid),
            created_at=now,
            last_seen_at=now,
            ip=ip,
            user_agent=(user_agent or "")[:255] or None,
            id_token_hint=id_token_hint,
        )
    )
    purge(db, now)
    return sid


def resolve(db: Session, sid: str | None, now: datetime | None = None) -> UserSession | None:
    """La sesion vigente para ese identificador, o None si no existe, fue revocada o expiro."""
    if not sid:
        return None
    now = now or utcnow()
    session = db.scalar(select(UserSession).where(UserSession.sid_hash == hash_sid(sid)))
    if session is None or session.revoked_at is not None:
        return None
    if now - session.last_seen_at > IDLE_TIMEOUT or now - session.created_at > ABSOLUTE_TIMEOUT:
        return None
    return session


def id_token_hint(db: Session, sid: str | None) -> str | None:
    """ID token guardado para el identificador, aunque la sesion ya haya expirado: el logout lo envia a Keycloak."""
    if not sid:
        return None
    return db.scalar(select(UserSession.id_token_hint).where(UserSession.sid_hash == hash_sid(sid)))


def touch(session: UserSession, now: datetime | None = None) -> bool:
    now = now or utcnow()
    if now - session.last_seen_at < TOUCH_INTERVAL:
        return False
    session.last_seen_at = now
    return True


def revoke(db: Session, sid: str | None, now: datetime | None = None) -> None:
    if sid:
        db.execute(
            update(UserSession)
            .where(UserSession.sid_hash == hash_sid(sid), UserSession.revoked_at.is_(None))
            .values(revoked_at=now or utcnow(), id_token_hint=None)
        )


def revoke_all_for_user(db: Session, user_id: int, now: datetime | None = None) -> None:
    db.execute(
        update(UserSession)
        .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=now or utcnow(), id_token_hint=None)
    )


def purge(db: Session, now: datetime) -> None:
    """Elimina sesiones vencidas o revocadas hace mas de 7 dias."""
    threshold = now - PURGE_AFTER
    db.execute(
        delete(UserSession).where(
            or_(UserSession.created_at < threshold - ABSOLUTE_TIMEOUT, UserSession.revoked_at < threshold)
        )
    )
