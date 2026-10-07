"""Reglas de Validacion por origen (ajustes-finales-configuracion).

- validation_rules: un registro por regla configurable y origen de proveedor (NATIONAL / INTERNATIONAL), con su
  nombre, su valor esperado (parameter, JSONB: texto o lista), baja logica (is_active, deleted_at, deleted_by) y
  version para la edicion concurrente. UNIQUE (origin, rule_code).
- La configuracion unica de validation_settings se convierte en reglas NATIONAL: cada regla queda activa si su
  comparacion lo estaba. El regimen fiscal, que era un dato de referencia, pasa a XML-011, que nace eliminada.
- Las reglas INTERNATIONAL se siembran con los valores vigentes, como las aplicaba el motor: INT-002 e INT-003 con la
  razon social, el codigo postal y sus interruptores; INT-004 con la direccion, activa solo si habia direccion.
  Asi ninguna validacion cambia al migrar.
- Se retira validation_settings. El downgrade la reconstruye con las reglas nacionales y se niega si las reglas no
  caben en la fila unica (valores internacionales distintos, INT-001 eliminada o XML-011 activa).
"""

from collections.abc import Mapping
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0020_validation_rules"
down_revision = "0019_types_soft_delete"
branch_labels = None
depends_on = None

CHECKS = (
    "check_receiver_rfc",
    "check_receiver_name",
    "check_receiver_postal_code",
    "check_payment_method",
    "check_payment_form",
    "check_cfdi_use",
)
# Regla -> (nombre inicial, columna de validation_settings con su valor, interruptor). Copiado aqui, no importado.
NATIONAL = {
    "XML-002": ("RFC del receptor", "receiver_rfc", "check_receiver_rfc"),
    "XML-003": ("Método de pago", "payment_method", "check_payment_method"),
    "XML-004": ("Forma de pago", "payment_form", "check_payment_form"),
    "XML-005": ("Usos de CFDI", "allowed_cfdi_uses", "check_cfdi_use"),
    "XML-009": ("Razón social del receptor", "receiver_name", "check_receiver_name"),
    "XML-010": ("Código postal del receptor", "receiver_postal_code", "check_receiver_postal_code"),
    "XML-011": ("Régimen fiscal del receptor", "receiver_tax_regime", None),
}
INTERNATIONAL = {
    "INT-001": ("Identificador fiscal del proveedor", None, None),
    "INT-002": ("Razón social de ULTRASIST", "receiver_name", "check_receiver_name"),
    "INT-003": ("Código postal de ULTRASIST", "receiver_postal_code", "check_receiver_postal_code"),
    "INT-004": ("Dirección de ULTRASIST", "receiver_address", None),
}


def _rules_table():
    return op.create_table(
        "validation_rules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "origin",
            sa.Enum("NATIONAL", "INTERNATIONAL", name="supplierorigin", native_enum=False, create_constraint=True),
            nullable=False,
        ),
        sa.Column("rule_code", sa.String(length=10), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("parameter", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", sa.Integer(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.CheckConstraint("is_active = (deleted_at IS NULL)", name="ck_validation_rules_soft_delete"),
        sa.CheckConstraint("version >= 1", name="ck_validation_rules_version_positive"),
        sa.CheckConstraint("char_length(name) BETWEEN 3 AND 80", name="ck_validation_rules_name_length"),
        sa.ForeignKeyConstraint(
            ["deleted_by"], ["users.id"], name=op.f("fk_validation_rules_deleted_by_users"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"], ["users.id"], name=op.f("fk_validation_rules_updated_by_users"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_validation_rules")),
        sa.UniqueConstraint("origin", "rule_code", name="uq_validation_rules_origin_code"),
    )


def rule_values(settings: Mapping) -> list[tuple[str, str, str, object, bool]]:
    """(origen, codigo, nombre, valor esperado, activa) de cada regla a partir de la configuracion unica. Las pruebas
    la usan para devolver las reglas a la instalacion inicial."""
    rows = []
    for code, (name, column, check) in NATIONAL.items():
        value = settings[column]
        parameter = list(value) if isinstance(value, (list, tuple)) else value
        rows.append(("NATIONAL", code, name, parameter, bool(check and settings[check])))
    for code, (name, column, check) in INTERNATIONAL.items():
        if code == "INT-004":
            active = bool(settings["receiver_address"].strip())
        else:
            active = bool(settings[check]) if check else True
        rows.append(("INTERNATIONAL", code, name, settings[column] if column else None, active))
    return rows


def upgrade() -> None:
    bind = op.get_bind()
    settings = bind.execute(sa.text("SELECT * FROM validation_settings WHERE id = 1")).mappings().one()
    table = _rules_table()
    now = datetime.now(timezone.utc)
    op.bulk_insert(
        table,
        [
            {
                "origin": origin,
                "rule_code": code,
                "name": name,
                "parameter": parameter,
                "is_active": active,
                "deleted_at": None if active else now,
                "deleted_by": None,
                "version": 1,
                "created_at": now,
                "updated_at": now,
                "updated_by": settings["updated_by"],
            }
            for origin, code, name, parameter, active in rule_values(settings)
        ],
    )
    op.drop_table("validation_settings")


def downgrade() -> None:
    bind = op.get_bind()
    rules = {
        (rule.origin, rule.rule_code): rule
        for rule in bind.execute(sa.text("SELECT origin, rule_code, parameter, is_active FROM validation_rules"))
    }

    def national(code):
        return rules[("NATIONAL", code)]

    def international(code):
        return rules[("INTERNATIONAL", code)]

    address = international("INT-004")
    representable = (
        (international("INT-002").parameter, international("INT-002").is_active)
        == (national("XML-009").parameter, national("XML-009").is_active)
        and (international("INT-003").parameter, international("INT-003").is_active)
        == (national("XML-010").parameter, national("XML-010").is_active)
        and address.is_active == bool((address.parameter or "").strip())
        and international("INT-001").is_active
        and not national("XML-011").is_active
    )
    if not representable:
        raise NotImplementedError(
            "No se puede revertir 0020_validation_rules: las reglas internacionales o XML-011 tienen configuracion que"
            " la fila unica de validation_settings no puede representar. Restaure un respaldo."
        )
    op.create_table(
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
        *(sa.Column(name, sa.Boolean(), nullable=False) for name in CHECKS),
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
    values = {column: national(code).parameter for code, (_, column, _) in NATIONAL.items()}
    values.update({check: national(code).is_active for code, (_, _, check) in NATIONAL.items() if check})
    values["receiver_address"] = address.parameter or ""
    bind.execute(
        sa.text(
            "INSERT INTO validation_settings (id, receiver_rfc, receiver_name, receiver_address, receiver_postal_code,"
            " receiver_tax_regime, payment_method, payment_form, allowed_cfdi_uses, check_receiver_rfc,"
            " check_receiver_name, check_receiver_postal_code, check_payment_method, check_payment_form,"
            " check_cfdi_use, version, updated_at) VALUES (1, :receiver_rfc, :receiver_name, :receiver_address,"
            " :receiver_postal_code, :receiver_tax_regime, :payment_method, :payment_form, :allowed_cfdi_uses,"
            " :check_receiver_rfc, :check_receiver_name, :check_receiver_postal_code, :check_payment_method,"
            " :check_payment_form, :check_cfdi_use, 1, now())"
        ),
        values,
    )
    op.drop_table("validation_rules")
