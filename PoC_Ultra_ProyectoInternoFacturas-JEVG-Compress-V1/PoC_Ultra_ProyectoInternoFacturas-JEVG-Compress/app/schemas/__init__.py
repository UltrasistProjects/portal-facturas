import re
from datetime import date, datetime, timezone
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
    FOREIGN_TAX_ID_FORMAT,
    FOREIGN_TAX_ID_FORMAT_MESSAGE,
    FORMAT_EXTENSIONS,
    PHONE_FORMAT,
    PHONE_FORMAT_MESSAGE,
    DocumentRequirement,
    Role,
    SupplierClassification,
    SupplierOrigin,
    SupplierType,
)
from app.core.countries import COUNTRIES
from app.core.timeutils import to_business
from app.core.types import to_money

MIN_INCORPORATION_DATE = date(1900, 1, 1)
FIELD_LABELS = {
    "name": "Nombre",
    "email": "Correo",
    "password": "Contrasena",
    "business_name": "Razon social",
    "origin": "Origen",
    "rfc": "RFC",
    "foreign_tax_id": "Identificador fiscal extranjero",
    "country": "Pais",
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
    "invoice_date": "Fecha de la factura",
    "subtotal": "Subtotal",
    "tax": "Impuestos",
    "total": "Total",
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
    "decimal_max_digits": "es demasiado grande",
    "decimal_parsing": "no es un importe valido",
    "finite_number": "no es un importe valido",
    "greater_than_equal": "no puede ser negativo",
    "date_parsing": "no es una fecha valida",
    "date_from_datetime_parsing": "no es una fecha valida",
    "enum": "no es una opcion valida",
}


def validation_message(exc: ValidationError) -> str:
    """Mensaje en espanol para mostrar en el formulario."""
    return " ".join(validation_messages(exc))


def validation_messages(exc: ValidationError) -> list[str]:
    """Un mensaje "<Campo>: <detalle>" por error, para listarlos juntos."""
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
    return messages


class UserCreate(BaseModel):
    """Alta en /admin/users. Sin contrasena: el usuario se crea en Keycloak con una temporal
    (add-keycloak-authentication, D15)."""

    name: str = Field(min_length=2, max_length=150)
    email: EmailStr
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
    """Alta individual. El origen decide la identidad fiscal, con las reglas de la carga masiva (HU-01): el nacional
    se identifica por RFC y su pais es MX; el internacional, por pais distinto de MX e identificador fiscal
    extranjero, sin RFC. `origin` va antes que los campos que valida."""

    origin: SupplierOrigin = SupplierOrigin.NATIONAL
    rfc: str | None = Field(None, min_length=12, max_length=13, validate_default=True)
    foreign_tax_id: str | None = Field(None, validate_default=True)
    country: str | None = Field(None, validate_default=True)
    email: EmailStr

    @field_validator("rfc")
    @classmethod
    def national_rfc(cls, value: str | None, info: ValidationInfo) -> str | None:
        origin = info.data.get("origin")
        if origin == SupplierOrigin.NATIONAL and value is None:
            raise ValueError("es obligatorio para proveedores nacionales")
        if origin == SupplierOrigin.INTERNATIONAL and value is not None:
            raise ValueError("debe quedar vacio para proveedores internacionales")
        return value.upper() if value else value

    @field_validator("foreign_tax_id")
    @classmethod
    def international_tax_id(cls, value: str | None, info: ValidationInfo) -> str | None:
        origin = info.data.get("origin")
        if origin == SupplierOrigin.NATIONAL and value is not None:
            raise ValueError("debe quedar vacio para proveedores nacionales")
        if origin == SupplierOrigin.INTERNATIONAL:
            if value is None:
                raise ValueError("es obligatorio para proveedores internacionales")
            # Espacios internos colapsados, como en la carga masiva: la unicidad compara el valor guardado.
            value = " ".join(value.split()).upper()
            if not re.fullmatch(FOREIGN_TAX_ID_FORMAT, value):
                raise ValueError(FOREIGN_TAX_ID_FORMAT_MESSAGE)
        return value

    @field_validator("country")
    @classmethod
    def origin_country(cls, value: str | None, info: ValidationInfo) -> str | None:
        origin = info.data.get("origin")
        value = value.upper() if value else value
        if origin == SupplierOrigin.NATIONAL:
            if value not in (None, "MX"):
                raise ValueError("debe quedar vacio o ser MX para proveedores nacionales")
            return "MX"
        if origin == SupplierOrigin.INTERNATIONAL:
            if value is None:
                raise ValueError("es obligatorio para proveedores internacionales")
            if value == "MX":
                raise ValueError("un proveedor internacional no puede tener pais MX")
            if value not in COUNTRIES:
                raise ValueError("use el codigo ISO de dos letras (p. ej. US)")
        return value

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


