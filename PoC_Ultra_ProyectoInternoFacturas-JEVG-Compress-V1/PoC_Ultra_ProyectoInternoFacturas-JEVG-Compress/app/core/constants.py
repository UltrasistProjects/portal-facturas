from datetime import timedelta
from enum import StrEnum


class Role(StrEnum):
    # Nombres del negocio (ERS): el valor es el que se guarda en users.role y el que se muestra.
    ADMINISTRADOR = "Administrador"
    PROVEEDOR = "Proveedor"
    PMO = "PMO"


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
# Identificador fiscal del proveedor internacional, ya en mayusculas: la misma regla que la carga masiva (HU-01).
FOREIGN_TAX_ID_FORMAT = r"[A-Z0-9 ./-]{1,40}"
FOREIGN_TAX_ID_FORMAT_MESSAGE = "use hasta 40 caracteres: letras, digitos, espacios, puntos, guiones o diagonales"


SUPPLIER_ORIGIN_LABELS = {SupplierOrigin.NATIONAL: "Nacional", SupplierOrigin.INTERNATIONAL: "Internacional"}


class RequirementProfile(StrEnum):
    """Tipo de proveedor para los requisitos de alta (HU-21): el internacional es un tipo propio, sin importar su tipo
    de persona; el nacional se distingue por persona moral o fisica. El valor es la clave del perfil en los campos de
    la matriz y en la auditoria."""

    PERSONA_MORAL = "persona_moral"
    PERSONA_FISICA = "persona_fisica"
    INTERNATIONAL = "international"


REQUIREMENT_PROFILE_LABELS = {
    RequirementProfile.PERSONA_MORAL: "Persona moral",
    RequirementProfile.PERSONA_FISICA: "Persona física",
    RequirementProfile.INTERNATIONAL: "Internacional",
}
REQUIREMENT_PROFILE_PLURALS = {
    RequirementProfile.PERSONA_MORAL: "personas morales",
    RequirementProfile.PERSONA_FISICA: "personas físicas",
    RequirementProfile.INTERNATIONAL: "proveedores internacionales",
}


class ContractStatus(StrEnum):
    # El alta crea el contrato Registrado; solo la activacion, con sus requisitos completos, lo pasa a Activo (HU-22).
    REGISTERED = "REGISTERED"
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


CONTRACT_STATUS_LABELS = {
    ContractStatus.REGISTERED: "Registrado",
    ContractStatus.ACTIVE: "Activo",
    ContractStatus.INACTIVE: "Inactivo",
}


class ProcessingStatus(StrEnum):
    PENDING = "PENDING"
    PROCESSED = "PROCESSED"
    FAILED = "FAILED"


class InvoiceStatus(StrEnum):
    """Modelo de estatus del ERS (EP-01, DT-01). Se conservan las claves que ya significaban lo mismo; cambia la
    etiqueta. Los pasos de ClickBalance del PoC se retiraron con HU-20: Autorizada y Rechazada solo admiten la
    cancelacion del proveedor (HU-14), y Cancelada es final."""

    DRAFT = "DRAFT"
    UPLOADED = "UPLOADED"
    UNDER_REVIEW = "UNDER_REVIEW"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    REQUIRES_CORRECTION = "REQUIRES_CORRECTION"
    CANCELLED = "CANCELLED"


STATUS_LABELS = {
    InvoiceStatus.DRAFT: "Borrador",
    InvoiceStatus.UPLOADED: "Cargada",
    InvoiceStatus.UNDER_REVIEW: "Enviada",
    InvoiceStatus.ACCEPTED: "Autorizada",
    InvoiceStatus.REJECTED: "Rechazada",
    InvoiceStatus.REQUIRES_CORRECTION: "Observaciones",
    InvoiceStatus.CANCELLED: "Cancelada",
}

# Plazo que tiene Recepcion de Facturas para aceptar ante el SAT la cancelacion del CFDI (HU-14): horas naturales
# desde la cancelacion en el portal.
CANCELLATION_WINDOW = timedelta(hours=72)


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
    # Se carga solo al cancelar la factura (HU-14): "No aplica" fijo para ambos origenes.
    CANCELLATION_ACK = "CANCELLATION_ACK"


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

