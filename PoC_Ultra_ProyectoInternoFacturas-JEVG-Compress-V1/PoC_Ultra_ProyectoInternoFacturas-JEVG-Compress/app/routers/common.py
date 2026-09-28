from decimal import Decimal, InvalidOperation
from pathlib import Path

from fastapi.templating import Jinja2Templates

from app.core.constants import STATUS_LABELS, SUPPLIER_CLASSIFICATION_LABELS, SUPPLIER_STATUS_LABELS
from app.core.security import csrf_token

templates = Jinja2Templates(directory=str(Path(__file__).parents[1] / "templates"))
templates.env.globals.update(
    status_labels=STATUS_LABELS,
    supplier_status_labels=SUPPLIER_STATUS_LABELS,
    supplier_classification_labels=SUPPLIER_CLASSIFICATION_LABELS,
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
