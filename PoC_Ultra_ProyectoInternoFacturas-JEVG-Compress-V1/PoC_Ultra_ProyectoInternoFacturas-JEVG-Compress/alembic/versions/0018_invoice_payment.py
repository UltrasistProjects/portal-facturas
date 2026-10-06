"""Pago de la factura y Complemento de Pago (HU Complemento de Pagos).

- invoices: paid_at, paid_by (FK a users con RESTRICT, indexada), payment_complement_due_at y
  payment_complement_received_at, con el CHECK ck_invoices_payment: una factura PAID tiene fecha y autor del pago, la
  fecha limite del complemento (si lo requiere) es posterior al pago y solo se recibe un complemento requerido; las
  demas no tienen ningun dato del pago. Indice parcial ix_invoices_pending_complement para los complementos
  pendientes de cada proveedor.
- El CHECK invoicestatus agrega PAID. La columna sigue en VARCHAR(19).
- El CHECK notificationevent de notification_templates, notification_copies y email_deliveries agrega INVOICE_PAID y
  PAYMENT_COMPLEMENT (caben en VARCHAR(20)); las dos plantillas nacen en la version 1 con su texto predeterminado y
  sus listas de copias vacias.
- invoice_document_types: PAYMENT_COMPLEMENT_XML y PAYMENT_COMPLEMENT_PDF quedan con nivel fijo Opcional para
  Nacional y No aplica para Internacional. Si el Administrador los habia cambiado, se normalizan y el cambio se
  audita (INVOICE_DOCUMENT_REQUIREMENTS_UPDATED, sin usuario).
- El downgrade se niega si hay facturas pagadas o envios de los eventos nuevos; si no, revierte en orden inverso.
"""

from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0018_invoice_payment"
down_revision = "0017_contract_document_types"
branch_labels = None
depends_on = None

PREVIOUS_STATUSES = ("DRAFT", "UPLOADED", "UNDER_REVIEW", "ACCEPTED", "REJECTED", "REQUIRES_CORRECTION", "CANCELLED")
STATUSES = (*PREVIOUS_STATUSES, "PAID")
PREVIOUS_EVENTS = (
    "INVOICE_AUTHORIZED",
    "INVOICE_REJECTED",
    "INVOICE_OBSERVATIONS",
    "INVOICE_CANCELLED",
    "SUPPLIER_CREDENTIALS",
)
NEW_EVENTS = ("INVOICE_PAID", "PAYMENT_COMPLEMENT")
EVENTS = (*PREVIOUS_EVENTS, *NEW_EVENTS)
EVENT_TABLES = ("notification_templates", "notification_copies", "email_deliveries")
PAYMENT_CHECK = (
    "(status = 'PAID' AND paid_at IS NOT NULL AND paid_by IS NOT NULL"
    " AND (payment_complement_due_at IS NULL OR payment_complement_due_at > paid_at)"
    " AND (payment_complement_received_at IS NULL OR payment_complement_due_at IS NOT NULL))"
    " OR (status <> 'PAID' AND paid_at IS NULL AND paid_by IS NULL"
    " AND payment_complement_due_at IS NULL AND payment_complement_received_at IS NULL)"
)
PENDING_COMPLEMENT_WHERE = (
    "status = 'PAID' AND payment_complement_due_at IS NOT NULL AND payment_complement_received_at IS NULL"
)
PREVIOUS_FIXED_LEVELS_CHECK = (
    "(code NOT IN ('INVOICE_XML', 'INVOICE_PDF')"
    " OR (national_requirement = 'REQUIRED' AND international_requirement = 'NOT_APPLICABLE'))"
    " AND (code <> 'FOREIGN_INVOICE'"
    " OR (national_requirement = 'NOT_APPLICABLE' AND international_requirement = 'REQUIRED'))"
    " AND (code <> 'CANCELLATION_ACK'"
    " OR (national_requirement = 'NOT_APPLICABLE' AND international_requirement = 'NOT_APPLICABLE'))"
)
COMPLEMENT_CODES = ("PAYMENT_COMPLEMENT_XML", "PAYMENT_COMPLEMENT_PDF")
FIXED_LEVELS_CHECK = (
    PREVIOUS_FIXED_LEVELS_CHECK + " AND (code NOT IN ('PAYMENT_COMPLEMENT_XML', 'PAYMENT_COMPLEMENT_PDF')"
    " OR (national_requirement = 'OPTIONAL' AND international_requirement = 'NOT_APPLICABLE'))"
)
FIXED_LEVELS = {"national": "OPTIONAL", "international": "NOT_APPLICABLE"}

