from __future__ import annotations

from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from lxml import etree


class XMLParseError(ValueError):
    pass


def _decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def _attr(node: etree._Element | None, *names: str) -> str | None:
    if node is None:
        return None
    for name in names:
        if name in node.attrib:
            return node.attrib[name]
    return None


def parse_cfdi(source: bytes | str | Path) -> dict[str, Any]:
    """Extrae CFDI sin resolver entidades ni depender de prefijos de namespace."""
    try:
        raw = source if isinstance(source, bytes) else Path(source).read_bytes()
        parser = etree.XMLParser(resolve_entities=False, no_network=True, recover=False, huge_tree=False)
        root = etree.fromstring(raw, parser=parser)
    except (OSError, etree.XMLSyntaxError) as exc:
        raise XMLParseError(f"XML no parseable: {exc}") from exc
    if etree.QName(root).localname != "Comprobante":
        raise XMLParseError("El nodo raiz no es Comprobante")
    issuer = next(iter(root.xpath("./*[local-name()='Emisor']")), None)
    receiver = next(iter(root.xpath("./*[local-name()='Receptor']")), None)
    stamp = next(iter(root.xpath(".//*[local-name()='TimbreFiscalDigital']")), None)
    concepts: list[dict[str, Any]] = []
    for concept in root.xpath("./*[local-name()='Conceptos']/*[local-name()='Concepto']"):
        taxes = concept.xpath(".//*[local-name()='Traslado' or local-name()='Retencion']")
        concepts.append(
            {
                "description": _attr(concept, "Descripcion"),
                "quantity": _decimal(_attr(concept, "Cantidad")),
                "unit_value": _decimal(_attr(concept, "ValorUnitario")),
                "amount": _decimal(_attr(concept, "Importe")),
                "taxes": [
                    {
                        "tax": _attr(t, "Impuesto"),
                        "rate": _attr(t, "TasaOCuota"),
                        "amount": _decimal(_attr(t, "Importe")),
                    }
                    for t in taxes
                ],
            }
        )
    transferred = _attr(next(iter(root.xpath("./*[local-name()='Impuestos']")), None), "TotalImpuestosTrasladados")
    return {
        "version": _attr(root, "Version", "version"),
        "uuid": _attr(stamp, "UUID"),
        "issuer_rfc": _attr(issuer, "Rfc", "rfc"),
        "issuer_name": _attr(issuer, "Nombre"),
        "receiver_rfc": _attr(receiver, "Rfc", "rfc"),
        "receiver_name": _attr(receiver, "Nombre"),
        "receiver_postal_code": _attr(receiver, "DomicilioFiscalReceptor"),
        "receiver_regime": _attr(receiver, "RegimenFiscalReceptor"),
        "date": _attr(root, "Fecha"),
        "subtotal": _decimal(_attr(root, "SubTotal")),
        "tax": _decimal(transferred) or Decimal("0"),
        "total": _decimal(_attr(root, "Total")),
        "currency": _attr(root, "Moneda"),
        "payment_form": _attr(root, "FormaPago"),
        "payment_method": _attr(root, "MetodoPago"),
        "cfdi_use": _attr(receiver, "UsoCFDI"),
        "voucher_type": _attr(root, "TipoDeComprobante"),
        "concepts": concepts,
    }
