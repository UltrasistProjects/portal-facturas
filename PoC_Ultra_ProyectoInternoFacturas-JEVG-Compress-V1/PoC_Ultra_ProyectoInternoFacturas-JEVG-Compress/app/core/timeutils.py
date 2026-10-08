"""Zona horaria de negocio: los plazos de calendario (corte del dia 20, ano del folio) se evaluan en hora local."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.core.config import settings


def business_tz() -> ZoneInfo:
    return ZoneInfo(settings.business_timezone)


def to_business(value: datetime) -> datetime:
    """Convierte a la zona de negocio. Un valor naive se interpreta como UTC (asi se almacena en la BD)."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(business_tz())


def business_now() -> datetime:
    return datetime.now(business_tz())
