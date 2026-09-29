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


class SupplierClassification(StrEnum):
    INTERNAL = "INTERNAL"
    EXTERNAL = "EXTERNAL"


SUPPLIER_CLASSIFICATION_LABELS = {
    SupplierClassification.INTERNAL: "Interno",
    SupplierClassification.EXTERNAL: "Externo",
}

# Telefono del proveedor, de su contacto y de su representante legal: la misma regla que la carga masiva (HU-01).
PHONE_FORMAT = r"[0-9+() -]{7,30}"
PHONE_FORMAT_MESSAGE = "debe tener de 7 a 30 caracteres: digitos, espacios, +, (, ) o -"


SUPPLIER_ORIGIN_LABELS = {SupplierOrigin.NATIONAL: "Nacional", SupplierOrigin.INTERNATIONAL: "Internacional"}


class ContractStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class ProcessingStatus(StrEnum):
    PENDING = "PENDING"
    PROCESSED = "PROCESSED"
    FAILED = "FAILED"


class InvoiceStatus(StrEnum):
    """Modelo de estatus del ERS (EP-01, DT-01). Se conservan las claves que ya significaban lo mismo; cambia la
    etiqueta. READY_FOR_CLICKBALANCE y UPLOADED_TO_CLICKBALANCE los resuelve HU-20."""

    DRAFT = "DRAFT"
    UPLOADED = "UPLOADED"
    UNDER_REVIEW = "UNDER_REVIEW"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    REQUIRES_CORRECTION = "REQUIRES_CORRECTION"
    READY_FOR_CLICKBALANCE = "READY_FOR_CLICKBALANCE"
    UPLOADED_TO_CLICKBALANCE = "UPLOADED_TO_CLICKBALANCE"


