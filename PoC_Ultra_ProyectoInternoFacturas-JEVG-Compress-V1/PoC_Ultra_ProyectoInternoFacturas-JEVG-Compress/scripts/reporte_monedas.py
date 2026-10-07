"""Reporte de monedas fuera del catalogo (ajustes-finales-configuracion). Solo lectura.

Lista las facturas (folio, proveedor, estatus y moneda) y los contratos (id, proyecto y moneda) cuya moneda no es una
clave del catalogo de monedas. La migracion 0021_currency_catalog_mapping normaliza las que puede (mayusculas y alias)
y conserva las demas; este reporte las muestra para que se corrijan a mano.

Uso: python scripts/reporte_monedas.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import STATUS_LABELS, CatalogType
from app.core.database import SessionLocal
from app.models import CatalogEntry, Contract, Invoice, Supplier


def catalog_codes(db: Session) -> set[str]:
    return set(db.scalars(select(CatalogEntry.code).where(CatalogEntry.catalog == CatalogType.CURRENCY)))


def unmapped_invoices(db: Session, codes: set[str]) -> list[tuple[str, str, str, str]]:
    stmt = (
        select(Invoice.internal_folio, Supplier.business_name, Invoice.status, Invoice.currency)
        .join(Invoice.supplier)
        .where(Invoice.currency.not_in(codes))
        .order_by(Invoice.internal_folio)
    )
    return [
        (folio, supplier, STATUS_LABELS[status], currency) for folio, supplier, status, currency in db.execute(stmt)
    ]


def unmapped_contracts(db: Session, codes: set[str]) -> list[tuple[int, str, str]]:
    stmt = (
        select(Contract.id, Contract.project_name, Contract.currency)
        .where(Contract.currency.not_in(codes))
        .order_by(Contract.id)
    )
    return [tuple(row) for row in db.execute(stmt)]


def main() -> int:
    with SessionLocal() as db:
        codes = catalog_codes(db)
        invoices = unmapped_invoices(db, codes)
        contracts = unmapped_contracts(db, codes)
    print(f"Catálogo de monedas: {', '.join(sorted(codes))}")
    print(f"Facturas con moneda fuera del catálogo: {len(invoices)}")
    for folio, supplier, status, currency in invoices:
        print(f"  {folio} · {supplier} · {status} · moneda {currency!r}")
    print(f"Contratos con moneda fuera del catálogo: {len(contracts)}")
    for contract_id, project, currency in contracts:
        print(f"  contrato {contract_id} · {project} · moneda {currency!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
