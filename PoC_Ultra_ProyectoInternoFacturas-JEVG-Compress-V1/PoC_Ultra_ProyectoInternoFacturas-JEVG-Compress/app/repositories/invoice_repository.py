from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import Invoice


def visible_invoices(db: Session, user):
    stmt = select(Invoice).order_by(Invoice.created_at.desc())
    if user.role.value == "PROVIDER":
        stmt = stmt.where(Invoice.supplier_id == user.supplier_id)
    return list(db.scalars(stmt))


def get_visible_invoice(db: Session, invoice_id: int, user) -> Invoice | None:
    invoice = db.get(Invoice, invoice_id)
    if invoice and user.role.value == "PROVIDER" and invoice.supplier_id != user.supplier_id:
        return None
    return invoice

