"""Esquema inicial de la PoC.

Snapshot explicito del esquema previo a la remediacion de la auditoria (2026-09-22). No importa los modelos ORM:
el historial de esquema no debe cambiar cuando cambian los modelos. Todo cambio posterior va en una revision nueva.
"""

import sqlalchemy as sa
from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "suppliers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("business_name", sa.String(length=250), nullable=False),
        sa.Column("rfc", sa.String(length=13), nullable=False),
        sa.Column("supplier_type", sa.Enum("PERSONA_FISICA", "PERSONA_MORAL", name="suppliertype"), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=30), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("confidentiality_agreement", sa.Boolean(), nullable=False),
        sa.Column("economic_proposal", sa.Boolean(), nullable=False),
        sa.Column("bank_information", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_suppliers_rfc"), "suppliers", ["rfc"], unique=True)
    op.create_table(
        "contracts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("supplier_id", sa.Integer(), nullable=False),
        sa.Column("project_name", sa.String(length=200), nullable=False),
        sa.Column("project_leader", sa.String(length=150), nullable=False),
        sa.Column("authorized_technology", sa.String(length=250), nullable=False),
        sa.Column("authorized_amount", sa.Numeric(precision=16, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["supplier_id"],
            ["suppliers.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_contracts_supplier_id"), "contracts", ["supplier_id"], unique=False)
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=512), nullable=False),
        sa.Column("role", sa.Enum("PROVIDER", "INTERNAL", "ADMIN", name="role"), nullable=False),
        sa.Column("supplier_id", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["supplier_id"],
            ["suppliers.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)
    op.create_index(op.f("ix_users_role"), "users", ["role"], unique=False)
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("entity", sa.String(length=80), nullable=False),
        sa.Column("entity_id", sa.String(length=80), nullable=True),
        sa.Column("old_value", sa.JSON(), nullable=True),
        sa.Column("new_value", sa.JSON(), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ip_address", sa.String(length=50), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_audit_logs_action"), "audit_logs", ["action"], unique=False)
    op.create_index(op.f("ix_audit_logs_timestamp"), "audit_logs", ["timestamp"], unique=False)
    op.create_index(op.f("ix_audit_logs_user_id"), "audit_logs", ["user_id"], unique=False)
    op.create_table(
        "invoices",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("internal_folio", sa.String(length=30), nullable=False),
        sa.Column("supplier_id", sa.Integer(), nullable=False),
        sa.Column("uploaded_by", sa.Integer(), nullable=False),
        sa.Column("contract_id", sa.Integer(), nullable=True),
        sa.Column("invoice_number", sa.String(length=100), nullable=False),
        sa.Column("uuid", sa.String(length=50), nullable=True),
        sa.Column("invoice_date", sa.Date(), nullable=True),
        sa.Column("service_period", sa.String(length=20), nullable=False),
        sa.Column("purchase_order_number", sa.String(length=100), nullable=True),
        sa.Column("project_name", sa.String(length=200), nullable=False),
        sa.Column("project_leader", sa.String(length=150), nullable=True),
        sa.Column("subtotal", sa.Numeric(precision=16, scale=2), nullable=False),
        sa.Column("tax", sa.Numeric(precision=16, scale=2), nullable=False),
        sa.Column("total", sa.Numeric(precision=16, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "DRAFT",
                "UPLOADED",
                "VALIDATING",
                "VALIDATION_FAILED",
                "REQUIRES_CORRECTION",
                "PREVALIDATED",
                "UNDER_REVIEW",
                "ACCEPTED",
                "REJECTED",
                "READY_FOR_CLICKBALANCE",
                "UPLOADED_TO_CLICKBALANCE",
                name="invoicestatus",
            ),
            nullable=False,
        ),
        sa.Column("validation_score", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", sa.Integer(), nullable=True),
        sa.Column("comments", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["contract_id"],
            ["contracts.id"],
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["supplier_id"],
            ["suppliers.id"],
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_invoices_internal_folio"), "invoices", ["internal_folio"], unique=True)
    op.create_index(op.f("ix_invoices_invoice_number"), "invoices", ["invoice_number"], unique=False)
    op.create_index(op.f("ix_invoices_status"), "invoices", ["status"], unique=False)
    op.create_index(op.f("ix_invoices_supplier_id"), "invoices", ["supplier_id"], unique=False)
    op.create_index(op.f("ix_invoices_uuid"), "invoices", ["uuid"], unique=False)
    op.create_table(
        "documents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("invoice_id", sa.Integer(), nullable=True),
        sa.Column("supplier_id", sa.Integer(), nullable=True),
        sa.Column("document_type", sa.String(length=60), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("stored_filename", sa.String(length=255), nullable=False),
        sa.Column("path", sa.String(length=500), nullable=False),
        sa.Column("mime_type", sa.String(length=120), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("uploaded_by", sa.Integer(), nullable=False),
        sa.Column("processing_status", sa.String(length=30), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("document_date", sa.Date(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("replaced_document_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["invoice_id"],
            ["invoices.id"],
        ),
        sa.ForeignKeyConstraint(
            ["replaced_document_id"],
            ["documents.id"],
        ),
        sa.ForeignKeyConstraint(
            ["supplier_id"],
            ["suppliers.id"],
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_documents_document_type"), "documents", ["document_type"], unique=False)
    op.create_index(op.f("ix_documents_invoice_id"), "documents", ["invoice_id"], unique=False)
    op.create_index(op.f("ix_documents_supplier_id"), "documents", ["supplier_id"], unique=False)
    op.create_table(
        "reviews",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("invoice_id", sa.Integer(), nullable=False),
        sa.Column("reviewer_id", sa.Integer(), nullable=False),
        sa.Column("decision", sa.String(length=40), nullable=False),
        sa.Column("comments", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["invoice_id"],
            ["invoices.id"],
        ),
        sa.ForeignKeyConstraint(
            ["reviewer_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_reviews_invoice_id"), "reviews", ["invoice_id"], unique=False)
    op.create_table(
        "validation_results",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("invoice_id", sa.Integer(), nullable=False),
        sa.Column("rule_code", sa.String(length=20), nullable=False),
        sa.Column("category", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("expected_value", sa.Text(), nullable=True),
        sa.Column("detected_value", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("source_document", sa.String(length=255), nullable=True),
        sa.Column("source_reference", sa.String(length=255), nullable=True),
        sa.Column("evidence_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["invoice_id"],
            ["invoices.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_validation_results_invoice_id"), "validation_results", ["invoice_id"], unique=False)
    op.create_index(op.f("ix_validation_results_rule_code"), "validation_results", ["rule_code"], unique=False)


def downgrade() -> None:
    raise NotImplementedError("Revertir el esquema inicial destruiria todos los datos. Restaure un respaldo.")
