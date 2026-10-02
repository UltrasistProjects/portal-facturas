"""Perfil del proveedor y catalogo de actividades economicas.

- suppliers: classification (INTERNAL / EXTERNAL, con CHECK), main_activity (clave del catalogo INDUSTRY),
  incorporation_date, website, legal_rep_name, legal_rep_phone, contact_name y contact_phone. Todas admiten NULL: los
  proveedores existentes y los de la carga masiva (HU-01) las completan al editarse.
- catalog_entries: el CHECK de la enumeracion de catalogos admite INDUSTRY, sembrado con los 20 sectores del SCIAN
  (INEGI). Los valores se copian aqui y no se importan de app.
- Los tipos de documento nuevos del expediente (SUPPLIER_CONTRACT, LEGAL_REP_ADDRESS_PROOF) no requieren cambios:
  documents.document_type no tiene CHECK.
"""

from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "0009_supplier_profile"
down_revision = "0008_password_change_required"
branch_labels = None
depends_on = None

PREVIOUS_CATALOGS = ("CURRENCY", "CFDI_USE", "PAYMENT_FORM", "PAYMENT_METHOD", "TAX_REGIME")
CATALOGS = (*PREVIOUS_CATALOGS, "INDUSTRY")
# Sectores del SCIAN; los sectores de varios codigos (31-33, 48-49) se registran con el primero.
ENTRIES = {
    "INDUSTRY": [
        ("11", "Agricultura, cría y explotación de animales, aprovechamiento forestal, pesca y caza"),
        ("21", "Minería"),
        (
            "22",
            "Generación, transmisión, distribución y comercialización de energía eléctrica, suministro de agua y de "
            "gas natural por ductos al consumidor final",
        ),
        ("23", "Construcción"),
        ("31", "Industrias manufactureras"),
        ("43", "Comercio al por mayor"),
        ("46", "Comercio al por menor"),
        ("48", "Transportes, correos y almacenamiento"),
        ("51", "Información en medios masivos"),
        ("52", "Servicios financieros y de seguros"),
        ("53", "Servicios inmobiliarios y de alquiler de bienes muebles e intangibles"),
        ("54", "Servicios profesionales, científicos y técnicos"),
        ("55", "Corporativos"),
        ("56", "Servicios de apoyo a los negocios y manejo de residuos, y servicios de remediación"),
        ("61", "Servicios educativos"),
        ("62", "Servicios de salud y de asistencia social"),
        ("71", "Servicios de esparcimiento culturales y deportivos, y otros servicios recreativos"),
        ("72", "Servicios de alojamiento temporal y de preparación de alimentos y bebidas"),
        ("81", "Otros servicios excepto actividades gubernamentales"),
        (
            "93",
            "Actividades legislativas, gubernamentales, de impartición de justicia y de organismos internacionales y "
            "extraterritoriales",
        ),
    ]
}
PROFILE_COLUMNS = (
    ("classification", sa.String(length=8)),
    ("main_activity", sa.String(length=10)),
    ("incorporation_date", sa.Date()),
    ("website", sa.String(length=255)),
    ("legal_rep_name", sa.String(length=150)),
    ("legal_rep_phone", sa.String(length=30)),
    ("contact_name", sa.String(length=150)),
    ("contact_phone", sa.String(length=30)),
)


def replace_catalog_check(catalogs: tuple[str, ...]) -> None:
    values = ", ".join(f"'{catalog}'" for catalog in catalogs)
    op.drop_constraint("catalogtype", "catalog_entries", type_="check")
    op.create_check_constraint("catalogtype", "catalog_entries", f"catalog IN ({values})")


def upgrade() -> None:
    for name, type_ in PROFILE_COLUMNS:
        op.add_column("suppliers", sa.Column(name, type_, nullable=True))
    op.create_check_constraint("supplierclassification", "suppliers", "classification IN ('INTERNAL', 'EXTERNAL')")
    replace_catalog_check(CATALOGS)
    entries = sa.table(
        "catalog_entries",
        sa.column("catalog", sa.String),
        sa.column("code", sa.String),
        sa.column("name", sa.String),
        sa.column("is_active", sa.Boolean),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
        sa.column("updated_by", sa.Integer),
    )
    now = datetime.now(timezone.utc)
    op.bulk_insert(
        entries,
        [
            {
                "catalog": catalog,
                "code": code,
                "name": name,
                "is_active": True,
                "created_at": now,
                "updated_at": now,
                "updated_by": None,
            }
            for catalog, rows in ENTRIES.items()
            for code, name in rows
        ],
    )


def downgrade() -> None:
    filled = " OR ".join(f"{name} IS NOT NULL" for name, _ in PROFILE_COLUMNS)
    changed = op.get_bind().scalar(
        sa.text(
            f"SELECT (SELECT count(*) FROM suppliers WHERE {filled})"
            " + (SELECT count(*) FROM catalog_entries"
            "    WHERE catalog = 'INDUSTRY' AND (updated_by IS NOT NULL OR NOT is_active))"
            f" + (SELECT abs(count(*) - {len(ENTRIES['INDUSTRY'])}) FROM catalog_entries WHERE catalog = 'INDUSTRY')"
        )
    )
    if changed:
        raise NotImplementedError(
            "Hay proveedores con datos de perfil o el catalogo de actividades economicas fue modificado: revertir "
            "perderia datos. Restaure un respaldo."
        )
    op.execute("DELETE FROM catalog_entries WHERE catalog = 'INDUSTRY'")
    replace_catalog_check(PREVIOUS_CATALOGS)
    op.drop_constraint("supplierclassification", "suppliers", type_="check")
    for name, _ in reversed(PROFILE_COLUMNS):
        op.drop_column("suppliers", name)
