"""Roles con los nombres del negocio (ERS): Administrador, Proveedor y PMO.

- users.role pasa de ADMIN / PROVIDER / INTERNAL a Administrador / Proveedor / PMO; la columna crece a VARCHAR(13).
- Se rehacen el CHECK role y ck_users_provider_supplier con los nombres nuevos.
- No se audita: el rol de cada usuario no cambia, solo su nombre. Los audit_logs previos conservan el nombre que
  tenia el rol al registrarse (evidencia).
- El downgrade restaura los nombres, la longitud y los CHECK anteriores.
"""

import sqlalchemy as sa
from alembic import op

revision = "0014_business_role_names"
down_revision = "0013_provider_user_supplier"
branch_labels = None
depends_on = None

PREVIOUS_TO_BUSINESS = {"ADMIN": "Administrador", "PROVIDER": "Proveedor", "INTERNAL": "PMO"}


def provider_supplier_check(provider: str) -> str:
    return (
        f"(role = '{provider}' AND (supplier_id IS NOT NULL OR NOT is_active))"
        f" OR (role <> '{provider}' AND supplier_id IS NULL)"
    )


def rename_roles(mapping: dict[str, str], provider: str, length: int) -> None:
    op.drop_constraint("ck_users_provider_supplier", "users", type_="check")
    op.drop_constraint("role", "users", type_="check")
    # Al reducir la longitud (downgrade), primero los datos: los nombres nuevos no caben en VARCHAR(8).
    cases = " ".join(f"WHEN '{old}' THEN '{new}'" for old, new in mapping.items())
    if length < 13:
        op.execute(f"UPDATE users SET role = CASE role {cases} END")
    op.alter_column("users", "role", type_=sa.String(length=length), existing_nullable=False)
    if length >= 13:
        op.execute(f"UPDATE users SET role = CASE role {cases} END")
    values = ", ".join(f"'{value}'" for value in mapping.values())
    op.create_check_constraint("role", "users", f"role IN ({values})")
    op.create_check_constraint("ck_users_provider_supplier", "users", provider_supplier_check(provider))


def upgrade() -> None:
    rename_roles(PREVIOUS_TO_BUSINESS, "Proveedor", 13)


def downgrade() -> None:
    rename_roles({new: old for old, new in PREVIOUS_TO_BUSINESS.items()}, "PROVIDER", 8)
