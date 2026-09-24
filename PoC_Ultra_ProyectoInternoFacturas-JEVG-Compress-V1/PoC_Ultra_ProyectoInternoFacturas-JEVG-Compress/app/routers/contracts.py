from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import Role
from app.core.database import get_db
from app.core.security import require_roles, validate_csrf
from app.models import Contract, Supplier
from app.routers.common import templates
from app.schemas import ContractCreate, validation_message
from app.services.audit_service import audit

router = APIRouter(prefix="/contracts")


@router.get("")
def list_contracts(
    request: Request, db: Session = Depends(get_db), user=Depends(require_roles(Role.INTERNAL, Role.ADMIN))
):
    return _contracts_page(request, db, user)


def _contracts_page(request: Request, db: Session, user, error: str | None = None, status_code: int = 200):
    context = {
        "user": user,
        "contracts": list(db.scalars(select(Contract))),
        "suppliers": list(db.scalars(select(Supplier))),
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
    contract = Contract(**data.model_dump())
    db.add(contract)
    db.flush()
    audit(db, "CONTRACT_CREATED", "Contract", contract.id, user.id)
    db.commit()
    return RedirectResponse("/contracts", status_code=303)
