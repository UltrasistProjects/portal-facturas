"""Requisitos de alta del proveedor (HU-21): catalogo de documentos del expediente.

- Tabla supplier_document_types: clave (valor de documents.document_type en el expediente), nombre, descripcion,
  requisito del sistema o del Administrador, estado activo y nivel de exigencia para persona moral, persona fisica
  e internacional.
- Siembra los 13 requisitos del sistema: los 12 documentos del expediente previo (Anexo A) y Poderes. Para la persona
  moral son obligatorios los siete de la solicitud de negocio; el internacional no tiene requisitos, como antes.
  suppliers y documents no cambian: no hay FK de document_type al catalogo.
"""

from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "0016_supplier_document_types"
down_revision = "0015_keycloak_identity"
branch_labels = None
depends_on = None

LEVELS = ("REQUIRED", "OPTIONAL", "NOT_APPLICABLE")
REQ, OPT, NA = LEVELS
# (clave, nombre, descripcion, persona moral, persona fisica, internacional), en el orden del catalogo.
SYSTEM_TYPES = [
    (
        "INCORPORATION_ACT",
        "Acta constitutiva",
        "Acta constitutiva con cédula del Registro Público de la Propiedad y del Comercio",
        REQ,
        NA,
        NA,
    ),
    ("POWER_OF_ATTORNEY", "Poderes", "Poder notarial del representante legal", REQ, NA, NA),
    ("TAX_STATUS", "Cédula fiscal", "Constancia de situación fiscal emitida por el SAT", REQ, REQ, NA),
    (
        "LEGAL_REP_ID",
        "Identificación del representante legal",
        "Identificación oficial (INE o pasaporte) del apoderado legal",
        REQ,
        NA,
        NA,
    ),
    (
        "LEGAL_REP_ADDRESS_PROOF",
        "Comprobante de domicilio del representante legal",
        "Recibo de teléfono, luz o agua a nombre del representante legal",
        REQ,
        NA,
        NA,
    ),
    (
        "ADDRESS_PROOF",
        "Comprobante de domicilio",
        "Recibo de teléfono, luz o agua del domicilio del proveedor",
        REQ,
        REQ,
        NA,
    ),
    ("BANK_STATEMENT", "Estado de cuenta bancario", "Carátula del último estado de cuenta con la CLABE", REQ, REQ, NA),
    (
        "OFFICIAL_ID",
        "Identificación oficial",
        "Identificación oficial (INE o pasaporte) de la persona física",
        NA,
        REQ,
        NA,
    ),
    (
        "SAT_OPINION",
        "Opinión de cumplimiento",
        "Opinión de cumplimiento de obligaciones fiscales del SAT",
        OPT,
        OPT,
        NA,
    ),
    (
        "ECONOMIC_PROPOSAL",
        "Propuesta económica",
        "Propuesta económica autorizada por el líder de ULTRASIST",
        OPT,
        OPT,
        NA,
    ),
    ("DUE_DILIGENCE", "Debida diligencia", "Formato de debida diligencia requisitado", OPT, NA, NA),
    ("LOCATION", "Ubicación", "Liga de Google Maps o coordenadas geográficas", OPT, OPT, NA),
    ("SUPPLIER_CONTRACT", "Contrato", "Contrato firmado con ULTRASIST", OPT, OPT, NA),
]


def level_column(name: str) -> sa.Column:
    return sa.Column(
        name,
        sa.Enum(*LEVELS, name=f"ck_supplier_document_types_{name}", native_enum=False, create_constraint=True),
        nullable=False,
    )


def upgrade() -> None:
    table = op.create_table(
        "supplier_document_types",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=60), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("description", sa.String(length=300), nullable=True),
        sa.Column("is_system", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        level_column("persona_moral_requirement"),
        level_column("persona_fisica_requirement"),
        level_column("international_requirement"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("is_active OR NOT is_system", name="ck_supplier_document_types_system_active"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_supplier_document_types")),
        sa.UniqueConstraint("code", name="uq_supplier_document_types_code"),
    )
    op.create_index(
        "uq_supplier_document_types_name_lower",
        "supplier_document_types",
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
                "persona_moral_requirement": moral,
                "persona_fisica_requirement": fisica,
                "international_requirement": international,
                "created_at": now,
                "updated_at": now,
            }
            for code, name, description, moral, fisica, international in SYSTEM_TYPES
        ],
    )


def downgrade() -> None:
    bind = op.get_bind()
    custom = bind.scalar(sa.text("SELECT count(*) FROM supplier_document_types WHERE NOT is_system"))
    documents = bind.scalar(
        sa.text(
            "SELECT count(*) FROM documents WHERE invoice_id IS NULL"
            " AND (document_type = 'POWER_OF_ATTORNEY' OR document_type LIKE 'REQUISITO\\_%')"
        )
    )
    if custom or documents:
        raise NotImplementedError(
            "Hay requisitos de alta del Administrador o documentos de Poderes o de esos requisitos: revertir los "
            "dejaria sin catalogo. Restaure un respaldo."
        )
    op.drop_index("uq_supplier_document_types_name_lower", table_name="supplier_document_types")
    op.drop_table("supplier_document_types")
