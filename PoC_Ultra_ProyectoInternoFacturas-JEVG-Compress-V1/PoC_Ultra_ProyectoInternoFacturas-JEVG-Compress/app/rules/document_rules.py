from collections.abc import Iterable
from typing import Protocol

from app.core.constants import DocumentType, SupplierOrigin
from app.rules.base import not_applicable, outcome


class RequiredDocument(Protocol):
    """Tipo de documento exigido para el origen del proveedor (clave y nombre del catalogo)."""

    code: str
    name: str


# Tipos con regla propia -> (codigo, severidad). Resultan PASS/FAIL cuando el tipo es Obligatorio para el origen y
# NOT_APPLICABLE en otro caso. Cada otro tipo Obligatorio genera un resultado DOC-009.
DEDICATED_RULES = {
    DocumentType.INVOICE_XML: ("DOC-001", "CRITICAL"),
    DocumentType.INVOICE_PDF: ("DOC-002", "ERROR"),
    DocumentType.PURCHASE_ORDER: ("DOC-003", "ERROR"),
    DocumentType.APPROVAL: ("DOC-004", "ERROR"),
    DocumentType.FOREIGN_INVOICE: ("DOC-008", "CRITICAL"),
}
NOT_REQUIRED = {
    SupplierOrigin.NATIONAL: "No requerido para proveedores nacionales",
    SupplierOrigin.INTERNATIONAL: "No requerido para proveedores internacionales",
}


def _presence(code: str, severity: str, document: RequiredDocument, present: set[str], source_document=None):
    return outcome(
        code,
        "DOC",
        document.code in present,
        severity,
        f"{document.name} presente",
        f"Falta {document.name}",
        document.code,
        document.code if document.code in present else "Ausente",
        source_document=source_document,
    )


def document_rules(
    present: set[str],
    required: Iterable[RequiredDocument],
    origin: SupplierOrigin,
    processable: bool,
    contract_available: bool,
):
    """Reglas documentales segun los archivos minimos configurados para el origen del proveedor (HU-04). `present`
    son las claves de los documentos vigentes; `required`, los tipos activos Obligatorios en el orden del catalogo."""
    required = list(required)
    by_code = {document.code: document for document in required}

    def dedicated(document_type: DocumentType):
        code, severity = DEDICATED_RULES[document_type]
        document = by_code.get(document_type)
        if document is None:
            return not_applicable(code, "DOC", severity, NOT_REQUIRED[origin], document_type.value)
        return _presence(code, severity, document, present)

    results = [
        dedicated(t)
        for t in (
            DocumentType.INVOICE_XML,
            DocumentType.INVOICE_PDF,
            DocumentType.PURCHASE_ORDER,
            DocumentType.APPROVAL,
        )
    ]
    results.append(
        outcome(
            "DOC-005",
            "DOC",
            contract_available,
            "ERROR",
            "Contrato/anexo disponible",
            "Falta contrato/anexo",
            "Contrato activo",
            contract_available,
        )
    )
    results.append(
        outcome(
            "DOC-006",
            "DOC",
            True,
            "INFO",
            "Complemento no requerido en esta etapa",
            "Falta complemento",
            "No aplicable",
            "No aplicable",
        )
    )
    results.append(
        outcome("DOC-007", "DOC", processable, "CRITICAL", "Archivos procesables", "Hay archivos no procesables")
    )
    results.append(dedicated(DocumentType.FOREIGN_INVOICE))
    results += [
        _presence("DOC-009", "ERROR", document, present, source_document=document.code)
        for document in required
        if document.code not in DEDICATED_RULES
    ]
    return results
