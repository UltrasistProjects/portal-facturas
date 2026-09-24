"""Tabla login_attempts para limitar intentos de inicio de sesion por correo y por IP (AUDITORIA SEC-04)."""

import sqlalchemy as sa
from alembic import op

revision = "0003_login_attempts"
down_revision = "0002_indices"
branch_labels = None
depends_on = None


def upgrade() -> None:
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
        sa.Column("attempted_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_login_attempts_email_attempted_at", "login_attempts", ["email", "attempted_at"], unique=False)
    op.create_index("ix_login_attempts_ip_attempted_at", "login_attempts", ["ip", "attempted_at"], unique=False)


def downgrade() -> None:
    # Solo contiene intentos de login con retencion de 24 h; eliminarla no pierde datos de negocio.
    op.drop_index("ix_login_attempts_ip_attempted_at", table_name="login_attempts")
    op.drop_index("ix_login_attempts_email_attempted_at", table_name="login_attempts")
    op.drop_table("login_attempts")
