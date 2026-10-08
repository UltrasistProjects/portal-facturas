"""Reglas de Validacion (HU-06) y catalogos de referencia (HU-07).

- validation_settings: una fila con los datos de ULTRASIST y los parametros del CFDI, sembrada con los valores que
  aplicaba el motor desde BUSINESS_RULES, con todas las comparaciones activas y la direccion vacia.
- catalog_entries: catalogos del SAT para CFDI 4.0 (usos de CFDI, formas y metodos de pago, regimenes fiscales) y las
  monedas que aceptaba XML-007 (MXN, USD y EUR). Los valores se copian aqui y no se importan de app.
"""

from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007_validation_rules_catalogs"
down_revision = "0006_supplier_credentials"
branch_labels = None
depends_on = None

CATALOGS = ("CURRENCY", "CFDI_USE", "PAYMENT_FORM", "PAYMENT_METHOD", "TAX_REGIME")
ENTRIES = {
    "CURRENCY": [("MXN", "Peso mexicano"), ("USD", "Dólar americano"), ("EUR", "Euro")],
    "CFDI_USE": [
        ("G01", "Adquisición de mercancías"),
        ("G02", "Devoluciones, descuentos o bonificaciones"),
        ("G03", "Gastos en general"),
        ("I01", "Construcciones"),
        ("I02", "Mobiliario y equipo de oficina por inversiones"),
        ("I03", "Equipo de transporte"),
        ("I04", "Equipo de cómputo y accesorios"),
        ("I05", "Dados, troqueles, moldes, matrices y herramental"),
        ("I06", "Comunicaciones telefónicas"),
        ("I07", "Comunicaciones satelitales"),
        ("I08", "Otra maquinaria y equipo"),
        ("D01", "Honorarios médicos, dentales y gastos hospitalarios"),
        ("D02", "Gastos médicos por incapacidad o discapacidad"),
        ("D03", "Gastos funerales"),
        ("D04", "Donativos"),
        ("D05", "Intereses reales efectivamente pagados por créditos hipotecarios (casa habitación)"),
        ("D06", "Aportaciones voluntarias al SAR"),
        ("D07", "Primas por seguros de gastos médicos"),
        ("D08", "Gastos de transportación escolar obligatoria"),
        ("D09", "Depósitos en cuentas para el ahorro, primas que tengan como base planes de pensiones"),
        ("D10", "Pagos por servicios educativos (colegiaturas)"),
        ("S01", "Sin efectos fiscales"),
        ("CP01", "Pagos"),
        ("CN01", "Nómina"),
    ],
    "PAYMENT_FORM": [
        ("01", "Efectivo"),
        ("02", "Cheque nominativo"),
        ("03", "Transferencia electrónica de fondos"),
        ("04", "Tarjeta de crédito"),
        ("05", "Monedero electrónico"),
        ("06", "Dinero electrónico"),
        ("08", "Vales de despensa"),
        ("12", "Dación en pago"),
        ("13", "Pago por subrogación"),
        ("14", "Pago por consignación"),
        ("15", "Condonación"),
        ("17", "Compensación"),
        ("23", "Novación"),
        ("24", "Confusión"),
        ("25", "Remisión de deuda"),
        ("26", "Prescripción o caducidad"),
        ("27", "A satisfacción del acreedor"),
        ("28", "Tarjeta de débito"),
        ("29", "Tarjeta de servicios"),
        ("30", "Aplicación de anticipos"),
        ("31", "Intermediario pagos"),
        ("99", "Por definir"),
    ],
    "PAYMENT_METHOD": [("PUE", "Pago en una sola exhibición"), ("PPD", "Pago en parcialidades o diferido")],
    "TAX_REGIME": [
        ("601", "General de Ley Personas Morales"),
        ("603", "Personas Morales con Fines no Lucrativos"),
        ("605", "Sueldos y Salarios e Ingresos Asimilados a Salarios"),
        ("606", "Arrendamiento"),
        ("607", "Régimen de Enajenación o Adquisición de Bienes"),
        ("608", "Demás ingresos"),
        ("610", "Residentes en el Extranjero sin Establecimiento Permanente en México"),
        ("611", "Ingresos por Dividendos (socios y accionistas)"),
        ("612", "Personas Físicas con Actividades Empresariales y Profesionales"),
        ("614", "Ingresos por intereses"),
        ("615", "Régimen de los ingresos por obtención de premios"),
        ("616", "Sin obligaciones fiscales"),
        ("620", "Sociedades Cooperativas de Producción que optan por diferir sus ingresos"),
        ("621", "Incorporación Fiscal"),
        ("622", "Actividades Agrícolas, Ganaderas, Silvícolas y Pesqueras"),
        ("623", "Opcional para Grupos de Sociedades"),
        ("624", "Coordinados"),
        ("625", "Régimen de las Actividades Empresariales con ingresos a través de Plataformas Tecnológicas"),
        ("626", "Régimen Simplificado de Confianza"),
    ],
}
SETTINGS = {
    "id": 1,
    "receiver_rfc": "ULT940623AG0",
    "receiver_name": "ULTRASIST",
    "receiver_address": "",
    "receiver_postal_code": "03930",
    "receiver_tax_regime": "601",
    "payment_method": "PPD",
    "payment_form": "99",
    "allowed_cfdi_uses": ["G03", "I04"],
    "check_receiver_rfc": True,
    "check_receiver_name": True,
    "check_receiver_postal_code": True,
    "check_payment_method": True,
    "check_payment_form": True,
    "check_cfdi_use": True,
    "version": 1,
    "updated_by": None,
}


