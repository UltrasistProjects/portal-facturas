from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, contains_eager, selectinload

from app.core.constants import Role
from app.core.database import get_db
from app.core.security import require_roles, validate_csrf
from app.models import Contract, ContractAmendment, Supplier
from app.repositories.pagination import back_to, list_query, paginate, search
from app.routers.common import templates
from app.schemas import ContractAmendmentCreate, ContractCreate, validation_message
from app.services.audit_service import audit
from app.services.contract_service import amend_authorized_amount

router = APIRouter(prefix="/contracts")


CONTRACTS_URL = "/contracts"
CONTRACT_NOTICES = {"created": "Contrato creado"}


@router.get("")
def list_contracts(
    request: Request,
    q: str = "",
    page: int = 1,
    ok: str = "",
    db: Session = Depends(get_db),
    user=Depends(require_roles(Role.INTERNAL, Role.ADMIN)),
):
    return _contracts_page(request, db, user, q=q, page=page, notice=CONTRACT_NOTICES.get(ok))


def _contracts_page(
    request: Request,
    db: Session,
    user,
    error: str | None = None,
    status_code: int = 200,
    q: str = "",
    page: int = 1,
    notice: str | None = None,
):
    # Del mas reciente al mas antiguo, con busqueda y paginacion en SQL (listados-paginados). El proveedor llega en
    # el mismo JOIN de la busqueda; las enmiendas de la pagina, en una consulta.
    q = q.strip()
    stmt = (
        select(Contract)
        .join(Contract.supplier)
        .options(
            contains_eager(Contract.supplier),
            selectinload(Contract.amendments).selectinload(ContractAmendment.author),
        )
        .order_by(Contract.id.desc())
    )
    result = paginate(db, search(stmt, q, Contract.project_name, Supplier.business_name), page)
    context = {
        "user": user,
        "contracts": result.items,
        "page": result,
        "q": q,
        "base_query": list_query(q=q),
        "notice": notice,
        "suppliers": list(db.scalars(select(Supplier).order_by(Supplier.business_name))),
        "error": error,
    }
    return templates.TemplateResponse(request, "contracts/list.html", context, status_code=status_code)


@router.post("")
async def create_contract(
    request: Request,
    supplier_id: int = Form(...),
    project_name: str = Form(...),
    project_leader: str = Form(...),
    authorized_technology: str = Form(...),
    authorized_amount: str = Form(...),
    currency: str = Form("MXN"),
    start_date: str = Form(...),
    end_date: str = Form(...),
    db: Session = Depends(get_db),
    user=Depends(require_roles(Role.ADMIN)),
):
    await validate_csrf(request)
    try:
        data = ContractCreate(
            supplier_id=supplier_id,
            project_name=project_name,
            project_leader=project_leader,
            authorized_technology=authorized_technology,
            authorized_amount=authorized_amount,
            currency=currency,
            start_date=start_date,
            end_date=end_date,
        )
    except ValidationError as exc:
        return _contracts_page(request, db, user, validation_message(exc), 400)
    if db.get(Supplier, data.supplier_id) is None:
        return _contracts_page(request, db, user, "Proveedor inexistente.", 400)
    contract = Contract(**data.model_dump(), created_by=user.id, updated_by=user.id)
    db.add(contract)
    db.flush()
    audit(db, "CONTRACT_CREATED", "Contract", contract.id, user.id)
    db.commit()
    # El alta regresa a la lista buscando el proyecto creado, con el aviso (listados-paginados).
    return RedirectResponse(f"{CONTRACTS_URL}?{list_query(q=contract.project_name, ok='created')}", status_code=303)


@router.post("/{contract_id}/amendments")
async def amend_contract(
    contract_id: int,
    request: Request,
    new_amount: str = Form(...),
    reason: str = Form(""),
    db: Session = Depends(get_db),
    user=Depends(require_roles(Role.ADMIN)),
):
    await validate_csrf(request)
    contract = db.get(Contract, contract_id)
    if contract is None:
        raise HTTPException(404, "Contrato no encontrado")
    try:
        data = ContractAmendmentCreate(new_amount=new_amount, reason=reason)
    except ValidationError as exc:
        return _contracts_page(request, db, user, validation_message(exc), 400)
    amend_authorized_amount(db, contract, data.new_amount, data.reason, user.id)
    db.commit()
    return RedirectResponse(back_to(CONTRACTS_URL, await request.form()), status_code=303)
