"""Visualizacion de documentos dentro del portal (HU-19): las paginas del PDF como imagenes PNG renderizadas en el
servidor, las imagenes tal cual y el XML o el texto escapados en una pagina del portal.

El navegador nunca recibe el PDF, el XML ni el texto como documento, solo HTML del portal e imagenes: no depende del
visor PDF de cada navegador ni hay que relajar la CSP (object-src 'none', frame-ancestors 'none').
"""

import logging
from enum import StrEnum
from pathlib import Path

import fitz

logger = logging.getLogger(__name__)

MAX_PAGES = 20
TEXT_LIMIT = 200_000
# Zoom del render y ancho maximo de la imagen: acotan memoria y tamano de la respuesta.
ZOOM = 1.5
MAX_WIDTH = 1600
IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}


class ViewKind(StrEnum):
    PDF = "PDF"
    IMAGE = "IMAGE"
    TEXT = "TEXT"
    NONE = "NONE"


def kind(relative_path: str) -> ViewKind:
    """Segun la extension del archivo almacenado, que la carga verifico por contenido."""
    suffix = Path(relative_path).suffix.lower()
    if suffix == ".pdf":
        return ViewKind.PDF
    if suffix in IMAGE_TYPES:
        return ViewKind.IMAGE
    if suffix in {".xml", ".txt"}:
        return ViewKind.TEXT
    return ViewKind.NONE


def _log_failure(exc: Exception) -> None:
    logger.warning(
        "document.view_failed",
        extra={"event": "document.view_failed", "error_type": type(exc).__name__, "error": str(exc)},
    )


def pdf_page_count(path: Path) -> int | None:
    """Paginas del PDF, o None si no puede abrirse."""
    try:
        with fitz.open(path) as document:
            return document.page_count
    except Exception as exc:  # MuPDF lanza varios tipos de error ante un PDF danado
        _log_failure(exc)
        return None


def render_page(path: Path, number: int) -> bytes | None:
    """PNG de la pagina `number` (desde 1), o None si no existe, supera MAX_PAGES o el PDF no puede abrirse."""
    try:
        with fitz.open(path) as document:
            if not 1 <= number <= min(document.page_count, MAX_PAGES):
                return None
            page = document[number - 1]
            zoom = min(ZOOM, MAX_WIDTH / page.rect.width) if page.rect.width else ZOOM
            return page.get_pixmap(matrix=fitz.Matrix(zoom, zoom)).tobytes("png")
    except Exception as exc:
        _log_failure(exc)
        return None


def read_text(path: Path) -> tuple[str, bool]:
    """Texto del XML o TXT (UTF-8, bytes invalidos reemplazados, sin BOM) y si se trunco a TEXT_LIMIT caracteres.
    El archivo esta acotado por MAX_UPLOAD_MB desde la carga."""
    text = path.read_bytes().decode("utf-8", errors="replace").removeprefix("﻿")
    return text[:TEXT_LIMIT], len(text) > TEXT_LIMIT