# Niveles que el Administrador no puede cambiar (RD-04): el nacional factura con CFDI, el internacional con Invoice;
# el acuse de cancelacion no se pide en la carga documental (HU-14).
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
    DocumentType.CANCELLATION_ACK: {
        SupplierOrigin.NATIONAL: DocumentRequirement.NOT_APPLICABLE,
        SupplierOrigin.INTERNATIONAL: DocumentRequirement.NOT_APPLICABLE,
    },
}
FIXED_REQUIREMENT_REASONS = {
    DocumentType.INVOICE_XML: "El proveedor nacional factura con CFDI",
    DocumentType.INVOICE_PDF: "El proveedor nacional factura con CFDI",
    DocumentType.FOREIGN_INVOICE: "El proveedor internacional factura con Invoice",
    DocumentType.CANCELLATION_ACK: "Se carga al cancelar la factura",
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


class ReviewDecision(StrEnum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    REQUIRES_CORRECTION = "REQUIRES_CORRECTION"
    COMMENT = "COMMENT"


# DRAFT <-> UPLOADED lo asigna el sistema segun los archivos obligatorios; UNDER_REVIEW, un envio que procede;
# REQUIRES_CORRECTION ("Observaciones"), solo la decision del PMO. El proveedor cancela desde cualquier estatus
# distinto de CANCELLED (HU-14, EP-01 P-05); CANCELLED no tiene salidas.
ALLOWED_TRANSITIONS: dict[InvoiceStatus, set[InvoiceStatus]] = {
    InvoiceStatus.DRAFT: {InvoiceStatus.UPLOADED, InvoiceStatus.CANCELLED},
    InvoiceStatus.UPLOADED: {InvoiceStatus.DRAFT, InvoiceStatus.UNDER_REVIEW, InvoiceStatus.CANCELLED},
    InvoiceStatus.REQUIRES_CORRECTION: {InvoiceStatus.UNDER_REVIEW, InvoiceStatus.CANCELLED},
    InvoiceStatus.UNDER_REVIEW: {
        InvoiceStatus.ACCEPTED,
        InvoiceStatus.REJECTED,
        InvoiceStatus.REQUIRES_CORRECTION,
        InvoiceStatus.CANCELLED,
    },
    InvoiceStatus.ACCEPTED: {InvoiceStatus.CANCELLED},
    InvoiceStatus.REJECTED: {InvoiceStatus.CANCELLED},
}


# Pesos del score por severidad. Los datos de ULTRASIST y los parametros del CFDI viven en la configuracion de Reglas
# de Validacion (tabla validation_settings, HU-06); las monedas aceptadas, en el catalogo de monedas (HU-07).
BUSINESS_RULES = {
    "score_weights": {Severity.CRITICAL: 35, Severity.ERROR: 18, Severity.WARNING: 6, Severity.INFO: 0},
}


# Requisitos de alta del proveedor (HU-21): el catalogo, sus nombres y sus niveles viven en supplier_document_types.
# Aqui quedan las reglas por clave que no se configuran. La propuesta economica es exigible si el alta responde a una
# cotizacion o licitacion (Supplier.economic_proposal) y su nivel no es "No aplica".
QUOTATION_DOCUMENT = "ECONOMIC_PROPOSAL"
# Documentos con vigencia: advertencia (SUP-004) si su fecha tiene mas de tres meses; no impiden la autorizacion.
DATED_SUPPLIER_DOCUMENTS = {"TAX_STATUS", "SAT_OPINION", "ADDRESS_PROOF", "LEGAL_REP_ADDRESS_PROOF", "BANK_STATEMENT"}
# El contrato firmado se carga en cada contrato (HU-22): en el expediente del proveedor queda fijo en "No aplica".
# Clave -> {perfil: nivel}. La base de datos lo garantiza con ck_supplier_document_types_fixed_levels.
SUPPLIER_CONTRACT_DOCUMENT = "SUPPLIER_CONTRACT"
FIXED_SUPPLIER_REQUIREMENTS: dict[str, dict[RequirementProfile, DocumentRequirement]] = {
    SUPPLIER_CONTRACT_DOCUMENT: {profile: DocumentRequirement.NOT_APPLICABLE for profile in RequirementProfile},
}
FIXED_SUPPLIER_REQUIREMENT_REASONS = {SUPPLIER_CONTRACT_DOCUMENT: "Se carga en cada contrato"}


# Requisitos de alta del contrato (HU-22): el catalogo vive en contract_document_types. El contrato firmado es
# Obligatorio fijo; la base de datos lo garantiza con ck_contract_document_types_fixed_levels.
SIGNED_CONTRACT_DOCUMENT = "SIGNED_CONTRACT"
FIXED_CONTRACT_REQUIREMENTS = {SIGNED_CONTRACT_DOCUMENT: DocumentRequirement.REQUIRED}
FIXED_CONTRACT_REQUIREMENT_REASONS = {SIGNED_CONTRACT_DOCUMENT: "Todo contrato activo tiene su contrato firmado"}


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
