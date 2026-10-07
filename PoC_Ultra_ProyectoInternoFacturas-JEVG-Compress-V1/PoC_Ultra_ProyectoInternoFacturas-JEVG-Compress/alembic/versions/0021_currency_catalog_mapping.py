"""Monedas de facturas y contratos del catalogo de monedas (ajustes-finales-configuracion).

Normaliza invoices.currency y contracts.currency: sin espacios, en mayusculas y con alias conocidos (MN y MXP -> MXN;
DLS, DLL y US -> USD; EU -> EUR), siempre que el resultado sea una clave del catalogo de monedas. Cada cambio se
audita como CURRENCY_NORMALIZED, sin usuario. Un valor que no se puede mapear se conserva y se registra en el log de
la migracion; scripts/reporte_monedas.py los lista.

Sin cambios de esquema. El downgrade no revierte la normalizacion: los valores normalizados son validos.
"""

import json
import logging
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "0021_currency_catalog_mapping"
down_revision = "0020_validation_rules"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

ALIASES = {"MN": "MXN", "MXP": "MXN", "DLS": "USD", "DLL": "USD", "US": "USD", "EU": "EUR"}
# Tabla -> (entidad de la auditoria, columna que identifica el registro en el log).
TABLES = {"invoices": ("Invoice", "internal_folio"), "contracts": ("Contract", "project_name")}
UNMAPPED = "Moneda sin clave en el catalogo: %s %s (%s) = %r"
AUDIT_INSERT = sa.text(
    "INSERT INTO audit_logs (action, entity, entity_id, old_value, new_value, timestamp) VALUES"
    " ('CURRENCY_NORMALIZED', :entity, :entity_id, CAST(:old AS jsonb), CAST(:new AS jsonb), :now)"
)


def normalize(value: str | None, codes: set[str]) -> str | None:
    """Clave del catalogo que corresponde al valor, o None si no hay una."""
    plain = (value or "").strip().upper()
    candidate = ALIASES.get(plain, plain)
    return candidate if candidate in codes else None


def upgrade() -> None:
    bind = op.get_bind()
    codes = set(bind.scalars(sa.text("SELECT code FROM catalog_entries WHERE catalog = 'CURRENCY'")))
    now = datetime.now(timezone.utc)
    for table, (entity, label) in TABLES.items():
        rows = bind.execute(sa.text(f"SELECT id, {label} AS label, currency FROM {table}"))
        for row in rows.all():
            target = normalize(row.currency, codes)
            if target is None:
                logger.warning(
                    "Moneda sin clave en el catalogo: %s %s (%s) = %r", entity, row.id, row.label, row.currency
                )
                continue
            if target == row.currency:
                continue
            bind.execute(
                sa.text(f"UPDATE {table} SET currency = :currency WHERE id = :id"), {"currency": target, "id": row.id}
            )
            bind.execute(
                AUDIT_INSERT,
                {
                    "entity": entity,
                    "entity_id": str(row.id),
                    "old": json.dumps({"currency": row.currency}),
                    "new": json.dumps({"currency": target}),
                    "now": now,
                },
            )


def downgrade() -> None:
    """La normalizacion no se revierte: los valores anteriores no eran claves del catalogo."""