def _amount_text(value):
    """Importe capturado en un formulario: admite el separador de miles "," y el simbolo "$"."""
    if isinstance(value, str):
        value = value.replace("$", "").replace(",", "").strip()
        if not value:
            raise ValueError("es obligatorio")
    return value


class ForeignInvoiceData(BaseModel):
    """Datos del Invoice de un proveedor internacional (HU-15): sin XML, el proveedor los captura. Se guardan en las
    columnas de la factura que el XML llena para el proveedor nacional. El total no se captura: es subtotal +
    impuestos (ajustes-finales-configuracion)."""

    invoice_date: date
    subtotal: Decimal = Field(gt=0, max_digits=16, decimal_places=2)
    tax: Decimal = Field(ge=0, max_digits=16, decimal_places=2)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    model_config = ConfigDict(str_strip_whitespace=True)

    @field_validator("invoice_date", mode="before")
    @classmethod
    def date_required(cls, value):
        if value is None or (isinstance(value, str) and not value.strip()):
            raise ValueError("es obligatoria")
        return value

    @field_validator("invoice_date")
    @classmethod
    def not_future(cls, value: date) -> date:
        if value > to_business(datetime.now(timezone.utc)).date():
            raise ValueError("no puede ser posterior a hoy")
        return value

    @field_validator("subtotal", "tax", mode="before")
    @classmethod
    def amount_text(cls, value):
        return _amount_text(value)

    @field_validator("currency", mode="before")
    @classmethod
    def currency_upper(cls, value):
        return value.strip().upper() if isinstance(value, str) else value

    @property
    def total(self) -> Decimal:
        """Subtotal mas impuestos, calculado en el servidor: el total que envie el cliente se ignora."""
        return to_money(self.subtotal + self.tax)


INVALID_REQUIREMENT = "Nivel de exigencia inválido"


def parse_requirement(value) -> DocumentRequirement:
    """Nivel de exigencia recibido de un formulario; ValueError con el mensaje de la spec si no existe."""
    try:
        return DocumentRequirement(value)
    except ValueError:
        raise ValueError(INVALID_REQUIREMENT) from None


class NamedDocumentType(BaseModel):
    """Nombre y descripcion de un tipo de documento configurable: tipo soporte de factura (HU-04) o requisito de alta
    (HU-21). Los validadores emiten frases completas, que document_type_message muestra tal cual."""

    name: str
    description: str | None = None

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


class DocumentTypeUpdate(NamedDocumentType):
    """Campos editables de un tipo de documento soporte (HU-04)."""

    formats: list[str]

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


class SupplierDocumentTypeUpdate(NamedDocumentType):
    """Campos editables de un requisito de alta del Administrador (HU-21): nombre y descripcion."""


class SupplierDocumentTypeCreate(SupplierDocumentTypeUpdate):
    # "No aplica" por defecto: crear un requisito no cambia nada hasta que el Administrador decida.
    persona_moral_requirement: DocumentRequirement = DocumentRequirement.NOT_APPLICABLE
    persona_fisica_requirement: DocumentRequirement = DocumentRequirement.NOT_APPLICABLE
    international_requirement: DocumentRequirement = DocumentRequirement.NOT_APPLICABLE

    @field_validator(
        "persona_moral_requirement", "persona_fisica_requirement", "international_requirement", mode="before"
    )
    @classmethod
    def known_requirement(cls, value):
        return parse_requirement(value)


class ContractDocumentTypeUpdate(NamedDocumentType):
    """Campos editables de un requisito del contrato del Administrador (HU-22): nombre y descripcion. Si admite
    varios archivos se fija al crearlo."""


class ContractDocumentTypeCreate(ContractDocumentTypeUpdate):
    # "No aplica" y un solo archivo por defecto: crear un requisito no cambia nada hasta que el Administrador decida.
    requirement: DocumentRequirement = DocumentRequirement.NOT_APPLICABLE
    allows_multiple: bool = False

    @field_validator("requirement", mode="before")
    @classmethod
    def known_requirement(cls, value):
        return parse_requirement(value)


def document_type_message(exc: ValidationError) -> str:
    """Mensajes de los tipos de documento soporte y de los requisitos de alta y del contrato: frases completas, sin
    prefijo de campo."""
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