SUPPLIER_FOOTER = (
    "Puede consultar el detalle en el Portal de Proveedores ULTRASIST. "
    "Este es un mensaje automático; no responda a este correo."
)
RECEPTION_FOOTER = "Este es un mensaje automático del Portal de Proveedores ULTRASIST. No responda a este correo."
# Textos predeterminados de app/services/notification_templates.py (una prueba verifica que coinciden).
TEMPLATES = [
    (
        "INVOICE_PAID",
        "Factura {{numero_factura}} pagada",
        "{{proveedor}}:\n\n"
        "Su factura número {{numero_factura}} ha sido pagada.\n\n"
        "{{aviso_complemento}}\n\n"
        "Folio interno: {{folio_interno}}\n"
        "Monto: {{monto}}\n"
        "Fecha de pago: {{fecha_estatus}}\n\n" + SUPPLIER_FOOTER,
    ),
    (
        "PAYMENT_COMPLEMENT",
        "Complemento de pago de la factura {{numero_factura}}",
        "Recepción de Facturas:\n\n"
        "El Complemento de Pago ha sido adjuntado a la factura {{numero_factura}} del proveedor {{proveedor}}.\n\n"
        "Folio interno: {{folio_interno}}\n"
        "Monto: {{monto}}\n"
        "Fecha de carga: {{fecha_estatus}}\n\n" + RECEPTION_FOOTER,
    ),
]


