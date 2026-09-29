"""Retiro de los pasos de ClickBalance del PoC (HU-20; EP-02 DT-06).

- Las facturas READY_FOR_CLICKBALANCE y UPLOADED_TO_CLICKBALANCE pasan a ACCEPTED ("Autorizada"): el ERS termina en
  Autorizada. Cada factura migrada recibe un registro de auditoria STATUS_MIGRATED.
- El CHECK invoicestatus queda con los 6 estatus del ERS y la columna pasa de VARCHAR(24) a VARCHAR(19): la longitud
  de la enumeracion es la de su valor mas largo, que era UPLOADED_TO_CLICKBALANCE y ahora es REQUIRES_CORRECTION.
- El downgrade restaura el VARCHAR(24) y el CHECK de 8 estatus. Los estatus migrados no se revierten: ACCEPTED es
  valido antes.
"""

import sqlalchemy as sa
from alembic import op

revision = "0011_retire_clickbalance"
down_revision = "0010_invoice_status_model"
branch_labels = None
depends_on = None

STATUSES = ("DRAFT", "UPLOADED", "UNDER_REVIEW", "ACCEPTED", "REJECTED", "REQUIRES_CORRECTION")
RETIRED = ("READY_FOR_CLICKBALANCE", "UPLOADED_TO_CLICKBALANCE")


def sql_list(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


MIGRATE_STATUSES = f"""
WITH changed AS (
    UPDATE invoices i SET status = 'ACCEPTED'
    FROM (SELECT id, status FROM invoices WHERE status IN ({sql_list(RETIRED)})) previous
    WHERE i.id = previous.id
    RETURNING i.id, previous.status AS old_status
)
INSERT INTO audit_logs (action, entity, entity_id, old_value, new_value, timestamp)
SELECT 'STATUS_MIGRATED', 'Invoice', id::text, jsonb_build_object('status', old_status),
       jsonb_build_object('status', 'ACCEPTED'), now()
FROM changed
"""


def replace_status_check(statuses: tuple[str, ...]) -> None:
    op.drop_constraint("invoicestatus", "invoices", type_="check")
    op.create_check_constraint("invoicestatus", "invoices", f"status IN ({sql_list(statuses)})")


def upgrade() -> None:
    # Primero los datos: ACCEPTED tambien es valido en el CHECK anterior y cabe en la columna mas corta.
    op.execute(MIGRATE_STATUSES)
    replace_status_check(STATUSES)
    op.alter_column(
        "invoices", "status", existing_type=sa.String(length=24), type_=sa.String(length=19), existing_nullable=False
    )


def downgrade() -> None:
    op.alter_column(
        "invoices", "status", existing_type=sa.String(length=19), type_=sa.String(length=24), existing_nullable=False
    )
    replace_status_check((*STATUSES, *RETIRED))
