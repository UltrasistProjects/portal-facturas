"""Cambio obligatorio de la contrasena asignada (HU-10).

- users.must_change_password: el usuario debe cambiar su contrasena antes de usar el portal.
- Se marca a todo usuario con un registro de auditoria USER_CREATED: los creados por la autorizacion de proveedores o
  por /admin/users. Hasta esta revision nadie podia cambiar su propia contrasena, asi que todos conservan la que les
  asigno otra persona. El seed no audita sus altas: los usuarios demo no se marcan.
- El downgrade elimina la columna; la version anterior no la usa.
"""

import sqlalchemy as sa
from alembic import op

revision = "0008_password_change_required"
down_revision = "0007_validation_rules_catalogs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("must_change_password", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.execute(
        "UPDATE users SET must_change_password = true WHERE id::text IN "
        "(SELECT entity_id FROM audit_logs WHERE action = 'USER_CREATED' AND entity = 'User')"
    )


def downgrade() -> None:
    op.drop_column("users", "must_change_password")
