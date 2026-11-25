"""Ferromex: "Marcar como pagada" pasa a "Programar pago" y la factura queda "Programado para pago".

- El estatus PAID se conserva; solo cambia su etiqueta (app/core/constants.py), sin cambio de esquema.
- La plantilla INVOICE_PAID cambia su texto predeterminado: "Factura {{numero_factura}} programada para pago". Solo
  se actualiza si nadie la ha modificado (updated_by IS NULL y el texto sigue siendo el predeterminado de 0018); una
  plantilla personalizada por el Administrador se conserva. La version no cambia: es el texto inicial, no una edicion.
- El downgrade restaura el texto anterior con la misma condicion.
"""

import sqlalchemy as sa
from alembic import op

revision = "0024_ferromex_programar_pago"
down_revision = "0023_ferromex_purchase_orders"
branch_labels = None
depends_on = None

SUPPLIER_FOOTER = (
    "Puede consultar el detalle en el Portal de Proveedores FERROMEX. "
    "Este es un mensaje automático; no responda a este correo."
)
PREVIOUS = (
    "Factura {{numero_factura}} pagada",
    "{{proveedor}}:\n\n"
    "Su factura número {{numero_factura}} ha sido pagada.\n\n"
    "{{aviso_complemento}}\n\n"
    "Folio interno: {{folio_interno}}\n"
    "Monto: {{monto}}\n"
    "Fecha de pago: {{fecha_estatus}}\n\n" + SUPPLIER_FOOTER,
)
# Textos predeterminados de app/services/notification_templates.py (una prueba verifica que coinciden).
SCHEDULED = (
    "Factura {{numero_factura}} programada para pago",
    "{{proveedor}}:\n\n"
    "Su factura número {{numero_factura}} ha sido programada para pago.\n\n"
    "{{aviso_complemento}}\n\n"
    "Folio interno: {{folio_interno}}\n"
    "Monto: {{monto}}\n"
    "Fecha de programación: {{fecha_estatus}}\n\n" + SUPPLIER_FOOTER,
)


def _replace(old: tuple[str, str], new: tuple[str, str]) -> None:
    op.get_bind().execute(
        sa.text(
            "UPDATE notification_templates SET subject = :new_subject, body = :new_body "
            "WHERE event = 'INVOICE_PAID' AND updated_by IS NULL AND subject = :old_subject AND body = :old_body"
        ),
        {"new_subject": new[0], "new_body": new[1], "old_subject": old[0], "old_body": old[1]},
    )


def upgrade() -> None:
    _replace(PREVIOUS, SCHEDULED)


def downgrade() -> None:
    _replace(SCHEDULED, PREVIOUS)
