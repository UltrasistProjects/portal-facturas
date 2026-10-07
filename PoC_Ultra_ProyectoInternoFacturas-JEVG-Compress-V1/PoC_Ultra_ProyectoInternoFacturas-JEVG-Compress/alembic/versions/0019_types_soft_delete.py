"""Baja logica de los tipos de documento de los tres catalogos de Requisitos minimos (ajustes-finales-configuracion).

- invoice_document_types, supplier_document_types y contract_document_types: deleted_at y deleted_by (FK a users con
  RESTRICT). Eliminar un tipo lo deja con is_active = false y la fecha y el autor de la baja; la fila no se borra. Los
  tipos que ya estaban inactivos quedan eliminados en su updated_at, sin autor. CHECK ck_<tabla>_soft_delete:
  is_active si y solo si deleted_at es nulo.
- Todo registro se puede editar y eliminar, tambien los precargados: se retiran ck_<tabla>_system_active y
  ck_<tabla>_fixed_levels. Los niveles vigentes no cambian.
- El downgrade reinstala los CHECK retirados solo si los datos los cumplen; si un tipo del sistema esta eliminado o un
  nivel fijo cambio, se niega: revertir perderia configuracion.
"""

import sqlalchemy as sa
from alembic import op

revision = "0019_types_soft_delete"
down_revision = "0018_invoice_payment"
branch_labels = None
depends_on = None

TABLES = ("invoice_document_types", "supplier_document_types", "contract_document_types")
SOFT_DELETE_CHECK = "is_active = (deleted_at IS NULL)"
SYSTEM_ACTIVE_CHECK = "is_active OR NOT is_system"
# Niveles fijos vigentes hasta 0018 (se copian aqui y no se importan de app).
FIXED_LEVELS = {
    "invoice_document_types": (
        "(code NOT IN ('INVOICE_XML', 'INVOICE_PDF')"
        " OR (national_requirement = 'REQUIRED' AND international_requirement = 'NOT_APPLICABLE'))"
        " AND (code <> 'FOREIGN_INVOICE'"
        " OR (national_requirement = 'NOT_APPLICABLE' AND international_requirement = 'REQUIRED'))"
        " AND (code <> 'CANCELLATION_ACK'"
        " OR (national_requirement = 'NOT_APPLICABLE' AND international_requirement = 'NOT_APPLICABLE'))"
        " AND (code NOT IN ('PAYMENT_COMPLEMENT_XML', 'PAYMENT_COMPLEMENT_PDF')"
        " OR (national_requirement = 'OPTIONAL' AND international_requirement = 'NOT_APPLICABLE'))"
    ),
    "supplier_document_types": (
        "code <> 'SUPPLIER_CONTRACT' OR (persona_moral_requirement = 'NOT_APPLICABLE'"
        " AND persona_fisica_requirement = 'NOT_APPLICABLE' AND international_requirement = 'NOT_APPLICABLE')"
    ),
    "contract_document_types": "code <> 'SIGNED_CONTRACT' OR requirement = 'REQUIRED'",
}


def upgrade() -> None:
    for table in TABLES:
        op.drop_constraint(f"ck_{table}_system_active", table, type_="check")
        op.drop_constraint(f"ck_{table}_fixed_levels", table, type_="check")
        op.add_column(table, sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
        op.add_column(table, sa.Column("deleted_by", sa.Integer(), nullable=True))
        op.create_foreign_key(
            op.f(f"fk_{table}_deleted_by_users"), table, "users", ["deleted_by"], ["id"], ondelete="RESTRICT"
        )
        op.execute(f"UPDATE {table} SET deleted_at = updated_at WHERE NOT is_active")
        op.create_check_constraint(f"ck_{table}_soft_delete", table, SOFT_DELETE_CHECK)


def downgrade() -> None:
    bind = op.get_bind()
    for table in TABLES:
        condition = f"NOT ({SYSTEM_ACTIVE_CHECK}) OR NOT ({FIXED_LEVELS[table]})"
        violations = bind.scalar(sa.text(f"SELECT count(*) FROM {table} WHERE {condition}"))
        if violations:
            raise NotImplementedError(
                f"No se puede revertir 0019_types_soft_delete: {table} tiene tipos del sistema eliminados o"
                " niveles fijos modificados; revertir perderia configuracion. Restaure un respaldo."
            )
    for table in TABLES:
        op.drop_constraint(f"ck_{table}_soft_delete", table, type_="check")
        op.drop_constraint(op.f(f"fk_{table}_deleted_by_users"), table, type_="foreignkey")
        op.drop_column(table, "deleted_by")
        op.drop_column(table, "deleted_at")
        op.create_check_constraint(f"ck_{table}_system_active", table, SYSTEM_ACTIVE_CHECK)
        op.create_check_constraint(f"ck_{table}_fixed_levels", table, FIXED_LEVELS[table])
