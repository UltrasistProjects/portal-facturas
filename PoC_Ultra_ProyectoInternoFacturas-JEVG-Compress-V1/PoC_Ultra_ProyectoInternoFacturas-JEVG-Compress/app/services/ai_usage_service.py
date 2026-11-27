"""Consumo de la lectura con IA (pantalla "Consumo de IA" del Administrador).

Cada lectura de factura con IA, exitosa o no, deja una fila en ai_usage con sus paginas de OCR, tokens de OpenAI y
duraciones. Se escribe en su propia transaccion: el consumo se conserva aunque el registro de la factura falle
despues (por ejemplo, un numero repetido). Registrarlo nunca impide leer la factura.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.models import AiUsage, now_utc
from app.repositories.pagination import Page, paginate

logger = logging.getLogger(__name__)

OCR_SERVICE = "azure_document_intelligence"
WINDOW_DAYS = 30
DAILY_DAYS = 14
OUTCOME_LABELS = {"ok": "Leída", "incomplete": "Incompleta", "error": "Falló"}
PROVIDER_LABELS = {
    "document_intelligence_openai": "Document Intelligence + OpenAI",
    "azure_document_intelligence": "Document Intelligence",
    "azure_openai": "Azure OpenAI",
    "openai": "OpenAI",
}
REASON_LABELS = {
    "not_configured": "Sin configurar",
    "auth": "Llave inválida",
    "not_found": "Endpoint o modelo inexistente",
    "quota": "Cuota agotada",
    "timeout": "Tiempo agotado",
    "network": "Sin conexión",
    "service": "Error del servicio",
    "failed": "El análisis falló",
    "invalid_response": "Respuesta inválida",
    "no_text": "Sin texto",
    "error": "Error inesperado",
}


def _steps(evidence: dict[str, Any], steps: list[dict[str, Any]] | None) -> tuple[dict, dict]:
    """(paso de OCR, paso de OpenAI) de la evidencia o de los pasos que se completaron antes de una falla."""
    ocr, llm = {}, {}
    for step in [*(evidence.get("steps") or []), *(steps or [])]:
        if step.get("service") == OCR_SERVICE:
            ocr = step
        elif step.get("service"):
            llm = step
    return ocr, llm


def usage_row(evidence: dict[str, Any], has_text: bool, source: str | None, steps=None) -> AiUsage:
    ocr, llm = _steps(evidence, steps)
    discrepancies = evidence.get("discrepancies")
    return AiUsage(
        created_at=now_utc(),
        provider=str(evidence.get("provider") or "desconocido")[:60],
        outcome=evidence.get("outcome") or "error",
        reason=evidence.get("reason"),
        has_text=has_text,
        source=source,
        duration_ms=int(evidence.get("duration_ms") or 0),
        ocr_model=ocr.get("model"),
        ocr_pages=ocr.get("pages"),
        ocr_duration_ms=ocr.get("duration_ms"),
        llm_service=llm.get("service"),
        llm_model=llm.get("deployment") or llm.get("model"),
        llm_duration_ms=llm.get("duration_ms"),
        input_tokens=llm.get("input_tokens"),
        output_tokens=llm.get("output_tokens"),
        discrepancies=len(discrepancies) if isinstance(discrepancies, list) else None,
    )


def record(evidence: dict[str, Any], has_text: bool, source: str | None, steps=None) -> None:
    """Guarda la lectura en su propia transaccion. Un error al guardarla se registra y se ignora."""
    try:
        with SessionLocal() as db:
            db.add(usage_row(evidence, has_text, source, steps))
            db.commit()
    except Exception as exc:  # noqa: BLE001 - medir el consumo nunca impide registrar la factura
        logger.warning(
            "ai.usage_not_recorded", extra={"event": "ai.usage_not_recorded", "error_type": type(exc).__name__}
        )


@dataclass(frozen=True)
class Summary:
    readings: int = 0
    ok: int = 0
    failed: int = 0
    pages: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    avg_ms: int = 0
    max_ms: int = 0

    @property
    def tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def cost(self) -> Decimal | None:
        return estimated_cost(self.pages, self.input_tokens, self.output_tokens)


def estimated_cost(pages: int, input_tokens: int, output_tokens: int) -> Decimal | None:
    """Costo estimado en USD con los precios configurados; None si no hay ninguno."""
    prices = (
        settings.ai_price_ocr_1k_pages_usd,
        settings.ai_price_input_1m_tokens_usd,
        settings.ai_price_output_1m_tokens_usd,
    )
    if all(price is None for price in prices):
        return None
    ocr, prompt, completion = (price or Decimal(0) for price in prices)
    total = ocr * pages / 1000 + prompt * input_tokens / 1_000_000 + completion * output_tokens / 1_000_000
    return total.quantize(Decimal("0.0001"))


def _aggregates():
    return (
        func.count(AiUsage.id),
        func.count(case((AiUsage.outcome == "ok", 1))),
        func.coalesce(func.sum(AiUsage.ocr_pages), 0),
        func.coalesce(func.sum(AiUsage.input_tokens), 0),
        func.coalesce(func.sum(AiUsage.output_tokens), 0),
        func.coalesce(func.avg(AiUsage.duration_ms), 0),
        func.coalesce(func.max(AiUsage.duration_ms), 0),
    )


def _summary(row) -> Summary:
    readings, ok, pages, prompt, completion, avg_ms, max_ms = row
    return Summary(readings, ok, readings - ok, int(pages), int(prompt), int(completion), round(avg_ms), max_ms)


def summary(db: Session, since: datetime | None = None) -> Summary:
    stmt = select(*_aggregates())
    if since is not None:
        stmt = stmt.where(AiUsage.created_at >= since)
    return _summary(db.execute(stmt).one())


def daily(db: Session, days: int = DAILY_DAYS) -> list[tuple[Any, Summary]]:
    """Consumo por dia (zona horaria del negocio) de los ultimos `days` dias con lecturas, del mas reciente."""
    day = func.date(func.timezone(settings.business_timezone, AiUsage.created_at)).label("day")
    since = now_utc() - timedelta(days=days)
    stmt = select(day, *_aggregates()).where(AiUsage.created_at >= since).group_by(day).order_by(day.desc())
    return [(row[0], _summary(row[1:])) for row in db.execute(stmt)]


def readings_page(db: Session, page: int = 1) -> Page[AiUsage]:
    stmt = select(AiUsage).order_by(AiUsage.created_at.desc(), AiUsage.id.desc())
    return paginate(db, stmt, page)


def overview(db: Session) -> dict[str, Any]:
    now = now_utc()
    today = datetime.now(ZoneInfo(settings.business_timezone)).replace(hour=0, minute=0, second=0, microsecond=0)
    return {
        "today": summary(db, today),
        "window": summary(db, now - timedelta(days=WINDOW_DAYS)),
        "total": summary(db),
        "daily": daily(db),
    }


def configuration() -> list[tuple[str, str]]:
    """Configuracion vigente para la pantalla, sin llaves (solo si estan definidas)."""

    def defined(secret) -> str:
        return "Definida" if secret.get_secret_value() else "Sin definir"

    from app.services.ai.openai_analyzer import target

    llm = target()
    rows = [
        ("IA activa", "Sí" if settings.ai_enabled else "No (el portal lee el PDF sin IA)"),
        ("Proveedor", settings.document_ai_provider),
        ("Document Intelligence", settings.azure_document_intelligence_endpoint or "Sin definir"),
        ("Llave de Document Intelligence", defined(settings.azure_document_intelligence_key)),
        (
            "Modelo de OCR",
            f"{settings.azure_document_intelligence_model} · API {settings.azure_document_intelligence_api_version}",
        ),
        ("OpenAI", PROVIDER_LABELS.get(llm.provider, llm.provider) if llm else "Sin configurar"),
        ("Deployment o modelo", f"{llm.model} · API {llm.api_version or 'v1'}" if llm else "—"),
        (
            "Tiempos límite",
            f"OCR {settings.azure_document_intelligence_timeout:g} s · OpenAI {settings.openai_timeout:g} s",
        ),
    ]
    return rows


def check_services() -> list[dict[str, Any]]:
    """health_check de Document Intelligence y OpenAI (una llamada minima a cada uno)."""
    from app.services.ai.document_intelligence import AzureDocumentIntelligenceAnalyzer
    from app.services.ai.openai_analyzer import OpenAIInvoiceAnalyzer

    results = []
    for label, analyzer in (
        ("Document Intelligence", AzureDocumentIntelligenceAnalyzer()),
        ("OpenAI", OpenAIInvoiceAnalyzer()),
    ):
        status = analyzer.health_check()
        results.append({"label": label, **status, "reason_label": REASON_LABELS.get(status.get("reason"), "")})
    return results
