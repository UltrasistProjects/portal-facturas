"""Alta de contratos y cambios del monto autorizado. No hace commit.

El monto autorizado es el techo contra el que FIN-001 aprueba o bloquea facturas: solo cambia mediante una enmienda
registrada y auditada (AUDITORIA BD-09). La moneda es una clave activa del catalogo de monedas, tambien en una peticion
directa (ajustes-finales-configuracion)."""

from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.constants import CatalogType, ContractStatus
from app.core.errors import InvalidInputError
from app.models import Contract, ContractAmendment, Supplier
from app.schemas import ContractCreate
from app.services import catalog_service
from app.services.audit_service import audit

MSG_SUPPLIER_NOT_FOUND = "Proveedor inexistente."


def create_contract(db: Session, data: ContractCreate, user_id: int) -> Contract:
    """Alta "Registrado": no se factura contra el contrato hasta activarlo con sus requisitos completos (HU-22)."""
    if db.get(Supplier, data.supplier_id) is None:
        raise InvalidInputError(MSG_SUPPLIER_NOT_FOUND)
    if data.currency not in catalog_service.active_codes(db, CatalogType.CURRENCY):
        raise InvalidInputError(catalog_service.MSG_INACTIVE_CURRENCY)
    contract = Contract(**data.model_dump(), status=ContractStatus.REGISTERED, created_by=user_id, updated_by=user_id)
    db.add(contract)
    db.flush()
    audit(db, "CONTRACT_CREATED", "Contract", contract.id, user_id)
    return contract


def amend_authorized_amount(
    db: Session, contract: Contract, new_amount: Decimal, reason: str, user_id: int
) -> ContractAmendment:
    previous = contract.authorized_amount
    amendment = ContractAmendment(
        contract_id=contract.id, previous_amount=previous, new_amount=new_amount, reason=reason, created_by=user_id
    )
    db.add(amendment)
    contract.authorized_amount = new_amount
    contract.updated_by = user_id
    db.flush()
    audit(
        db,
        "CONTRACT_AMOUNT_CHANGED",
        "Contract",
        contract.id,
        user_id,
        old={"authorized_amount": f"{previous:.2f}"},
        new={"authorized_amount": f"{new_amount:.2f}", "amendment_id": amendment.id, "reason": reason},
    )
    return amendment


def current_amendment_id(contract) -> int | None:
    """Enmienda vigente (la ultima) o None si rige el monto original."""
    amendments = getattr(contract, "amendments", None) or []
    return max((amendment.id for amendment in amendments), default=None)
