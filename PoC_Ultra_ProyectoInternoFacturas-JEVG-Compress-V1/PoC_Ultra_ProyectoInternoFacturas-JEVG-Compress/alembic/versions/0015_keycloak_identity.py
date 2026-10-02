"""Identidad en Keycloak (change add-keycloak-authentication).

- users.keycloak_sub: identificador (sub) de la cuenta en Keycloak, con indice unico ix_users_keycloak_sub. El inicio de
  sesion enlaza al usuario solo por este valor (D7).
- users.password_hash pasa a nullable: las credenciales viven en Keycloak y el portal no guarda hashes (RN-HU03-01).
  La columna queda obsoleta; se elimina en el cambio de limpieza, cuando todos los usuarios esten enlazados.
- user_sessions.id_token_hint: ID token de la sesion, solo del lado del servidor, para cerrar la sesion en Keycloak.
- Se elimina login_attempts: la limitacion de intentos pasa a Keycloak (deteccion de fuerza bruta del realm). Sus filas
  solo se conservaban 24 horas.
- El downgrade recrea login_attempts vacia y revierte lo demas. Con usuarios sin password_hash (enlazados o creados en
  Keycloak) no puede restaurar el NOT NULL: se detiene antes de cambiar nada y pide restaurar un respaldo.
"""

import sqlalchemy as sa
from alembic import op

revision = "0015_keycloak_identity"
down_revision = "0014_business_role_names"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("keycloak_sub", sa.String(length=36), nullable=True))
    op.create_index("ix_users_keycloak_sub", "users", ["keycloak_sub"], unique=True)
    op.alter_column("users", "password_hash", existing_type=sa.String(length=512), nullable=True)
    op.add_column("user_sessions", sa.Column("id_token_hint", sa.Text(), nullable=True))
    op.drop_index("ix_login_attempts_ip_attempted_at", table_name="login_attempts")
    op.drop_index("ix_login_attempts_email_attempted_at", table_name="login_attempts")
    op.drop_table("login_attempts")


def downgrade() -> None:
    without_hash = op.get_bind().scalar(sa.text("SELECT count(*) FROM users WHERE password_hash IS NULL"))
    if without_hash:
        raise NotImplementedError(
            f"Hay {without_hash} usuarios sin password_hash (sus credenciales estan en Keycloak): la version anterior"
            " no podria autenticarlos. Restaure un respaldo previo a la migracion (scripts/restore_backup.py)."
        )
    op.create_table(
        "login_attempts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("ip", sa.String(length=50), nullable=True),
        sa.Column(
            "result",
            sa.Enum("SUCCESS", "FAILURE", "THROTTLED", name="loginresult", native_enum=False, create_constraint=True),
            nullable=False,
        ),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_login_attempts")),
    )
    op.create_index("ix_login_attempts_email_attempted_at", "login_attempts", ["email", "attempted_at"], unique=False)
    op.create_index("ix_login_attempts_ip_attempted_at", "login_attempts", ["ip", "attempted_at"], unique=False)
    op.drop_column("user_sessions", "id_token_hint")
    op.alter_column("users", "password_hash", existing_type=sa.String(length=512), nullable=False)
    op.drop_index("ix_users_keycloak_sub", table_name="users")
    op.drop_column("users", "keycloak_sub")