STATUS_LABELS = {
    InvoiceStatus.DRAFT: "Borrador",
    InvoiceStatus.UPLOADED: "Cargada",
    InvoiceStatus.UNDER_REVIEW: "Enviada",
    InvoiceStatus.ACCEPTED: "Autorizada",
    InvoiceStatus.REJECTED: "Rechazada",
    InvoiceStatus.REQUIRES_CORRECTION: "Observaciones",
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


# DRAFT <-> UPLOADED lo asigna el sistema segun los archivos obligatorios; UNDER_REVIEW, un envio que procede;
# REQUIRES_CORRECTION ("Observaciones"), solo la decision del PMO.
ALLOWED_TRANSITIONS: dict[InvoiceStatus, set[InvoiceStatus]] = {
    InvoiceStatus.DRAFT: {InvoiceStatus.UPLOADED},
    InvoiceStatus.UPLOADED: {InvoiceStatus.DRAFT, InvoiceStatus.UNDER_REVIEW},
    InvoiceStatus.REQUIRES_CORRECTION: {InvoiceStatus.UNDER_REVIEW},
    InvoiceStatus.UNDER_REVIEW: {InvoiceStatus.ACCEPTED, InvoiceStatus.REJECTED, InvoiceStatus.REQUIRES_CORRECTION},
    InvoiceStatus.ACCEPTED: {InvoiceStatus.READY_FOR_CLICKBALANCE},
    InvoiceStatus.READY_FOR_CLICKBALANCE: {InvoiceStatus.UPLOADED_TO_CLICKBALANCE},
}


# Pesos del score por severidad. Los datos de ULTRASIST y los parametros del CFDI viven en la configuracion de Reglas
# de Validacion (tabla validation_settings, HU-06); las monedas aceptadas, en el catalogo de monedas (HU-07).
BUSINESS_RULES = {
    "score_weights": {Severity.CRITICAL: 35, Severity.ERROR: 18, Severity.WARNING: 6, Severity.INFO: 0},
}


# Expediente del proveedor (Anexo A) por tipo de persona: los documentos que se pueden cargar. Cuentan para el
# expediente minimo (SUP-003) salvo los opcionales y la propuesta economica sin cotizacion; los comprobantes de
# domicilio alternativos cuentan como uno.
SUPPLIER_REQUIREMENTS = {
    SupplierType.PERSONA_MORAL: [
        "DUE_DILIGENCE",
        "INCORPORATION_ACT",
        "LEGAL_REP_ID",
        "LEGAL_REP_ADDRESS_PROOF",
        "TAX_STATUS",
        "SAT_OPINION",
        "ADDRESS_PROOF",
        "LOCATION",
        "BANK_STATEMENT",
        "ECONOMIC_PROPOSAL",
        "SUPPLIER_CONTRACT",
    ],
    SupplierType.PERSONA_FISICA: [
        "OFFICIAL_ID",
        "TAX_STATUS",
        "SAT_OPINION",
        "ADDRESS_PROOF",
        "LOCATION",
        "BANK_STATEMENT",
        "ECONOMIC_PROPOSAL",
        "SUPPLIER_CONTRACT",
    ],
}
SUPPLIER_DOCUMENT_LABELS = {
    "DUE_DILIGENCE": "Debida diligencia",
    "INCORPORATION_ACT": "Acta constitutiva",
    "LEGAL_REP_ID": "Identificación del representante legal",
    "LEGAL_REP_ADDRESS_PROOF": "Comprobante de domicilio del representante legal",
    "OFFICIAL_ID": "Identificación oficial",
    "TAX_STATUS": "Cédula fiscal",
    "SAT_OPINION": "Opinión de cumplimiento",
    "ADDRESS_PROOF": "Comprobante de domicilio",
    "LOCATION": "Ubicación",
    "BANK_STATEMENT": "Estado de cuenta bancario",
    "ECONOMIC_PROPOSAL": "Propuesta económica",
    "SUPPLIER_CONTRACT": "Contrato",
}
# Dependen de la etapa del proceso (el contrato formaliza el expediente completo) o del nivel de riesgo.
OPTIONAL_SUPPLIER_DOCUMENTS = {"SUPPLIER_CONTRACT", "DUE_DILIGENCE", "LOCATION"}
# Obligatoria solo si el alta responde a una cotizacion o licitacion (Supplier.economic_proposal).
QUOTATION_DOCUMENT = "ECONOMIC_PROPOSAL"
# Requisitos que se cumplen con cualquiera de los dos documentos: el domicilio de la empresa o el del representante.
ALTERNATIVE_SUPPLIER_DOCUMENTS = {
    "ADDRESS_PROOF": "LEGAL_REP_ADDRESS_PROOF",
    "LEGAL_REP_ADDRESS_PROOF": "ADDRESS_PROOF",
}
# Documentos con vigencia: advertencia (SUP-004) si su fecha tiene mas de tres meses.
DATED_SUPPLIER_DOCUMENTS = {"TAX_STATUS", "SAT_OPINION", "ADDRESS_PROOF", "LEGAL_REP_ADDRESS_PROOF", "BANK_STATEMENT"}


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


class CatalogType(StrEnum):
    """Catalogos de referencia administrables (HU-07). Las claves del SAT las usan las Reglas de Validacion (HU-06);
    las actividades economicas (sectores del SCIAN), la actividad principal del proveedor."""

    CURRENCY = "CURRENCY"
    CFDI_USE = "CFDI_USE"
    PAYMENT_FORM = "PAYMENT_FORM"
    PAYMENT_METHOD = "PAYMENT_METHOD"
    TAX_REGIME = "TAX_REGIME"
    INDUSTRY = "INDUSTRY"


CATALOG_LABELS = {
    CatalogType.CURRENCY: "Monedas",
    CatalogType.CFDI_USE: "Usos de CFDI",
    CatalogType.PAYMENT_FORM: "Formas de pago",
    CatalogType.PAYMENT_METHOD: "Métodos de pago",
    CatalogType.TAX_REGIME: "Regímenes fiscales",
    CatalogType.INDUSTRY: "Actividades económicas",
}
# Formato de la clave por catalogo (claves del SAT y del SCIAN) y su descripcion para los mensajes de error.
CATALOG_CODE_FORMATS = {
    CatalogType.CURRENCY: (r"[A-Z]{3}", "debe tener tres letras"),
    CatalogType.CFDI_USE: (r"[A-Z]{1,2}[0-9]{2}", "debe tener una o dos letras seguidas de dos dígitos"),
    CatalogType.PAYMENT_FORM: (r"[0-9]{2}", "debe tener dos dígitos"),
    CatalogType.PAYMENT_METHOD: (r"[A-Z]{3}", "debe tener tres letras"),
    CatalogType.TAX_REGIME: (r"[0-9]{3}", "debe tener tres dígitos"),
    CatalogType.INDUSTRY: (r"[0-9]{2,6}", "debe tener de 2 a 6 dígitos (clave del SCIAN)"),
}
