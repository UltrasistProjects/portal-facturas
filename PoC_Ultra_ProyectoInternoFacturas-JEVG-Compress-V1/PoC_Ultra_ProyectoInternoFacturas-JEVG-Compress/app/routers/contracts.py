from datetime import date
from decimal import Decimal
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.constants import Role
from app.core.database import get_db
from app.core.security import require_roles, validate_csrf
from app.models import Contract, Supplier
from app.routers.common import templates
from app.services.audit_service import audit

router = APIRouter(prefix="/contracts")


@router.get("")
def list_contracts(request: Request, db: Session = Depends(get_db), user=Depends(require_roles(Role.INTERNAL, Role.ADMIN))):
    return templates.TemplateResponse(request, "contracts/list.html", {"user": user, "contracts": list(db.scalars(select(Contract))), "suppliers": list(db.scalars(select(Supplier)))})


@router.post("")
async def create_contract(request: Request, supplier_id: int = Form(...), project_name: str = Form(...), project_leader: str = Form(...),
                          authorized_technology: str = Form(...), authorized_amount: Decimal = Form(...), currency: str = Form("MXN"),
                          start_date: date = Form(...), end_date: date = Form(...), db: Session = Depends(get_db), user=Depends(require_roles(Role.ADMIN))):
    await validate_csrf(request)
    contract = Contract(supplier_id=supplier_id, project_name=project_name, project_leader=project_leader,
        authorized_technology=authorized_technology, authorized_amount=authorized_amount, currency=currency.upper(), start_date=start_date, end_date=end_date)
    db.add(contract); db.flush(); audit(db, "CONTRACT_CREATED", "Contract", contract.id, user.id); db.commit()
    return RedirectResponse("/contracts", status_code=303)

