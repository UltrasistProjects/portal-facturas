from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Reconciliation:
    authorized_amount: Decimal
    invoiced_subtotal: Decimal
    difference: Decimal
    percentage: Decimal
    result: str


def reconcile_amount(authorized: Decimal, invoiced: Decimal) -> Reconciliation:
    difference = invoiced - authorized
    percentage = (difference / authorized * Decimal("100")) if authorized else Decimal("0")
    return Reconciliation(
        authorized, invoiced, difference, percentage.quantize(Decimal("0.01")), "PASS" if difference <= 0 else "FAIL"
    )
