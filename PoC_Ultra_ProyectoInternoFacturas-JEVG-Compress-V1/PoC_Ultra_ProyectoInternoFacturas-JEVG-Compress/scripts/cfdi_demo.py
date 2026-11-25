"""CFDI 4.0 de demostracion: XML y representacion impresa en PDF a partir de un diccionario (HU-24).

Reproduce la factura 3668 del documento de negocio (EXAMPLE_3668) y genera variantes para las pruebas. Los documentos
son ficticios: el XML no esta timbrado y el PDF lo indica en su pie. La maqueta del PDF sigue las etiquetas de la
seccion 6.3 de la HU, que lee invoice_extraction_service.parse_printed_cfdi.

Uso: python scripts/cfdi_demo.py   (reescribe en data/demo_documents la factura 3668 y los cfdi_demo_*.xml)
"""

from __future__ import annotations

import copy
import sys
import textwrap
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from xml.sax.saxutils import quoteattr

ROOT = Path(__file__).resolve().parents[1]

import fitz  # noqa: E402

CENTS = Decimal("0.01")
REGIMES = {
    "601": "General de Ley Personas Morales",
    "612": "Personas Físicas con Actividades Empresariales y Profesionales",
    "626": "Régimen Simplificado de Confianza",
}
CFDI_USES = {"G03": "Gastos en general", "I04": "Equipo de computo y accesorios"}
PAYMENT_FORMS = {"99": "Por definir", "03": "Transferencia electrónica de fondos"}
PAYMENT_METHODS = {"PPD": "Pago en parcialidades o diferido", "PUE": "Pago en una sola exhibición"}
CURRENCIES = {"MXN": "Peso Mexicano", "USD": "Dólar americano"}
FOOTER = "Reproducción de un CFDI para pruebas del portal. Documento ficticio, sin validez fiscal."

EXAMPLE_3668: dict = {
    "series": None,
    "folio": "3668",
    "uuid": "A328F91A-DDDD-4624-89AC-877819F5B540",
    "date": "2026-01-03T14:24:46",
    "place": "36100",
    "voucher_type": "I",
    "currency": "MXN",
    "payment_form": "99",
    "payment_method": "PPD",
    "issuer": {"rfc": "GOHS60031745A", "name": "SOCORRO PATRICIA GONZALEZ HERNANDEZ", "regime": "612"},
    "receiver": {
        "rfc": "IME010718PU3",
        "name": "INTERMODAL MEXICO",
        "regime": "601",
        "use": "G03",
        "postal_code": "11700",
    },
    "concepts": [
        {
            "product_key": "26111700",
            "quantity": "1.00",
            "unit_key": "H87",
            "unit": "PZ",
            "identification": "L-31T-900",
            "description": "LTH TIPO L-31T-900 AR BATERIA (OC/25704872)",
            "unit_value": "3559.05",
            "tax_object": "02",
            "iva_rate": "0.160000",
        }
    ],
}


def _money(value) -> Decimal:
    return Decimal(str(value)).quantize(CENTS, ROUND_HALF_UP)


# Factura demo del proveedor persona moral (TIC210101ABC) contra su orden de compra de servicios. La siembra cambia por
# factura el UUID, el folio y el convenio citado; cfdi_demo_*.xml son copias para pruebas manuales.
DEMO_MORAL: dict = {
    "series": "A",
    "folio": "1001",
    "uuid": "DEMO0001-0000-4000-8000-000000000001",
    "date": "2026-08-15T10:30:00",
    "place": "76000",
    "voucher_type": "I",
    "currency": "MXN",
    "payment_form": "99",
    "payment_method": "PPD",
    "issuer": {"rfc": "TIC210101ABC", "name": "TECNOLOGIA INTEGRAL DEL CENTRO SA DE CV", "regime": "601"},
    "receiver": dict(EXAMPLE_3668["receiver"]),
    "concepts": [
        {
            "product_key": "81111500",
            "quantity": "1",
            "unit_key": "E48",
            "unit": "Servicio",
            "identification": None,
            "description": "08 Servicios desarrollo Power Automate (OC/45001001)",
            "unit_value": "100000.00",
            "tax_object": "02",
            "iva_rate": "0.160000",
        }
    ],
}
DEMO_FILES = {
    "cfdi_demo_correcto.xml": {},
    # Subtotal por encima del total de su orden de compra: OC-005, OC-006 y OC-009 fallan.
    "cfdi_demo_monto_excedido.xml": {
        "uuid": "DEMO0003-0000-4000-8000-000000000003",
        "folio": "1003",
        "date": "2026-08-17T10:30:00",
        "concept": {"unit_value": "118000.00"},
    },
    # Emitida a otro receptor: XML-002 y XML-009 fallan.
    "cfdi_demo_rfc_incorrecto.xml": {
        "uuid": "DEMO0002-0000-4000-8000-000000000002",
        "folio": "1002",
        "date": "2026-08-16T10:30:00",
        "receiver": {"rfc": "XXX010101XXX", "name": "RECEPTOR INCORRECTO DEMO"},
    },
}


