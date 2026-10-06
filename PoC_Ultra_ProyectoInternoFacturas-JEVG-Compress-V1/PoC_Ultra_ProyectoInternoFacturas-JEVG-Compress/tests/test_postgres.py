from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.database import SessionLocal, engine
from app.models import Invoice
from tests.conftest import invoice_by_number, supplier_by_email


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
        with pytest.raises(IntegrityError, match="violates foreign key constraint"):
            db.flush()
        db.rollback()


def test_todas_las_llaves_foraneas_son_restrict():
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT conname, confdeltype FROM pg_constraint "
                "WHERE contype = 'f' AND connamespace = 'public'::regnamespace"
            )
        ).all()
    assert len(rows) >= 19
    assert {name: action for name, action in rows if action != "r"} == {}


def test_sesion_en_utc():
    with engine.connect() as connection:
        assert connection.execute(text("SHOW TimeZone")).scalar() == "UTC"


def test_lectura_durante_una_escritura_abierta():
    with engine.connect() as writer, engine.connect() as reader:
        before = reader.execute(text("SELECT count(*) FROM invoices")).scalar()
        reader.rollback()
        writer.execute(text("UPDATE invoices SET comments = 'escritura en curso'"))  # sin confirmar
        # Si la lectura esperara al escritor, este limite la haria fallar en lugar de bloquear la prueba.
        reader.execute(text("SET LOCAL statement_timeout = '2s'"))
        assert reader.execute(text("SELECT count(*) FROM invoices")).scalar() == before
        pending = reader.execute(text("SELECT count(*) FROM invoices WHERE comments = 'escritura en curso'"))
        assert pending.scalar() == 0
        writer.rollback()


def test_listado_de_proveedor_usa_indice_compuesto():
    supplier = supplier_by_email("proveedor1@poc.local")
    with engine.connect() as connection:
        # Con pocas filas el planificador preferiria recorrer la tabla, o un bitmap scan seguido de un Sort, segun
        # las estadisticas del momento. Sin ellos se evalua el plan que tendria con volumen: acceso ordenado por indice.
        # Estadisticas al dia: si el autovacuum las tomo a mitad de la suite, sobrestiman a un proveedor y el
        # planificador prefiere ix_invoices_created_at con filtro.
        connection.execute(text("ANALYZE invoices"))
        connection.execute(text("SET LOCAL enable_seqscan = off"))
        connection.execute(text("SET LOCAL enable_bitmapscan = off"))
        # Con una tabla de pocas paginas, el recorrido de ix_invoices_created_at sigue el orden fisico del heap y el
        # costo por lectura aleatoria (4 por defecto) empata los dos planes; el ancho de la fila basta para inclinarlo.
        # Con el costo de un disco SSD el resultado ya no depende del tamano de la tabla de pruebas.
        connection.execute(text("SET LOCAL random_page_cost = 1.1"))
        plan = connection.execute(
            text("EXPLAIN SELECT * FROM invoices WHERE supplier_id = :id ORDER BY created_at DESC"),
            {"id": supplier.id},
        ).scalars()
        detail = "\n".join(plan)
    assert "ix_invoices_supplier_created" in detail, detail
    assert "Sort" not in detail, detail
