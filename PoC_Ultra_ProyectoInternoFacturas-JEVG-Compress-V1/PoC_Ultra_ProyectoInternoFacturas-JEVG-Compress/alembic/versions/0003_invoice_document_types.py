"""Archivos minimos por tipo de proveedor (HU-04): catalogo de tipos de documento de factura.

- Tabla invoice_document_types: clave (valor de documents.document_type), nombre, descripcion, formatos, tipo del
  sistema o del Administrador, estado activo y nivel de exigencia para proveedores nacionales e internacionales.
- Siembra los 10 tipos del sistema. Los valores iniciales conservan el comportamiento previo para el nacional
  (XML, PDF, orden de compra y Vo.Bo. obligatorios). documents no cambia: no hay FK de document_type al catalogo.
"""

from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_invoice_document_types"
down_revision = "0002_supplier_bulk_import"
branch_labels = None
depends_on = None

LEVELS = ("REQUIRED", "OPTIONAL", "NOT_APPLICABLE")
FIXED_LEVELS_CHECK = (
    "(code NOT IN ('INVOICE_XML', 'INVOICE_PDF')"
    " OR (national_requirement = 'REQUIRED' AND international_requirement = 'NOT_APPLICABLE'))"
    " AND (code <> 'FOREIGN_INVOICE'"
    " OR (national_requirement = 'NOT_APPLICABLE' AND international_requirement = 'REQUIRED'))"
)
SUPPORT = ["PDF", "PNG", "JPEG", "TXT"]
# (clave, nombre, descripcion, formatos, nacional, internacional), en el orden del catalogo.
SYSTEM_TYPES = [
    ("INVOICE_XML", "XML del CFDI", "Archivo XML del CFDI timbrado", ["XML"], "REQUIRED", "NOT_APPLICABLE"),
    ("INVOICE_PDF", "PDF del CFDI", "Representación impresa del CFDI", ["PDF"], "REQUIRED", "NOT_APPLICABLE"),
    ("FOREIGN_INVOICE", "Invoice (PDF)", "Factura del proveedor extranjero", ["PDF"], "NOT_APPLICABLE", "REQUIRED"),
    (
        "PURCHASE_ORDER",
        "Orden de compra",
        "Orden de compra que ampara el servicio facturado",
        SUPPORT,
        "REQUIRED",
        "REQUIRED",
    ),
    (
        "APPROVAL",
        "Vo.Bo. del líder de proyecto",
        "Visto bueno del líder de proyecto sobre los entregables del periodo facturado",
        SUPPORT,
        "REQUIRED",
        "REQUIRED",
    ),
    ("CONTRACT", "Contrato", "Contrato firmado con ULTRASIST", SUPPORT, "OPTIONAL", "OPTIONAL"),
    ("CONTRACT_ANNEX", "Anexo del contrato", "Anexo firmado del contrato", SUPPORT, "OPTIONAL", "OPTIONAL"),
    (
        "PAYMENT_COMPLEMENT_XML",
        "Complemento de pago (XML)",
        "XML de complementos de pago previos, cuando aplique",
        ["XML"],
        "OPTIONAL",
        "NOT_APPLICABLE",
    ),
    (
        "PAYMENT_COMPLEMENT_PDF",
        "Complemento de pago (PDF)",
        "PDF de complementos de pago previos, cuando aplique",
        ["PDF"],
        "OPTIONAL",
        "NOT_APPLICABLE",
    ),
    (
        "ADDITIONAL",
        "Documentación adicional",
        "Cualquier otro documento que respalde la factura",
        ["PDF", "PNG", "JPEG", "XML", "TXT"],
        "OPTIONAL",
        "OPTIONAL",
    ),
]


def level_column(name: str) -> sa.Column:
    return sa.Column(
        name,
        sa.Enum(*LEVELS, name=f"ck_invoice_document_types_{name}", native_enum=False, create_constraint=True),
        nullable=False,
    )


def upgrade() -> None:
    table = op.create_table(
        "invoice_document_types",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=60), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("description", sa.String(length=300), nullable=True),
        sa.Column("formats", postgresql.ARRAY(sa.String(length=4)), nullable=False),
        sa.Column("is_system", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        level_column("national_requirement"),
        level_column("international_requirement"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "cardinality(formats) >= 1 AND formats <@ ARRAY['PDF', 'PNG', 'JPEG', 'XML', 'TXT']::varchar[]",
            name="ck_invoice_document_types_formats",
        ),
        sa.CheckConstraint("is_active OR NOT is_system", name="ck_invoice_document_types_system_active"),
        sa.CheckConstraint(FIXED_LEVELS_CHECK, name="ck_invoice_document_types_fixed_levels"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_invoice_document_types")),
        sa.UniqueConstraint("code", name="uq_invoice_document_types_code"),
    )
    op.create_index(
        "uq_invoice_document_types_name_lower", "invoice_document_types", [sa.text("lower((name)::text)")], unique=True
    )
    now = datetime.now(timezone.utc)
    op.bulk_insert(
        table,
        [
            {
                "code": code,
                "name": name,
                "description": description,
                "formats": formats,
                "is_system": True,
                "is_active": True,
                "national_requirement": national,
                "international_requirement": international,
                "created_at": now,
                "updated_at": now,
            }
            for code, name, description, formats, national, international in SYSTEM_TYPES
        ],
    )


def downgrade() -> None:
    bind = op.get_bind()
    custom = bind.scalar(sa.text("SELECT count(*) FROM invoice_document_types WHERE NOT is_system"))
    documents = bind.scalar(
        sa.text(
            "SELECT count(*) FROM documents WHERE document_type = 'FOREIGN_INVOICE' OR document_type LIKE 'SOPORTE\\_%'"
        )
    )
    if custom or documents:
        raise NotImplementedError(
            "Hay tipos de documento soporte o documentos Invoice o soporte: revertir perderia datos. "
            "Restaure un respaldo."
        )
    op.drop_index("uq_invoice_document_types_name_lower", table_name="invoice_document_types")
    op.drop_table("invoice_document_types")
