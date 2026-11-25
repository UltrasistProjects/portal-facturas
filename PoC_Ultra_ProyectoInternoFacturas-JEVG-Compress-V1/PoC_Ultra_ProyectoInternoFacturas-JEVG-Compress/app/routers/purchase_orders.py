"""Ordenes de compra para PMO y Administrador (HU-24): consulta y, en la rama ferromex, alta y edicion desde el portal.
Las de SAP se siguen sembrando con purchase_order_service.create."""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.constants import PO_CURRENCY, PURCHASE_ORDER_ITEM_KEYS, PURCHASE_ORDER_ITEM_LABELS, Role
from app.core.database import get_db, violates
from app.core.errors import InvalidInputError
from app.core.security import require_roles, validate_csrf
from app.models import PurchaseOrder
from app.repositories.pagination import list_query
from app.routers.common import templates
from app.rules.purchase_order_rules import order_items
from app.services import purchase_order_service
from app.services.purchase_order_service import DATE_KEYS, MSG_DUPLICATE, OrderForm

router = APIRouter(prefix="/purchase-orders")
reviewers_only = require_roles(Role.PMO, Role.ADMINISTRADOR)
# Avisos que llegan por ?notice= tras guardar; otro valor se ignora.
NOTICES = {
    "created": "Orden de compra creada",
    "updated": "Orden de compra actualizada",
    "unchanged": "Sin cambios",
}
UNIQUE_CONVENIO = "uq_purchase_orders_convenio"


@router.get("")
def list_purchase_orders(
    request: Request, q: str = "", page: int = 1, db: Session = Depends(get_db), user=Depends(reviewers_only)
):
    q = q.strip()
    result = purchase_order_service.search(db, q, page)
    context = {"user": user, "rows": result.items, "page": result, "q": q, "base_query": list_query(q=q)}
    return templates.TemplateResponse(request, "purchase_orders/list.html", context)


def _order_or_404(db: Session, order_id: int) -> PurchaseOrder:
    order = db.get(PurchaseOrder, order_id)
    if order is None:
        raise HTTPException(404, "Orden de compra no encontrada")
    return order


def _form_page(
    request: Request,
    db: Session,
    user,
    form: OrderForm,
    order: PurchaseOrder | None = None,
    error: str | None = None,
    status_code: int = 200,
):
    linked = purchase_order_service.linked_count(db, order.id) if order else 0
    context = {
        "user": user,
        "form": form,
        "order": order,
        "linked": linked,
        "error": error,
        "item_labels": PURCHASE_ORDER_ITEM_LABELS,
        "required_keys": PURCHASE_ORDER_ITEM_KEYS,
        "date_keys": DATE_KEYS,
        "currency_key": PO_CURRENCY,
        "action": f"/purchase-orders/{order.id}/edit" if order else "/purchase-orders/new",
        **purchase_order_service.form_options(db, form),
    }
    return templates.TemplateResponse(request, "purchase_orders/form.html", context, status_code=status_code)


def _duplicate(exc: IntegrityError, form: OrderForm) -> str:
    if not violates(exc, UNIQUE_CONVENIO):
        raise exc
    return MSG_DUPLICATE.format(convenio=form.convenio)


@router.get("/new")
def new_purchase_order(request: Request, db: Session = Depends(get_db), user=Depends(reviewers_only)):
    return _form_page(request, db, user, OrderForm.blank())


@router.post("/new")
async def create_purchase_order(request: Request, db: Session = Depends(get_db), user=Depends(reviewers_only)):
    await validate_csrf(request)
    form = OrderForm.from_form(await request.form())
    try:
        order = purchase_order_service.create_from_form(db, form, user.id)
        db.commit()
    except InvalidInputError as exc:
        db.rollback()
        return _form_page(request, db, user, form, error=exc.message, status_code=400)
    except IntegrityError as exc:
        db.rollback()
        return _form_page(request, db, user, form, error=_duplicate(exc, form), status_code=400)
    return RedirectResponse(f"/purchase-orders/{order.id}?notice=created", status_code=303)


@router.get("/{order_id}/edit")
def edit_purchase_order(order_id: int, request: Request, db: Session = Depends(get_db), user=Depends(reviewers_only)):
    order = _order_or_404(db, order_id)
    return _form_page(request, db, user, OrderForm.from_order(db, order), order)


@router.post("/{order_id}/edit")
async def update_purchase_order(
    order_id: int, request: Request, db: Session = Depends(get_db), user=Depends(reviewers_only)
):
    await validate_csrf(request)
    order = _order_or_404(db, order_id)
    form = OrderForm.from_form(await request.form())
    try:
        changed = purchase_order_service.update_from_form(db, order, form, user.id)
        db.commit()
    except InvalidInputError as exc:
        db.rollback()
        return _form_page(request, db, user, form, _order_or_404(db, order_id), exc.message, 400)
    except IntegrityError as exc:
        db.rollback()
        return _form_page(request, db, user, form, _order_or_404(db, order_id), _duplicate(exc, form), 400)
    notice = "updated" if changed else "unchanged"
    return RedirectResponse(f"/purchase-orders/{order.id}?notice={notice}", status_code=303)


@router.get("/{order_id}")
def purchase_order_detail(
    order_id: int, request: Request, notice: str = "", db: Session = Depends(get_db), user=Depends(reviewers_only)
):
    order = _order_or_404(db, order_id)
    context = {
        "user": user,
        "order": order,
        "items": order_items(order.data),
        "item_labels": PURCHASE_ORDER_ITEM_LABELS,
        "invoices": purchase_order_service.linked_invoices(db, order.id),
        "notice": NOTICES.get(notice),
    }
    return templates.TemplateResponse(request, "purchase_orders/detail.html", context)
