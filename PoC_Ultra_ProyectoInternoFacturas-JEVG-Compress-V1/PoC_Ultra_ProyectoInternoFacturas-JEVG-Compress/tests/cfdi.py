"""Facturas de prueba registradas por sus archivos y ordenes de compra (HU-24).

Los CFDI salen de scripts/cfdi_demo.py: cada prueba arma el suyo con un UUID y un folio nuevos y cita su propia orden
de compra, porque una orden solo admite una factura vigente (OC-012) y el UUID es unico en la base.
"""

from __future__ import annotations

import secrets
from datetime import date
from decimal import Decimal

from sqlalchemy import delete, select

from scripts import cfdi_demo
from tests.conftest import ROOT, csrf, invoice_by_number

DEMO = ROOT / "data" / "demo_documents"
# PDF sin datos de un CFDI: con XML, el registro toma los datos del XML.
PLAIN_PDF = (DEMO / "factura_demo.pdf").read_bytes()
EXAMPLE_PDF = (DEMO / "factura_3668.pdf").read_bytes()
EXAMPLE_XML = (DEMO / "factura_3668.xml").read_bytes()
SUPPORT = b"Documento soporte de prueba"
MORAL_EMAIL, PHYSICAL_EMAIL, FOREIGN_EMAIL = "proveedor1@poc.local", "proveedor2@poc.local", "proveedor3@poc.local"
MORAL_RFC, MORAL_NAME = "TIC210101ABC", "TECNOLOGIA INTEGRAL DEL CENTRO SA DE CV"
EXAMPLE_RFC, EXAMPLE_NAME = "GOHS60031745A", "SOCORRO PATRICIA GONZALEZ HERNANDEZ"
POWER_AUTOMATE = "SERVICIOS DESARROLLO POWER AUTOMATE"
EXAMPLE_TEXT = "LTH TIPO L-31 T-900 AR"


def new_uuid() -> str:
    parts = (secrets.token_hex(4), secrets.token_hex(2), "4000", "8000", secrets.token_hex(6))
    return "-".join(parts).upper()


def new_convenio() -> int:
    """Convenio de 8 digitos fuera de los rangos sembrados (25704872 y 4500xxxx)."""
    return 60_000_000 + secrets.randbelow(39_999_999)


def new_folio() -> str:
    return secrets.token_hex(4).upper()


def moral_cfdi(convenio: int | None = None, **changes) -> dict:
    """CFDI del proveedor moral demo (TIC210101ABC, 100,000.00 + IVA) con UUID y folio nuevos; su concepto cita la
    orden `convenio`. `concept={...}` cambia el concepto y `receiver={...}`/`issuer={...}` el receptor o el emisor."""
    concept = dict(changes.pop("concept", {}))
    if convenio is not None:
        concept.setdefault("description", f"08 Servicios desarrollo Power Automate (OC/{convenio})")
    changes.setdefault("uuid", new_uuid())
    changes.setdefault("folio", new_folio())
    return cfdi_demo.variant(cfdi_demo.DEMO_MORAL, concept=concept, **changes)


def example_cfdi(convenio: int | None = None, **changes) -> dict:
    """Variante de la factura 3668 del ejemplo (proveedor GOHS60031745A) con UUID y folio nuevos."""
    concept = dict(changes.pop("concept", {}))
    if convenio is not None:
        concept.setdefault("description", f"LTH TIPO L-31T-900 AR BATERIA (OC/{convenio})")
    changes.setdefault("uuid", new_uuid())
    changes.setdefault("folio", new_folio())
    return cfdi_demo.variant(cfdi_demo.EXAMPLE_3668, concept=concept, **changes)


def xml_of(data: dict) -> bytes:
    return cfdi_demo.invoice_xml(data).encode()


def pdf_of(data: dict) -> bytes:
    return cfdi_demo.invoice_pdf(data)


def number_of(data: dict) -> str:
    return cfdi_demo.invoice_number(data)


def token(client) -> str:
    return csrf(client, "/invoices")


def register(client, pdf: bytes | None, xml: bytes | None = None, pdf_name="factura.pdf", xml_name="cfdi.xml", **data):
    """Paso 1 nacional: POST /invoices/new con el PDF y el XML."""
    files = {}
    if pdf is not None:
        files["pdf"] = (pdf_name, pdf, "application/pdf")
    if xml is not None:
        files["xml"] = (xml_name, xml, "application/xml")
    return client.post(
        "/invoices/new", data={"csrf_token": token(client), **data}, files=files or None, follow_redirects=False
    )


def register_cfdi(client, data: dict, with_xml: bool = True):
    """Registra el CFDI `data` con su PDF y, si `with_xml`, su XML; devuelve (respuesta, factura)."""
    response = register(client, pdf_of(data), xml_of(data) if with_xml else None)
    return response, invoice_by_number(number_of(data))


