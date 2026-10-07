"""Esquema base para PostgreSQL.

Describe de forma explicita las 11 tablas del dominio con sus tipos nativos (NUMERIC, TIMESTAMPTZ, JSONB), llaves
foraneas ON DELETE RESTRICT, UNIQUE, CHECK e indices. No importa los modelos ORM: el historial de esquema no debe
cambiar cuando cambian los modelos. Todo cambio posterior va en una revision nueva.

Reemplaza a la cadena 0001_initial..0006_user_sessions, escrita para la base anterior (queda en el historial de Git).
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_postgresql_baseline"
down_revision = None
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
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_login_attempts")),
    )
    op.create_index("ix_login_attempts_email_attempted_at", "login_attempts", ["email", "attempted_at"], unique=False)
    op.create_index("ix_login_attempts_ip_attempted_at", "login_attempts", ["ip", "attempted_at"], unique=False)
    op.create_table(
        "suppliers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("business_name", sa.String(length=250), nullable=False),
        sa.Column("rfc", sa.String(length=13), nullable=False),
        sa.Column(
            "supplier_type",
            sa.Enum("PERSONA_FISICA", "PERSONA_MORAL", name="suppliertype", native_enum=False, create_constraint=True),
            nullable=False,
        ),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=30), nullable=True),
        sa.Column(
            "status",
            sa.Enum("ACTIVE", "INACTIVE", name="supplierstatus", native_enum=False, create_constraint=True),
            nullable=False,
        ),
        sa.Column("confidentiality_agreement", sa.Boolean(), nullable=False),
        sa.Column("economic_proposal", sa.Boolean(), nullable=False),
        sa.Column("bank_information", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_suppliers")),
    )
    op.create_index(op.f("ix_suppliers_rfc"), "suppliers", ["rfc"], unique=True)
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=512), nullable=False),
        sa.Column(
            "role",
            sa.Enum("PROVIDER", "INTERNAL", "ADMIN", name="role", native_enum=False, create_constraint=True),
            nullable=False,
        ),
        sa.Column("supplier_id", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["supplier_id"], ["suppliers.id"], name=op.f("fk_users_supplier_id_suppliers"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)
    op.create_index(op.f("ix_users_role"), "users", ["role"], unique=False)
    op.create_index(op.f("ix_users_supplier_id"), "users", ["supplier_id"], unique=False)
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("entity", sa.String(length=80), nullable=False),
        sa.Column("entity_id", sa.String(length=80), nullable=True),
        sa.Column("old_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("new_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ip_address", sa.String(length=50), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_audit_logs_user_id_users"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_logs")),
    )
    op.create_index(op.f("ix_audit_logs_action"), "audit_logs", ["action"], unique=False)
    op.create_index(op.f("ix_audit_logs_timestamp"), "audit_logs", ["timestamp"], unique=False)
    op.create_index(op.f("ix_audit_logs_user_id"), "audit_logs", ["user_id"], unique=False)
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
        sa.Column(
            "status",
            sa.Enum("ACTIVE", "INACTIVE", name="contractstatus", native_enum=False, create_constraint=True),
            nullable=False,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.CheckConstraint("authorized_amount > 0", name="ck_contracts_authorized_amount_positive"),
        sa.CheckConstraint("end_date >= start_date", name="ck_contracts_valid_period"),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_contracts_created_by_users"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["supplier_id"], ["suppliers.id"], name=op.f("fk_contracts_supplier_id_suppliers"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"], ["users.id"], name=op.f("fk_contracts_updated_by_users"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_contracts")),
    )
    op.create_index(op.f("ix_contracts_supplier_id"), "contracts", ["supplier_id"], unique=False)
    op.create_table(
        "user_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("sid_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ip", sa.String(length=50), nullable=True),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_user_sessions_user_id_users"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_sessions")),
        sa.UniqueConstraint("sid_hash"),
    )
    op.create_index(op.f("ix_user_sessions_user_id"), "user_sessions", ["user_id"], unique=False)
    op.create_table(
        "contract_amendments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("contract_id", sa.Integer(), nullable=False),
        sa.Column("previous_amount", sa.Numeric(precision=16, scale=2), nullable=False),
        sa.Column("new_amount", sa.Numeric(precision=16, scale=2), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("new_amount > 0", name="ck_contract_amendments_new_amount_positive"),
        sa.ForeignKeyConstraint(
            ["contract_id"],
            ["contracts.id"],
            name=op.f("fk_contract_amendments_contract_id_contracts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_contract_amendments_created_by_users"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_contract_amendments")),
    )
    op.create_index(op.f("ix_contract_amendments_contract_id"), "contract_amendments", ["contract_id"], unique=False)
    op.create_index(op.f("ix_contract_amendments_created_by"), "contract_amendments", ["created_by"], unique=False)
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
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("validation_score", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", sa.Integer(), nullable=True),
        sa.Column("comments", sa.Text(), nullable=True),
        sa.CheckConstraint("subtotal >= 0", name="ck_invoices_subtotal_non_negative"),
        sa.CheckConstraint("tax >= 0", name="ck_invoices_tax_non_negative"),
        sa.CheckConstraint("total >= 0", name="ck_invoices_total_non_negative"),
        sa.CheckConstraint(
            "validation_score IS NULL OR validation_score BETWEEN 0 AND 100", name="ck_invoices_score_range"
        ),
        sa.ForeignKeyConstraint(
            ["contract_id"], ["contracts.id"], name=op.f("fk_invoices_contract_id_contracts"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by"], ["users.id"], name=op.f("fk_invoices_reviewed_by_users"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["supplier_id"], ["suppliers.id"], name=op.f("fk_invoices_supplier_id_suppliers"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by"], ["users.id"], name=op.f("fk_invoices_uploaded_by_users"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_invoices")),
        sa.UniqueConstraint("supplier_id", "invoice_number", name="uq_invoices_supplier_number"),
        sa.UniqueConstraint("uuid", name="uq_invoices_uuid"),
    )
    op.create_index(op.f("ix_invoices_contract_id"), "invoices", ["contract_id"], unique=False)
    op.create_index(op.f("ix_invoices_created_at"), "invoices", ["created_at"], unique=False)
    op.create_index(op.f("ix_invoices_internal_folio"), "invoices", ["internal_folio"], unique=True)
    op.create_index(op.f("ix_invoices_invoice_number"), "invoices", ["invoice_number"], unique=False)
    op.create_index(op.f("ix_invoices_reviewed_by"), "invoices", ["reviewed_by"], unique=False)
    op.create_index(op.f("ix_invoices_status"), "invoices", ["status"], unique=False)
    op.create_index("ix_invoices_supplier_created", "invoices", ["supplier_id", "created_at"], unique=False)
    op.create_index(op.f("ix_invoices_uploaded_by"), "invoices", ["uploaded_by"], unique=False)
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
        sa.Column(
            "processing_status",
            sa.Enum(
                "PENDING", "PROCESSED", "FAILED", name="processingstatus", native_enum=False, create_constraint=True
            ),
            nullable=False,
        ),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("document_date", sa.Date(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("replaced_document_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["invoice_id"], ["invoices.id"], name=op.f("fk_documents_invoice_id_invoices"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["replaced_document_id"],
            ["documents.id"],
            name=op.f("fk_documents_replaced_document_id_documents"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["supplier_id"], ["suppliers.id"], name=op.f("fk_documents_supplier_id_suppliers"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by"], ["users.id"], name=op.f("fk_documents_uploaded_by_users"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_documents")),
    )
    op.create_index(op.f("ix_documents_document_type"), "documents", ["document_type"], unique=False)
    op.create_index(op.f("ix_documents_invoice_id"), "documents", ["invoice_id"], unique=False)
    op.create_index(op.f("ix_documents_replaced_document_id"), "documents", ["replaced_document_id"], unique=False)
    op.create_index(op.f("ix_documents_supplier_id"), "documents", ["supplier_id"], unique=False)
    op.create_index(op.f("ix_documents_uploaded_by"), "documents", ["uploaded_by"], unique=False)
    op.create_table(
        "reviews",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("invoice_id", sa.Integer(), nullable=False),
        sa.Column("reviewer_id", sa.Integer(), nullable=False),
        sa.Column(
            "decision",
            sa.Enum(
                "ACCEPTED",
                "REJECTED",
                "REQUIRES_CORRECTION",
                "COMMENT",
                name="reviewdecision",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("comments", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["invoice_id"], ["invoices.id"], name=op.f("fk_reviews_invoice_id_invoices"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["reviewer_id"], ["users.id"], name=op.f("fk_reviews_reviewer_id_users"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reviews")),
    )
    op.create_index(op.f("ix_reviews_invoice_id"), "reviews", ["invoice_id"], unique=False)
    op.create_index(op.f("ix_reviews_reviewer_id"), "reviews", ["reviewer_id"], unique=False)
    op.create_table(
        "validation_results",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("invoice_id", sa.Integer(), nullable=False),
        sa.Column("rule_code", sa.String(length=20), nullable=False),
        sa.Column("category", sa.String(length=30), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "PASS",
                "FAIL",
                "WARNING",
                "NOT_APPLICABLE",
                "NOT_EVALUATED",
                name="rulestatus",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "severity",
            sa.Enum("INFO", "WARNING", "ERROR", "CRITICAL", name="severity", native_enum=False, create_constraint=True),
            nullable=False,
        ),
        sa.Column("expected_value", sa.Text(), nullable=True),
        sa.Column("detected_value", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("source_document", sa.String(length=255), nullable=True),
        sa.Column("source_reference", sa.String(length=255), nullable=True),
        sa.Column("evidence_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("confidence IS NULL OR confidence BETWEEN 0 AND 1", name="ck_validation_results_confidence"),
        sa.ForeignKeyConstraint(
            ["invoice_id"], ["invoices.id"], name=op.f("fk_validation_results_invoice_id_invoices"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_validation_results")),
    )
    op.create_index(op.f("ix_validation_results_invoice_id"), "validation_results", ["invoice_id"], unique=False)
    op.create_index(op.f("ix_validation_results_rule_code"), "validation_results", ["rule_code"], unique=False)


def downgrade() -> None:
    raise NotImplementedError("Revertir el esquema base destruiria todos los datos. Restaure un respaldo.")
