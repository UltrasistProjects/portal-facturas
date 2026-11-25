"""Reporte resumen de facturas en PDF (Ferromex): totales por estatus y por origen y un grafico de pie por estatus.

Usa los mismos filtros y el mismo alcance que el listado (invoice_repository.filter_invoices): el proveedor solo ve sus
facturas. Los agregados se calculan en SQL; el PDF se dibuja con PyMuPDF, ya dependencia del portal, sin servicios
externos ni archivos temporales.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import fitz
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.constants import (
    ROLE_LABELS,
    STATUS_LABELS,
    SUPPLIER_ORIGIN_LABELS,
    InvoiceStatus,
    SupplierOrigin,
)
from app.core.timeutils import to_business
from app.models import Invoice, Supplier
from app.repositories.invoice_repository import filter_invoices

LOGO = Path(__file__).parents[1] / "static" / "img" / "Ferromexlogo.png"
TITLE = "Reporte resumen de facturas"
# Color de cada estatus en el grafico y en la tabla (RGB 0-1), cercanos a los de las etiquetas del portal.
STATUS_COLORS = {
    InvoiceStatus.DRAFT: (0.60, 0.65, 0.70),
    InvoiceStatus.UPLOADED: (0.25, 0.31, 0.66),
    InvoiceStatus.UNDER_REVIEW: (0.09, 0.41, 0.88),
    InvoiceStatus.REQUIRES_CORRECTION: (0.88, 0.63, 0.13),
    InvoiceStatus.ACCEPTED: (0.09, 0.52, 0.36),
    InvoiceStatus.PAID: (0.06, 0.56, 0.72),
    InvoiceStatus.REJECTED: (0.80, 0.23, 0.23),
    InvoiceStatus.CANCELLED: (0.33, 0.38, 0.45),
}
# Orden del flujo: el de la tabla y el de las rebanadas del pie.
STATUS_ORDER = tuple(STATUS_COLORS)
NAVY = (0.07, 0.14, 0.23)
INK = (0.08, 0.13, 0.21)
MUTED = (0.41, 0.47, 0.54)
LINE = (0.89, 0.91, 0.94)
SOFT = (0.97, 0.98, 0.99)
WHITE = (1, 1, 1)
FONT, BOLD = "helv", "hebo"
PAGE = fitz.paper_rect("a4")
MARGIN = 40


@dataclass(frozen=True)
class StatusRow:
    status: InvoiceStatus
    label: str
    count: int
    share: float
    amounts: dict[str, Decimal]


@dataclass(frozen=True)
class OriginRow:
    label: str
    count: int
    share: float


@dataclass(frozen=True)
class ReportData:
    rows: list[StatusRow]
    origins: list[OriginRow]
    total: int
    totals: dict[str, Decimal]
    filters: list[tuple[str, str]]
    generated_at: datetime
    generated_by: str


def _share(count: int, total: int) -> float:
    return count / total if total else 0.0


def summary(db: Session, user, q: str = "", status: str = "", origin: str = "") -> ReportData:
    """Facturas por estatus y moneda, y por origen, con los filtros del listado."""
    base = select(Invoice.status, Invoice.currency, func.count(Invoice.id), func.sum(Invoice.total)).join(
        Invoice.supplier
    )
    grouped = filter_invoices(base, user, q, status, origin).group_by(Invoice.status, Invoice.currency)
    counts: dict[InvoiceStatus, int] = {}
    amounts: dict[InvoiceStatus, dict[str, Decimal]] = {}
    totals: dict[str, Decimal] = {}
    for state, currency, count, amount in db.execute(grouped):
        state = InvoiceStatus(state)
        counts[state] = counts.get(state, 0) + count
        amount = amount or Decimal("0")
        amounts.setdefault(state, {})[currency] = amounts.get(state, {}).get(currency, Decimal("0")) + amount
        totals[currency] = totals.get(currency, Decimal("0")) + amount
    total = sum(counts.values())
    rows = [
        StatusRow(state, STATUS_LABELS[state], counts[state], _share(counts[state], total), amounts[state])
        for state in STATUS_ORDER
        if counts.get(state)
    ]
    by_origin = filter_invoices(
        select(Supplier.origin, func.count(Invoice.id)).join(Invoice.supplier), user, q, status, origin
    ).group_by(Supplier.origin)
    origin_counts = {SupplierOrigin(value): count for value, count in db.execute(by_origin)}
    origins = [
        OriginRow(SUPPLIER_ORIGIN_LABELS[value], origin_counts[value], _share(origin_counts[value], total))
        for value in SupplierOrigin
        if origin_counts.get(value)
    ]
    filters = [
        ("Estatus", STATUS_LABELS.get(status, "Todos") if status else "Todos"),
        ("Origen", SUPPLIER_ORIGIN_LABELS.get(origin, "Todos") if origin else "Todos"),
        ("Búsqueda", q.strip() or "-"),
    ]
    role = ROLE_LABELS.get(user.role, str(user.role))
    return ReportData(
        rows=rows,
        origins=origins,
        total=total,
        totals=dict(sorted(totals.items())),
        filters=filters,
        generated_at=datetime.now(timezone.utc),
        generated_by=f"{user.name} ({role})",
    )


# --- Dibujo -----------------------------------------------------------------------------------------------------------


def money(value: Decimal) -> str:
    return f"${value:,.2f}"


def percent(share: float) -> str:
    return f"{share * 100:.1f} %"


def _text(page, x, y, text, size=10, font=FONT, color=INK, align="left"):
    if align == "right":
        x -= fitz.get_text_length(text, fontname=font, fontsize=size)
    elif align == "center":
        x -= fitz.get_text_length(text, fontname=font, fontsize=size) / 2
    page.insert_text((x, y), text, fontsize=size, fontname=font, color=color)


def _fit(text: str, width: float, size: float, font: str = FONT) -> str:
    """Recorta el texto con "..." para que quepa en `width`."""
    if fitz.get_text_length(text, fontname=font, fontsize=size) <= width:
        return text
    while text and fitz.get_text_length(text + "...", fontname=font, fontsize=size) > width:
        text = text[:-1]
    return text + "..."


def _header(page, data: ReportData) -> float:
    band = fitz.Rect(0, 0, PAGE.width, 92)
    page.draw_rect(band, color=None, fill=NAVY)
    if LOGO.exists():
        page.insert_image(fitz.Rect(MARGIN, 20, MARGIN + 160, 72), filename=str(LOGO), keep_proportion=True)
    right = PAGE.width - MARGIN
    _text(page, right, 44, "Invoice Portal", 15, BOLD, WHITE, "right")
    _text(page, right, 62, "PORTAL DE PROVEEDORES", 8, BOLD, (0.58, 0.67, 0.77), "right")
    y = 128
    _text(page, MARGIN, y, TITLE, 20, BOLD)
    generated = to_business(data.generated_at).strftime("%d/%m/%Y %H:%M")
    _text(page, MARGIN, y + 18, f"Generado el {generated} por {data.generated_by}", 9, color=MUTED)
    filters = "   ·   ".join(f"{name}: {value}" for name, value in data.filters)
    _text(page, MARGIN, y + 32, _fit(f"Filtros   {filters}", PAGE.width - 2 * MARGIN, 9), 9, color=MUTED)
    return y + 52


def _kpis(page, data: ReportData, y: float) -> float:
    cards = [("Facturas", str(data.total))] + [(f"Monto {currency}", money(v)) for currency, v in data.totals.items()]
    cards = cards[:4]
    gap = 10
    width = (PAGE.width - 2 * MARGIN - gap * (len(cards) - 1)) / len(cards)
    for index, (label, value) in enumerate(cards):
        x = MARGIN + index * (width + gap)
        rect = fitz.Rect(x, y, x + width, y + 58)
        page.draw_rect(rect, color=LINE, fill=WHITE, width=0.8)
        page.draw_line((x, y), (x + width, y), color=(0.62, 0.69, 0.78), width=2.5)
        _text(page, x + 12, y + 20, label.upper(), 7.5, BOLD, MUTED)
        _text(page, x + 12, y + 44, _fit(value, width - 24, 16, BOLD), 16, BOLD)
    return y + 58 + 24


def _slice(center: fitz.Point, radius: float, start: float, sweep: float) -> list[fitz.Point]:
    """Rebanada como poligono: el centro y el arco de `start` a `start + sweep` grados, a pasos de 2 grados como
    maximo (a esta escala el arco se ve continuo)."""
    steps = max(2, math.ceil(sweep / 2))
    arc = [
        fitz.Point(
            center.x + radius * math.cos(math.radians(start + sweep * step / steps)),
            center.y + radius * math.sin(math.radians(start + sweep * step / steps)),
        )
        for step in range(steps + 1)
    ]
    return [center, *arc, center]


def _pie(page, data: ReportData, center: fitz.Point, radius: float) -> None:
    shape = page.new_shape()
    if not data.rows:
        shape.draw_circle(center, radius)
        shape.finish(color=LINE, fill=SOFT, width=1)
        shape.commit()
        _text(page, center.x, center.y + 3, "Sin facturas", 10, color=MUTED, align="center")
        return
    if len(data.rows) == 1:
        shape.draw_circle(center, radius)
        shape.finish(color=WHITE, fill=STATUS_COLORS[data.rows[0].status], width=1.2)
    else:
        start = -90.0  # desde las 12 en punto, en el sentido de las agujas del reloj (y crece hacia abajo)
        for row in data.rows:
            sweep = 360.0 * row.share
            shape.draw_polyline(_slice(center, radius, start, sweep))
            shape.finish(color=WHITE, fill=STATUS_COLORS[row.status], width=1.2, closePath=True)
            start += sweep
    shape.commit()
    # Porcentaje sobre cada rebanada que tenga espacio.
    start = -90.0
    for row in data.rows:
        sweep = 360.0 * row.share
        if row.share >= 0.06:
            middle = math.radians(start + sweep / 2)
            label = fitz.Point(center.x + radius * 0.64 * math.cos(middle), center.y + radius * 0.64 * math.sin(middle))
            _text(page, label.x, label.y + 3, f"{row.share * 100:.0f}%", 8.5, BOLD, WHITE, "center")
        start += sweep


def _legend(page, data: ReportData, x: float, y: float, width: float) -> None:
    _text(page, x, y, "DISTRIBUCIÓN POR ESTATUS", 8, BOLD, MUTED)
    y += 18
    for row in data.rows:
        page.draw_rect(fitz.Rect(x, y - 8, x + 10, y + 2), color=None, fill=STATUS_COLORS[row.status])
        _text(page, x + 16, y, _fit(row.label, width - 110, 10), 10)
        _text(page, x + width - 50, y, str(row.count), 10, BOLD, align="right")
        _text(page, x + width, y, percent(row.share), 10, color=MUTED, align="right")
        y += 19
    if not data.rows:
        _text(page, x, y, "No hay facturas con los filtros aplicados.", 10, color=MUTED)


def _table(page, y: float, title: str, headers, rows, widths, aligns) -> float:
    _text(page, MARGIN, y, title, 12, BOLD)
    y += 10
    x0, x1 = MARGIN, PAGE.width - MARGIN
    page.draw_rect(fitz.Rect(x0, y, x1, y + 22), color=None, fill=SOFT)
    page.draw_line((x0, y + 22), (x1, y + 22), color=LINE, width=0.8)

    def cells(values, top, size, font, color):
        x = x0
        for value, width, align in zip(values, widths, aligns, strict=True):
            value = _fit(value, width - 16, size, font)
            if align == "right":
                _text(page, x + width - 8, top, value, size, font, color, "right")
            else:
                _text(page, x + 8, top, value, size, font, color)
            x += width

    cells([header.upper() for header in headers], y + 14.5, 7.5, BOLD, MUTED)
    y += 22
    for values, swatch, bold in rows:
        if swatch:
            page.draw_rect(fitz.Rect(x0 + 8, y + 7, x0 + 16, y + 15), color=None, fill=swatch)
            values = ["    " + values[0], *values[1:]]
        cells(values, y + 14.5, 9.5, BOLD if bold else FONT, INK)
        y += 22
        page.draw_line((x0, y), (x1, y), color=LINE, width=0.6)
    return y + 22


def render(data: ReportData) -> bytes:
    document = fitz.open()
    document.set_metadata({"title": TITLE, "author": "Portal de Proveedores FERROMEX", "creator": "Invoice Portal"})
    page = document.new_page(width=PAGE.width, height=PAGE.height)
    y = _header(page, data)
    y = _kpis(page, data, y)
    radius = 82
    _pie(page, data, fitz.Point(MARGIN + radius + 10, y + radius + 6), radius)
    legend_x = MARGIN + 2 * radius + 60
    _legend(page, data, legend_x, y + 16, PAGE.width - MARGIN - legend_x)
    y += 2 * radius + 40

    currencies = list(data.totals) or ["MXN"]
    headers = ["Estatus", "Facturas", "%"] + [f"Monto {currency}" for currency in currencies]
    fixed = [150, 62, 56]
    remaining = PAGE.width - 2 * MARGIN - sum(fixed)
    widths = fixed + [remaining / len(currencies)] * len(currencies)
    aligns = ["left", "right", "right"] + ["right"] * len(currencies)
    rows = [
        (
            [row.label, str(row.count), percent(row.share)]
            + [money(row.amounts[c]) if c in row.amounts else "-" for c in currencies],
            STATUS_COLORS[row.status],
            False,
        )
        for row in data.rows
    ]
    rows.append(
        (
            ["Total", str(data.total), percent(1.0 if data.total else 0.0)]
            + [money(data.totals.get(c, Decimal("0"))) for c in currencies],
            None,
            True,
        )
    )
    y = _table(page, y, "Resumen por estatus", headers, rows, widths, aligns)
    origin_rows = [([row.label, str(row.count), percent(row.share)], None, False) for row in data.origins]
    if origin_rows:
        width = PAGE.width - 2 * MARGIN
        _table(
            page, y, "Resumen por origen", ["Origen", "Facturas", "%"], origin_rows, [width - 236, 118, 118], aligns[:3]
        )
    footer = "Portal de Proveedores FERROMEX · Reporte informativo: los montos suman el total de cada factura."
    _text(page, MARGIN, PAGE.height - 24, footer, 7.5, color=MUTED)
    _text(page, PAGE.width - MARGIN, PAGE.height - 24, "Página 1 de 1", 7.5, color=MUTED, align="right")
    content = document.tobytes(garbage=3, deflate=True)
    document.close()
    return content


def filename(data: ReportData) -> str:
    return f"reporte-facturas-{to_business(data.generated_at).strftime('%Y%m%d-%H%M')}.pdf"
