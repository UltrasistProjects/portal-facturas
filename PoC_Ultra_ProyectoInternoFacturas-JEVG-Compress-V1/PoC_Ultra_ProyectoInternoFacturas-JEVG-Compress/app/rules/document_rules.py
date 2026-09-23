from app.rules.base import outcome


def document_rules(types: set[str], processable: bool, contract_available: bool):
    specs = [("DOC-001", "INVOICE_XML", "XML CFDI"), ("DOC-002", "INVOICE_PDF", "PDF de factura"),
             ("DOC-003", "PURCHASE_ORDER", "orden de compra"), ("DOC-004", "APPROVAL", "Vo.Bo.")]
    results = [outcome(code, "DOC", doc_type in types, "CRITICAL" if code == "DOC-001" else "ERROR",
                       f"{label} presente", f"Falta {label}", doc_type, doc_type if doc_type in types else "Ausente") for code, doc_type, label in specs]
    results.append(outcome("DOC-005", "DOC", contract_available, "ERROR", "Contrato/anexo disponible", "Falta contrato/anexo", "Contrato activo", contract_available))
    results.append(outcome("DOC-006", "DOC", True, "INFO", "Complemento no requerido en esta etapa", "Falta complemento", "No aplicable", "No aplicable"))
    results.append(outcome("DOC-007", "DOC", processable, "CRITICAL", "Archivos procesables", "Hay archivos no procesables"))
    return results

