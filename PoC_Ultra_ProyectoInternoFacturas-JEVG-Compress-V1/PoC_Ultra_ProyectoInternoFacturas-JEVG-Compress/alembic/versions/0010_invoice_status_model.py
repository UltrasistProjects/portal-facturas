"""Modelo de estatus de la factura del ERS (HU-12, HU-13; EP-01 DT-01).

- Se retiran VALIDATING, VALIDATION_FAILED y PREVALIDATED: la validacion ocurre dentro del envio.
- Cada factura previa al envio (DRAFT, UPLOADED, VALIDATING, VALIDATION_FAILED, PREVALIDATED, REQUIRES_CORRECTION) se
  reasigna:
  - REQUIRES_CORRECTION si su ultima revision con decision (no COMMENT) es REQUIRES_CORRECTION: el PMO la devolvio y
    aun no se reenvia;
  - UPLOADED si tiene completos los archivos obligatorios vigentes para el origen de su proveedor; DRAFT si no. Es la
    misma regla que el checklist de HU-04.
- Cada factura cuyo estatus cambia recibe un registro de auditoria STATUS_MIGRATED.
- El CHECK invoicestatus queda con los 8 estatus vigentes.
- El downgrade restaura el CHECK de 11 estatus. Los estatus migrados no se revierten: todos son validos antes.
"""

from alembic import op

revision = "0010_invoice_status_model"
down_revision = "0009_supplier_profile"
branch_labels = None
depends_on = None

PREVIOUS_STATUSES = (
    "DRAFT",
    "UPLOADED",
    "VALIDATING",
    "VALIDATION_FAILED",
    "REQUIRES_CORRECTION",
    "PREVALIDATED",
    "UNDER_REVIEW",
    "ACCEPTED",
    "REJECTED",
    "READY_FOR_CLICKBALANCE",
    "UPLOADED_TO_CLICKBALANCE",
)
RETIRED = ("VALIDATING", "VALIDATION_FAILED", "PREVALIDATED")
STATUSES = tuple(status for status in PREVIOUS_STATUSES if status not in RETIRED)
PRE_SUBMISSION = ("DRAFT", "UPLOADED", "VALIDATING", "VALIDATION_FAILED", "PREVALIDATED", "REQUIRES_CORRECTION")


def sql_list(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


MIGRATE_STATUSES = f"""
WITH candidates AS (
    SELECT
        i.id,
        i.status AS old_status,
        CASE
            WHEN (
                SELECT r.decision FROM reviews r
                WHERE r.invoice_id = i.id AND r.decision <> 'COMMENT'
                ORDER BY r.created_at DESC, r.id DESC
                LIMIT 1
            ) = 'REQUIRES_CORRECTION' THEN 'REQUIRES_CORRECTION'
            WHEN NOT EXISTS (
                SELECT 1 FROM invoice_document_types t
                WHERE t.is_active
                  AND CASE s.origin
                          WHEN 'INTERNATIONAL' THEN t.international_requirement
                          ELSE t.national_requirement
                      END = 'REQUIRED'
                  AND NOT EXISTS (
                      SELECT 1 FROM documents d
                      WHERE d.invoice_id = i.id AND d.is_current AND d.document_type = t.code
                  )
            ) THEN 'UPLOADED'
            ELSE 'DRAFT'
        END AS new_status
    FROM invoices i
    JOIN suppliers s ON s.id = i.supplier_id
    WHERE i.status IN ({sql_list(PRE_SUBMISSION)})
),
changed AS (
    UPDATE invoices i SET status = c.new_status
    FROM candidates c
    WHERE i.id = c.id AND c.new_status <> c.old_status
    RETURNING i.id, c.old_status, c.new_status
)
INSERT INTO audit_logs (action, entity, entity_id, old_value, new_value, timestamp)
SELECT 'STATUS_MIGRATED', 'Invoice', id::text, jsonb_build_object('status', old_status),
       jsonb_build_object('status', new_status), now()
FROM changed
"""


def replace_status_check(statuses: tuple[str, ...]) -> None:
    op.drop_constraint("invoicestatus", "invoices", type_="check")
    op.create_check_constraint("invoicestatus", "invoices", f"status IN ({sql_list(statuses)})")


def upgrade() -> None:
    # Primero los datos: los estatus destino tambien son validos en el CHECK anterior.
    op.execute(MIGRATE_STATUSES)
    replace_status_check(STATUSES)


def downgrade() -> None:
    replace_status_check(PREVIOUS_STATUSES)
