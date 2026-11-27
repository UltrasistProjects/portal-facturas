"""Consumo de la lectura con IA: una fila por lectura de factura con Azure Document Intelligence y OpenAI.

Sin datos fiscales, contenido del documento ni llaves: proveedor, resultado, motivo, paginas, tokens y duraciones.
"""

import sqlalchemy as sa
from alembic import op

revision = "0026_ai_usage"
down_revision = "0025_ferromex_sin_complemento"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_usage",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provider", sa.String(60), nullable=False),
        sa.Column("outcome", sa.String(20), nullable=False),
        sa.Column("reason", sa.String(30), nullable=True),
        sa.Column("has_text", sa.Boolean(), nullable=False),
        sa.Column("source", sa.String(20), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("ocr_model", sa.String(60), nullable=True),
        sa.Column("ocr_pages", sa.Integer(), nullable=True),
        sa.Column("ocr_duration_ms", sa.Integer(), nullable=True),
        sa.Column("llm_service", sa.String(30), nullable=True),
        sa.Column("llm_model", sa.String(100), nullable=True),
        sa.Column("llm_duration_ms", sa.Integer(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("discrepancies", sa.Integer(), nullable=True),
        sa.CheckConstraint("outcome IN ('ok', 'incomplete', 'error')", name="ck_ai_usage_outcome"),
    )
    op.create_index("ix_ai_usage_created_at", "ai_usage", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_ai_usage_created_at", table_name="ai_usage")
    op.drop_table("ai_usage")
