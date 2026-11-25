"""Datos de la factura nacional a partir de sus archivos (HU-24, RN-HU24-01 a 03, RD-01 a RD-03).

Con XML, los datos fiscales salen del XML (parse_cfdi). Sin XML, del texto de la representacion impresa del CFDI 4.0
(parse_printed_cfdi) y, si el PDF no tiene texto, del analizador documental configurado (OCR). Las tres fuentes
devuelven las mismas claves, asi que el motor, la revision y el detalle no distinguen de donde salieron. Los datos y su
fuente se guardan en metadata_json del documento: el XML, plano como hasta ahora con "source": "xml"; el PDF, con el
analisis del archivo y los datos en "invoice".
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from app.core.constants import DocumentType
from app.core.errors import BusinessRuleError
from app.services.ai import AnalyzerUnavailable, get_document_analyzer
from app.services.pdf_service import analyze_pdf
from app.services.xml_service import parse_cfdi

logger = logging.getLogger(__name__)

SOURCE_XML, SOURCE_PDF_TEXT, SOURCE_OCR = "xml", "pdf_text", "ocr"
SOURCE_LABELS = {SOURCE_XML: "XML", SOURCE_PDF_TEXT: "Texto del PDF", SOURCE_OCR: "OCR"}
ESSENTIALS = ("uuid", "issuer_rfc", "receiver_rfc", "date", "subtotal", "total", "currency")
MSG_UNREADABLE = "No pudimos leer los datos de la factura en el PDF. Adjunte el XML."
MSG_MISMATCH = "El PDF y el XML no corresponden a la misma factura"
MSG_NO_PDF = "Adjunte el PDF de la factura"
TEXT_PREVIEW = 2000


class UnreadableInvoiceError(BusinessRuleError):
    """Sin XML y sin los datos esenciales del PDF (RD-03)."""

    status_code = 422

    def __init__(self, message: str = MSG_UNREADABLE):
        super().__init__(message)


def json_safe(value):
    """Decimales como texto: metadata_json y la evidencia son JSON."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    return value


# --- Representacion impresa del CFDI 4.0 (seccion 6.3 de la HU) --------------------------------------------------

AMOUNT = r"\$?\s*(-?[\d,]+\.\d{2,6})"
RFC = r"([A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3})"
UUID = r"([0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12})"
FLAGS = re.IGNORECASE
RECEIVER_START = re.compile(r"^\s*(?:CLIENTE|RECEPTOR)\b", FLAGS | re.MULTILINE)
CONCEPTS_START = re.compile(r"^\s*CONCEPTOS\b", FLAGS | re.MULTILINE)
CONCEPTS_END = re.compile(
    r"\b(?:MONEDA|FORMA\s+DE\s+PAGO|M[ÉE]TODO\s+DE\s+PAGO|SUBTOTAL|TOTAL\s+CON\s+LETRA|SELLO\s+DIGITAL)\b", FLAGS
)
COLUMN_HEADERS = re.compile(r"Objeto\s+Imp\.?\s+Importe", FLAGS)
# Renglon de la tabla de conceptos: cantidad, "clave - unidad", identificacion y descripcion, precio unitario y, en
# cualquiera de los dos ordenes habituales, objeto de impuesto e importe. El objeto de impuesto puede llevar su nombre
# ("02 - Sí objeto de impuesto.", como en la factura 3668). Una clave de producto antes de la cantidad se salta sola:
# no va seguida de "clave - unidad".
CONCEPT = re.compile(
    r"(?<![\w.,$])(?P<quantity>\d+(?:\.\d+)?)\s+(?P<unit_key>[A-Z0-9]{2,3})\s*-\s*(?P<unit>[A-ZÁÉÍÓÚÑ]{1,20})\s+"
    r"(?P<body>.+?)\s+"
    + AMOUNT.replace("(", "(?P<unit_value>", 1)
    + r"\s+(?:(?P<tax_object>0[1-8])(?:\s*-\s*[^\d$]{1,80}?)?\s+"
    + AMOUNT.replace("(", "(?P<amount>", 1)
    + r"|"
    + AMOUNT.replace("(", "(?P<amount_first>", 1)
    + r"\s+(?P<tax_object_last>0[1-8]))(?!\d)",
    FLAGS,
)
TAX = re.compile(
    r"(?P<tax>\d{3})\s+(?:IVA|ISR|IEPS)\s+Base\s*-\s*" + AMOUNT.replace("(", "(?P<base>", 1) + r"\s+Tasa\s*-\s*"
    r"(?P<rate>\d+(?:\.\d+)?)\s+Importe\s*-\s*" + AMOUNT.replace("(", "(?P<amount>", 1),
    FLAGS,
)
PRINTED_NUMBER = r"\bFACTURA\s*(?:No\.?|N[ÚU]MERO|#)?\s*:?\s*([A-Z0-9-]*\d[A-Z0-9-]*)"
IDENTIFICATION = re.compile(r"(?=[^\s]*\d)(?=[^\s]*[A-Z-])[A-Z0-9][A-Z0-9./-]{2,}", FLAGS)


