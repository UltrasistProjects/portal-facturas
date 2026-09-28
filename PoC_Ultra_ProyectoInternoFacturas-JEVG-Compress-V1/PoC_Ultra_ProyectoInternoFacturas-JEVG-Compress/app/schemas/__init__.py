import re
from datetime import date
from decimal import Decimal
from urllib.parse import urlsplit

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    ValidationError,
    ValidationInfo,
    field_validator,
    model_validator,
)

from app.core.constants import (
    FORMAT_EXTENSIONS,
    PHONE_FORMAT,
    PHONE_FORMAT_MESSAGE,
    DocumentRequirement,
    Role,
    SupplierClassification,
    SupplierType,
)
from app.core.passwords import validate_password

MIN_INCORPORATION_DATE = date(1900, 1, 1)
FIELD_LABELS = {
    "name": "Nombre",
    "email": "Correo",
    "password": "Contrasena",
    "business_name": "Razon social",
    "rfc": "RFC",
    "supplier_type": "Tipo de persona",
    "phone": "Telefono",
    "bank_information": "Informacion bancaria",
    "confidentiality_agreement": "Confidencialidad",
    "economic_proposal": "Alta por cotizacion o licitacion",
    "classification": "Clasificacion",
    "main_activity": "Actividad principal",
    "incorporation_date": "Fecha de constitucion",
    "website": "Pagina web",
    "legal_rep_name": "Nombre del representante legal",
    "legal_rep_phone": "Telefono del representante legal",
    "contact_name": "Nombre del contacto",
    "contact_phone": "Telefono del contacto",
    "invoice_number": "Numero de factura",
    "service_period": "Periodo de servicio (MM/AAAA)",
    "project_name": "Proyecto",
    "project_leader": "Lider de proyecto",
    "authorized_technology": "Tecnologia autorizada",
    "authorized_amount": "Monto autorizado",
    "currency": "Moneda",
    "end_date": "Vigencia",
    "new_amount": "Monto nuevo",
    "reason": "Motivo",
}
ERROR_MESSAGES = {
    "missing": "es obligatorio",
    "string_too_short": "es demasiado corto",
    "string_too_long": "es demasiado largo",
    "string_pattern_mismatch": "tiene un formato invalido",
    "greater_than": "debe ser mayor que cero",
    "decimal_max_places": "admite a lo sumo 2 decimales",
    "date_from_datetime_parsing": "no es una fecha valida",
    "enum": "no es una opcion valida",
}


def validation_message(exc: ValidationError) -> str:
    """Mensaje en espanol para mostrar en el formulario."""
    messages = []
    for error in exc.errors():
        field = str(error["loc"][0]) if error["loc"] else "end_date"
        label = FIELD_LABELS.get(field, field)
        if field == "email":
            detail = "no es un correo valido"
        elif error["type"] == "value_error":
            detail = str(error.get("ctx", {}).get("error", error["msg"]))
        else:
            detail = ERROR_MESSAGES.get(error["type"], "es invalido")
        messages.append(f"{label}: {detail}")
    return " ".join(messages)