def sql_list(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def replace_check(name: str, table: str, condition: str) -> None:
    op.drop_constraint(name, table, type_="check")
    op.create_check_constraint(name, table, condition)


def _normalize_complement_levels(bind, now: datetime) -> None:
    """Deja los complementos en su nivel fijo; un cambio del Administrador se revierte y queda auditado."""
    rows = bind.execute(
        sa.text(
            "SELECT code, national_requirement, international_requirement FROM invoice_document_types "
            "WHERE code IN :codes"
        ).bindparams(sa.bindparam("codes", expanding=True)),
        {"codes": list(COMPLEMENT_CODES)},
    ).all()
    old, new = {}, {}
    for code, national, international in rows:
        current = {"national": national, "international": international}
        changed = {origin: level for origin, level in current.items() if level != FIXED_LEVELS[origin]}
        if changed:
            old[code] = changed
            new[code] = {origin: FIXED_LEVELS[origin] for origin in changed}
    if not old:
        return
    bind.execute(
        sa.text(
            "UPDATE invoice_document_types SET national_requirement = 'OPTIONAL', "
            "international_requirement = 'NOT_APPLICABLE', updated_at = :now WHERE code IN :codes"
        ).bindparams(sa.bindparam("codes", expanding=True)),
        {"codes": list(old), "now": now},
    )
    audit_logs = sa.table(
        "audit_logs",
        sa.column("action", sa.String),
        sa.column("entity", sa.String),
        sa.column("entity_id", sa.String),
        sa.column("old_value", postgresql.JSONB),
        sa.column("new_value", postgresql.JSONB),
        sa.column("timestamp", sa.DateTime(timezone=True)),
    )
    op.bulk_insert(
        audit_logs,
        [
            {
                "action": "INVOICE_DOCUMENT_REQUIREMENTS_UPDATED",
                "entity": "InvoiceDocumentType",
                "entity_id": None,
                "old_value": old,
                "new_value": new,
                "timestamp": now,
            }
        ],
    )


def upgrade() -> None:
    bind = op.get_bind()
    now = datetime.now(timezone.utc)
    op.add_column("invoices", sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("invoices", sa.Column("paid_by", sa.Integer(), nullable=True))
    op.add_column("invoices", sa.Column("payment_complement_due_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("invoices", sa.Column("payment_complement_received_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key("fk_invoices_paid_by_users", "invoices", "users", ["paid_by"], ["id"], ondelete="RESTRICT")
    op.create_index("ix_invoices_paid_by", "invoices", ["paid_by"], unique=False)
    op.create_index(
        "ix_invoices_pending_complement",
        "invoices",
        ["supplier_id", "payment_complement_due_at"],
        unique=False,
        postgresql_where=sa.text(PENDING_COMPLEMENT_WHERE),
    )
    replace_check("invoicestatus", "invoices", f"status IN ({sql_list(STATUSES)})")
    op.create_check_constraint("ck_invoices_payment", "invoices", PAYMENT_CHECK)

    for table in EVENT_TABLES:
        replace_check("notificationevent", table, f"event IN ({sql_list(EVENTS)})")
    templates = sa.table(
        "notification_templates",
        sa.column("event", sa.String),
        sa.column("subject", sa.String),
        sa.column("body", sa.Text),
        sa.column("version", sa.Integer),
        sa.column("updated_at", sa.DateTime(timezone=True)),
        sa.column("updated_by", sa.Integer),
    )
    op.bulk_insert(
        templates,
        [
            {"event": event, "subject": subject, "body": body, "version": 1, "updated_at": now, "updated_by": None}
            for event, subject, body in TEMPLATES
        ],
    )
    copies = sa.table(
        "notification_copies",
        sa.column("event", sa.String),
        sa.column("addresses", postgresql.ARRAY(sa.String)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
        sa.column("updated_by", sa.Integer),
    )
    op.bulk_insert(
        copies, [{"event": event, "addresses": [], "updated_at": now, "updated_by": None} for event in NEW_EVENTS]
    )

    _normalize_complement_levels(bind, now)
    replace_check("ck_invoice_document_types_fixed_levels", "invoice_document_types", FIXED_LEVELS_CHECK)


def downgrade() -> None:
    bind = op.get_bind()
    paid = bind.scalar(sa.text("SELECT count(*) FROM invoices WHERE status = 'PAID'"))
    deliveries = bind.scalar(
        sa.text("SELECT count(*) FROM email_deliveries WHERE event IN :events").bindparams(
            sa.bindparam("events", expanding=True)
        ),
        {"events": list(NEW_EVENTS)},
    )
    if paid or deliveries:
        raise NotImplementedError(
            "Hay facturas pagadas o correos de pago y de complemento enviados: no existen antes de la HU Complemento "
            "de Pagos. Restaure un respaldo."
        )
    replace_check("ck_invoice_document_types_fixed_levels", "invoice_document_types", PREVIOUS_FIXED_LEVELS_CHECK)
    for table in ("notification_copies", "notification_templates"):
        bind.execute(
            sa.text(f"DELETE FROM {table} WHERE event IN :events").bindparams(sa.bindparam("events", expanding=True)),
            {"events": list(NEW_EVENTS)},
        )
    for table in EVENT_TABLES:
        replace_check("notificationevent", table, f"event IN ({sql_list(PREVIOUS_EVENTS)})")
    op.drop_constraint("ck_invoices_payment", "invoices", type_="check")
    replace_check("invoicestatus", "invoices", f"status IN ({sql_list(PREVIOUS_STATUSES)})")
    op.drop_index("ix_invoices_pending_complement", table_name="invoices")
    op.drop_index("ix_invoices_paid_by", table_name="invoices")
    op.drop_constraint("fk_invoices_paid_by_users", "invoices", type_="foreignkey")
    op.drop_column("invoices", "payment_complement_received_at")
    op.drop_column("invoices", "payment_complement_due_at")
    op.drop_column("invoices", "paid_by")
    op.drop_column("invoices", "paid_at")
