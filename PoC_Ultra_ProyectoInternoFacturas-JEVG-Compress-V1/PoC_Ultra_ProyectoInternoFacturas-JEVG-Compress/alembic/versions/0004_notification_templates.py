"""Plantillas de correo de estatus de factura (HU-05).

- Tabla notification_templates: una fila por evento (Autorizada, Rechazada, Observaciones y Cancelada) con asunto,
  cuerpo, version (bloqueo optimista) y fecha y Administrador de la ultima modificacion.
- Siembra las cuatro plantillas en la version 1, sin Administrador, con el texto predeterminado. Los textos se copian
  aqui y no se importan de app; una prueba verifica que coinciden con app/services/notification_templates.py.
"""

from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "0004_notification_templates"
down_revision = "0003_invoice_document_types"
branch_labels = None
depends_on = None

EVENTS = ("INVOICE_AUTHORIZED", "INVOICE_REJECTED", "INVOICE_OBSERVATIONS", "INVOICE_CANCELLED")
RECEPTION_FOOTER = "Este es un mensaje automático del Portal de Proveedores ULTRASIST. No responda a este correo."
SUPPLIER_FOOTER = (
    "Puede consultar el detalle en el Portal de Proveedores ULTRASIST. "
    "Este es un mensaje automático; no responda a este correo."
)
SUPPLIER_DETAILS = (
    "{{observaciones}}\n\nFolio interno: {{folio_interno}}\nFecha: {{fecha_estatus}}\n\n" + SUPPLIER_FOOTER
)
# (evento, asunto, cuerpo), en el orden del catalogo.
TEMPLATES = [
    (
        "INVOICE_AUTHORIZED",
        "Factura {{numero_factura}} autorizada para pago",
        "Recepción de Facturas:\n\n"
        "La factura número {{numero_factura}} del proveedor {{proveedor}} por el monto {{monto}} "
        "ha sido Autorizada para su pago.\n\n"
        "Folio interno: {{folio_interno}}\n"
        "Fecha de autorización: {{fecha_estatus}}\n\n" + RECEPTION_FOOTER,
    ),
    (
        "INVOICE_REJECTED",
        "Factura {{numero_factura}} rechazada",
        "{{proveedor}}:\n\n"
        "La factura número {{numero_factura}} ha sido “Rechazada” por la siguiente causa:\n\n" + SUPPLIER_DETAILS,
    ),
    (
        "INVOICE_OBSERVATIONS",
        "Factura {{numero_factura}} con observaciones",
        "{{proveedor}}:\n\n"
        "La factura número {{numero_factura}} tiene “Observaciones” por la siguiente causa:\n\n" + SUPPLIER_DETAILS,
    ),
    (
        "INVOICE_CANCELLED",
        "Cancelación de la factura {{numero_factura}} de {{proveedor}}",
        "Recepción de Facturas:\n\n"
        "La factura número {{numero_factura}} del proveedor {{proveedor}} ha sido cancelada. "
        "Por favor acepte la “Cancelación” antes del {{fecha_limite_cancelacion}}.\n\n"
        "Folio interno: {{folio_interno}}\n"
        "Monto: {{monto}}\n"
        "Fecha de la solicitud: {{fecha_estatus}}\n\n" + RECEPTION_FOOTER,
    ),
]


def upgrade() -> None:
    table = op.create_table(
        "notification_templates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "event",
            sa.Enum(*EVENTS, name="notificationevent", native_enum=False, create_constraint=True),
            nullable=False,
        ),
        sa.Column("subject", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.CheckConstraint("char_length(subject) BETWEEN 1 AND 200", name="ck_notification_templates_subject_length"),
        sa.CheckConstraint("char_length(body) BETWEEN 1 AND 5000", name="ck_notification_templates_body_length"),
        sa.CheckConstraint("version >= 1", name="ck_notification_templates_version_positive"),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["users.id"],
            name=op.f("fk_notification_templates_updated_by_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notification_templates")),
        sa.UniqueConstraint("event", name="uq_notification_templates_event"),
    )
    now = datetime.now(timezone.utc)
    op.bulk_insert(
        table,
        [
            {"event": event, "subject": subject, "body": body, "version": 1, "updated_at": now, "updated_by": None}
            for event, subject, body in TEMPLATES
        ],
    )


def downgrade() -> None:
    modified = op.get_bind().scalar(sa.text("SELECT count(*) FROM notification_templates WHERE version > 1"))
    if modified:
        raise NotImplementedError(
            "Hay plantillas de correo modificadas por el Administrador: revertir perderia sus cambios. "
            "Restaure un respaldo."
        )
    op.drop_table("notification_templates")
