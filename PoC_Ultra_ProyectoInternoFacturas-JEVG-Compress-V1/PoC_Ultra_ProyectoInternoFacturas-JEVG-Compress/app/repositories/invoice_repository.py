"""Consultas de facturas con alcance por usuario. Filtro, busqueda, paginacion y agregados se resuelven en SQL."""

from decimal import Decimal

from sqlalchemy import Select, false, func, select
from sqlalchemy.orm import Session, contains_eager

from app.core.constants import InvoiceStatus, Role, RuleStatus, SupplierOrigin
from app.models import Invoice, Supplier, ValidationResult
from app.repositories.pagination import PER_PAGE, Page, paginate, search

INVOICES_PER_PAGE = PER_PAGE


def _scoped(stmt: Select, user) -> Select:
    if user.role == Role.PROVIDER:
        return stmt.where(Invoice.supplier_id == user.supplier_id)
    return stmt


def inbox_status(user, status: str | None) -> str:
    """Estatus efectivo del listado: sin `status`, el PMO y el Administrador abren su bandeja de "Enviadas" (HU-18);
    el proveedor ve todo. Un `status` vacio siempre significa "Todos los estados"."""
    if status is None:
        return "" if user.role == Role.PROVIDER else InvoiceStatus.UNDER_REVIEW.value
    return status


def search_invoices(
    db: Session,
    user,
    q: str = "",
    status: str = "",
    page: int = 1,
    per_page: int = INVOICES_PER_PAGE,
    origin: str = "",
) -> Page[Invoice]:
    # contains_eager: el proveedor llega en la misma consulta (sin N+1) y el JOIN permite buscar por razon social.
    stmt = select(Invoice).join(Invoice.supplier).options(contains_eager(Invoice.supplier))
    stmt = _scoped(stmt, user)
    stmt = search(stmt, q, Invoice.internal_folio, Invoice.invoice_number, Invoice.project_name, Supplier.business_name)
    if status:
        valid = status in {state.value for state in InvoiceStatus}
        stmt = stmt.where(Invoice.status == status) if valid else stmt.where(false())
    if origin in {value.value for value in SupplierOrigin}:
        stmt = stmt.where(Supplier.origin == origin)
    if user.role != Role.PROVIDER and status == InvoiceStatus.UNDER_REVIEW:
        # Bandeja del PMO: lo que mas ha esperado primero, tambien en las paginas siguientes (HU-18, D1).
        stmt = stmt.order_by(Invoice.submitted_at.asc(), Invoice.id.asc())
    else:
        stmt = stmt.order_by(Invoice.created_at.desc(), Invoice.id.desc())
    return paginate(db, stmt, page, per_page)


def warning_counts(db: Session, invoice_ids: list[int]) -> dict[int, int]:
    """Advertencias (WARNING) de la ultima validacion de cada factura de la pagina, en una sola consulta."""
    if not invoice_ids:
        return {}
    stmt = (
        select(ValidationResult.invoice_id, func.count())
        .where(ValidationResult.invoice_id.in_(invoice_ids), ValidationResult.status == RuleStatus.WARNING)
        .group_by(ValidationResult.invoice_id)
    )
    return {invoice_id: count for invoice_id, count in db.execute(stmt)}


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
