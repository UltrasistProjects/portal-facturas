from decimal import Decimal

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.constants import InvoiceStatus
from app.core.database import get_db
from app.core.security import get_current_user
from app.repositories.invoice_repository import visible_invoices
from app.routers.common import templates

router = APIRouter()


@router.get("/")
def dashboard(request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)):
    invoices = visible_invoices(db, user)
    counts = {status.value: sum(i.status == status for i in invoices) for status in InvoiceStatus}
    kpis = {
        "total": len(invoices),
        "amount": sum((i.total for i in invoices), Decimal("0")),
        "review": counts.get("UNDER_REVIEW", 0),
        "correction": counts.get("REQUIRES_CORRECTION", 0),
        "accepted": counts.get("ACCEPTED", 0),
        "rejected": counts.get("REJECTED", 0),
        "prevalidated": counts.get("PREVALIDATED", 0),
    }
    return templates.TemplateResponse(
        request, "dashboard.html", {"user": user, "invoices": invoices[:10], "kpis": kpis}
    )
