"""Cancelacion de la factura por el proveedor (HU-14; EP-01 DT-01, DT-10).

- invoices: cancelled_at, cancelled_by (FK a users con RESTRICT, indexada) y cancellation_deadline, con el CHECK
  ck_invoices_cancellation: una factura CANCELLED tiene los tres datos y la fecha limite es posterior; las demas no
  tienen ninguno.
- El CHECK invoicestatus agrega CANCELLED. La columna sigue en VARCHAR(19): CANCELLED es mas corto.
- invoice_document_types: tipo del sistema CANCELLATION_ACK ("Acuse de cancelacion", PDF y XML) con nivel fijo
  NOT_APPLICABLE para ambos origenes en ck_invoice_document_types_fixed_levels. Si un tipo del Administrador ya usa
  ese nombre, la migracion se detiene: no renombra datos del Administrador.
- El downgrade se niega si hay facturas canceladas; si no, retira el tipo, los CHECK y las columnas.
"""

from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "0012_invoice_cancellation"
down_revision = "0011_retire_clickbalance"
branch_labels = None
depends_on = None

PREVIOUS_STATUSES = ("DRAFT", "UPLOADED", "UNDER_REVIEW", "ACCEPTED", "REJECTED", "REQUIRES_CORRECTION")
STATUSES = (*PREVIOUS_STATUSES, "CANCELLED")
CANCELLATION_CHECK = (
    "(status = 'CANCELLED' AND cancelled_at IS NOT NULL AND cancelled_by IS NOT NULL"
    " AND cancellation_deadline IS NOT NULL AND cancellation_deadline > cancelled_at)"
    " OR (status <> 'CANCELLED' AND cancelled_at IS NULL AND cancelled_by IS NULL AND cancellation_deadline IS NULL)"
)
PREVIOUS_FIXED_LEVELS_CHECK = (
    "(code NOT IN ('INVOICE_XML', 'INVOICE_PDF')"
    " OR (national_requirement = 'REQUIRED' AND international_requirement = 'NOT_APPLICABLE'))"
    " AND (code <> 'FOREIGN_INVOICE'"
    " OR (national_requirement = 'NOT_APPLICABLE' AND international_requirement = 'REQUIRED'))"
)
FIXED_LEVELS_CHECK = (
    PREVIOUS_FIXED_LEVELS_CHECK + " AND (code <> 'CANCELLATION_ACK'"
    " OR (national_requirement = 'NOT_APPLICABLE' AND international_requirement = 'NOT_APPLICABLE'))"
)
ACK_CODE = "CANCELLATION_ACK"
ACK_NAME = "Acuse de cancelación"
ACK_DESCRIPTION = "Acuse de cancelación del CFDI emitido por el SAT o documento que acredita la cancelación"


def sql_list(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def replace_check(name: str, table: str, condition: str) -> None:
    op.drop_constraint(name, table, type_="check")
    op.create_check_constraint(name, table, condition)


def upgrade() -> None:
    bind = op.get_bind()
    taken = bind.scalar(
        sa.text("SELECT code FROM invoice_document_types WHERE lower(name) = lower(:name)"), {"name": ACK_NAME}
    )
    if taken is not None:
        raise RuntimeError(
            f"El tipo de documento {taken} ya se llama «{ACK_NAME}», el nombre del tipo del sistema de HU-14. "
            "Renómbrelo desde Tipos de documento y vuelva a migrar."
        )
    op.add_column("invoices", sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("invoices", sa.Column("cancelled_by", sa.Integer(), nullable=True))
    op.add_column("invoices", sa.Column("cancellation_deadline", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        "fk_invoices_cancelled_by_users", "invoices", "users", ["cancelled_by"], ["id"], ondelete="RESTRICT"
    )
    op.create_index("ix_invoices_cancelled_by", "invoices", ["cancelled_by"], unique=False)
    replace_check("invoicestatus", "invoices", f"status IN ({sql_list(STATUSES)})")
    op.create_check_constraint("ck_invoices_cancellation", "invoices", CANCELLATION_CHECK)
    replace_check("ck_invoice_document_types_fixed_levels", "invoice_document_types", FIXED_LEVELS_CHECK)
    now = datetime.now(timezone.utc)
    bind.execute(
        sa.text(
            "INSERT INTO invoice_document_types (code, name, description, formats, is_system, is_active, "
            "national_requirement, international_requirement, created_at, updated_at) "
            "VALUES (:code, :name, :description, ARRAY['PDF', 'XML']::varchar[], true, true, "
            "'NOT_APPLICABLE', 'NOT_APPLICABLE', :now, :now)"
        ),
        {"code": ACK_CODE, "name": ACK_NAME, "description": ACK_DESCRIPTION, "now": now},
    )


def downgrade() -> None:
    bind = op.get_bind()
    cancelled = bind.scalar(sa.text("SELECT count(*) FROM invoices WHERE status = 'CANCELLED'"))
    if cancelled:
        raise NotImplementedError(
            "Hay facturas canceladas: su estatus y su acuse no existen antes de HU-14. Restaure un respaldo."
        )
    bind.execute(sa.text("DELETE FROM invoice_document_types WHERE code = :code"), {"code": ACK_CODE})
    replace_check("ck_invoice_document_types_fixed_levels", "invoice_document_types", PREVIOUS_FIXED_LEVELS_CHECK)
    op.drop_constraint("ck_invoices_cancellation", "invoices", type_="check")
    replace_check("invoicestatus", "invoices", f"status IN ({sql_list(PREVIOUS_STATUSES)})")
    op.drop_index("ix_invoices_cancelled_by", table_name="invoices")
    op.drop_constraint("fk_invoices_cancelled_by_users", "invoices", type_="foreignkey")
    op.drop_column("invoices", "cancellation_deadline")
    op.drop_column("invoices", "cancelled_by")
    op.drop_column("invoices", "cancelled_at")
