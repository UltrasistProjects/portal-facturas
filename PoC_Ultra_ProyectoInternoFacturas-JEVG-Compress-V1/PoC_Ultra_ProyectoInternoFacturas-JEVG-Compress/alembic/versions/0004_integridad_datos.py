"""Integridad de datos (AUDITORIA BD-02, BD-04, BD-05, BD-11, BD-12).

- Montos como enteros en centavos (*_cents) y confianza en diezmilesimas (confidence_bp).
- Rutas de documentos relativas a la raiz de almacenamiento.
- FKs con ON DELETE RESTRICT, enumeraciones con CHECK, CHECKs de montos/vigencias/score y UNIQUE fiscales.

Antes de modificar nada verifica precondiciones y, si alguna falla, aborta con un informe sin tocar la BD:
los datos inconsistentes se corrigen a mano, nunca en silencio.
"""

import re

import sqlalchemy as sa
from alembic import op

revision = "0004_integridad_datos"
down_revision = "0003_login_attempts"
branch_labels = None
depends_on = None

# SQLite no nombra las FKs; la convencion permite eliminarlas y recrearlas en modo batch.
NAMING = {"fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"}

ENUMS = {
    ("users", "role"): ("role", ("PROVIDER", "INTERNAL", "ADMIN")),
    ("suppliers", "supplier_type"): ("suppliertype", ("PERSONA_FISICA", "PERSONA_MORAL")),
    ("suppliers", "status"): ("supplierstatus", ("ACTIVE", "INACTIVE")),
    ("contracts", "status"): ("contractstatus", ("ACTIVE", "INACTIVE")),
    ("invoices", "status"): (
        "invoicestatus",
        (
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
        ),
    ),
    ("documents", "processing_status"): ("processingstatus", ("PENDING", "PROCESSED", "FAILED")),
    ("validation_results", "status"): ("rulestatus", ("PASS", "FAIL", "WARNING", "NOT_APPLICABLE", "NOT_EVALUATED")),
    ("validation_results", "severity"): ("severity", ("INFO", "WARNING", "ERROR", "CRITICAL")),
    ("reviews", "decision"): ("reviewdecision", ("ACCEPTED", "REJECTED", "REQUIRES_CORRECTION", "COMMENT")),
}

# (tabla, columna local, tabla referida) de cada FK que pasa a ON DELETE RESTRICT.
FOREIGN_KEYS = {
    "users": [("supplier_id", "suppliers")],
    "contracts": [("supplier_id", "suppliers")],
    "invoices": [
        ("supplier_id", "suppliers"),
        ("uploaded_by", "users"),
        ("contract_id", "contracts"),
        ("reviewed_by", "users"),
    ],
    "documents": [
        ("invoice_id", "invoices"),
        ("supplier_id", "suppliers"),
        ("uploaded_by", "users"),
        ("replaced_document_id", "documents"),
    ],
    "validation_results": [("invoice_id", "invoices")],
    "reviews": [("invoice_id", "invoices"), ("reviewer_id", "users")],
    "audit_logs": [("user_id", "users")],
}

CHECKS = {
    "contracts": [
        ("ck_contracts_authorized_amount_positive", "authorized_amount_cents > 0"),
        ("ck_contracts_valid_period", "end_date >= start_date"),
    ],
    "invoices": [
        ("ck_invoices_subtotal_non_negative", "subtotal_cents >= 0"),
        ("ck_invoices_tax_non_negative", "tax_cents >= 0"),
        ("ck_invoices_total_non_negative", "total_cents >= 0"),
        ("ck_invoices_score_range", "validation_score IS NULL OR validation_score BETWEEN 0 AND 100"),
    ],
    "validation_results": [
        ("ck_validation_results_confidence", "confidence_bp IS NULL OR confidence_bp BETWEEN 0 AND 10000"),
    ],
}

# Columna original -> (columna nueva, escala).
SCALED = {
    "invoices": [("subtotal", "subtotal_cents", 2), ("tax", "tax_cents", 2), ("total", "total_cents", 2)],
    "contracts": [("authorized_amount", "authorized_amount_cents", 2)],
    "validation_results": [("confidence", "confidence_bp", 4)],
}


def relative_storage_path(path: str) -> str | None:
    """Ruta relativa a storage/ con "/", o None si no puede derivarse con seguridad."""
    parts = [part for part in path.replace("\\", "/").split("/") if part not in ("", ".")]
    if ".." in parts:
        return None
    if "storage" in parts:
        rest = parts[len(parts) - parts[::-1].index("storage") :]
        return "/".join(rest) or None
    if path.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", path):
        return None
    return "/".join(parts) or None


def _rows(bind, sql: str, **params) -> list:
    return list(bind.execute(sa.text(sql), params))


