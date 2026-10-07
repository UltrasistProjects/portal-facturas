from decimal import Decimal, InvalidOperation
from pathlib import Path

from fastapi.templating import Jinja2Templates

from app.core.constants import (
    STATUS_LABELS,
    SUPPLIER_CLASSIFICATION_LABELS,
    SUPPLIER_ORIGIN_LABELS,
    SUPPLIER_STATUS_LABELS,
    SUPPLIER_TYPE_LABELS,
)
from app.core.security import csrf_token
from app.core.timeutils import to_business

templates = Jinja2Templates(directory=str(Path(__file__).parents[1] / "templates"))
templates.env.globals.update(
    status_labels=STATUS_LABELS,
    supplier_status_labels=SUPPLIER_STATUS_LABELS,
    supplier_origin_labels=SUPPLIER_ORIGIN_LABELS,
    supplier_classification_labels=SUPPLIER_CLASSIFICATION_LABELS,
    supplier_type_labels=SUPPLIER_TYPE_LABELS,
    csrf_token=csrf_token,
)


def money(value) -> str:
    if value is None:
        return "—"
    try:
        return f"${Decimal(str(value)):,.2f}"
    except (InvalidOperation, ValueError):
        return str(value)


templates.env.filters["money"] = money


def business_date(value) -> str:
    """Fecha en la zona horaria de negocio (dd/mm/aaaa); "—" si no hay."""
    return to_business(value).strftime("%d/%m/%Y") if value else "—"


templates.env.filters["business_date"] = business_date


def business_datetime(value) -> str:
    """Fecha y hora en la zona horaria de negocio (dd/mm/aaaa HH:MM); "—" si no hay."""
    return to_business(value).strftime("%d/%m/%Y %H:%M") if value else "—"


templates.env.filters["business_datetime"] = business_datetime
