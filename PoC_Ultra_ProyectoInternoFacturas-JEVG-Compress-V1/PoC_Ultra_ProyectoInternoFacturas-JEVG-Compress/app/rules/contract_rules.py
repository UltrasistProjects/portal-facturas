import re
import unicodedata
from datetime import date

from app.rules.base import outcome


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.lower()).encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", value).split())


def month_of(day: date) -> tuple[int, int]:
    return day.year, day.month


def month_label(month: tuple[int, int]) -> str:
    """Mes en el formato del periodo capturado: MM/AAAA."""
    return f"{month[1]:02d}/{month[0]}"


def validity_label(contract) -> str | None:
    """Vigencia del contrato en el formato del periodo: "MM/AAAA a MM/AAAA"."""
    if contract is None:
        return None
    return f"{month_label(month_of(contract.start_date))} a {month_label(month_of(contract.end_date))}"


def period_month(period: str | None) -> tuple[int, int] | None:
    """(año, mes) de un periodo MM/AAAA; None si no tiene ese formato."""
    try:
        month, year = (int(part) for part in (period or "").split("/"))
    except ValueError:
        return None
    return (year, month) if 1 <= month <= 12 else None


def contract_rules(invoice, contract, descriptions: list[str]):
    exists = contract is not None
    project = bool(contract and normalize_text(invoice.project_name) == normalize_text(contract.project_name))
    period = period_month(invoice.service_period)
    # Por mes, como se captura: el periodo vale si su mes cae en la vigencia, aunque el contrato empiece o termine a
    # mitad de mes.
    period_ok = bool(contract and period and month_of(contract.start_date) <= period <= month_of(contract.end_date))
    normalized = normalize_text(" ".join(descriptions))
    tech_tokens = set(normalize_text(contract.authorized_technology).split()) if contract else set()
    overlap = tech_tokens.intersection(normalized.split())
    local_match = bool(overlap) and invoice.service_period[:2] in normalized
    return [
        outcome("CON-001", "CON", exists, "CRITICAL", "Contrato correspondiente disponible", "Contrato no disponible"),
        outcome(
            "CON-002",
            "CON",
            project,
            "ERROR",
            "Proyecto coincide",
            "Proyecto no coincide",
            contract.project_name if contract else None,
            invoice.project_name,
        ),
        outcome(
            "CON-003",
            "CON",
            period_ok,
            "ERROR",
            "Periodo dentro de vigencia",
            "Periodo fuera de vigencia",
            f"{month_label(month_of(contract.start_date))} a {month_label(month_of(contract.end_date))}"
            if contract
            else None,
            invoice.service_period,
        ),
        outcome(
            "CON-004",
            "CON",
            local_match if descriptions else None,
            "WARNING",
            "Mes y tecnologia detectados por heuristica",
            "Coincidencia local ambigua; delegada a SEM-001",
            contract.authorized_technology if contract else None,
            " | ".join(descriptions),
            warning=True,
            evidence={"matched_tokens": sorted(overlap)},
        ),
    ]