def _amount(text: str | None) -> Decimal | None:
    if not text:
        return None
    try:
        return Decimal(text.replace(",", "").replace("$", "").strip())
    except InvalidOperation:
        return None


def _search(pattern: str, text: str, flags=FLAGS) -> str | None:
    match = re.search(pattern, text, flags)
    return match.group(1).strip() if match else None


def _lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


# "Nombre: X" o, en una tabla, "Nombre" y su valor en la linea siguiente.
NAME_LABEL = r"^[ \t]*(?:NOMBRE|RAZ[ÓO]N\s+SOCIAL)[ \t]*:?[ \t]*\n?[ \t]*(\S.*)$"
LABEL = re.compile(r"^(?:RFC|USO|DOMICILIO|R[ÉE]GIMEN|NOMBRE|LUGAR|FOLIO|FECHA|TIPO|C\.?P\.?)\b", FLAGS)
# Etiqueta del RFC del proveedor de certificacion, que la representacion impresa trae junto a los datos del timbre.
PAC_LABEL = re.compile(r"PROVEEDOR\s+DE\s+CERTIFICACI|\bPAC\b", FLAGS)


def _rfc(block: str) -> str | None:
    """RFC del bloque: el que sigue a la etiqueta "RFC" o, sin etiqueta (factura 3668), la linea que solo trae un RFC.
    Nunca el del proveedor de certificacion."""
    labeled = _search(r"RFC\s*:?\s*" + RFC, block)
    if labeled:
        return labeled.upper()
    lines = _lines(block)
    for index, line in enumerate(lines):
        if re.fullmatch(RFC, line, FLAGS) and not (index and PAC_LABEL.search(lines[index - 1])):
            return line.upper()
    return None


def _name_before_rfc(block: str, rfc: str | None) -> str | None:
    """Nombre del emisor: "NOMBRE: …" o la linea anterior a la de su RFC (con etiqueta o sin ella)."""
    named = _search(NAME_LABEL, block, FLAGS | re.MULTILINE)
    if named:
        return named
    lines = _lines(block)
    for index, line in enumerate(lines):
        labeled = re.match(r"RFC\b", line, FLAGS) and not PAC_LABEL.search(line)
        if labeled or (rfc and line.upper() == rfc):
            previous = [candidate for candidate in lines[:index] if not LABEL.match(candidate)]
            return previous[-1] if previous else None
    return None


def _receiver_name(block: str) -> str | None:
    """Nombre del cliente: "NOMBRE: …" o la primera linea del bloque que no es una etiqueta."""
    named = _search(NAME_LABEL, block, FLAGS | re.MULTILINE)
    if named:
        return named
    lines = _lines(block)[1:]  # la primera es "CLIENTE"
    return next((line for line in lines if not LABEL.match(line)), None)


def _split_number(number: str | None) -> tuple[str | None, str | None]:
    """ "A-1001" -> ("A", "1001"); "3668" -> (None, "3668")."""
    if not number:
        return None, None
    match = re.fullmatch(r"([A-Z]{1,25})-(\d[\w-]*)", number, FLAGS)
    return (match.group(1).upper(), match.group(2)) if match else (None, number)


