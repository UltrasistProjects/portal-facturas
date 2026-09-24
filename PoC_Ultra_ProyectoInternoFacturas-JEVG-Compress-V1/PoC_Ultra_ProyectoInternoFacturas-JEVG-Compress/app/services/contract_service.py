"""El monto autorizado es el techo contra el que FIN-001 aprueba o bloquea facturas: solo cambia mediante una
enmienda registrada y auditada (AUDITORIA BD-09). No hace commit."""

from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import Contract, ContractAmendment
from app.services.audit_service import audit


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
