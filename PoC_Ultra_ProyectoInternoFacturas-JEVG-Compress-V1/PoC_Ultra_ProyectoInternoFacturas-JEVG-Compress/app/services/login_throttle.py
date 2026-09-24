"""Limitacion de intentos de inicio de sesion por correo (bloqueo exponencial) y por IP (AUDITORIA SEC-04).

Se consulta antes de verificar la contrasena: un intento bloqueado no consume Argon2.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.constants import LoginResult
from app.models import LoginAttempt
from app.services.audit_service import audit

logger = logging.getLogger(__name__)

EMAIL_FAILURE_THRESHOLD = 5
EMAIL_WINDOW = timedelta(hours=24)
MAX_LOCK_MINUTES = 60
IP_FAILURE_THRESHOLD = 20
IP_WINDOW = timedelta(minutes=15)
RETENTION = timedelta(hours=24)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class ThrottleDecision:
    allowed: bool
    retry_after_seconds: int = 0


def lock_minutes(consecutive_failures: int) -> int:
    return min(MAX_LOCK_MINUTES, 2 ** (consecutive_failures - EMAIL_FAILURE_THRESHOLD))


def consecutive_failures(db: Session, email: str, now: datetime) -> tuple[int, datetime | None]:
    """Fallos del correo desde su ultimo acceso exitoso, dentro de la ventana de 24 h."""
    since = now - EMAIL_WINDOW
    last_success = db.scalar(
        select(func.max(LoginAttempt.attempted_at)).where(
            LoginAttempt.email == email,
            LoginAttempt.result == LoginResult.SUCCESS,
            LoginAttempt.attempted_at >= since,
        )
    )
    start = max(since, last_success) if last_success else since
    count, last_failure = db.execute(
        select(func.count(), func.max(LoginAttempt.attempted_at)).where(
            LoginAttempt.email == email,
            LoginAttempt.result == LoginResult.FAILURE,
            LoginAttempt.attempted_at > start,
        )
    ).one()
    if last_failure is not None and last_failure.tzinfo is None:
        last_failure = last_failure.replace(tzinfo=timezone.utc)  # func.max no pasa por UTCDateTime
    return count, last_failure


def check(db: Session, email: str, ip: str | None, now: datetime | None = None) -> ThrottleDecision:
    now = now or utcnow()
    failures, last_failure = consecutive_failures(db, email, now)
    if failures >= EMAIL_FAILURE_THRESHOLD and last_failure is not None:
        locked_until = last_failure + timedelta(minutes=lock_minutes(failures))
        if now < locked_until:
            return ThrottleDecision(False, int((locked_until - now).total_seconds()) + 1)
    if ip:
        window_start = now - IP_WINDOW
        failures_by_ip = db.scalar(
            select(func.count()).where(
                LoginAttempt.ip == ip,
                LoginAttempt.result == LoginResult.FAILURE,
                LoginAttempt.attempted_at >= window_start,
            )
        )
        if failures_by_ip >= IP_FAILURE_THRESHOLD:
            return ThrottleDecision(False, int(IP_WINDOW.total_seconds()))
    return ThrottleDecision(True)


def record(db: Session, email: str, ip: str | None, result: LoginResult, now: datetime | None = None) -> None:
    now = now or utcnow()
    db.add(LoginAttempt(email=email, ip=ip, result=result, attempted_at=now))
    db.flush()
    if result == LoginResult.SUCCESS:
        db.execute(delete(LoginAttempt).where(LoginAttempt.attempted_at < now - RETENTION))
    elif result == LoginResult.FAILURE:
        failures, _ = consecutive_failures(db, email, now)
        if failures >= EMAIL_FAILURE_THRESHOLD:
            minutes = lock_minutes(failures)
            audit(
                db, "LOGIN_LOCKED", "User", None, new={"email": email, "failures": failures, "minutes": minutes}, ip=ip
            )
            logger.warning(
                "login.locked",
                extra={"event": "login.locked", "email": email, "failures": failures, "minutes": minutes},
            )
