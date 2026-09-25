"""Verificaciones que impiden arrancar en produccion con una configuracion insegura."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.demo import DEMO_EMAIL_DOMAIN


def startup_problems(settings: Settings, db: Session) -> list[str]:
    if settings.app_env != "production":
        return []
    from app.models import User

    problems = []
    if not settings.session_https_only:
        problems.append("SESSION_HTTPS_ONLY=false: en produccion la cookie de sesion debe ser Secure (HTTPS).")
    if settings.mail_backend == "file":
        problems.append("MAIL_BACKEND=file: en produccion los correos deben enviarse por SMTP.")
    elif settings.smtp_security == "none":
        problems.append("SMTP_SECURITY=none: en produccion la conexion SMTP debe cifrarse (starttls o ssl).")
    demo_users = db.scalars(select(User.email).where(User.is_active.is_(True), User.email.endswith(DEMO_EMAIL_DOMAIN)))
    demo_users = sorted(demo_users)
    if demo_users:
        problems.append(f"Cuentas demo activas que deben deshabilitarse: {', '.join(demo_users)}.")
    return problems


def run_startup_checks(settings: Settings, db: Session) -> None:
    problems = startup_problems(settings, db)
    if problems:
        raise RuntimeError("Arranque abortado por configuracion insegura:\n- " + "\n- ".join(problems))
