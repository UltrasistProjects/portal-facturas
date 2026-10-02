"""Version HTML del correo: el cuerpo de texto plano en una tarjeta centrada con el logo de ULTRASIST.

El HTML se deriva del texto ya compuesto, de modo que las plantillas de HU-05 siguen siendo de texto plano y el texto
del Administrador nunca se interpreta como plantilla. Jinja2 escapa cada valor (autoescape): una razon social o unas
observaciones con `<b>` llegan como texto. Los estilos van en linea porque los clientes de correo descartan las hojas
de estilo, y el logo viaja dentro del mensaje (cid:) para verse sin descargar imagenes remotas. Por esos estilos la
plantilla vive en app/email_templates y no en app/templates, cuyas paginas se sirven con la CSP del portal.

La vista previa del editor de plantillas (HU-05) muestra este mismo HTML en un iframe srcdoc, con el logo como data:
URI. El iframe hereda la CSP de la pagina, asi que esa respuesta admite solo los hashes de sus atributos style.
"""

import base64
import hashlib
import html
import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

APP_DIR = Path(__file__).resolve().parents[1]
LOGO_PATH = APP_DIR / "static" / "img" / "Ultrasistlogo.png"
TEMPLATE = "layout.html"

PARAGRAPH_BREAK = re.compile(r"\n[ \t]*\n")
LINE_BREAK = re.compile(r"\r\n|\r")
URL = re.compile(r"https?://[^\s<>\"']+")
# Puntuacion que cierra la frase y no forma parte de la direccion: "ingrese a https://portal/login."
URL_TRAILING = ".,;:!?)]»”'\""
# "Etiqueta: valor". Un parrafo cuyas lineas son todas asi se muestra como tabla de datos (folio, fecha, usuario).
FIELD = re.compile(r"([^:\s][^:\n]{0,39}):[ \t]+(\S.*)")
MIN_FIELDS = 2
STYLE_ATTRIBUTE = re.compile(r'\sstyle="([^"]*)"')

_env = Environment(
    loader=FileSystemLoader(APP_DIR / "email_templates"),
    autoescape=True,
    trim_blocks=True,
    lstrip_blocks=True,
)


@dataclass(frozen=True)
class Segment:
    text: str
    href: str | None = None


@dataclass(frozen=True)
class Field:
    label: str
    value: list[Segment]


@dataclass(frozen=True)
class Block:
    lines: list[list[Segment]] | None = None
    fields: list[Field] | None = None


def segments(text: str) -> list[Segment]:
    """Texto con sus direcciones http(s) como enlaces. Otro esquema (javascript:, data:) queda como texto."""
    parts: list[Segment] = []
    last = 0
    for match in URL.finditer(text):
        url = match.group(0).rstrip(URL_TRAILING)
        start = match.start()
        if start > last:
            parts.append(Segment(text[last:start]))
        parts.append(Segment(url, url))
        last = start + len(url)
    if last < len(text):
        parts.append(Segment(text[last:]))
    return parts


def blocks(body: str) -> list[Block]:
    """Parrafos separados por una linea en blanco; dentro de un parrafo, cada salto de linea se conserva."""
    result: list[Block] = []
    for paragraph in PARAGRAPH_BREAK.split(LINE_BREAK.sub("\n", body).strip()):
        lines = [line.rstrip() for line in paragraph.split("\n")]
        matches = [FIELD.fullmatch(line) for line in lines]
        if len(lines) >= MIN_FIELDS and all(matches):
            result.append(Block(fields=[Field(m.group(1), segments(m.group(2))) for m in matches]))
        elif paragraph.strip():
            result.append(Block(lines=[segments(line) for line in lines]))
    return result


def render_html(subject: str, body: str, logo_src: str) -> str:
    """`logo_src` es `cid:<Content-ID>` en el correo y un data: URI en la vista previa."""
    return _env.get_template(TEMPLATE).render(subject=subject, blocks=blocks(body), logo_src=logo_src)


def render_preview(subject: str, body: str) -> str:
    return render_html(subject, body, logo_data_uri())


def style_hashes(document: str) -> list[str]:
    """Fuentes CSP ('sha256-...') de los atributos style distintos de `document`, en orden. El hash se calcula sobre
    el valor que ve el navegador, ya sin entidades."""
    values = sorted({html.unescape(value) for value in STYLE_ATTRIBUTE.findall(document)})
    return [f"'sha256-{base64.b64encode(hashlib.sha256(value.encode()).digest()).decode()}'" for value in values]


@cache
def logo() -> bytes:
    return LOGO_PATH.read_bytes()


@cache
def logo_data_uri() -> str:
    return "data:image/png;base64," + base64.b64encode(logo()).decode()
