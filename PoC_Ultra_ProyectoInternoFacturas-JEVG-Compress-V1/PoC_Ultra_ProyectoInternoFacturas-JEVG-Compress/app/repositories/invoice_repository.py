"""Consultas de facturas con alcance por usuario. Filtro, busqueda, paginacion y agregados se resuelven en SQL."""

from decimal import Decimal

from sqlalchemy import Select, false, func, or_, select
from sqlalchemy.orm import Session, contains_eager

from app.core.constants import InvoiceStatus, Role
from app.models import Invoice, Supplier
from app.repositories.pagination import Page, paginate

INVOICES_PER_PAGE = 25


def _scoped(stmt: Select, user) -> Select:
    if user.role == Role.PROVIDER:
        return stmt.where(Invoice.supplier_id == user.supplier_id)
    return stmt


def escape_like(value: str) -> str:
    """% y _ se buscan como caracteres literales."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def search_invoices(
    db: Session, user, q: str = "", status: str = "", page: int = 1, per_page: int = INVOICES_PER_PAGE
) -> Page[Invoice]:
    # contains_eager: el proveedor llega en la misma consulta (sin N+1) y el JOIN permite buscar por razon social.
    stmt = select(Invoice).join(Invoice.supplier).options(contains_eager(Invoice.supplier))
    stmt = _scoped(stmt, user)
    if q.strip():
        pattern = f"%{escape_like(q.strip())}%"
        stmt = stmt.where(
            or_(
                *(
                    column.ilike(pattern, escape="\\")
                    for column in (
                        Invoice.internal_folio,
                        Invoice.invoice_number,
                        Invoice.project_name,
                        Supplier.business_name,
                    )
                )
            )
        )
    if status:
        valid = status in {state.value for state in InvoiceStatus}
        stmt = stmt.where(Invoice.status == status) if valid else stmt.where(false())
    stmt = stmt.order_by(Invoice.created_at.desc(), Invoice.id.desc())
    return paginate(db, stmt, page, per_page)


def status_counts(db: Session, user) -> dict[InvoiceStatus, int]:
    stmt = _scoped(select(Invoice.status, func.count()).group_by(Invoice.status), user)
    return {status: count for status, count in db.execute(stmt)}


def total_amount(db: Session, user) -> Decimal:
    """Suma exacta en SQL: los montos son enteros en centavos."""
    return db.scalar(_scoped(select(func.sum(Invoice.total)), user)) or Decimal("0.00")


def get_visible_invoice(db: Session, invoice_id: int, user) -> Invoice | None:
    invoice = db.get(Invoice, invoice_id)
    if invoice and user.role == Role.PROVIDER and invoice.supplier_id != user.supplier_id:
        return None
    return invoice
