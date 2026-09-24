from enum import StrEnum


class Role(StrEnum):
    PROVIDER = "PROVIDER"
    INTERNAL = "INTERNAL"
    ADMIN = "ADMIN"


class SupplierType(StrEnum):
    PERSONA_FISICA = "PERSONA_FISICA"
    PERSONA_MORAL = "PERSONA_MORAL"


class SupplierStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class ContractStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class ProcessingStatus(StrEnum):
    PENDING = "PENDING"
    PROCESSED = "PROCESSED"
    FAILED = "FAILED"


class InvoiceStatus(StrEnum):
    DRAFT = "DRAFT"
    UPLOADED = "UPLOADED"
    VALIDATING = "VALIDATING"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    REQUIRES_CORRECTION = "REQUIRES_CORRECTION"
    PREVALIDATED = "PREVALIDATED"
    UNDER_REVIEW = "UNDER_REVIEW"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    READY_FOR_CLICKBALANCE = "READY_FOR_CLICKBALANCE"
    UPLOADED_TO_CLICKBALANCE = "UPLOADED_TO_CLICKBALANCE"


STATUS_LABELS = {
    InvoiceStatus.DRAFT: "Borrador",
    InvoiceStatus.UPLOADED: "Cargada",
    InvoiceStatus.VALIDATING: "Validando",
    InvoiceStatus.VALIDATION_FAILED: "Validacion fallida",
    InvoiceStatus.REQUIRES_CORRECTION: "Requiere correccion",
    InvoiceStatus.PREVALIDATED: "Prevalidada",
    InvoiceStatus.UNDER_REVIEW: "En revision",
    InvoiceStatus.ACCEPTED: "Aceptada",
    InvoiceStatus.REJECTED: "Rechazada",
    InvoiceStatus.READY_FOR_CLICKBALANCE: "Lista para ClickBalance",
    InvoiceStatus.UPLOADED_TO_CLICKBALANCE: "Cargada a ClickBalance",
}


class DocumentType(StrEnum):
    INVOICE_XML = "INVOICE_XML"
    INVOICE_PDF = "INVOICE_PDF"
    PURCHASE_ORDER = "PURCHASE_ORDER"
    APPROVAL = "APPROVAL"
    CONTRACT = "CONTRACT"
    CONTRACT_ANNEX = "CONTRACT_ANNEX"
    PAYMENT_COMPLEMENT_XML = "PAYMENT_COMPLEMENT_XML"
    PAYMENT_COMPLEMENT_PDF = "PAYMENT_COMPLEMENT_PDF"
    ADDITIONAL = "ADDITIONAL"


class RuleStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    WARNING = "WARNING"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    NOT_EVALUATED = "NOT_EVALUATED"


class Severity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class LoginResult(StrEnum):
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    THROTTLED = "THROTTLED"


class ReviewDecision(StrEnum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    REQUIRES_CORRECTION = "REQUIRES_CORRECTION"
    COMMENT = "COMMENT"


ALLOWED_TRANSITIONS: dict[InvoiceStatus, set[InvoiceStatus]] = {
    InvoiceStatus.DRAFT: {InvoiceStatus.UPLOADED},
    InvoiceStatus.UPLOADED: {InvoiceStatus.VALIDATING},
    InvoiceStatus.VALIDATING: {
        InvoiceStatus.PREVALIDATED,
        InvoiceStatus.REQUIRES_CORRECTION,
        InvoiceStatus.VALIDATION_FAILED,
    },
    InvoiceStatus.VALIDATION_FAILED: {InvoiceStatus.VALIDATING},
    InvoiceStatus.REQUIRES_CORRECTION: {InvoiceStatus.UPLOADED, InvoiceStatus.VALIDATING},
    InvoiceStatus.PREVALIDATED: {InvoiceStatus.UNDER_REVIEW},
    InvoiceStatus.UNDER_REVIEW: {InvoiceStatus.ACCEPTED, InvoiceStatus.REJECTED, InvoiceStatus.REQUIRES_CORRECTION},
    InvoiceStatus.ACCEPTED: {InvoiceStatus.READY_FOR_CLICKBALANCE},
    InvoiceStatus.READY_FOR_CLICKBALANCE: {InvoiceStatus.UPLOADED_TO_CLICKBALANCE},
}


BUSINESS_RULES = {
    "receiver": {"business_name": "ULTRASIST", "rfc": "ULT940623AG0", "postal_code": "03930", "tax_regime": "601"},
    "payment_method": "PPD",
    "payment_form": "99",
    "allowed_cfdi_uses": ["G03", "I04"],
    "score_weights": {Severity.CRITICAL: 35, Severity.ERROR: 18, Severity.WARNING: 6, Severity.INFO: 0},
}


SUPPLIER_REQUIREMENTS = {
    SupplierType.PERSONA_MORAL: [
        "DUE_DILIGENCE",
        "INCORPORATION_ACT",
        "LEGAL_REP_ID",
        "TAX_STATUS",
        "SAT_OPINION",
        "ADDRESS_PROOF",
        "LOCATION",
        "BANK_STATEMENT",
        "ECONOMIC_PROPOSAL",
    ],
    SupplierType.PERSONA_FISICA: [
        "OFFICIAL_ID",
        "TAX_STATUS",
        "SAT_OPINION",
        "ADDRESS_PROOF",
        "LOCATION",
        "BANK_STATEMENT",
        "ECONOMIC_PROPOSAL",
    ],
}
