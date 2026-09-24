import sqlite3
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.database import SessionLocal, engine
from app.models import Invoice
from tests.conftest import invoice_by_number


def test_pragmas_en_cada_conexion_nueva():
    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
        assert connection.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"
        assert connection.exec_driver_sql("PRAGMA busy_timeout").scalar() == 5000
        assert connection.exec_driver_sql("PRAGMA synchronous").scalar() == 1  # NORMAL


def test_llave_foranea_inexistente_rechazada():
    existing = invoice_by_number("A-CORRECTA")
    with SessionLocal() as db:
        db.add(
            Invoice(
                internal_folio="FAC-FK-00001",
                supplier_id=9999,
                uploaded_by=existing.uploaded_by,
                invoice_number="FK-HUERFANA",
                service_period="08/2026",
                project_name="Proyecto",
                subtotal=Decimal("0"),
                tax=Decimal("0"),
                total=Decimal("0"),
            )
        )
        with pytest.raises(IntegrityError, match="FOREIGN KEY"):
            db.flush()
        db.rollback()


def test_lectura_durante_una_escritura_abierta():
    database = engine.url.database
    writer = sqlite3.connect(database, isolation_level=None)
    reader = sqlite3.connect(database, timeout=0)
    try:
        before = reader.execute("SELECT count(*) FROM invoices").fetchone()[0]
        writer.execute("BEGIN IMMEDIATE")
        writer.execute("UPDATE invoices SET comments = 'escritura en curso'")
        assert reader.execute("SELECT count(*) FROM invoices").fetchone()[0] == before
        assert reader.execute("SELECT count(*) FROM invoices WHERE comments = 'escritura en curso'").fetchone()[0] == 0
    finally:
        writer.execute("ROLLBACK")
        writer.close()
        reader.close()


def test_listado_de_proveedor_usa_indice_compuesto():
    with engine.connect() as connection:
        plan = connection.exec_driver_sql(
            "EXPLAIN QUERY PLAN SELECT * FROM invoices WHERE supplier_id = 1 ORDER BY created_at DESC"
        ).fetchall()
    detail = " ".join(row[-1] for row in plan)
    assert "ix_invoices_supplier_created" in detail
    assert "TEMP B-TREE" not in detail