def _taxes(text: str) -> list[dict[str, Any]]:
    traslados = re.split(r"Retenciones\s*:", text, maxsplit=1, flags=FLAGS)
    taxes = []
    for kind, part in zip(("Traslado", "Retencion"), traslados, strict=False):
        for match in TAX.finditer(part):
            taxes.append(
                {
                    "kind": kind,
                    "tax": match.group("tax"),
                    "rate": match.group("rate"),
                    "base": _amount(match.group("base")),
                    "amount": _amount(match.group("amount")),
                }
            )
    return taxes


def _concepts(text: str) -> list[dict[str, Any]]:
    start = CONCEPTS_START.search(text)
    if not start:
        return []
    section = text[start.end() :]
    end = CONCEPTS_END.search(section)
    section = section[: end.start()] if end else section
    headers = COLUMN_HEADERS.search(section)
    section = " ".join(section[headers.end() if headers else 0 :].split())
    matches = list(CONCEPT.finditer(section))
    concepts = []
    for index, match in enumerate(matches):
        tail = section[match.end() : matches[index + 1].start() if index + 1 < len(matches) else len(section)]
        body = match.group("body").strip()
        first, _, rest = body.partition(" ")
        identification = first if rest and IDENTIFICATION.fullmatch(first) else None
        concepts.append(
            {
                "description": rest.strip() if identification else body,
                "quantity": _amount(match.group("quantity")),
                "unit_key": match.group("unit_key").upper(),
                "unit": match.group("unit").upper(),
                "identification": identification,
                "unit_value": _amount(match.group("unit_value")),
                "tax_object": match.group("tax_object") or match.group("tax_object_last"),
                "amount": _amount(match.group("amount") or match.group("amount_first")),
                "taxes": _taxes(tail),
            }
        )
    return concepts


def _date(text: str) -> str | None:
    raw = _search(
        r"FECHA\s+Y\s+HORA\s+DE\s+EMISI[ÓO]N(?:\s+DEL?\s+CFDI)?\s*:?\s*(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2})", text
    )
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace(" ", "T")).isoformat()
    except ValueError:
        return None


def parse_printed_cfdi(text: str) -> dict[str, Any]:
    """Datos de la representacion impresa de un CFDI 4.0 por sus etiquetas (seccion 6.3 de la HU), con las mismas
    claves que parse_cfdi. Lo que no encuentra queda en None; quien llama decide si bastan (RD-03)."""
    text = text or ""
    receiver_start = RECEIVER_START.search(text)
    concepts_start = CONCEPTS_START.search(text)
    issuer_block = text[: receiver_start.start()] if receiver_start else ""
    receiver_end = concepts_start.start() if concepts_start else len(text)
    receiver_block = text[receiver_start.start() : receiver_end] if receiver_start else ""
    series = _search(r"\bSERIE\s*:\s*([A-Z]{1,25})\b", issuer_block or text)
    folio = _search(r"\bFOLIO\s*:\s*(\d[\w-]*)", issuer_block or text)
    if not folio:
        series, folio = _split_number(_search(PRINTED_NUMBER, text))
    concepts = _concepts(text)
    tax = _amount(_search(r"TRASLADO\s+IVA\s+TASA\s+[\d.]+\s*:?\s*" + AMOUNT, text)) or _amount(
        _search(r"TOTAL\s+(?:DE\s+)?IMPUESTOS\s+TRASLADADOS\s*:?\s*" + AMOUNT, text)
    )
    if tax is None and concepts:
        tax = sum(
            (t["amount"] or Decimal("0") for c in concepts for t in c["taxes"] if t["kind"] == "Traslado"), Decimal()
        )
    uuid = _search(r"FOLIO\s+FISCAL\s*(?:\(UUID\))?\s*:?\s*" + UUID, text) or _search(UUID, text)
    issuer_rfc = _rfc(issuer_block)
    return {
        "version": "4.0" if text.strip() else None,
        "uuid": uuid.upper() if uuid else None,
        "series": series,
        "folio": folio,
        "issuer_rfc": issuer_rfc,
        "issuer_name": _name_before_rfc(issuer_block, issuer_rfc),
        "issuer_regime": _search(r"R[ÉE]GIMEN\s+FISCAL\s*:?\s*(\d{3})\b", issuer_block),
        "receiver_rfc": _rfc(receiver_block),
        "receiver_name": _receiver_name(receiver_block) if receiver_block else None,
        "receiver_postal_code": _search(r"DOMICILIO\s+FISCAL\s*:?\s*(?:C\.?P\.?\s*)?(\d{5})\b", receiver_block),
        "receiver_regime": _search(r"R[ÉE]GIMEN\s+FISCAL\s*:?\s*(\d{3})\b", receiver_block),
        "date": _date(text),
        "subtotal": _amount(_search(r"\bSUBTOTAL\s*:?\s*" + AMOUNT, text)),
        "tax": tax if tax is not None else Decimal("0"),
        "total": _amount(_search(r"(?<![A-Z])TOTAL\b(?!\s+(?:DE\s+)?IMPUESTOS|\s+CON\s+LETRA)\s*:?\s*" + AMOUNT, text)),
        "currency": (_search(r"\bMONEDA\s*:?\s*([A-Z]{3})\b", text) or "").upper() or None,
        "payment_form": _search(r"FORMA\s+DE\s+PAGO\s*:?\s*(\d{2})\b", text),
        "payment_method": (_search(r"M[ÉE]TODO\s+DE\s+PAGO\s*:?\s*(PUE|PPD)\b", text) or "").upper() or None,
        "cfdi_use": (_search(r"USO\s+(?:DE\s+|DEL\s+)?CFDI\s*:?\s*([A-Z]{1,2}\d{2})\b", receiver_block) or "").upper()
        or None,
        "voucher_type": (_search(r"TIPO\s+DE\s+COMPROBANTE\s*:?\s*([IEPTN])\b", text) or "").upper() or None,
        "concepts": concepts,
    }


