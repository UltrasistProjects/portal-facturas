from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field


class InvoiceCreate(BaseModel):
    invoice_number: str = Field(min_length=1, max_length=100)
    service_period: str = Field(pattern=r"^(0[1-9]|1[0-2])/\d{4}$")
    project_name: str = Field(min_length=2, max_length=200)
    purchase_order_number: str | None = None
    project_leader: str | None = None
    subtotal: Decimal = Decimal("0")
    tax: Decimal = Decimal("0")
    total: Decimal = Decimal("0")
    currency: str = "MXN"
    model_config = ConfigDict(str_strip_whitespace=True)


class ValidationOutcome(BaseModel):
    rule_code: str
    category: str
    status: str
    severity: str
    expected_value: str | None = None
    detected_value: str | None = None
    confidence: Decimal | None = None
    message: str
    source_document: str | None = None
    source_reference: str | None = None
    evidence: dict = Field(default_factory=dict)
