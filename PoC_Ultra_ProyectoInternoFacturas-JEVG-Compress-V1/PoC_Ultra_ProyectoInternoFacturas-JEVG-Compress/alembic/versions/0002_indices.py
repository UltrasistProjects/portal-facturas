"""Indices en llaves foraneas y en la columna de ordenamiento del listado (AUDITORIA BD-07).

El indice compuesto (supplier_id, created_at) cubre el listado de un proveedor ordenado por fecha y deja
redundante el indice simple sobre supplier_id.
"""

from alembic import op

revision = "0002_indices"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

NEW_INDEXES = (
    ("ix_invoices_supplier_created", "invoices", ["supplier_id", "created_at"]),
    ("ix_invoices_created_at", "invoices", ["created_at"]),
    ("ix_invoices_uploaded_by", "invoices", ["uploaded_by"]),
    ("ix_invoices_reviewed_by", "invoices", ["reviewed_by"]),
    ("ix_invoices_contract_id", "invoices", ["contract_id"]),
    ("ix_documents_uploaded_by", "documents", ["uploaded_by"]),
    ("ix_documents_replaced_document_id", "documents", ["replaced_document_id"]),
    ("ix_reviews_reviewer_id", "reviews", ["reviewer_id"]),
    ("ix_users_supplier_id", "users", ["supplier_id"]),
)


def upgrade() -> None:
    for name, table, columns in NEW_INDEXES:
        op.create_index(name, table, columns, unique=False)
    op.drop_index("ix_invoices_supplier_id", table_name="invoices")


def downgrade() -> None:
    op.create_index("ix_invoices_supplier_id", "invoices", ["supplier_id"], unique=False)
    for name, table, _columns in reversed(NEW_INDEXES):
        op.drop_index(name, table_name=table)
