from datetime import date, timedelta

from app.core.constants import SUPPLIER_REQUIREMENTS


def supplier_requirement_status(supplier, documents) -> list[dict]:
    current = {d.document_type: d for d in documents if d.is_current}
    rows = []
    for code in SUPPLIER_REQUIREMENTS[supplier.supplier_type]:
        doc = current.get(code)
        expired = bool(
            doc
            and doc.document_date
            and doc.document_date < date.today() - timedelta(days=93)
            and code in {"TAX_STATUS", "SAT_OPINION", "ADDRESS_PROOF", "BANK_STATEMENT"}
        )
        rows.append({"code": code, "present": bool(doc), "expired": expired})
    return rows