class UserCreate(BaseModel):
    # Sin str_strip_whitespace a nivel de modelo: los espacios de la contrasena son significativos.
    name: str = Field(min_length=2, max_length=150)
    email: EmailStr
    password: str
    role: Role
    supplier_id: int | None = None

    @field_validator("name", mode="before")
    @classmethod
    def stripped(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("email", mode="before")
    @classmethod
    def normalized_email(cls, value):
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("password")
    @classmethod
    def password_policy(cls, value: str) -> str:
        return validate_password(value)


class SupplierProfile(BaseModel):
    """Datos del proveedor que capturan el alta individual y la edicion. La base de datos los admite vacios (proveedores
    previos y carga masiva); aqui se exigen los obligatorios. Los campos vacios del formulario no se envian: faltan, y
    una casilla sin marcar es falso. `supplier_type` va primero porque decide si aplica la fecha de constitucion; la
    edicion lo toma del proveedor. En persona fisica el representante legal puede ser la misma persona."""

    model_config = ConfigDict(str_strip_whitespace=True)
    supplier_type: SupplierType
    business_name: str = Field(min_length=2, max_length=250)
    phone: str
    classification: SupplierClassification
    main_activity: str = Field(max_length=10)
    incorporation_date: date | None = Field(None, validate_default=True)
    website: str | None = None
    legal_rep_name: str = Field(min_length=2, max_length=150)
    legal_rep_phone: str
    contact_name: str = Field(min_length=2, max_length=150)
    contact_phone: str
    # Opcional al registrar; el pago, que ocurre fuera del portal, la requiere.
    bank_information: str | None = Field(None, max_length=255)
    confidentiality_agreement: bool = False
    # Alta por cotizacion o licitacion: exige la propuesta economica en el expediente.
    economic_proposal: bool = False

    @field_validator("incorporation_date")
    @classmethod
    def legal_entity_date(cls, value: date | None, info: ValidationInfo) -> date | None:
        """Obligatoria para persona moral; no aplica a persona fisica, que no la guarda."""
        supplier_type = info.data.get("supplier_type")
        if supplier_type == SupplierType.PERSONA_FISICA:
            return None
        if value is None and supplier_type == SupplierType.PERSONA_MORAL:
            raise ValueError("es obligatorio para persona moral")
        if value and not MIN_INCORPORATION_DATE <= value <= date.today():
            raise ValueError("debe estar entre 1900 y hoy")
        return value

    @field_validator("website")
    @classmethod
    def http_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        url = value if "://" in value else f"https://{value}"
        try:
            parts = urlsplit(url)
            valid = parts.scheme.lower() in ("http", "https") and "." in (parts.hostname or "")
            parts.port  # ValueError si el puerto no es numerico o esta fuera de rango
        except ValueError:
            valid = False
        if not valid or len(url) > 255 or any(char.isspace() for char in url):
            raise ValueError("no es una direccion web valida (http o https, hasta 255 caracteres)")
        return url

    @field_validator("phone", "legal_rep_phone", "contact_phone")
    @classmethod
    def phone_format(cls, value: str) -> str:
        if not re.fullmatch(PHONE_FORMAT, value):
            raise ValueError(PHONE_FORMAT_MESSAGE)
        return value


class SupplierUpdate(SupplierProfile):
    """Edicion del Administrador. La identidad fiscal (origen, RFC, identificador extranjero, pais y tipo de persona)
    y el correo, que es el usuario del portal (HU-03), no se editan."""


class SupplierCreate(SupplierProfile):
    rfc: str = Field(min_length=12, max_length=13)
    email: EmailStr

    @field_validator("rfc")
    @classmethod
    def upper_rfc(cls, value: str) -> str:
        return value.upper()

    @field_validator("email", mode="before")
    @classmethod
    def normalized_email(cls, value):
        return value.strip().lower() if isinstance(value, str) else value


class ContractCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    supplier_id: int
    project_name: str = Field(min_length=2, max_length=200)
    project_leader: str = Field(min_length=2, max_length=150)
    authorized_technology: str = Field(min_length=2, max_length=250)
    authorized_amount: Decimal = Field(gt=0, decimal_places=2)
    currency: str = Field(pattern=r"^[A-Za-z]{3}$")
    start_date: date
    end_date: date

    @field_validator("currency")
    @classmethod
    def upper_currency(cls, value: str) -> str:
        return value.upper()

    @model_validator(mode="after")
    def valid_period(self):
        if self.end_date < self.start_date:
            raise ValueError("la fecha de fin no puede ser anterior a la de inicio")
        return self


class ContractAmendmentCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    new_amount: Decimal = Field(gt=0, decimal_places=2)
    reason: str = Field(min_length=3, max_length=500)


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


INVALID_REQUIREMENT = "Nivel de exigencia inválido"


def parse_requirement(value) -> DocumentRequirement:
    """Nivel de exigencia recibido de un formulario; ValueError con el mensaje de la spec si no existe."""
    try:
        return DocumentRequirement(value)
    except ValueError:
        raise ValueError(INVALID_REQUIREMENT) from None


class DocumentTypeUpdate(BaseModel):
    """Campos editables de un tipo de documento soporte (HU-04). Los validadores emiten frases completas, que
    document_type_message muestra tal cual."""

    name: str
    description: str | None = None
    formats: list[str]

    @field_validator("name", mode="before")
    @classmethod
    def normalized_name(cls, value):
        name = " ".join(str(value or "").split())
        if not 3 <= len(name) <= 80:
            raise ValueError("El nombre debe tener entre 3 y 80 caracteres")
        return name

    @field_validator("description", mode="before")
    @classmethod
    def optional_description(cls, value):
        description = str(value or "").strip()
        if len(description) > 300:
            raise ValueError("La descripción admite hasta 300 caracteres")
        return description or None

    @field_validator("formats", mode="before")
    @classmethod
    def known_formats(cls, value):
        formats = set(value or [])
        if not formats:
            raise ValueError("Seleccione al menos un formato")
        if not formats <= FORMAT_EXTENSIONS.keys():
            raise ValueError("Formato no válido")
        return [name for name in FORMAT_EXTENSIONS if name in formats]  # orden canonico


class DocumentTypeCreate(DocumentTypeUpdate):
    # "No aplica" por defecto: crear un tipo no cambia nada para los proveedores hasta que el Administrador decida.
    national_requirement: DocumentRequirement = DocumentRequirement.NOT_APPLICABLE
    international_requirement: DocumentRequirement = DocumentRequirement.NOT_APPLICABLE

    @field_validator("national_requirement", "international_requirement", mode="before")
    @classmethod
    def known_requirement(cls, value):
        return parse_requirement(value)


def document_type_message(exc: ValidationError) -> str:
    """Mensajes de los tipos de documento soporte: frases completas, sin prefijo de campo."""
    return " ".join(dict.fromkeys(str(error.get("ctx", {}).get("error", error["msg"])) for error in exc.errors()))


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
