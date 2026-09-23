import re
import unicodedata
from datetime import date
from app.rules.base import outcome


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.lower()).encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", value).split())


def contract_rules(invoice, contract, descriptions: list[str]):
    exists = contract is not None
    project = bool(contract and normalize_text(invoice.project_name) == normalize_text(contract.project_name))
    try:
        month, year = (int(x) for x in invoice.service_period.split("/"))
        period_ok = bool(contract and contract.start_date <= date(year, month, 1) <= contract.end_date)
    except (ValueError, TypeError):
        period_ok = False
    normalized = normalize_text(" ".join(descriptions))
    tech_tokens = set(normalize_text(contract.authorized_technology).split()) if contract else set()
    overlap = tech_tokens.intersection(normalized.split())
    local_match = bool(overlap) and invoice.service_period[:2] in normalized
    return [
        outcome("CON-001", "CON", exists, "CRITICAL", "Contrato correspondiente disponible", "Contrato no disponible"),
        outcome("CON-002", "CON", project, "ERROR", "Proyecto coincide", "Proyecto no coincide", contract.project_name if contract else None, invoice.project_name),
        outcome("CON-003", "CON", period_ok, "ERROR", "Periodo dentro de vigencia", "Periodo fuera de vigencia", f"{contract.start_date} a {contract.end_date}" if contract else None, invoice.service_period),
        outcome("CON-004", "CON", local_match if descriptions else None, "WARNING", "Mes y tecnologia detectados por heuristica", "Coincidencia local ambigua; delegada a SEM-001", contract.authorized_technology if contract else None, " | ".join(descriptions), warning=True, evidence={"matched_tokens": sorted(overlap)}),
    ]
