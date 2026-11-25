"""Ordenes de compra (HU-24): alta validada para la siembra, busqueda de la orden de una factura, facturas vigentes de
una orden y consulta para PMO y Administrador. En la rama ferromex el PMO (analista de cuentas por pagar) y el
Administrador tambien las dan de alta y las editan desde el portal (OrderForm).

Sin commit: el endpoint confirma la transaccion. find() lee la orden con FOR UPDATE: el bloqueo dura hasta ese commit,
de modo que dos envios que citan la misma orden se ejecutan uno despues del otro y el segundo ve la liga del primero
(RD-16).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.constants import (
    PO_CURRENCY,
    PO_NET_PRICE,
    PO_POSTING_DATE,
    PO_QUANTITY,
    PURCHASE_ORDER_ITEM_KEYS,
    PURCHASE_ORDER_ITEM_LABELS,
    UNIT_EQUIVALENCES,
    CatalogType,
    InvoiceStatus,
)
from app.core.errors import InvalidInputError
from app.models import Invoice, PurchaseOrder, Supplier
from app.repositories.pagination import Page, escape_like, paginate
from app.rules.purchase_order_rules import OrderView, order_items, to_decimal
from app.services.audit_service import audit
from app.services.catalog_service import active_entries

# Estatus de una factura que ya no ocupa su orden de compra (RD-16): las demas facturas ligadas la ocupan.
RELEASED_STATUSES = (InvoiceStatus.REJECTED, InvoiceStatus.CANCELLED)
CURRENCY = re.compile(r"[A-Z]{3}")


def validate_items(data: Mapping) -> None:
    """Estructura de data (seccion 6.2 de la HU): una lista `items` no vacia; cada partida con las etiquetas que usan
    las reglas, cantidad y precio decimales positivos y moneda de tres letras. ValueError con el motivo."""
    items = data.get("items") if isinstance(data, Mapping) else None
    if not isinstance(items, list) or not items:
        raise ValueError("La orden de compra debe tener al menos una partida")
    for position, item in enumerate(items, 1):
        if not isinstance(item, Mapping):
            raise ValueError(f"Partida {position}: formato inválido")
        missing = [key for key in PURCHASE_ORDER_ITEM_KEYS if not str(item.get(key) or "").strip()]
        if missing:
            raise ValueError(f"Partida {position}: faltan {', '.join(missing)}")
        for key in (PO_QUANTITY, PO_NET_PRICE):
            value = to_decimal(item.get(key))
            if value is None or value <= 0:
                raise ValueError(f"Partida {position}: {key} debe ser un decimal positivo")
        if not CURRENCY.fullmatch(str(item[PO_CURRENCY]).strip()):
            raise ValueError(f"Partida {position}: {PO_CURRENCY} debe tener tres letras")


def create(
    db: Session,
    *,
    convenio: int,
    rfc: str,
    supplier_name: str,
    order_date: date,
    total: Decimal,
    taxes: Decimal,
    items: list[dict],
    supplier_id: int | None = None,
) -> PurchaseOrder:
    """Orden de compra validada (la siembra y las pruebas; las ordenes vienen de SAP). Sin supplier_id, se liga al
    proveedor nacional con ese RFC si existe."""
    data = {"items": items}
    validate_items(data)
    rfc = rfc.strip().upper()
    if supplier_id is None:
        supplier_id = db.scalar(select(Supplier.id).where(Supplier.rfc == rfc))
    order = PurchaseOrder(
        convenio=convenio,
        rfc=rfc,
        supplier_name=supplier_name,
        order_date=order_date,
        total=total,
        taxes=taxes,
        data=data,
        supplier_id=supplier_id,
    )
    db.add(order)
    db.flush()
    return order


def view(order: PurchaseOrder) -> OrderView:
    return OrderView(
        id=order.id,
        convenio=order.convenio,
        rfc=order.rfc,
        supplier_name=order.supplier_name,
        order_date=order.order_date,
        total=order.total,
        taxes=order.taxes,
        items=order_items(order.data),
    )


def find(db: Session, number: str | None, supplier: Supplier) -> PurchaseOrder | None:
    """La orden de compra `number` del proveedor (RD-07), con bloqueo de fila. El nacional la encuentra por su RFC; el
    internacional, por supplier_id. Una orden de otro proveedor responde igual que una inexistente."""
    if not number or not number.isdigit():
        return None
    stmt = select(PurchaseOrder).where(PurchaseOrder.convenio == int(number))
    if supplier.rfc:
        stmt = stmt.where(PurchaseOrder.rfc == supplier.rfc.upper())
    else:
        stmt = stmt.where(PurchaseOrder.supplier_id == supplier.id)
    return db.scalar(stmt.with_for_update())


def active_invoices(db: Session, order_id: int, invoice_id: int) -> list[str]:
    """Folios de las otras facturas ligadas a la orden que la siguen ocupando (RD-16)."""
    return list(
        db.scalars(
            select(Invoice.internal_folio)
            .where(
                Invoice.purchase_order_id == order_id,
                Invoice.id != invoice_id,
                Invoice.status.not_in(RELEASED_STATUSES),
            )
            .order_by(Invoice.internal_folio)
        )
    )


# --- Consulta (PMO y Administrador) -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class OrderRow:
    order: PurchaseOrder
    items: int
    invoices: int


def search(db: Session, q: str, page: int) -> Page[OrderRow]:
    """Listado de la mas reciente a la mas antigua, paginado en SQL. Un texto de solo digitos busca ademas el
    convenio exacto; cualquier texto busca en RFC y nombre sin distinguir mayusculas."""
    text = (q or "").strip()
    stmt = select(PurchaseOrder).order_by(PurchaseOrder.order_date.desc(), PurchaseOrder.id.desc())
    if text:
        pattern = f"%{escape_like(text)}%"
        conditions = [
            PurchaseOrder.rfc.ilike(pattern, escape="\\"),
            PurchaseOrder.supplier_name.ilike(pattern, escape="\\"),
        ]
        if text.isdigit() and len(text) <= 18:
            conditions.append(PurchaseOrder.convenio == int(text))
        stmt = stmt.where(or_(*conditions))
    result = paginate(db, stmt, page)
    ids = [order.id for order in result.items]
    counts = dict(
        db.execute(
            select(Invoice.purchase_order_id, func.count(Invoice.id))
            .where(Invoice.purchase_order_id.in_(ids))
            .group_by(Invoice.purchase_order_id)
        ).all()
    )
    items = dict(
        db.execute(
            select(PurchaseOrder.id, func.jsonb_array_length(PurchaseOrder.data["items"])).where(
                PurchaseOrder.id.in_(ids)
            )
        ).all()
    )
    rows = [OrderRow(order, items.get(order.id, 0), counts.get(order.id, 0)) for order in result.items]
    return Page(rows, result.page, result.per_page, result.total)


def linked_invoices(db: Session, order_id: int) -> list[Invoice]:
    return list(
        db.scalars(select(Invoice).where(Invoice.purchase_order_id == order_id).order_by(Invoice.internal_folio))
    )


def counts_by_supplier(db: Session, suppliers: list[Supplier]) -> dict[int, int]:
    """Ordenes de compra de cada proveedor de una pagina: por RFC (nacional) o por supplier_id (internacional)."""
    rfcs = {supplier.rfc: supplier.id for supplier in suppliers if supplier.rfc}
    result = {supplier.id: 0 for supplier in suppliers}
    if rfcs:
        for rfc, count in db.execute(
            select(PurchaseOrder.rfc, func.count()).where(PurchaseOrder.rfc.in_(rfcs)).group_by(PurchaseOrder.rfc)
        ):
            result[rfcs[rfc]] = count
    foreign = [supplier.id for supplier in suppliers if not supplier.rfc]
    if foreign:
        for supplier_id, count in db.execute(
            select(PurchaseOrder.supplier_id, func.count())
            .where(PurchaseOrder.supplier_id.in_(foreign))
            .group_by(PurchaseOrder.supplier_id)
        ):
            result[supplier_id] = count
    return result


# --- Alta y edicion desde el portal (Ferromex) ------------------------------------------------------------------------

# RFC generico de SAP del proveedor internacional: su orden se liga por supplier_id.
GENERIC_FOREIGN_RFC = "XEXX010101000"
# Las fechas de las partidas se guardan como las escribe SAP (dd.mm.aaaa); el formulario usa <input type="date">.
SAP_DATE_FORMAT = "%d.%m.%Y"
DATE_KEYS = ("Fe.Entrega", PO_POSTING_DATE)
ITEM_KEYS = tuple(key for key, _ in PURCHASE_ORDER_ITEM_LABELS)
ITEM_LABELS = dict(PURCHASE_ORDER_ITEM_LABELS)
# Numero de orden que se puede citar en una factura (RD-06): de 6 a 10 digitos.
CONVENIO_FORMAT = re.compile(r"\d{6,10}")
CENTS = Decimal("0.01")
MAX_AMOUNT = Decimal("9999999999.99")
DEFAULT_CURRENCY = "MXN"
MSG_CONVENIO = "El convenio debe tener de 6 a 10 dígitos"
MSG_DUPLICATE = "Ya existe la orden de compra {convenio}"
MSG_SUPPLIER = "Seleccione el proveedor de la orden"
MSG_DATE = "Capture la fecha de la orden"
MSG_TOTAL = "El total debe ser un importe mayor que cero"
MSG_TAXES = "Los impuestos deben ser un importe mayor o igual a cero"
MSG_ITEM_DATE = "Partida {position}: {label} debe ser una fecha válida"
MSG_LINKED = "La orden {convenio} ya tiene facturas ligadas: no se puede cambiar su convenio ni su proveedor"


def sap_date(value: str) -> str:
    """aaaa-mm-dd -> dd.mm.aaaa; vacio se queda vacio. ValueError si no es una fecha."""
    value = (value or "").strip()
    return datetime.strptime(value, "%Y-%m-%d").strftime(SAP_DATE_FORMAT) if value else ""


def iso_date(value: str | None) -> str:
    """dd.mm.aaaa -> aaaa-mm-dd para el formulario; vacio si el valor no tiene ese formato."""
    try:
        return datetime.strptime(str(value or "").strip(), SAP_DATE_FORMAT).strftime("%Y-%m-%d")
    except ValueError:
        return ""


def _blank_item() -> dict[str, str]:
    return {key: "" for key in ITEM_KEYS} | {PO_CURRENCY: DEFAULT_CURRENCY}


@dataclass
class OrderForm:
    """Lo capturado en el formulario, como texto: se conserva cuando el alta o la edicion se rechazan."""

    convenio: str = ""
    supplier_id: str = ""
    order_date: str = ""
    total: str = ""
    taxes: str = ""
    items: list[dict[str, str]] = field(default_factory=list)

    @classmethod
    def blank(cls) -> OrderForm:
        return cls(items=[_blank_item()])

    @classmethod
    def from_order(cls, db: Session, order: PurchaseOrder) -> OrderForm:
        items = []
        for item in order_items(order.data):
            values = {key: str(item.values.get(key) or "") for key in ITEM_KEYS}
            for key in DATE_KEYS:
                values[key] = iso_date(values[key])
            items.append(values)
        # Una orden nacional sembrada antes del alta de su proveedor no tiene supplier_id: se propone el del RFC.
        supplier_id = order.supplier_id or db.scalar(select(Supplier.id).where(Supplier.rfc == order.rfc))
        return cls(
            convenio=str(order.convenio),
            supplier_id=str(supplier_id or ""),
            order_date=order.order_date.isoformat(),
            total=f"{order.total:.2f}",
            taxes=f"{order.taxes:.2f}",
            items=items or [_blank_item()],
        )

    @classmethod
    def from_form(cls, form) -> OrderForm:
        """Cada columna de partidas llega como lista (item-<etiqueta de SAP>). Se descartan las filas sin datos (la
        moneda que el formulario propone no cuenta como dato)."""
        columns = {key: form.getlist(f"item-{key}") for key in ITEM_KEYS}
        rows = max((len(values) for values in columns.values()), default=0)
        items = []
        for index in range(rows):
            row = {key: str(values[index]).strip() if index < len(values) else "" for key, values in columns.items()}
            if any(value for key, value in row.items() if key != PO_CURRENCY):
                items.append(row)

        def text(name: str) -> str:
            return str(form.get(name) or "").strip()

        return cls(text("convenio"), text("supplier_id"), text("order_date"), text("total"), text("taxes"), items)


@dataclass(frozen=True)
class OrderData:
    convenio: int
    rfc: str
    supplier_name: str
    supplier_id: int | None
    order_date: date
    total: Decimal
    taxes: Decimal
    items: list[dict]


def _amount(value: str, minimum: Decimal, inclusive: bool, message: str) -> Decimal:
    amount = to_decimal(value)
    if amount is None:
        raise InvalidInputError(message)
    amount = amount.quantize(CENTS)
    if amount > MAX_AMOUNT or amount < minimum or (amount == minimum and not inclusive):
        raise InvalidInputError(message)
    return amount


def parse(db: Session, form: OrderForm, order: PurchaseOrder | None = None) -> OrderData:
    """Valida lo capturado; InvalidInputError con el primer motivo. El RFC y el nombre salen del proveedor elegido
    (el internacional lleva el RFC generico de SAP). Sin proveedor, una orden existente conserva los suyos: llego de
    SAP antes del alta de su proveedor en el portal."""
    if not CONVENIO_FORMAT.fullmatch(form.convenio):
        raise InvalidInputError(MSG_CONVENIO)
    if form.supplier_id:
        supplier = db.get(Supplier, int(form.supplier_id)) if form.supplier_id.isdigit() else None
        if supplier is None:
            raise InvalidInputError(MSG_SUPPLIER)
        rfc, name, supplier_id = supplier.rfc or GENERIC_FOREIGN_RFC, supplier.business_name, supplier.id
    elif order is not None:
        rfc, name, supplier_id = order.rfc, order.supplier_name, None
    else:
        raise InvalidInputError(MSG_SUPPLIER)
    try:
        order_date = date.fromisoformat(form.order_date)
    except ValueError:
        raise InvalidInputError(MSG_DATE) from None
    total = _amount(form.total, Decimal("0"), False, MSG_TOTAL)
    taxes = _amount(form.taxes, Decimal("0"), True, MSG_TAXES)
    items = []
    for position, row in enumerate(form.items, 1):
        item = {key: str(row.get(key) or "").strip() for key in ITEM_KEYS}
        for key in DATE_KEYS:
            try:
                item[key] = sap_date(item[key])
            except ValueError:
                raise InvalidInputError(MSG_ITEM_DATE.format(position=position, label=ITEM_LABELS[key])) from None
        item[PO_CURRENCY] = item[PO_CURRENCY].upper()
        items.append(item)
    try:
        validate_items({"items": items})
    except ValueError as exc:
        raise InvalidInputError(str(exc)) from None
    return OrderData(int(form.convenio), rfc, name, supplier_id, order_date, total, taxes, items)


def _ensure_unique(db: Session, convenio: int, order_id: int | None = None) -> None:
    stmt = select(PurchaseOrder.id).where(PurchaseOrder.convenio == convenio)
    if order_id is not None:
        stmt = stmt.where(PurchaseOrder.id != order_id)
    if db.scalar(stmt) is not None:
        raise InvalidInputError(MSG_DUPLICATE.format(convenio=convenio))


def snapshot(order: PurchaseOrder) -> dict:
    """Encabezado y numero de partidas para la auditoria."""
    return {
        "convenio": order.convenio,
        "rfc": order.rfc,
        "supplier_name": order.supplier_name,
        "supplier_id": order.supplier_id,
        "order_date": order.order_date.isoformat(),
        "total": f"{order.total:.2f}",
        "taxes": f"{order.taxes:.2f}",
        "items": len(order_items(order.data)),
    }


def linked_count(db: Session, order_id: int) -> int:
    return db.scalar(select(func.count(Invoice.id)).where(Invoice.purchase_order_id == order_id)) or 0


def create_from_form(db: Session, form: OrderForm, user_id: int) -> PurchaseOrder:
    """Alta desde el portal. Sin commit; un convenio repetido por una alta simultanea llega como IntegrityError de
    uq_purchase_orders_convenio al confirmar."""
    data = parse(db, form)
    _ensure_unique(db, data.convenio)
    order = create(
        db,
        convenio=data.convenio,
        rfc=data.rfc,
        supplier_name=data.supplier_name,
        order_date=data.order_date,
        total=data.total,
        taxes=data.taxes,
        items=data.items,
        supplier_id=data.supplier_id,
    )
    audit(db, "PURCHASE_ORDER_CREATED", "PurchaseOrder", order.id, user_id, new=snapshot(order))
    return order


def update_from_form(db: Session, order: PurchaseOrder, form: OrderForm, user_id: int) -> bool:
    """Edicion desde el portal; True si algo cambio. Bloquea la orden como find(): un envio que la cita espera a que
    la edicion se confirme. Con facturas ligadas no cambian el convenio ni el proveedor; las partidas y los montos si,
    y aplican a las validaciones siguientes (la evidencia de las anteriores guarda la orden como se leyo, RD-15)."""
    db.execute(select(PurchaseOrder.id).where(PurchaseOrder.id == order.id).with_for_update())
    data = parse(db, form, order)
    _ensure_unique(db, data.convenio, order.id)
    identity_changed = (
        data.convenio != order.convenio
        or data.rfc != order.rfc
        or (order.supplier_id is not None and data.supplier_id != order.supplier_id)
    )
    if identity_changed and linked_count(db, order.id):
        raise InvalidInputError(MSG_LINKED.format(convenio=order.convenio))
    before, items_before = snapshot(order), (order.data or {}).get("items")
    order.convenio = data.convenio
    order.rfc = data.rfc
    order.supplier_name = data.supplier_name
    order.supplier_id = data.supplier_id if data.supplier_id is not None else order.supplier_id
    order.order_date = data.order_date
    order.total = data.total
    order.taxes = data.taxes
    order.data = {**(order.data or {}), "items": data.items}
    after = snapshot(order)
    changed = before != after or items_before != data.items
    if changed:
        audit(db, "PURCHASE_ORDER_UPDATED", "PurchaseOrder", order.id, user_id, old=before, new=after)
    return changed


def form_options(db: Session, form: OrderForm) -> dict:
    """Opciones del formulario: proveedores, unidades de SAP y monedas activas del catalogo, mas los valores ya
    capturados que no esten en esas listas (una orden de SAP puede traer otros)."""
    suppliers = list(db.scalars(select(Supplier).order_by(Supplier.business_name, Supplier.id)))
    units = list(UNIT_EQUIVALENCES)
    currencies = [entry.code for entry in active_entries(db, CatalogType.CURRENCY)] or [DEFAULT_CURRENCY]
    for item in form.items:
        unit, currency = item.get("Unidad.Pedido"), item.get(PO_CURRENCY)
        if unit and unit not in units:
            units.append(unit)
        if currency and currency not in currencies:
            currencies.append(currency)
    return {"suppliers": suppliers, "units": units, "currencies": currencies}
