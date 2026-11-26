"""Ferromex: el portal ya no da seguimiento al Complemento de Pago.

- Da de baja (baja logica, como "Eliminar" en Archivos minimos) los tipos PAYMENT_COMPLEMENT_XML y
  PAYMENT_COMPLEMENT_PDF. Con el tipo XML inactivo ninguna factura requiere complemento al programar su pago, los
  vencidos no bloquean el envio y el portal no muestra avisos, paneles ni fechas limite del complemento
  (app/services/payment_service.py). El Administrador puede reactivarlos desde Archivos minimos.
- La baja no tiene autor (deleted_by nulo): asi la distingue el downgrade, que reactiva solo las de esta migracion.
- No toca las facturas: la fecha limite ya registrada se conserva y vuelve a mostrarse si se reactiva el tipo.
"""

from alembic import op

revision = "0025_ferromex_sin_complemento"
down_revision = "0024_ferromex_programar_pago"
branch_labels = None
depends_on = None

CODES = "('PAYMENT_COMPLEMENT_XML', 'PAYMENT_COMPLEMENT_PDF')"


def upgrade() -> None:
    op.execute(
        "UPDATE invoice_document_types SET is_active = false, deleted_at = now(), deleted_by = NULL "
        f"WHERE code IN {CODES} AND is_active"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE invoice_document_types SET is_active = true, deleted_at = NULL "
        f"WHERE code IN {CODES} AND NOT is_active AND deleted_by IS NULL"
    )