def complete(data: dict) -> dict:
    """Copia con los importes calculados: importe = cantidad x valor unitario, IVA por concepto y totales. Un valor ya
    presente (p. ej. un importe o un total distinto para una prueba) se respeta."""
    data = copy.deepcopy(data)
    subtotal = Decimal("0")
    iva_total = Decimal("0")
    for concept in data["concepts"]:
        amount = _money(concept.get("amount") or Decimal(concept["quantity"]) * Decimal(concept["unit_value"]))
        concept["amount"] = f"{amount:.2f}"
        rate = concept.get("iva_rate")
        if rate is not None and "iva" not in concept:
            concept["iva"] = f"{_money(amount * Decimal(rate)):.2f}"
        subtotal += amount
        iva_total += Decimal(concept.get("iva") or "0")
    data.setdefault("subtotal", f"{subtotal:.2f}")
    data.setdefault("tax", f"{iva_total:.2f}")
    data.setdefault("total", f"{Decimal(data['subtotal']) + Decimal(data['tax']):.2f}")
    return data


def variant(base: dict | None = None, **changes) -> dict:
    """EXAMPLE_3668 (o `base`) con cambios de primer nivel; `issuer`, `receiver` y el primer concepto se combinan
    con `issuer={...}`, `receiver={...}` y `concept={...}`."""
    data = copy.deepcopy(base or EXAMPLE_3668)
    for key in ("issuer", "receiver"):
        if key in changes:
            data[key] = {**data[key], **changes.pop(key)}
    if "concept" in changes:
        data["concepts"][0] = {**data["concepts"][0], **changes.pop("concept")}
    data.update(changes)
    return data


def invoice_number(data: dict) -> str:
    return f"{data['series']}-{data['folio']}" if data.get("series") else data["folio"]


# --- XML ------------------------------------------------------------------------------------------------------------


def _attrs(**values) -> str:
    return " ".join(f"{name}={quoteattr(str(value))}" for name, value in values.items() if value is not None)


def invoice_xml(data: dict) -> str:
    """CFDI 4.0 sin timbrar valido para el portal: el TimbreFiscalDigital solo lleva el UUID."""
    data = complete(data)
    issuer, receiver = data["issuer"], data["receiver"]
    concepts = []
    for c in data["concepts"]:
        taxes = ""
        if c.get("iva_rate") is not None:
            transfer = _attrs(Base=c["amount"], Impuesto="002", TipoFactor="Tasa", TasaOCuota=c["iva_rate"])
            taxes = (
                "<cfdi:Impuestos><cfdi:Traslados>"
                f"<cfdi:Traslado {transfer} {_attrs(Importe=c['iva'])}/>"
                "</cfdi:Traslados></cfdi:Impuestos>"
            )
        attributes = _attrs(
            ClaveProdServ=c.get("product_key", "81111500"),
            NoIdentificacion=c.get("identification"),
            Cantidad=c["quantity"],
            ClaveUnidad=c.get("unit_key"),
            Unidad=c.get("unit"),
            Descripcion=c["description"],
            ValorUnitario=c["unit_value"],
            Importe=c["amount"],
            ObjetoImp=c.get("tax_object", "02"),
        )
        concepts.append(f"    <cfdi:Concepto {attributes}>{taxes}</cfdi:Concepto>")
    comprobante = _attrs(
        Version="4.0",
        Serie=data.get("series"),
        Folio=data["folio"],
        Fecha=data["date"],
        FormaPago=data["payment_form"],
        SubTotal=data["subtotal"],
        Moneda=data["currency"],
        Total=data["total"],
        TipoDeComprobante=data["voucher_type"],
        Exportacion="01",
        MetodoPago=data["payment_method"],
        LugarExpedicion=data.get("place", "00000"),
    )
    return "\n".join(
        [
            '<?xml version="1.0" encoding="UTF-8"?>',
            "<!-- DOCUMENTO FICTICIO PARA PRUEBAS. NO ES UN CFDI TIMBRADO VALIDO. -->",
            '<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" '
            f'xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital" {comprobante}>',
            f"  <cfdi:Emisor {_attrs(Rfc=issuer['rfc'], Nombre=issuer['name'], RegimenFiscal=issuer.get('regime'))}/>",
            "  <cfdi:Receptor "
            + _attrs(
                Rfc=receiver["rfc"],
                Nombre=receiver["name"],
                DomicilioFiscalReceptor=receiver["postal_code"],
                RegimenFiscalReceptor=receiver["regime"],
                UsoCFDI=receiver["use"],
            )
            + "/>",
            "  <cfdi:Conceptos>",
            *concepts,
            "  </cfdi:Conceptos>",
            f'  <cfdi:Impuestos TotalImpuestosTrasladados="{data["tax"]}"/>',
            f'  <cfdi:Complemento><tfd:TimbreFiscalDigital Version="1.1" UUID="{data["uuid"]}"/></cfdi:Complemento>',
            "</cfdi:Comprobante>",
            "",
        ]
    )


# --- Representacion impresa ------------------------------------------------------------------------------------------


