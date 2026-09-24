from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError, StatementError

from app.core.database import SessionLocal
from app.core.errors import BusinessRuleError
from app.models import Contract, Document, Invoice
from app.services.reconciliation_service import reconcile_amount
from tests.conftest import csrf, invoice_by_number, login, supplier_by_email


@pytest.fixture()
def db():
    """Sesion cuya transaccion se revierte: las pruebas no alteran la BD compartida."""
    with SessionLocal() as session:
        yield session
        session.rollback()


def new_invoice(db, **overrides) -> Invoice:
    base = invoice_by_number("A-CORRECTA")
    values = {
        "internal_folio": f"TST-{uuid4().hex[:20]}",
        "supplier_id": base.supplier_id,
        "uploaded_by": base.uploaded_by,
        "contract_id": base.contract_id,
        "invoice_number": f"TST-{uuid4().hex[:12]}",
        "service_period": "08/2026",
        "project_name": "Proyecto",
        "subtotal": Decimal("0"),
        "tax": Decimal("0"),
        "total": Decimal("0"),
        **overrides,
    }
    invoice = Invoice(**values)
    db.add(invoice)
    return invoice


def test_almacenamiento_exacto_en_numeric(db):
    invoice = new_invoice(db, subtotal=Decimal("100000.10"))
    db.flush()
    stored = db.execute(
        text("SELECT subtotal, pg_typeof(subtotal)::text FROM invoices WHERE id = :id"), {"id": invoice.id}
    )
    assert stored.one() == (Decimal("100000.10"), "numeric")
    db.expire(invoice)
    assert invoice.subtotal == Decimal("100000.10")


# (tabla, columna) -> tipo nativo esperado (information_schema).
NATIVE_TYPES = {
    **{("invoices", column): ("numeric", 16, 2) for column in ("subtotal", "tax", "total")},
    ("contracts", "authorized_amount"): ("numeric", 16, 2),
    ("contract_amendments", "previous_amount"): ("numeric", 16, 2),
    ("contract_amendments", "new_amount"): ("numeric", 16, 2),
    ("validation_results", "confidence"): ("numeric", 5, 4),
    ("invoices", "created_at"): ("timestamp with time zone", None, None),
    ("audit_logs", "timestamp"): ("timestamp with time zone", None, None),
    ("documents", "metadata_json"): ("jsonb", None, None),
    ("validation_results", "evidence_json"): ("jsonb", None, None),
    ("audit_logs", "old_value"): ("jsonb", None, None),
    ("audit_logs", "new_value"): ("jsonb", None, None),
}


def test_columnas_con_tipos_nativos_sin_sufijos(db):
    rows = db.execute(
        text(
            "SELECT table_name, column_name, data_type, numeric_precision, numeric_scale "
            "FROM information_schema.columns WHERE table_schema = 'public'"
        )
    ).all()
    columns = {(table, column): (data_type, precision, scale) for table, column, data_type, precision, scale in rows}
    assert {key: columns.get(key) for key in NATIVE_TYPES} == NATIVE_TYPES
    assert [key for key in columns if key[1].endswith(("_cents", "_bp"))] == []
    # Ninguna fecha-hora sin zona horaria.
    assert [key for key, value in columns.items() if value[0] == "timestamp without time zone"] == []


def test_precision_excesiva_rechazada(db):
    stored_rounded = "SELECT count(*) FROM invoices WHERE total = 10.01"
    before = db.scalar(text(stored_rounded))
    new_invoice(db, total=Decimal("10.005"))
    with pytest.raises(StatementError, match="mas de 2 decimales"):
        db.flush()
    db.rollback()
    assert db.scalar(text(stored_rounded)) == before  # PostgreSQL no llego a redondearlo a 10.01


def test_suma_exacta_en_sql(db):
    ids = []
    for amount in ("0.10", "0.20", "0.30"):
        invoice = new_invoice(db, total=Decimal(amount))
        db.flush()
        ids.append(invoice.id)
    assert db.scalar(select(func.sum(Invoice.total)).where(Invoice.id.in_(ids))) == Decimal("0.60")


def test_limite_exacto_de_fin_001(db):
    supplier = supplier_by_email("proveedor1@poc.local")
    contract = Contract(
        supplier_id=supplier.id,
        project_name="Limite",
        project_leader="L",
        authorized_technology="T",
        authorized_amount=Decimal("100000.10"),
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
    )
    db.add(contract)
    db.flush()
    db.expire(contract)
    assert reconcile_amount(contract.authorized_amount, Decimal("100000.10")).result == "PASS"


def test_uuid_unico_y_multiples_nulos(db):
    new_invoice(db, uuid=None)
    new_invoice(db, uuid=None)
    db.flush()
    new_invoice(db, uuid="UUID-UNICO-1")
    db.flush()
    new_invoice(db, uuid="UUID-UNICO-1")
    with pytest.raises(IntegrityError, match='violates unique constraint "uq_invoices_uuid"'):
        db.flush()


