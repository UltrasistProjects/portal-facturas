"""Trazabilidad de contratos y enmiendas del monto autorizado (AUDITORIA BD-09).

Los contratos existentes reciben la marca temporal de la migracion en created_at/updated_at y NULL en created_by/
updated_by (su autor original no se registro).
"""

from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "0005_trazabilidad_contratos"
down_revision = "0004_integridad_datos"
branch_labels = None
depends_on = None

NAMING = {"fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"}


def upgrade() -> None:
    op.create_table(
        "contract_amendments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("contract_id", sa.Integer(), nullable=False),
        sa.Column("previous_amount_cents", sa.Integer(), nullable=False),
        sa.Column("new_amount_cents", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("new_amount_cents > 0", name="ck_contract_amendments_new_amount_positive"),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_contract_amendments_contract_id", "contract_amendments", ["contract_id"], unique=False)
    op.create_index("ix_contract_amendments_created_by", "contract_amendments", ["created_by"], unique=False)

    migrated_at = datetime.now(timezone.utc).replace(tzinfo=None).isoformat(sep=" ")
    with op.batch_alter_table("contracts", naming_convention=NAMING) as batch:
        batch.add_column(sa.Column("created_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("created_by", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("updated_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("updated_by", sa.Integer(), nullable=True))
    op.execute(sa.text("UPDATE contracts SET created_at = :at, updated_at = :at").bindparams(at=migrated_at))
    with op.batch_alter_table("contracts", naming_convention=NAMING) as batch:
        batch.alter_column("created_at", existing_type=sa.DateTime(), nullable=False)
        batch.alter_column("updated_at", existing_type=sa.DateTime(), nullable=False)
        batch.create_foreign_key("fk_contracts_created_by_users", "users", ["created_by"], ["id"], ondelete="RESTRICT")
        batch.create_foreign_key("fk_contracts_updated_by_users", "users", ["updated_by"], ["id"], ondelete="RESTRICT")


def downgrade() -> None:
    raise NotImplementedError("Revertir perderia el historial de enmiendas del monto autorizado. Restaure un respaldo.")