# --- Extraccion del Paso 1 y de los reemplazos ---------------------------------------------------------------------


def is_complete(data: dict | None) -> bool:
    """Datos esenciales de RD-03: UUID, RFC emisor y receptor, fecha, subtotal, total, moneda y un concepto."""
    return bool(data) and all(data.get(key) is not None for key in ESSENTIALS) and bool(data.get("concepts"))


def invoice_number(data: dict) -> str | None:
    """Numero de la factura (RD-01): serie y folio ("A-1001"), solo el folio ("3668") o, sin ellos, el UUID."""
    series, folio = (data.get("series") or "").strip(), (data.get("folio") or "").strip()
    if series and folio:
        return f"{series}-{folio}"
    return folio or series or data.get("uuid")


def service_period(data: dict) -> str | None:
    """Periodo MM/AAAA del mes de la fecha de emision (RD-01)."""
    try:
        issued = datetime.fromisoformat(str(data.get("date")))
    except (TypeError, ValueError):
        return None
    return f"{issued.month:02d}/{issued.year}"


def read_pdf(path: Path) -> tuple[dict[str, Any], dict[str, Any] | None, str | None]:
    """(analisis del PDF, datos, fuente). ValueError si el PDF no abre. Sin texto, el analizador documental; si no
    esta disponible, sin datos."""
    analysis = analyze_pdf(path)
    if analysis["has_extractable_text"]:
        return analysis, parse_printed_cfdi(analysis["text"]), SOURCE_PDF_TEXT
    try:
        return analysis, get_document_analyzer().extract_invoice(path), SOURCE_OCR
    except AnalyzerUnavailable as exc:
        logger.info("pdf.ocr_unavailable", extra={"event": "pdf.ocr_unavailable", "error": str(exc)})
        return analysis, None, None


@dataclass(frozen=True)
class Extraction:
    data: dict[str, Any]
    source: str
    pdf_analysis: dict[str, Any] | None
    pdf_data: dict[str, Any] | None
    pdf_source: str | None
    xml_data: dict[str, Any] | None

    @property
    def number(self) -> str | None:
        return invoice_number(self.data)

    @property
    def period(self) -> str | None:
        return service_period(self.data)

    def pdf_metadata(self) -> dict[str, Any] | None:
        if self.pdf_analysis is None:
            return None
        return pdf_metadata(self.pdf_analysis, self.pdf_data, self.pdf_source)

    def xml_metadata(self) -> dict[str, Any] | None:
        return xml_metadata(self.xml_data) if self.xml_data is not None else None