def upload(client, invoice, document_type: str, filename: str, content: bytes, next_step: str | None = None):
    data = {"document_type": document_type, "csrf_token": token(client)}
    if next_step:
        data["next"] = next_step
    return client.post(
        f"/invoices/{invoice.id}/documents",
        data=data,
        files={"upload": (filename, content, "application/octet-stream")},
        follow_redirects=False,
    )


def submit(client, invoice):
    return client.post(f"/invoices/{invoice.id}/submit", data={"csrf_token": token(client)}, follow_redirects=False)


def verify(client, invoice):
    return client.post(f"/invoices/{invoice.id}/validation", data={"csrf_token": token(client)}, follow_redirects=False)


def reload(invoice):
    from app.core.database import SessionLocal
    from app.models import Invoice

    with SessionLocal() as db:
        return db.get(Invoice, invoice.id)


def results(invoice) -> dict:
    """Resultados de la ultima validacion por codigo; el ultimo de cada codigo si hay varios (reglas por concepto)."""
    from app.core.database import SessionLocal
    from app.models import ValidationResult

    with SessionLocal() as db:
        rows = db.scalars(
            select(ValidationResult).where(ValidationResult.invoice_id == invoice.id).order_by(ValidationResult.id)
        )
        return {row.rule_code: row for row in rows}


def item(
    text: str = POWER_AUTOMATE,
    price: str = "100000.00",
    *,
    quantity: str = "1",
    unit: str = "SER",
    currency: str = "MXN",
    delivered: bool = True,
    material: str = "S-PRUEBA",
) -> dict:
    """Partida de orden de compra con las etiquetas de SAP."""
    return {
        "Material": material,
        "Txt.brv": text,
        "Ctd.Pedido": quantity,
        "Unidad.Pedido": unit,
        "Fe.Entrega": "31.07.2026",
        "Prc.Neto": price,
        "Moneda": currency,
        "Grupo.Art": "SERVICIOS TI",
        "Almacen": "CDMX_CORP",
        "Docto Material": "5000599999" if delivered else "",
        "Fecha Conta": "31.07.2026" if delivered else "",
    }


def order_factory():
    """Generador de la fixture purchase_orders (conftest): fabrica de ordenes de compra de prueba, por omision del
    proveedor moral demo y que cuadran con moral_cfdi(). Al terminar borra las que no quedaron ligadas a una factura
    (la llave foranea lo impide)."""
    from app.core.database import SessionLocal
    from app.models import Invoice, PurchaseOrder
    from app.services import purchase_order_service

    created: list[int] = []

    def make(
        *,
        rfc: str = MORAL_RFC,
        supplier_name: str = MORAL_NAME,
        total: str = "100000.00",
        taxes: str = "16000.00",
        items: list[dict] | None = None,
        convenio: int | None = None,
        supplier_id: int | None = None,
        order_date: date = date(2026, 7, 20),
    ) -> PurchaseOrder:
        with SessionLocal() as db:
            order = purchase_order_service.create(
                db,
                convenio=convenio or new_convenio(),
                rfc=rfc,
                supplier_name=supplier_name,
                order_date=order_date,
                total=Decimal(total),
                taxes=Decimal(taxes),
                items=items or [item()],
                supplier_id=supplier_id,
            )
            db.commit()
            created.append(order.id)
            return order

    yield make
    with SessionLocal() as db:
        linked = set(db.scalars(select(Invoice.purchase_order_id).where(Invoice.purchase_order_id.in_(created))))
        db.execute(delete(PurchaseOrder).where(PurchaseOrder.id.in_(set(created) - linked)))
        db.commit()


def example_order(purchase_orders, **changes):
    """Orden del proveedor del ejemplo (GOHS60031745A) que cuadra con example_cfdi()."""
    values = {
        "rfc": EXAMPLE_RFC,
        "supplier_name": EXAMPLE_NAME,
        "total": "3559.05",
        "taxes": "569.45",
        "items": [item(EXAMPLE_TEXT, "3559.05", unit="PZA", material="E20080")],
        **changes,
    }
    return purchase_orders(**values)


def ready_invoice(client, purchase_orders, vobo: bool = True, order=None, **changes):
    """Factura del proveedor moral registrada con PDF y XML contra una orden propia que cuadra, con el Vo.Bo.
    cargado ("Cargada"). Devuelve (factura, orden)."""
    order = order or purchase_orders()
    data = moral_cfdi(order.convenio, **changes)
    response, invoice = register_cfdi(client, data)
    assert response.status_code == 303, response.text
    if vobo:
        assert upload(client, invoice, "APPROVAL", "vobo.txt", SUPPORT).status_code == 303
    return reload(invoice), order