def _amount_text(value) -> str:
    return f"${Decimal(str(value)):,.2f}"


def _named(code: str | None, names: dict[str, str]) -> str:
    return f"{code} - {names[code]}" if code in names else str(code or "")


def invoice_pdf(data: dict) -> bytes:
    """Representacion impresa de una pagina con la maqueta habitual de un CFDI 4.0: emisor, datos del comprobante,
    cliente, tabla de conceptos con sus impuestos y totales. Cada celda es un texto independiente, como en los PDF
    reales, de modo que el texto extraido llega por lineas."""
    data = complete(data)
    issuer, receiver = data["issuer"], data["receiver"]
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    bold, regular = "hebo", "helv"

    def text(x, y, value, size=8.5, font=regular):
        page.insert_text((x, y), str(value), fontsize=size, fontname=font)

    text(36, 48, issuer["name"], 12, bold)
    text(36, 64, f"RFC: {issuer['rfc']}")
    if issuer.get("regime"):
        text(36, 76, f"RÉGIMEN FISCAL: {_named(issuer['regime'], REGIMES)}")
    text(36, 88, f"LUGAR DE EXPEDICIÓN: {data.get('place', '00000')}")
    text(400, 48, f"Factura {invoice_number(data)}", 12, bold)
    text(400, 64, "FOLIO FISCAL (UUID):", 7, bold)
    text(400, 74, data["uuid"], 7)
    text(400, 86, "FECHA Y HORA DE EMISIÓN DE CFDI:", 7, bold)
    text(400, 96, data["date"], 7)
    text(400, 108, f"TIPO DE COMPROBANTE: {data['voucher_type']} - Ingreso", 7)
    page.draw_line((36, 118), (576, 118))
    text(36, 134, "CLIENTE", 9, bold)
    text(36, 148, receiver["name"], 9)
    text(36, 160, f"RFC: {receiver['rfc']}")
    text(300, 148, f"USO CFDI: {_named(receiver['use'], CFDI_USES)}")
    text(300, 160, f"DOMICILIO FISCAL: {receiver['postal_code']}")
    text(300, 172, f"REGIMEN FISCAL: {_named(receiver['regime'], REGIMES)}")
    page.draw_line((36, 182), (576, 182))
    text(36, 198, "CONCEPTOS", 9, bold)
    columns = (36, 80, 130, 200, 410, 480, 525)
    headers = ("Cantidad", "Unidad", "No. Identificación", "Descripción", "Precio Unitario", "Objeto Imp.", "Importe")
    for x, header in zip(columns, headers, strict=True):
        text(x, 212, header, 7, bold)
    y = 228
    for concept in data["concepts"]:
        unit = " - ".join(filter(None, (concept.get("unit_key"), concept.get("unit"))))
        text(columns[0], y, concept["quantity"])
        text(columns[1], y, unit)
        text(columns[2], y, concept.get("identification") or "")
        lines = textwrap.wrap(concept["description"], 44) or [""]
        for index, line in enumerate(lines):
            text(columns[3], y + 10 * index, line)
        text(columns[4], y, _amount_text(concept["unit_value"]))
        text(columns[5], y, concept.get("tax_object", "02"))
        text(columns[6], y, _amount_text(concept["amount"]))
        y += 10 * len(lines) + 2
        if concept.get("iva_rate") is not None:
            text(
                columns[3],
                y,
                f"Impuestos: Traslados: 002 IVA Base - {_amount_text(concept['amount'])} "
                f"Tasa - {concept['iva_rate']} Importe - {_amount_text(concept['iva'])}",
                7,
            )
            y += 12
        y += 6
    page.draw_line((36, y), (576, y))
    y += 16
    text(36, y, f"MONEDA: {_named(data['currency'], CURRENCIES)}")
    text(36, y + 12, f"FORMA DE PAGO: {_named(data['payment_form'], PAYMENT_FORMS)}")
    text(36, y + 24, f"MÉTODO DE PAGO: {_named(data['payment_method'], PAYMENT_METHODS)}")
    text(400, y, "SUBTOTAL")
    text(510, y, _amount_text(data["subtotal"]))
    text(400, y + 12, "TRASLADO IVA TASA 0.160000")
    text(510, y + 12, _amount_text(data["tax"]))
    text(400, y + 24, "TOTAL", 9, bold)
    text(510, y + 24, _amount_text(data["total"]), 9, bold)
    text(36, 760, FOOTER, 7)
    content = doc.tobytes()
    doc.close()
    return content


def main() -> None:
    demo = ROOT / "data" / "demo_documents"
    (demo / "factura_3668.pdf").write_bytes(invoice_pdf(EXAMPLE_3668))
    (demo / "factura_3668.xml").write_text(invoice_xml(EXAMPLE_3668), encoding="utf-8")
    for name, changes in DEMO_FILES.items():
        (demo / name).write_text(invoice_xml(variant(DEMO_MORAL, **changes)), encoding="utf-8")
    print("Generados factura_3668.pdf, factura_3668.xml y " + ", ".join(DEMO_FILES) + " en data/demo_documents")


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    main()
