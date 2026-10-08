"""Verifica EVIDENCIA-PRUEBAS-HUs.pdf: se abre, numero de paginas, imagenes incrustadas, HUs y capturas presentes.
Uso: .venv/bin/python tests/hu/verificar-pdf.py [salida.json] [carpeta-para-renderizar-paginas]"""

import json
import sys
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parents[2]
pdf_path = ROOT / "EVIDENCIA-PRUEBAS-HUs.pdf"
catalogo = json.loads((ROOT / "tests" / "hu" / "hu-catalogo.json").read_text(encoding="utf-8"))
doc = fitz.open(pdf_path)
texto = "".join(page.get_text() for page in doc)
xrefs = {img[0] for page in doc for img in page.get_images(full=True)}
apariciones = sum(len(page.get_images(full=True)) for page in doc)
capturas = sorted(p.relative_to(ROOT / "evidencias").as_posix() for p in (ROOT / "evidencias").glob("HU-*/*.png"))
faltantes_hu = [hu["id"] for hu in catalogo["hus"] if f"{hu['id']} — {hu['nombre']}" not in texto.replace("\n", " ")]
faltantes_cap = [c for c in capturas if f"evidencias/{c}" not in texto.replace("\n", "")]
resultado = {
    "pymupdf": fitz.VersionBind,
    "paginas": doc.page_count,
    "imagenes_distintas": len(xrefs),
    "imagenes_en_paginas": apariciones,
    "capturas_en_disco": len(capturas),
    "hus_sin_seccion": faltantes_hu,
    "capturas_no_referenciadas": faltantes_cap,
    "tamano_mb": round(pdf_path.stat().st_size / 1024 / 1024, 1),
}
print(json.dumps(resultado, ensure_ascii=False, indent=2))
if len(sys.argv) > 1:
    Path(sys.argv[1]).write_text(json.dumps(resultado), encoding="utf-8")
if len(sys.argv) > 2:
    destino = Path(sys.argv[2])
    destino.mkdir(parents=True, exist_ok=True)
    for numero in range(doc.page_count):
        doc[numero].get_pixmap(dpi=60).save(destino / f"p{numero + 1:03d}.png")