def pdf_metadata(analysis: dict[str, Any], data: dict[str, Any] | None, source: str | None) -> dict[str, Any]:
    metadata = {key: value for key, value in analysis.items() if key != "text"}
    metadata["text_preview"] = analysis.get("text", "")[:TEXT_PREVIEW]
    metadata["invoice"] = {**json_safe(data), "source": source} if data else None
    return metadata


def xml_metadata(data: dict[str, Any]) -> dict[str, Any]:
    return {**json_safe(data), "source": SOURCE_XML}


def _same_invoice(pdf_data: dict | None, xml_data: dict) -> bool:
    """El PDF y el XML son la misma factura: se compara el UUID solo cuando ambos lo traen (RD-02)."""
    pdf_uuid = (pdf_data or {}).get("uuid")
    xml_uuid = xml_data.get("uuid")
    return not (pdf_uuid and xml_uuid) or pdf_uuid.upper() == xml_uuid.upper()


def extract(
    pdf_path: Path | None,
    xml_path: Path | None,
    *,
    pdf_read: tuple[dict, dict | None, str | None] | None = None,
) -> Extraction:
    """Datos de la factura con el PDF y el XML vigentes o recien cargados. Con XML, los del XML; sin XML, los del PDF.

    Lanza BusinessRuleError (409) si el PDF y el XML traen UUID distintos, UnreadableInvoiceError (422) sin datos
    esenciales ni XML o sin numero de factura, XMLParseError si el XML no se puede leer y ValueError si el PDF no
    abre. `pdf_read` reutiliza una lectura ya hecha del PDF (por ejemplo, los datos guardados del PDF vigente)."""
    analysis, pdf_data, pdf_source = pdf_read or (read_pdf(pdf_path) if pdf_path else (None, None, None))
    xml_data = parse_cfdi(xml_path) if xml_path else None
    if xml_data is not None:
        if not _same_invoice(pdf_data, xml_data):
            raise BusinessRuleError(MSG_MISMATCH)
        data, source = xml_data, SOURCE_XML
    else:
        if not is_complete(pdf_data):
            raise UnreadableInvoiceError()
        data, source = pdf_data, pdf_source
    if not invoice_number(data):
        raise UnreadableInvoiceError()
    return Extraction(data, source, analysis, pdf_data, pdf_source, xml_data)


def log_extraction(invoice_id: int, extraction: Extraction) -> None:
    """Evento invoice.extracted sin datos fiscales (spec observabilidad)."""
    logger.info(
        "invoice.extracted",
        extra={
            "event": "invoice.extracted",
            "invoice_id": invoice_id,
            "source": extraction.source,
            "complete": is_complete(extraction.data),
        },
    )


# --- Datos guardados de una factura --------------------------------------------------------------------------------


@dataclass(frozen=True)
class StoredData:
    data: dict[str, Any]
    source: str
    document_id: int

    @property
    def source_label(self) -> str:
        return SOURCE_LABELS.get(self.source, self.source)


def current_document(invoice, document_type: DocumentType):
    return next((d for d in invoice.documents if d.is_current and d.document_type == document_type.value), None)


def stored_data(invoice) -> StoredData | None:
    """Datos ya extraidos de la factura: los del XML vigente o, sin XML, los del PDF vigente."""
    xml = current_document(invoice, DocumentType.INVOICE_XML)
    if xml is not None and xml.metadata_json and ("uuid" in xml.metadata_json or "issuer_rfc" in xml.metadata_json):
        return StoredData(xml.metadata_json, SOURCE_XML, xml.id)
    pdf = current_document(invoice, DocumentType.INVOICE_PDF)
    data = (pdf.metadata_json or {}).get("invoice") if pdf is not None else None
    if data:
        return StoredData(data, data.get("source") or SOURCE_PDF_TEXT, pdf.id)
    return None
