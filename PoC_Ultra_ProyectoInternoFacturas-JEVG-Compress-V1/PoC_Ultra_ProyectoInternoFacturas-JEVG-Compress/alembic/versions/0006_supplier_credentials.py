"""Correo de credenciales del proveedor autorizado (HU-03).

- Agrega SUPPLIER_CREDENTIALS al CHECK de la enumeracion de eventos de notification_templates, notification_copies y
  email_deliveries.
- Siembra la plantilla "Credenciales de acceso" en la version 1, sin Administrador. El texto se copia aqui y no se
  importa de app; una prueba verifica que coincide con app/services/notification_templates.py.
"""

from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "0006_supplier_credentials"
down_revision = "0005_notification_recipients"
branch_labels = None
depends_on = None

INVOICE_EVENTS = ("INVOICE_AUTHORIZED", "INVOICE_REJECTED", "INVOICE_OBSERVATIONS", "INVOICE_CANCELLED")
EVENTS = (*INVOICE_EVENTS, "SUPPLIER_CREDENTIALS")
TABLES = ("notification_templates", "notification_copies", "email_deliveries")
SUBJECT = "Acceso al Portal de Proveedores ULTRASIST"
BODY = (
    "{{proveedor}}:\n\n"
    "Su registro como proveedor de ULTRASIST fue autorizado. Estos son sus datos para ingresar por primera vez "
    "al Portal de Proveedores:\n\n"
    "Portal: {{url_portal}}\n"
    "Usuario: {{usuario}}\n"
    "Contraseña temporal: {{contrasena_temporal}}\n\n"
    "Por seguridad, no comparta esta contraseña y cámbiela al ingresar por primera vez.\n\n"
    "Este es un mensaje automático del Portal de Proveedores ULTRASIST. No responda a este correo."
)


def replace_event_checks(events: tuple[str, ...]) -> None:
    values = ", ".join(f"'{event}'" for event in events)
    for table in TABLES:
        op.drop_constraint("notificationevent", table, type_="check")
        op.create_check_constraint("notificationevent", table, f"event IN ({values})")


def upgrade() -> None:
    replace_event_checks(EVENTS)
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
            {
                "event": "SUPPLIER_CREDENTIALS",
                "subject": SUBJECT,
                "body": BODY,
                "version": 1,
                "updated_at": datetime.now(timezone.utc),
                "updated_by": None,
            }
        ],
    )


def downgrade() -> None:
    bind = op.get_bind()
    in_use = bind.scalar(
        sa.text(
            "SELECT (SELECT count(*) FROM notification_templates"
            "        WHERE event = 'SUPPLIER_CREDENTIALS' AND version > 1)"
            " + (SELECT count(*) FROM email_deliveries WHERE event = 'SUPPLIER_CREDENTIALS')"
        )
    )
    if in_use:
        raise NotImplementedError(
            "La plantilla de credenciales fue modificada o ya se enviaron credenciales: revertir perderia datos. "
            "Restaure un respaldo."
        )
    op.execute("DELETE FROM notification_templates WHERE event = 'SUPPLIER_CREDENTIALS'")
    replace_event_checks(INVOICE_EVENTS)
