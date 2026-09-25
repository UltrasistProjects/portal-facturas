from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, ValidationError, field_validator, model_validator

from app.core.constants import FORMAT_EXTENSIONS, DocumentRequirement, Role, SupplierType
from app.core.passwords import validate_password

FIELD_LABELS = {
    "name": "Nombre",
    "email": "Correo",
    "password": "Contrasena",
    "business_name": "Razon social",
    "rfc": "RFC",
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


class SupplierCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    business_name: str = Field(min_length=2, max_length=250)
    rfc: str = Field(min_length=12, max_length=13)
    supplier_type: SupplierType
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
