"""Orden de compra en lugar del contrato (HU-24, rama ferromex).

- purchase_orders: convenio de SAP (unico, > 0), RFC y nombre del proveedor, fecha, total (> 0) e impuestos (>= 0), y
  las partidas en data (JSONB, al menos una). supplier_id (FK RESTRICT, nulo) liga la orden del proveedor
  internacional, cuyo RFC en SAP es generico.
- invoices.purchase_order_id (FK RESTRICT, con indice): la orden a la que se liga la factura al enviarse.
- invoices.project_name admite nulo: las facturas nuevas no tienen proyecto ni lider.
- Archivos de la factura (HU-04): el XML del CFDI pasa a Opcional para el nacional; Orden de compra, Contrato y Anexo
  del contrato pasan a No aplica en ambos origenes. Los documentos ya cargados no cambian.
- Reglas de Validacion del receptor con los datos de INTERMODAL MEXICO (P-01): RFC, razon social, codigo postal y
  regimen (XML-011 deja de estar eliminada), nacionales e internacionales.

No toca contratos: contracts, contract_amendments, contract_document_types, documents.contract_id e
invoices.contract_id se conservan con sus datos, sin uso (P-02). El downgrade se niega si hay ordenes de compra o
facturas ligadas a una orden.
"""

from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0023_ferromex_purchase_orders"
down_revision = "0022_stored_files"
branch_labels = None
depends_on = None

REQ, OPT, NA = "REQUIRED", "OPTIONAL", "NOT_APPLICABLE"
# Tipo de documento de factura -> ((nacional, internacional) nuevo, (nacional, internacional) de 0003).
DOCUMENT_LEVELS = {
    "INVOICE_XML": ((OPT, NA), (REQ, NA)),
    "PURCHASE_ORDER": ((NA, NA), (REQ, REQ)),
    "CONTRACT": ((NA, NA), (OPT, OPT)),
    "CONTRACT_ANNEX": ((NA, NA), (OPT, OPT)),
}
# Receptor de los CFDI (P-01): (origen, regla) -> valor esperado. Las pruebas lo aplican despues de 0020 para volver
# a la instalacion inicial.
RECEIVER = {
    ("NATIONAL", "XML-002"): "IME010718PU3",
    ("NATIONAL", "XML-009"): "INTERMODAL MEXICO",
    ("NATIONAL", "XML-010"): "11700",
    ("NATIONAL", "XML-011"): "601",
    ("INTERNATIONAL", "INT-002"): "INTERMODAL MEXICO",
    ("INTERNATIONAL", "INT-003"): "11700",
}
# Valores de 0007/0020, para el downgrade. XML-011 nacia eliminada.
PREVIOUS = {
    ("NATIONAL", "XML-002"): "ULT940623AG0",
    ("NATIONAL", "XML-009"): "FERROMEX",
    ("NATIONAL", "XML-010"): "03930",
    ("NATIONAL", "XML-011"): "601",
    ("INTERNATIONAL", "INT-002"): "FERROMEX",
    ("INTERNATIONAL", "INT-003"): "03930",
}
ACTIVATED = {("NATIONAL", "XML-011")}


def _set_levels(levels: dict[str, tuple[str, str]], now: datetime) -> None:
    for code, (national, international) in levels.items():
        op.execute(
            sa.text(
                "UPDATE invoice_document_types SET national_requirement = :national, "
                "international_requirement = :international, updated_at = :now WHERE code = :code"
            ).bindparams(national=national, international=international, now=now, code=code)
        )


def _set_rules(values: dict[tuple[str, str], str], active: bool, now: datetime) -> None:
    """Valor esperado de cada regla; las de ACTIVATED quedan activas (upgrade) o eliminadas (downgrade). La version
    no cambia: la migracion corre con la aplicacion detenida, sin formularios abiertos."""
    for (origin, code), parameter in values.items():
        op.execute(
            sa.text(
                "UPDATE validation_rules SET parameter = to_jsonb(CAST(:parameter AS text)), updated_at = :now "
                "WHERE origin = :origin AND rule_code = :code"
            ).bindparams(parameter=parameter, now=now, origin=origin, code=code)
        )
    for origin, code in ACTIVATED:
        op.execute(
            sa.text(
                "UPDATE validation_rules SET is_active = :active, deleted_at = :deleted_at, deleted_by = NULL "
                "WHERE origin = :origin AND rule_code = :code"
            ).bindparams(active=active, deleted_at=None if active else now, origin=origin, code=code)
        )


