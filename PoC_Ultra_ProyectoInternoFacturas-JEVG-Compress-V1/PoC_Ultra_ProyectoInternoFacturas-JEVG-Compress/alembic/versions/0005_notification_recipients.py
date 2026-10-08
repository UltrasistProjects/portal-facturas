"""Destinatarios de notificaciones y bitacora de envios de correo (HU-08).

- notification_mailboxes: buzones de destino; se siembra Recepcion de Facturas con recepcionfacturas@ultrasist.com.mx
  (minuta del 21-sep-2026).
- notification_copies: direcciones en copia por evento; una fila vacia por cada evento de estatus de factura.
- email_deliveries: un registro por intento de envio, sin asunto ni cuerpo.
"""

from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005_notification_recipients"
down_revision = "0004_notification_templates"
branch_labels = None
depends_on = None

EVENTS = ("INVOICE_AUTHORIZED", "INVOICE_REJECTED", "INVOICE_OBSERVATIONS", "INVOICE_CANCELLED")
RECEPTION_ADDRESS = "recepcionfacturas@ultrasist.com.mx"


def event_column(nullable: bool) -> sa.Column:
    return sa.Column(
        "event",
        sa.Enum(*EVENTS, name="notificationevent", native_enum=False, create_constraint=True),
        nullable=nullable,
    )


def updated_by_column(table: str) -> tuple[sa.Column, sa.ForeignKeyConstraint]:
    return (
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["updated_by"], ["users.id"], name=op.f(f"fk_{table}_updated_by_users"), ondelete="RESTRICT"
        ),
    )


def upgrade() -> None:
    mailboxes = op.create_table(
        "notification_mailboxes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "code",
            sa.Enum("INVOICE_RECEPTION", name="mailbox", native_enum=False, create_constraint=True),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("addresses", postgresql.ARRAY(sa.String(length=254)), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        *updated_by_column("notification_mailboxes"),
        sa.CheckConstraint("cardinality(addresses) BETWEEN 1 AND 10", name="ck_notification_mailboxes_addresses"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notification_mailboxes")),
        sa.UniqueConstraint("code", name="uq_notification_mailboxes_code"),
    )
    copies = op.create_table(
        "notification_copies",
        sa.Column("id", sa.Integer(), nullable=False),
        event_column(nullable=False),
        sa.Column("addresses", postgresql.ARRAY(sa.String(length=254)), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        *updated_by_column("notification_copies"),
        sa.CheckConstraint("cardinality(addresses) <= 10", name="ck_notification_copies_addresses"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notification_copies")),
        sa.UniqueConstraint("event", name="uq_notification_copies_event"),
    )
    op.create_table(
        "email_deliveries",
        sa.Column("id", sa.Integer(), nullable=False),
        event_column(nullable=True),
        sa.Column(
            "status",
            sa.Enum("SENT", "FAILED", name="deliverystatus", native_enum=False, create_constraint=True),
            nullable=False,
        ),
        sa.Column("to_addresses", postgresql.ARRAY(sa.String(length=254)), nullable=False),
        sa.Column("cc_addresses", postgresql.ARRAY(sa.String(length=254)), nullable=False),
        sa.Column("transport", sa.String(length=10), nullable=False),
        sa.Column("message_id", sa.String(length=255), nullable=False),
        sa.Column("error", sa.String(length=300), nullable=True),
        sa.Column("entity", sa.String(length=80), nullable=True),
        sa.Column("entity_id", sa.String(length=80), nullable=True),
        sa.Column("requested_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("cardinality(to_addresses) >= 1", name="ck_email_deliveries_to_addresses"),
        sa.CheckConstraint("status <> 'FAILED' OR error IS NOT NULL", name="ck_email_deliveries_failed_error"),
        sa.ForeignKeyConstraint(
            ["requested_by"],
            ["users.id"],
            name=op.f("fk_email_deliveries_requested_by_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_email_deliveries")),
    )
    op.create_index("ix_email_deliveries_created_at", "email_deliveries", ["created_at"])
    op.create_index("ix_email_deliveries_entity", "email_deliveries", ["entity", "entity_id"])
    op.create_index("ix_email_deliveries_requested_by", "email_deliveries", ["requested_by"])

    now = datetime.now(timezone.utc)
    op.bulk_insert(
        mailboxes,
        [
            {
                "code": "INVOICE_RECEPTION",
                "name": "Recepción de Facturas",
                "addresses": [RECEPTION_ADDRESS],
                "updated_at": now,
                "updated_by": None,
            }
        ],
    )
    op.bulk_insert(
        copies, [{"event": event, "addresses": [], "updated_at": now, "updated_by": None} for event in EVENTS]
    )


def downgrade() -> None:
    bind = op.get_bind()
    modified = bind.scalar(
        sa.text(
            "SELECT (SELECT count(*) FROM notification_mailboxes WHERE updated_by IS NOT NULL)"
            " + (SELECT count(*) FROM notification_copies WHERE updated_by IS NOT NULL)"
            " + (SELECT count(*) FROM email_deliveries)"
        )
    )
    if modified:
        raise NotImplementedError(
            "Hay destinatarios modificados por el Administrador o envios de correo registrados: revertir perderia "
            "datos. Restaure un respaldo."
        )
    op.drop_table("email_deliveries")
    op.drop_table("notification_copies")
    op.drop_table("notification_mailboxes")
