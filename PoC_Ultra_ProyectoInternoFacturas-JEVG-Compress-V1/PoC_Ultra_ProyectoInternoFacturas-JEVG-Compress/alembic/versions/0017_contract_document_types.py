"""Requisitos de alta del contrato (HU-22): catalogo de documentos del contrato y estatus Registrado.

- Tabla contract_document_types: clave (valor de documents.document_type en los documentos del contrato), nombre,
  descripcion, requisito del sistema o del Administrador, estado activo, un nivel de exigencia y si admite varios
  archivos. Siembra Contrato (Obligatorio fijo), Orden de compra y Anexos (Opcionales, varios archivos).
- documents.contract_id (FK RESTRICT): un documento del contrato no lleva invoice_id ni supplier_id.
- CHECK contractstatus admite REGISTERED; la columna crece a 10 caracteres. Los contratos existentes siguen ACTIVE.
- El Contrato sale del expediente del proveedor: SUPPLIER_CONTRACT queda "No aplica" fijo para los tres perfiles. Sus
  documentos ya cargados no cambian.
"""

from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "0017_contract_document_types"
down_revision = "0016_supplier_document_types"
branch_labels = None
depends_on = None

LEVELS = ("REQUIRED", "OPTIONAL", "NOT_APPLICABLE")
REQ, OPT, NA = LEVELS
# (clave, nombre, descripcion, nivel, varios archivos), en el orden del catalogo.
SYSTEM_TYPES = [
    ("SIGNED_CONTRACT", "Contrato", "Contrato firmado con ULTRASIST", REQ, False),
    ("CONTRACT_PURCHASE_ORDER", "Orden de compra", "Orden de compra que respalda la contratación", OPT, True),
    ("CONTRACT_ANNEXES", "Anexos", "Anexos del contrato: técnico, económico, de alcance u otros", OPT, True),
]
SUPPLIER_LEVELS = ("persona_moral_requirement", "persona_fisica_requirement", "international_requirement")
SUPPLIER_NOT_APPLICABLE = " AND ".join(f"{column} = 'NOT_APPLICABLE'" for column in SUPPLIER_LEVELS)
SUPPLIER_FIXED_CHECK = f"code <> 'SUPPLIER_CONTRACT' OR ({SUPPLIER_NOT_APPLICABLE})"
CONTRACT_OWNER_CHECK = "contract_id IS NULL OR (invoice_id IS NULL AND supplier_id IS NULL)"


def upgrade() -> None:
    table = op.create_table(
        "contract_document_types",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=60), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("description", sa.String(length=300), nullable=True),
        sa.Column("is_system", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "requirement",
            sa.Enum(*LEVELS, name="ck_contract_document_types_requirement", native_enum=False, create_constraint=True),
            nullable=False,
        ),
        sa.Column("allows_multiple", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("is_active OR NOT is_system", name="ck_contract_document_types_system_active"),
        sa.CheckConstraint(
            "code <> 'SIGNED_CONTRACT' OR requirement = 'REQUIRED'", name="ck_contract_document_types_fixed_levels"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_contract_document_types")),
        sa.UniqueConstraint("code", name="uq_contract_document_types_code"),
    )
    op.create_index(
        "uq_contract_document_types_name_lower",
        "contract_document_types",
        [sa.text("lower((name)::text)")],
        unique=True,
    )
    now = datetime.now(timezone.utc)
    op.bulk_insert(
        table,
        [
            {
                "code": code,
                "name": name,
                "description": description,
                "is_system": True,
                "is_active": True,
                "requirement": level,
                "allows_multiple": multiple,
                "created_at": now,
                "updated_at": now,
            }
            for code, name, description, level, multiple in SYSTEM_TYPES
        ],
    )

    op.add_column("documents", sa.Column("contract_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        op.f("fk_documents_contract_id_contracts"),
        "documents",
        "contracts",
        ["contract_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(op.f("ix_documents_contract_id"), "documents", ["contract_id"], unique=False)
    op.create_check_constraint("ck_documents_contract_owner", "documents", CONTRACT_OWNER_CHECK)

    op.drop_constraint("contractstatus", "contracts", type_="check")
    op.alter_column("contracts", "status", existing_type=sa.String(length=8), type_=sa.String(length=10))
    op.create_check_constraint("contractstatus", "contracts", "status IN ('REGISTERED', 'ACTIVE', 'INACTIVE')")

    op.execute(
        "UPDATE supplier_document_types SET "
        + ", ".join(f"{column} = 'NOT_APPLICABLE'" for column in SUPPLIER_LEVELS)
        + " WHERE code = 'SUPPLIER_CONTRACT'"
    )
    op.create_check_constraint(
        "ck_supplier_document_types_fixed_levels", "supplier_document_types", SUPPLIER_FIXED_CHECK
    )


def downgrade() -> None:
    bind = op.get_bind()
    registered = bind.scalar(sa.text("SELECT count(*) FROM contracts WHERE status = 'REGISTERED'"))
    documents = bind.scalar(sa.text("SELECT count(*) FROM documents WHERE contract_id IS NOT NULL"))
    custom = bind.scalar(sa.text("SELECT count(*) FROM contract_document_types WHERE NOT is_system"))
    if registered or documents or custom:
        raise NotImplementedError(
            "Hay contratos Registrado, documentos de contratos o requisitos del contrato del Administrador: revertir "
            "perderia datos. Restaure un respaldo."
        )
    op.drop_constraint("ck_supplier_document_types_fixed_levels", "supplier_document_types", type_="check")
    op.execute(
        "UPDATE supplier_document_types SET persona_moral_requirement = 'OPTIONAL',"
        " persona_fisica_requirement = 'OPTIONAL', international_requirement = 'NOT_APPLICABLE'"
        " WHERE code = 'SUPPLIER_CONTRACT'"
    )

    op.drop_constraint("contractstatus", "contracts", type_="check")
    op.alter_column("contracts", "status", existing_type=sa.String(length=10), type_=sa.String(length=8))
    op.create_check_constraint("contractstatus", "contracts", "status IN ('ACTIVE', 'INACTIVE')")

    op.drop_constraint("ck_documents_contract_owner", "documents", type_="check")
    op.drop_index(op.f("ix_documents_contract_id"), table_name="documents")
    op.drop_constraint(op.f("fk_documents_contract_id_contracts"), "documents", type_="foreignkey")
    op.drop_column("documents", "contract_id")

    op.drop_index("uq_contract_document_types_name_lower", table_name="contract_document_types")
    op.drop_table("contract_document_types")
