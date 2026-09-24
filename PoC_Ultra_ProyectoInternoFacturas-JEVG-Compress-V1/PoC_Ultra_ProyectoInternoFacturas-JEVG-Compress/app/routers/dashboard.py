from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.constants import InvoiceStatus
from app.core.database import get_db
from app.core.security import get_current_user
from app.repositories.invoice_repository import search_invoices, status_counts, total_amount
from app.routers.common import templates

router = APIRouter()
RECENT_INVOICES = 10


@router.get("/")
def dashboard(request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)):
    # KPIs agregados en SQL (COUNT ... GROUP BY y SUM exacta): no se cargan todas las facturas en memoria.
    counts = status_counts(db, user)
    kpis = {
        "total": sum(counts.values()),
        "amount": total_amount(db, user),
        "review": counts.get(InvoiceStatus.UNDER_REVIEW, 0),
        "correction": counts.get(InvoiceStatus.REQUIRES_CORRECTION, 0),
        "accepted": counts.get(InvoiceStatus.ACCEPTED, 0),
        "rejected": counts.get(InvoiceStatus.REJECTED, 0),
        "prevalidated": counts.get(InvoiceStatus.PREVALIDATED, 0),
    }
    recent = search_invoices(db, user, per_page=RECENT_INVOICES).items
    return templates.TemplateResponse(request, "dashboard.html", {"user": user, "invoices": recent, "kpis": kpis})
