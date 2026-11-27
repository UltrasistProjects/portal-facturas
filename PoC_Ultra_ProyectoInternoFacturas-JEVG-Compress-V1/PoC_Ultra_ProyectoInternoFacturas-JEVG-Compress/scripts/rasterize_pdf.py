"""Version escaneada (solo imagen, sin capa de texto) de un PDF: cada pagina se rasteriza con PyMuPDF.

Sirve para probar la lectura por OCR puro (Azure Document Intelligence + OpenAI):

    python scripts/rasterize_pdf.py data/pruebas-factura-3668/1-factura/CFDI-3668-GOHS60031745A.pdf
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import fitz

DEFAULT_DPI = 150


def rasterize(source: Path, target: Path, dpi: int = DEFAULT_DPI) -> Path:
    with fitz.open(source) as original, fitz.open() as image_only:
        for page in original:
            pixmap = page.get_pixmap(dpi=dpi)
            new_page = image_only.new_page(width=page.rect.width, height=page.rect.height)
            new_page.insert_image(new_page.rect, pixmap=pixmap)
        image_only.set_metadata({"title": f"{Path(source).stem} (escaneado)", "producer": "scripts/rasterize_pdf.py"})
        image_only.save(target, deflate=True, garbage=3)
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path, nargs="?", help="por omision, <nombre>-escaneado.pdf junto al original")
    parser.add_argument("--dpi", type=int, default=DEFAULT_DPI)
    args = parser.parse_args(argv)
    target = args.target or args.source.with_name(f"{args.source.stem}-escaneado.pdf")
    rasterize(args.source, target, args.dpi)
    print(f"{target} ({target.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
