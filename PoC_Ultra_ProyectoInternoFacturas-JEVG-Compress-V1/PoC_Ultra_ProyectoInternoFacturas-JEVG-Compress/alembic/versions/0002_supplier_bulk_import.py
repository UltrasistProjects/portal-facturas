"""Carga masiva de proveedores (HU-01): identidad fiscal por origen y estatus REGISTERED.

- suppliers.origin (NATIONAL / INTERNATIONAL), foreign_tax_id y country; rfc admite NULL (el proveedor internacional
  no tiene RFC propio). Los proveedores existentes quedan NATIONAL con country = 'MX'.
- CHECK supplierstatus admite REGISTERED; CHECK supplierorigin; UNIQUE (country, foreign_tax_id) y CHECK de
  coherencia entre el origen y la identidad fiscal.
"""

import sqlalchemy as sa
from alembic import op

revision = "0002_supplier_bulk_import"
down_revision = "0001_postgresql_baseline"
branch_labels = None
depends_on = None

IDENTITY_CHECK = (
    "(origin = 'NATIONAL' AND rfc IS NOT NULL AND foreign_tax_id IS NULL AND country = 'MX')"
    " OR (origin = 'INTERNATIONAL' AND rfc IS NULL AND foreign_tax_id IS NOT NULL AND country <> 'MX')"
)


def upgrade() -> None:
    op.add_column("suppliers", sa.Column("origin", sa.String(length=13), nullable=True))
    op.add_column("suppliers", sa.Column("foreign_tax_id", sa.String(length=40), nullable=True))
    op.add_column("suppliers", sa.Column("country", sa.String(length=2), nullable=True))
    op.execute("UPDATE suppliers SET origin = 'NATIONAL', country = 'MX'")
    op.alter_column("suppliers", "origin", existing_type=sa.String(length=13), nullable=False)
    op.alter_column("suppliers", "country", existing_type=sa.String(length=2), nullable=False)
    op.alter_column("suppliers", "rfc", existing_type=sa.String(length=13), nullable=True)
    op.create_check_constraint("supplierorigin", "suppliers", "origin IN ('NATIONAL', 'INTERNATIONAL')")
    # El Enum del modelo mide lo que su valor mas largo: REGISTERED amplia la columna de 8 a 10.
    op.drop_constraint("supplierstatus", "suppliers", type_="check")
    op.alter_column("suppliers", "status", existing_type=sa.String(length=8), type_=sa.String(length=10))
    op.create_check_constraint("supplierstatus", "suppliers", "status IN ('REGISTERED', 'ACTIVE', 'INACTIVE')")
    op.create_unique_constraint("uq_suppliers_country_foreign_tax_id", "suppliers", ["country", "foreign_tax_id"])
    op.create_check_constraint("ck_suppliers_origin_identity", "suppliers", IDENTITY_CHECK)


def downgrade() -> None:
    pending = op.get_bind().scalar(
        sa.text("SELECT count(*) FROM suppliers WHERE origin = 'INTERNATIONAL' OR status = 'REGISTERED'")
    )
    if pending:
        raise NotImplementedError(
            "Hay proveedores internacionales o en estatus REGISTERED: revertir perderia datos. Restaure un respaldo."
        )
    op.drop_constraint("ck_suppliers_origin_identity", "suppliers", type_="check")
    op.drop_constraint("uq_suppliers_country_foreign_tax_id", "suppliers", type_="unique")
    op.drop_constraint("supplierstatus", "suppliers", type_="check")
    op.alter_column("suppliers", "status", existing_type=sa.String(length=10), type_=sa.String(length=8))
    op.create_check_constraint("supplierstatus", "suppliers", "status IN ('ACTIVE', 'INACTIVE')")
    op.drop_constraint("supplierorigin", "suppliers", type_="check")
    op.alter_column("suppliers", "rfc", existing_type=sa.String(length=13), nullable=False)
    op.drop_column("suppliers", "country")
    op.drop_column("suppliers", "foreign_tax_id")
    op.drop_column("suppliers", "origin")
