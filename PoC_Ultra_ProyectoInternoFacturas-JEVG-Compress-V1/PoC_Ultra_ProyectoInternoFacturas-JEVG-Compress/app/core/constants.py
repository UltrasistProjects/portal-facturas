from enum import StrEnum


class Role(StrEnum):
    PROVIDER = "PROVIDER"
    INTERNAL = "INTERNAL"
    ADMIN = "ADMIN"


class SupplierType(StrEnum):
    PERSONA_FISICA = "PERSONA_FISICA"
    PERSONA_MORAL = "PERSONA_MORAL"


class SupplierStatus(StrEnum):
    # Alta (carga masiva o individual), aun sin acceso al portal: la autorizacion es posterior (HU-02).
    REGISTERED = "REGISTERED"
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


SUPPLIER_STATUS_LABELS = {
    SupplierStatus.REGISTERED: "Registrado",
    # "Autorizado" (HU-02): el estatus operativo que exige SUP-001; se llega a el autorizando un proveedor Registrado.
    SupplierStatus.ACTIVE: "Autorizado",
    SupplierStatus.INACTIVE: "Inactivo",
}


class SupplierOrigin(StrEnum):
    """Nacional: se identifica por RFC. Internacional: por pais + identificador fiscal extranjero."""

    NATIONAL = "NATIONAL"
    INTERNATIONAL = "INTERNATIONAL"


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
    """Claves de los tipos de documento de factura que usa el codigo. Nombres, formatos y niveles de exigencia
    viven en la tabla invoice_document_types (HU-04)."""

    INVOICE_XML = "INVOICE_XML"
    INVOICE_PDF = "INVOICE_PDF"
    FOREIGN_INVOICE = "FOREIGN_INVOICE"
    PURCHASE_ORDER = "PURCHASE_ORDER"
    APPROVAL = "APPROVAL"
    CONTRACT = "CONTRACT"
    CONTRACT_ANNEX = "CONTRACT_ANNEX"
    PAYMENT_COMPLEMENT_XML = "PAYMENT_COMPLEMENT_XML"
    PAYMENT_COMPLEMENT_PDF = "PAYMENT_COMPLEMENT_PDF"
    ADDITIONAL = "ADDITIONAL"


class DocumentRequirement(StrEnum):
    """Nivel de exigencia de un tipo de documento de factura para un origen de proveedor."""

    REQUIRED = "REQUIRED"
    OPTIONAL = "OPTIONAL"
    NOT_APPLICABLE = "NOT_APPLICABLE"


DOCUMENT_REQUIREMENT_LABELS = {
    DocumentRequirement.REQUIRED: "Obligatorio",
    DocumentRequirement.OPTIONAL: "Opcional",
    DocumentRequirement.NOT_APPLICABLE: "No aplica",
}

# Formato -> extensiones. La union coincide con ALLOWED_EXTENSIONS de file_service (lo verifica una prueba).
FORMAT_EXTENSIONS: dict[str, tuple[str, ...]] = {
    "PDF": (".pdf",),
    "PNG": (".png",),
    "JPEG": (".jpg", ".jpeg"),
    "XML": (".xml",),
    "TXT": (".txt",),
}

# Niveles que el Administrador no puede cambiar (RD-04): el nacional factura con CFDI, el internacional con Invoice.
# Clave -> {origen: nivel}. La base de datos los garantiza con ck_invoice_document_types_fixed_levels.
FIXED_REQUIREMENTS: dict[str, dict[SupplierOrigin, DocumentRequirement]] = {
    DocumentType.INVOICE_XML: {
        SupplierOrigin.NATIONAL: DocumentRequirement.REQUIRED,
        SupplierOrigin.INTERNATIONAL: DocumentRequirement.NOT_APPLICABLE,
    },
    DocumentType.INVOICE_PDF: {
        SupplierOrigin.NATIONAL: DocumentRequirement.REQUIRED,
        SupplierOrigin.INTERNATIONAL: DocumentRequirement.NOT_APPLICABLE,
    },
    DocumentType.FOREIGN_INVOICE: {
        SupplierOrigin.NATIONAL: DocumentRequirement.NOT_APPLICABLE,
        SupplierOrigin.INTERNATIONAL: DocumentRequirement.REQUIRED,
    },
}
FIXED_REQUIREMENT_REASONS = {
    DocumentType.INVOICE_XML: "El proveedor nacional factura con CFDI",
    DocumentType.INVOICE_PDF: "El proveedor nacional factura con CFDI",
    DocumentType.FOREIGN_INVOICE: "El proveedor internacional factura con Invoice",
}


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


class NotificationEvent(StrEnum):
    """Eventos con plantilla de correo (HU-05). Independientes de InvoiceStatus: HU-20 y HU-14 los disparan y hacen
    el mapeo desde sus estatus; HU-03 envia las credenciales del proveedor autorizado. Nombre, destinatario y
    variables viven en app/services/notification_templates.py."""

    INVOICE_AUTHORIZED = "INVOICE_AUTHORIZED"
    INVOICE_REJECTED = "INVOICE_REJECTED"
    INVOICE_OBSERVATIONS = "INVOICE_OBSERVATIONS"
    INVOICE_CANCELLED = "INVOICE_CANCELLED"
    SUPPLIER_CREDENTIALS = "SUPPLIER_CREDENTIALS"


class Mailbox(StrEnum):
    """Buzones de destino configurables por el Administrador (HU-08). Hoy solo Recepcion de Facturas."""

    INVOICE_RECEPTION = "INVOICE_RECEPTION"


MAILBOX_LABELS = {Mailbox.INVOICE_RECEPTION: "Recepción de Facturas"}


class DeliveryStatus(StrEnum):
    """Resultado de un intento de envio de correo registrado en la bitacora (HU-08)."""

    SENT = "SENT"
    FAILED = "FAILED"
