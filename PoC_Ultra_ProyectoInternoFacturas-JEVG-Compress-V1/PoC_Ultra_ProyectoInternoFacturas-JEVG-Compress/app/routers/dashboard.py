from dataclasses import dataclass

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.constants import InvoiceStatus, Role
from app.core.database import get_db
from app.core.security import get_current_user
from app.repositories.invoice_repository import search_invoices, status_counts, total_amount
from app.routers.common import templates
from app.services import payment_service

router = APIRouter()
RECENT_INVOICES = 10
# Avisos que llegan por ?notice= tras una redireccion (el portal no tiene mensajes flash); otro valor se ignora.
NOTICES = {"password_changed": "Contraseña actualizada"}


@dataclass(frozen=True)
class KPI:
    status: InvoiceStatus
    label: str
    note: str
    tone: str
    count: int


# Indicadores de seguimiento por estatus (HU-17, EP-01 DT-01): cada uno abre el listado filtrado.
STATUS_KPIS = [
    (InvoiceStatus.UNDER_REVIEW, "Enviadas", "En validación del PMO", ""),
    (InvoiceStatus.REQUIRES_CORRECTION, "Observaciones", "Por corregir y reenviar", "warning"),
    (InvoiceStatus.ACCEPTED, "Autorizadas", "Para su pago", "success"),
    (InvoiceStatus.PAID, "Pagadas", "Pago registrado", "success"),
    (InvoiceStatus.REJECTED, "Rechazadas", "Decisión definitiva", "danger"),
    (InvoiceStatus.CANCELLED, "Canceladas", "Con acuse de cancelación", "muted"),
]


@router.get("/")
def dashboard(request: Request, notice: str = "", db: Session = Depends(get_db), user=Depends(get_current_user)):
    # KPIs agregados en SQL (COUNT ... GROUP BY y SUM exacta): no se cargan todas las facturas en memoria.
    counts = status_counts(db, user)
    kpis = [KPI(status, label, note, tone, counts.get(status, 0)) for status, label, note, tone in STATUS_KPIS]
    recent = search_invoices(db, user, per_page=RECENT_INVOICES).items
    context = {
        "user": user,
        "invoices": recent,
        "total": sum(counts.values()),
        "amount": total_amount(db, user),
        "kpis": kpis,
        "notice": NOTICES.get(notice),
        # Complementos de pago pendientes del proveedor (HU Complemento de Pagos).
        "pending_complements": (
            payment_service.pending_notice(db, user.supplier_id) if user.role == Role.PROVEEDOR else []
        ),
    }
    return templates.TemplateResponse(request, "dashboard.html", context)