def upgrade() -> None:
    op.create_table(
        "purchase_orders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("convenio", sa.BigInteger(), nullable=False),
        sa.Column("rfc", sa.String(length=13), nullable=False),
        sa.Column("supplier_name", sa.String(length=150), nullable=False),
        sa.Column("order_date", sa.Date(), nullable=False),
        sa.Column("total", sa.Numeric(precision=16, scale=2), nullable=False),
        sa.Column("taxes", sa.Numeric(precision=16, scale=2), nullable=False),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("supplier_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("convenio > 0", name="ck_purchase_orders_convenio_positive"),
        sa.CheckConstraint("total > 0", name="ck_purchase_orders_total_positive"),
        sa.CheckConstraint("taxes >= 0", name="ck_purchase_orders_taxes_non_negative"),
        sa.CheckConstraint("char_length(rfc) BETWEEN 12 AND 13", name="ck_purchase_orders_rfc_length"),
        sa.CheckConstraint(
            "CASE WHEN jsonb_typeof(data -> 'items') = 'array' THEN jsonb_array_length(data -> 'items') >= 1"
            " ELSE false END",
            name="ck_purchase_orders_items",
        ),
        sa.ForeignKeyConstraint(
            ["supplier_id"],
            ["suppliers.id"],
            name=op.f("fk_purchase_orders_supplier_id_suppliers"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_purchase_orders")),
        sa.UniqueConstraint("convenio", name="uq_purchase_orders_convenio"),
    )
    op.create_index(op.f("ix_purchase_orders_rfc"), "purchase_orders", ["rfc"], unique=False)
    op.create_index(op.f("ix_purchase_orders_supplier_id"), "purchase_orders", ["supplier_id"], unique=False)
    op.add_column("invoices", sa.Column("purchase_order_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        op.f("fk_invoices_purchase_order_id_purchase_orders"),
        "invoices",
        "purchase_orders",
        ["purchase_order_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(op.f("ix_invoices_purchase_order_id"), "invoices", ["purchase_order_id"], unique=False)
    op.alter_column("invoices", "project_name", existing_type=sa.String(length=200), nullable=True)
    now = datetime.now(timezone.utc)
    _set_levels({code: new for code, (new, _) in DOCUMENT_LEVELS.items()}, now)
    _set_rules(RECEIVER, True, now)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.scalar(sa.text("SELECT count(*) FROM purchase_orders")) or bind.scalar(
        sa.text("SELECT count(*) FROM invoices WHERE purchase_order_id IS NOT NULL")
    ):
        raise NotImplementedError(
            "Hay ordenes de compra o facturas ligadas a una orden: revertir perderia esa informacion. "
            "Restaure un respaldo."
        )
    now = datetime.now(timezone.utc)
    _set_rules(PREVIOUS, False, now)
    _set_levels({code: old for code, (_, old) in DOCUMENT_LEVELS.items()}, now)
    if not bind.scalar(sa.text("SELECT count(*) FROM invoices WHERE project_name IS NULL")):
        op.alter_column("invoices", "project_name", existing_type=sa.String(length=200), nullable=False)
    op.drop_index(op.f("ix_invoices_purchase_order_id"), table_name="invoices")
    op.drop_constraint(op.f("fk_invoices_purchase_order_id_purchase_orders"), "invoices", type_="foreignkey")
    op.drop_column("invoices", "purchase_order_id")
    op.drop_index(op.f("ix_purchase_orders_supplier_id"), table_name="purchase_orders")
    op.drop_index(op.f("ix_purchase_orders_rfc"), table_name="purchase_orders")
    op.drop_table("purchase_orders")
