from pathlib import Path
from typing import Any
import fitz


def analyze_pdf(path: Path) -> dict[str, Any]:
    try:
        with fitz.open(path) as document:
            text = "\n".join(page.get_text("text") for page in document)
            return {
                "page_count": document.page_count,
                "text": text[:100_000],
                "has_extractable_text": len(text.strip()) >= 30,
                "requires_ocr": len(text.strip()) < 30,
                "metadata": dict(document.metadata or {}),
            }
    except Exception as exc:
        raise ValueError("El PDF no puede abrirse o esta danado") from exc