def test_numero_unico_por_proveedor(db):
    new_invoice(db, invoice_number="NUMERO-X")
    db.flush()
    other = supplier_by_email("proveedor2@poc.local")
    new_invoice(db, invoice_number="NUMERO-X", supplier_id=other.id, contract_id=None)
    db.flush()  # otro proveedor: permitido
    new_invoice(db, invoice_number="NUMERO-X")
    with pytest.raises(IntegrityError, match='violates unique constraint "uq_invoices_supplier_number"'):
        db.flush()


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE invoices SET status = 'APROBADA'",
        "UPDATE invoices SET total = -1.00",
        "UPDATE invoices SET validation_score = 101",
        "UPDATE contracts SET end_date = '2025-01-01'",
        "UPDATE contracts SET authorized_amount = 0",
        "UPDATE validation_results SET confidence = 1.0001",
        "UPDATE suppliers SET status = 'BAJA'",
        "UPDATE users SET role = 'ROOT'",
        "UPDATE reviews SET decision = 'QUIZAS'",
        "UPDATE documents SET processing_status = 'RARO'",
    ],
)
def test_check_rechaza_valores_invalidos_por_sql_directo(db, sql):
    with pytest.raises(IntegrityError, match="violates check constraint"):
        db.execute(text(sql))


def test_enmienda_con_monto_no_positivo_rechazada(db):
    with pytest.raises(IntegrityError, match='violates check constraint "ck_contract_amendments_new_amount_positive"'):
        db.execute(
            text(
                "INSERT INTO contract_amendments (contract_id, previous_amount, new_amount, reason, created_by, "
                "created_at) SELECT c.id, c.authorized_amount, 0, 'prueba', u.id, now() "
                "FROM contracts c CROSS JOIN users u LIMIT 1"
            )
        )


def test_borrado_de_factura_por_orm_prohibido(db):
    invoice = db.get(Invoice, invoice_by_number("A-CORRECTA").id)
    db.delete(invoice)
    with pytest.raises(BusinessRuleError, match="Borrado fisico"):
        db.flush()
    db.rollback()
    assert db.get(Invoice, invoice.id) is not None


def test_quitar_documento_de_la_coleccion_no_lo_borra(db):
    invoice = db.get(Invoice, invoice_by_number("A-CORRECTA").id)
    document = invoice.documents[0]
    invoice.documents.remove(document)
    db.flush()
    assert db.get(Document, document.id) is not None


def test_borrado_sql_de_factura_con_documentos(db):
    invoice = invoice_by_number("A-CORRECTA")
    with pytest.raises(IntegrityError, match='violates RESTRICT setting of foreign key constraint "fk_documents_'):
        db.execute(text("DELETE FROM invoices WHERE id = :id"), {"id": invoice.id})


def test_fechas_hora_en_utc(db):
    assert invoice_by_number("A-CORRECTA").created_at.tzinfo == timezone.utc
    local = datetime(2026, 8, 20, 19, 0, tzinfo=ZoneInfo("America/Mexico_City"))
    invoice = new_invoice(db, created_at=local)
    db.flush()
    raw = db.execute(
        text("SELECT to_char(created_at AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS') FROM invoices WHERE id = :id"),
        {"id": invoice.id},
    ).scalar()
    assert raw == "2026-08-21 01:00:00"
    db.expire(invoice)
    assert invoice.created_at == datetime(2026, 8, 21, 1, 0, tzinfo=timezone.utc)
    assert invoice.created_at.tzinfo == timezone.utc


def test_ruta_manipulada_fuera_de_la_raiz(client):
    invoice = invoice_by_number("A-CORRECTA")
    with SessionLocal() as session:
        document = session.scalar(select(Document).where(Document.invoice_id == invoice.id).order_by(Document.id))
        original, document.path = document.path, "../../.env"
        session.commit()
        try:
            login(client)
            assert client.get(f"/invoices/{invoice.id}/documents/{document.id}/download").status_code == 404
        finally:
            document.path = original
            session.commit()


def test_rutas_relativas_en_documentos():
    with SessionLocal() as session:
        paths = session.scalars(select(Document.path)).all()
    assert paths
    for path in paths:
        assert not path.startswith("/") and "\\" not in path and ":" not in path
        assert path.split("/")[0] in {"invoices", "suppliers"}


def test_contrato_con_vigencia_invertida_muestra_error(client):
    supplier = supplier_by_email("proveedor1@poc.local")
    login(client)
    data = {
        "supplier_id": supplier.id,
        "project_name": "Vigencia invertida",
        "project_leader": "Lider",
        "authorized_technology": "Python",
        "authorized_amount": "1000.00",
        "currency": "MXN",
        "start_date": "2026-12-31",
        "end_date": "2026-01-01",
        "csrf_token": csrf(client, "/contracts"),
    }
    response = client.post("/contracts", data=data)
    assert response.status_code == 400
    assert "la fecha de fin no puede ser anterior" in response.text
    with SessionLocal() as session:
        assert session.scalar(select(Contract).where(Contract.project_name == "Vigencia invertida")) is None