def precondition_problems(bind) -> list[str]:
    problems = []
    orphans = bind.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
    if orphans:
        problems.append(f"filas huerfanas (tabla, rowid, tabla referida): {[tuple(r)[:3] for r in orphans[:20]]}")
    for uuid, ids in _rows(
        bind, "SELECT uuid, group_concat(id) FROM invoices WHERE uuid IS NOT NULL GROUP BY uuid HAVING count(*) > 1"
    ):
        problems.append(f"UUID {uuid} duplicado en facturas {ids}")
    for supplier_id, number, ids in _rows(
        bind,
        "SELECT supplier_id, invoice_number, group_concat(id) FROM invoices "
        "GROUP BY supplier_id, invoice_number HAVING count(*) > 1",
    ):
        problems.append(f"numero {number!r} duplicado para el proveedor {supplier_id} en facturas {ids}")
    for (table, column), (_name, allowed) in ENUMS.items():
        values = ", ".join(f"'{value}'" for value in allowed)
        for row_id, value in _rows(bind, f"SELECT id, {column} FROM {table} WHERE {column} NOT IN ({values})"):
            problems.append(f"{table}.{column} con valor fuera de catalogo en id {row_id}: {value!r}")
    checks = {
        "montos negativos en facturas": "SELECT id FROM invoices WHERE subtotal < 0 OR tax < 0 OR total < 0",
        "monto autorizado no positivo": "SELECT id FROM contracts WHERE authorized_amount <= 0",
        "vigencia invertida": "SELECT id FROM contracts WHERE end_date < start_date",
        "score fuera de 0..100": (
            "SELECT id FROM invoices WHERE validation_score IS NOT NULL AND validation_score NOT BETWEEN 0 AND 100"
        ),
        "confianza fuera de 0..1": (
            "SELECT id FROM validation_results WHERE confidence IS NOT NULL AND (confidence < 0 OR confidence > 1)"
        ),
    }
    for table, columns in SCALED.items():
        for old, _new, scale in columns:
            factor = 10**scale
            checks[f"{table}.{old} con mas de {scale} decimales"] = (
                f"SELECT id FROM {table} WHERE {old} IS NOT NULL "
                f"AND abs({old} * {factor} - round({old} * {factor})) > 0.000001"
            )
    for description, sql in checks.items():
        ids = [row[0] for row in _rows(bind, sql)]
        if ids:
            problems.append(f"{description}: ids {ids[:20]}")
    for doc_id, path in _rows(bind, "SELECT id, path FROM documents"):
        if relative_storage_path(path) is None:
            problems.append(f"documents.id {doc_id}: no se puede derivar una ruta relativa de {path!r}")
    return problems


def upgrade() -> None:
    bind = op.get_bind()
    problems = precondition_problems(bind)
    if problems:
        raise RuntimeError(
            "Migracion 0004 abortada sin cambios. Corrija los datos y vuelva a ejecutar:\n- " + "\n- ".join(problems)
        )

    # 1. Datos: montos a enteros escalados y rutas relativas (antes de reconstruir las tablas).
    for table, columns in SCALED.items():
        for old, _new, scale in columns:
            op.execute(
                f"UPDATE {table} SET {old} = CAST(ROUND({old} * {10**scale}) AS INTEGER) WHERE {old} IS NOT NULL"
            )
    for doc_id, path in _rows(bind, "SELECT id, path FROM documents"):
        bind.execute(
            sa.text("UPDATE documents SET path = :path WHERE id = :id"),
            {"path": relative_storage_path(path), "id": doc_id},
        )

    # 2. Esquema: una reconstruccion por tabla.
    tables = sorted(set(FOREIGN_KEYS) | {table for table, _column in ENUMS} | set(CHECKS))
    for table in tables:
        with op.batch_alter_table(table, naming_convention=NAMING, recreate="always") as batch:
            for old, new, scale in SCALED.get(table, []):
                batch.alter_column(
                    old,
                    new_column_name=new,
                    type_=sa.Integer(),
                    existing_type=sa.Numeric(16, 2) if scale == 2 else sa.Numeric(5, 4),
                    existing_nullable=scale != 4,
                )
            for (enum_table, column), (name, allowed) in ENUMS.items():
                if enum_table == table:
                    batch.alter_column(
                        column,
                        type_=sa.Enum(*allowed, name=name, native_enum=False, create_constraint=True),
                        existing_nullable=False,
                    )
            for column, referred in FOREIGN_KEYS.get(table, []):
                name = f"fk_{table}_{column}_{referred}"
                batch.drop_constraint(name, type_="foreignkey")
                batch.create_foreign_key(name, referred, [column], ["id"], ondelete="RESTRICT")
            for name, condition in CHECKS.get(table, []):
                batch.create_check_constraint(name, condition)
            if table == "invoices":
                batch.drop_index("ix_invoices_uuid")
                batch.create_unique_constraint("uq_invoices_uuid", ["uuid"])
                batch.create_unique_constraint("uq_invoices_supplier_number", ["supplier_id", "invoice_number"])


def downgrade() -> None:
    raise NotImplementedError("Revertir la conversion de montos y restricciones requiere restaurar un respaldo.")