def upgrade() -> None:
    settings = op.create_table(
        "validation_settings",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("receiver_rfc", sa.String(length=13), nullable=False),
        sa.Column("receiver_name", sa.String(length=254), nullable=False),
        sa.Column("receiver_address", sa.String(length=300), nullable=False),
        sa.Column("receiver_postal_code", sa.String(length=5), nullable=False),
        sa.Column("receiver_tax_regime", sa.String(length=10), nullable=False),
        sa.Column("payment_method", sa.String(length=10), nullable=False),
        sa.Column("payment_form", sa.String(length=10), nullable=False),
        sa.Column("allowed_cfdi_uses", postgresql.ARRAY(sa.String(length=10)), nullable=False),
        *(
            sa.Column(name, sa.Boolean(), nullable=False)
            for name in (
                "check_receiver_rfc",
                "check_receiver_name",
                "check_receiver_postal_code",
                "check_payment_method",
                "check_payment_form",
                "check_cfdi_use",
            )
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.CheckConstraint("id = 1", name="ck_validation_settings_single_row"),
        sa.CheckConstraint("receiver_postal_code ~ '^[0-9]{5}$'", name="ck_validation_settings_postal_code"),
        sa.CheckConstraint("cardinality(allowed_cfdi_uses) >= 1", name="ck_validation_settings_cfdi_uses"),
        sa.CheckConstraint("version >= 1", name="ck_validation_settings_version_positive"),
        sa.ForeignKeyConstraint(
            ["updated_by"], ["users.id"], name=op.f("fk_validation_settings_updated_by_users"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_validation_settings")),
    )
    entries = op.create_table(
        "catalog_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "catalog", sa.Enum(*CATALOGS, name="catalogtype", native_enum=False, create_constraint=True), nullable=False
        ),
        sa.Column("code", sa.String(length=10), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.CheckConstraint("code ~ '^[A-Z0-9]{1,10}$'", name="ck_catalog_entries_code"),
        sa.CheckConstraint("char_length(name) BETWEEN 1 AND 150", name="ck_catalog_entries_name_length"),
        sa.ForeignKeyConstraint(
            ["updated_by"], ["users.id"], name=op.f("fk_catalog_entries_updated_by_users"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_catalog_entries")),
        sa.UniqueConstraint("catalog", "code", name="uq_catalog_entries_catalog_code"),
    )
    now = datetime.now(timezone.utc)
    op.bulk_insert(settings, [{**SETTINGS, "updated_at": now}])
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
    changed = op.get_bind().scalar(
        sa.text(
            "SELECT (SELECT count(*) FROM validation_settings WHERE version > 1)"
            " + (SELECT count(*) FROM catalog_entries WHERE updated_by IS NOT NULL OR NOT is_active)"
            f" + (SELECT abs(count(*) - {sum(len(rows) for rows in ENTRIES.values())}) FROM catalog_entries)"
        )
    )
    if changed:
        raise NotImplementedError(
            "Las Reglas de Validacion o los catalogos fueron modificados: revertir perderia datos. "
            "Restaure un respaldo."
        )
    op.drop_table("catalog_entries")
    op.drop_table("validation_settings")
