from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    event,
    false,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

from app.core.constants import (
    CatalogType,
    ContractStatus,
    DeliveryStatus,
    DocumentRequirement,
    InvoiceStatus,
    LoginResult,
    Mailbox,
    NotificationEvent,
    ProcessingStatus,
    ReviewDecision,
    Role,
    RuleStatus,
    Severity,
    SupplierOrigin,
    SupplierStatus,
    SupplierType,
)
from app.core.database import Base
from app.core.errors import BusinessRuleError
from app.core.types import ExactNumeric, Money, UTCDateTime


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def enum_column(enum: type[StrEnum], name: str | None = None) -> SAEnum:
    """Enumeracion como VARCHAR con CHECK: la BD rechaza valores fuera del catalogo (AUDITORIA BD-05). El CHECK
    se llama como la enumeracion; `name` lo cambia cuando dos columnas de una tabla usan la misma."""
    return SAEnum(enum, name=name, native_enum=False, create_constraint=True, validate_strings=True)


def restrict(target: str) -> ForeignKey:
    """FK que impide borrar la fila referenciada (evidencia fiscal)."""
    return ForeignKey(target, ondelete="RESTRICT")


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(512))
    role: Mapped[Role] = mapped_column(enum_column(Role), index=True)
    supplier_id: Mapped[int | None] = mapped_column(restrict("suppliers.id"), nullable=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now_utc)
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    # Contrasena asignada por otra persona (autorizacion, reenvio de credenciales o alta en /admin/users): el usuario
    # debe cambiarla antes de usar el portal (HU-10). El seed crea sin marca.
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    supplier: Mapped[Supplier | None] = relationship(back_populates="users")


class Supplier(Base):
    __tablename__ = "suppliers"
    __table_args__ = (
        # Identidad fiscal por origen: el nacional por RFC (unico, NULL permitido); el internacional por pais + id.
        UniqueConstraint("country", "foreign_tax_id", name="uq_suppliers_country_foreign_tax_id"),
        CheckConstraint(
            "(origin = 'NATIONAL' AND rfc IS NOT NULL AND foreign_tax_id IS NULL AND country = 'MX')"
            " OR (origin = 'INTERNATIONAL' AND rfc IS NULL AND foreign_tax_id IS NOT NULL AND country <> 'MX')",
            name="ck_suppliers_origin_identity",
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    business_name: Mapped[str] = mapped_column(String(250))
    rfc: Mapped[str | None] = mapped_column(String(13), unique=True, index=True)
    # Los valores por defecto mantienen el alta individual (solo nacionales) sin cambios.
    origin: Mapped[SupplierOrigin] = mapped_column(enum_column(SupplierOrigin), default=SupplierOrigin.NATIONAL)
    foreign_tax_id: Mapped[str | None] = mapped_column(String(40))
    country: Mapped[str] = mapped_column(String(2), default="MX")
    supplier_type: Mapped[SupplierType] = mapped_column(enum_column(SupplierType))
    email: Mapped[str] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(30))
    status: Mapped[SupplierStatus] = mapped_column(enum_column(SupplierStatus), default=SupplierStatus.ACTIVE)
    confidentiality_agreement: Mapped[bool] = mapped_column(Boolean, default=False)
    economic_proposal: Mapped[bool] = mapped_column(Boolean, default=False)
    bank_information: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now_utc, onupdate=now_utc)
    users: Mapped[list[User]] = relationship(back_populates="supplier")
    contracts: Mapped[list[Contract]] = relationship(back_populates="supplier")
    invoices: Mapped[list[Invoice]] = relationship(back_populates="supplier")

    @property
    def tax_identifier(self) -> str:
        """RFC del proveedor nacional, o pais e identificador fiscal del internacional."""
        return self.rfc or f"{self.country} {self.foreign_tax_id}"


class Contract(Base):
    __tablename__ = "contracts"
    __table_args__ = (
        CheckConstraint("authorized_amount > 0", name="ck_contracts_authorized_amount_positive"),
        CheckConstraint("end_date >= start_date", name="ck_contracts_valid_period"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_id: Mapped[int] = mapped_column(restrict("suppliers.id"), index=True)
    project_name: Mapped[str] = mapped_column(String(200))
    project_leader: Mapped[str] = mapped_column(String(150))
    authorized_technology: Mapped[str] = mapped_column(String(250))
    authorized_amount: Mapped[Decimal] = mapped_column(Money())
    currency: Mapped[str] = mapped_column(String(3), default="MXN")
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    status: Mapped[ContractStatus] = mapped_column(enum_column(ContractStatus), default=ContractStatus.ACTIVE)
    notes: Mapped[str | None] = mapped_column(Text)
    # Trazabilidad del control financiero principal (AUDITORIA BD-09).
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now_utc)
    created_by: Mapped[int | None] = mapped_column(restrict("users.id"))
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now_utc, onupdate=now_utc)
    updated_by: Mapped[int | None] = mapped_column(restrict("users.id"))
    supplier: Mapped[Supplier] = relationship(back_populates="contracts")
    amendments: Mapped[list[ContractAmendment]] = relationship(
        back_populates="contract", order_by="ContractAmendment.id", passive_deletes="all"
    )


class ContractAmendment(Base):
    """Cambio del monto autorizado. El monto solo se modifica mediante una enmienda auditada."""

    __tablename__ = "contract_amendments"
    __table_args__ = (CheckConstraint("new_amount > 0", name="ck_contract_amendments_new_amount_positive"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    contract_id: Mapped[int] = mapped_column(restrict("contracts.id"), index=True)
    previous_amount: Mapped[Decimal] = mapped_column(Money())
    new_amount: Mapped[Decimal] = mapped_column(Money())
    reason: Mapped[str] = mapped_column(Text)
    created_by: Mapped[int] = mapped_column(restrict("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now_utc)
    contract: Mapped[Contract] = relationship(back_populates="amendments")
    author: Mapped[User] = relationship()


class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (
        # (supplier_id, created_at) cubre el listado de un proveedor ordenado por fecha; created_at, el interno.
        Index("ix_invoices_supplier_created", "supplier_id", "created_at"),
        # La BD es la autoridad sobre duplicados fiscales; FIN-004/FIN-005 solo dan retroalimentacion.
        UniqueConstraint("uuid", name="uq_invoices_uuid"),
        UniqueConstraint("supplier_id", "invoice_number", name="uq_invoices_supplier_number"),
        CheckConstraint("subtotal >= 0", name="ck_invoices_subtotal_non_negative"),
        CheckConstraint("tax >= 0", name="ck_invoices_tax_non_negative"),
        CheckConstraint("total >= 0", name="ck_invoices_total_non_negative"),
        CheckConstraint(
            "validation_score IS NULL OR validation_score BETWEEN 0 AND 100", name="ck_invoices_score_range"
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    internal_folio: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    supplier_id: Mapped[int] = mapped_column(restrict("suppliers.id"))
    uploaded_by: Mapped[int] = mapped_column(restrict("users.id"), index=True)
    contract_id: Mapped[int | None] = mapped_column(restrict("contracts.id"), index=True)
    invoice_number: Mapped[str] = mapped_column(String(100), index=True)
    uuid: Mapped[str | None] = mapped_column(String(50))
    invoice_date: Mapped[date | None] = mapped_column(Date)
    service_period: Mapped[str] = mapped_column(String(20))
    purchase_order_number: Mapped[str | None] = mapped_column(String(100))
    project_name: Mapped[str] = mapped_column(String(200))
    project_leader: Mapped[str | None] = mapped_column(String(150))
    subtotal: Mapped[Decimal] = mapped_column(Money(), default=Decimal("0"))
    tax: Mapped[Decimal] = mapped_column(Money(), default=Decimal("0"))
    total: Mapped[Decimal] = mapped_column(Money(), default=Decimal("0"))
    currency: Mapped[str] = mapped_column(String(3), default="MXN")
    status: Mapped[InvoiceStatus] = mapped_column(enum_column(InvoiceStatus), default=InvoiceStatus.DRAFT, index=True)
    validation_score: Mapped[int | None]
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now_utc, index=True)
    submitted_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    reviewed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    reviewed_by: Mapped[int | None] = mapped_column(restrict("users.id"), index=True)
    comments: Mapped[str | None] = mapped_column(Text)
    supplier: Mapped[Supplier] = relationship(back_populates="invoices")
    contract: Mapped[Contract | None] = relationship()
    # Sin delete/delete-orphan: documentos, validaciones y revisiones son evidencia fiscal (AUDITORIA BD-12).
    documents: Mapped[list[Document]] = relationship(
        back_populates="invoice", cascade="save-update, merge", passive_deletes="all"
    )
    validations: Mapped[list[ValidationResult]] = relationship(
        back_populates="invoice", cascade="save-update, merge", passive_deletes="all"
    )
    reviews: Mapped[list[Review]] = relationship(
        back_populates="invoice", cascade="save-update, merge", passive_deletes="all"
    )


@event.listens_for(Session, "before_flush")
def _forbid_invoice_deletion(session: Session, _flush_context, _instances) -> None:
    if any(isinstance(instance, Invoice) for instance in session.deleted):
        raise BusinessRuleError("Borrado fisico de facturas prohibido: la factura es evidencia fiscal.")


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int | None] = mapped_column(restrict("invoices.id"), index=True)
    supplier_id: Mapped[int | None] = mapped_column(restrict("suppliers.id"), index=True)
    document_type: Mapped[str] = mapped_column(String(60), index=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    stored_filename: Mapped[str] = mapped_column(String(255))
    # Ruta relativa a la raiz de almacenamiento, con separadores "/" (AUDITORIA BD-11).
    path: Mapped[str] = mapped_column(String(500))
    mime_type: Mapped[str] = mapped_column(String(120))
    file_size: Mapped[int]
    sha256: Mapped[str] = mapped_column(String(64))
    uploaded_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now_utc)
    uploaded_by: Mapped[int] = mapped_column(restrict("users.id"), index=True)
    processing_status: Mapped[ProcessingStatus] = mapped_column(
        enum_column(ProcessingStatus), default=ProcessingStatus.PENDING
    )
    page_count: Mapped[int | None]
    document_date: Mapped[date | None] = mapped_column(Date)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    replaced_document_id: Mapped[int | None] = mapped_column(restrict("documents.id"), index=True)
    invoice: Mapped[Invoice | None] = relationship(back_populates="documents", foreign_keys=[invoice_id])


class InvoiceDocumentType(Base):
    """Tipo de documento de factura y su nivel de exigencia por origen del proveedor (HU-04). `code` es el valor de
    documents.document_type; no hay FK porque esa columna tambien guarda claves del expediente del Anexo A."""

    __tablename__ = "invoice_document_types"
    __table_args__ = (
        UniqueConstraint("code", name="uq_invoice_document_types_code"),
        CheckConstraint(
            "cardinality(formats) >= 1 AND formats <@ ARRAY['PDF', 'PNG', 'JPEG', 'XML', 'TXT']::varchar[]",
            name="ck_invoice_document_types_formats",
        ),
        CheckConstraint("is_active OR NOT is_system", name="ck_invoice_document_types_system_active"),
        # Niveles fijos (RD-04): el nacional factura con CFDI y el internacional con Invoice.
        CheckConstraint(
            "(code NOT IN ('INVOICE_XML', 'INVOICE_PDF')"
            " OR (national_requirement = 'REQUIRED' AND international_requirement = 'NOT_APPLICABLE'))"
            " AND (code <> 'FOREIGN_INVOICE'"
            " OR (national_requirement = 'NOT_APPLICABLE' AND international_requirement = 'REQUIRED'))",
            name="ck_invoice_document_types_fixed_levels",
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(60))
    name: Mapped[str] = mapped_column(String(80))
    description: Mapped[str | None] = mapped_column(String(300))
    formats: Mapped[list[str]] = mapped_column(ARRAY(String(4)))
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    national_requirement: Mapped[DocumentRequirement] = mapped_column(
        enum_column(DocumentRequirement, "ck_invoice_document_types_national_requirement"),
        default=DocumentRequirement.NOT_APPLICABLE,
    )
    international_requirement: Mapped[DocumentRequirement] = mapped_column(
        enum_column(DocumentRequirement, "ck_invoice_document_types_international_requirement"),
        default=DocumentRequirement.NOT_APPLICABLE,
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now_utc, onupdate=now_utc)


# Nombre unico sin distinguir mayusculas (el servicio normaliza espacios antes de guardar).
Index("uq_invoice_document_types_name_lower", func.lower(InvoiceDocumentType.name), unique=True)


class ValidationResult(Base):
    __tablename__ = "validation_results"
    __table_args__ = (
        CheckConstraint("confidence IS NULL OR confidence BETWEEN 0 AND 1", name="ck_validation_results_confidence"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(restrict("invoices.id"), index=True)
    rule_code: Mapped[str] = mapped_column(String(20), index=True)
    category: Mapped[str] = mapped_column(String(30))
    status: Mapped[RuleStatus] = mapped_column(enum_column(RuleStatus))
    severity: Mapped[Severity] = mapped_column(enum_column(Severity))
    expected_value: Mapped[str | None] = mapped_column(Text)
    detected_value: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[Decimal | None] = mapped_column(ExactNumeric(5, 4))
    message: Mapped[str] = mapped_column(Text)
    source_document: Mapped[str | None] = mapped_column(String(255))
    source_reference: Mapped[str | None] = mapped_column(String(255))
    evidence_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now_utc)
    invoice: Mapped[Invoice] = relationship(back_populates="validations")


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(restrict("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(80), index=True)
    entity: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[str | None] = mapped_column(String(80))
    old_value: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    new_value: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime, default=now_utc, index=True)
    ip_address: Mapped[str | None] = mapped_column(String(50))
    user: Mapped[User | None] = relationship()


class LoginAttempt(Base):
    """Intento de inicio de sesion; base de la limitacion por correo y por IP (AUDITORIA SEC-04)."""

    __tablename__ = "login_attempts"
    __table_args__ = (
        Index("ix_login_attempts_email_attempted_at", "email", "attempted_at"),
        Index("ix_login_attempts_ip_attempted_at", "ip", "attempted_at"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255))
    ip: Mapped[str | None] = mapped_column(String(50))
    result: Mapped[LoginResult] = mapped_column(SAEnum(LoginResult, native_enum=False, create_constraint=True))
    attempted_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now_utc)


class UserSession(Base):
    """Sesion del lado del servidor: la cookie solo lleva un identificador opaco; aqui se guarda su SHA-256
    (AUDITORIA SEC-07)."""

    __tablename__ = "user_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(restrict("users.id"), index=True)
    sid_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now_utc)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now_utc)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    ip: Mapped[str | None] = mapped_column(String(50))
    user_agent: Mapped[str | None] = mapped_column(String(255))


class Review(Base):
    __tablename__ = "reviews"
    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(restrict("invoices.id"), index=True)
    reviewer_id: Mapped[int] = mapped_column(restrict("users.id"), index=True)
    decision: Mapped[ReviewDecision] = mapped_column(enum_column(ReviewDecision))
    comments: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now_utc)
    invoice: Mapped[Invoice] = relationship(back_populates="reviews")
    reviewer: Mapped[User] = relationship()


class NotificationTemplate(Base):
    """Plantilla de correo de un evento de estatus de factura (HU-05). Las cuatro filas las crea la migracion y la
    interfaz solo las edita. `version` es el bloqueo optimista; `updated_by` es NULL si nunca se ha modificado."""

    __tablename__ = "notification_templates"
    __table_args__ = (
        UniqueConstraint("event", name="uq_notification_templates_event"),
        CheckConstraint("char_length(subject) BETWEEN 1 AND 200", name="ck_notification_templates_subject_length"),
        CheckConstraint("char_length(body) BETWEEN 1 AND 5000", name="ck_notification_templates_body_length"),
        CheckConstraint("version >= 1", name="ck_notification_templates_version_positive"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    event: Mapped[NotificationEvent] = mapped_column(enum_column(NotificationEvent))
    subject: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(default=1)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now_utc)
    updated_by: Mapped[int | None] = mapped_column(restrict("users.id"))
    updater: Mapped[User | None] = relationship()


class NotificationMailbox(Base):
    """Buzon de destino de notificaciones (HU-08), p. ej. Recepcion de Facturas. La fila la crea la migracion y la
    interfaz solo cambia sus direcciones. `updated_by` es NULL si nunca se ha modificado."""

    __tablename__ = "notification_mailboxes"
    __table_args__ = (
        UniqueConstraint("code", name="uq_notification_mailboxes_code"),
        CheckConstraint("cardinality(addresses) BETWEEN 1 AND 10", name="ck_notification_mailboxes_addresses"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[Mailbox] = mapped_column(enum_column(Mailbox))
    name: Mapped[str] = mapped_column(String(80))
    addresses: Mapped[list[str]] = mapped_column(ARRAY(String(254)))
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now_utc)
    updated_by: Mapped[int | None] = mapped_column(restrict("users.id"))


class NotificationCopy(Base):
    """Direcciones que reciben copia del correo de un evento (HU-08), ademas de su destinatario principal. Una fila
    por evento que admite copias, creada por la migracion."""

    __tablename__ = "notification_copies"
    __table_args__ = (
        UniqueConstraint("event", name="uq_notification_copies_event"),
        CheckConstraint("cardinality(addresses) <= 10", name="ck_notification_copies_addresses"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    event: Mapped[NotificationEvent] = mapped_column(enum_column(NotificationEvent))
    addresses: Mapped[list[str]] = mapped_column(ARRAY(String(254)), default=list)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now_utc)
    updated_by: Mapped[int | None] = mapped_column(restrict("users.id"))


class EmailDelivery(Base):
    """Bitacora de envios de correo (HU-08). Sin asunto ni cuerpo: el correo de credenciales lleva una contrasena
    temporal. `event` es NULL en el correo de prueba."""

    __tablename__ = "email_deliveries"
    __table_args__ = (
        Index("ix_email_deliveries_entity", "entity", "entity_id"),
        CheckConstraint("cardinality(to_addresses) >= 1", name="ck_email_deliveries_to_addresses"),
        CheckConstraint("status <> 'FAILED' OR error IS NOT NULL", name="ck_email_deliveries_failed_error"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    event: Mapped[NotificationEvent | None] = mapped_column(enum_column(NotificationEvent))
    status: Mapped[DeliveryStatus] = mapped_column(enum_column(DeliveryStatus))
    to_addresses: Mapped[list[str]] = mapped_column(ARRAY(String(254)))
    cc_addresses: Mapped[list[str]] = mapped_column(ARRAY(String(254)), default=list)
    transport: Mapped[str] = mapped_column(String(10))
    message_id: Mapped[str] = mapped_column(String(255))
    error: Mapped[str | None] = mapped_column(String(300))
    entity: Mapped[str | None] = mapped_column(String(80))
    entity_id: Mapped[str | None] = mapped_column(String(80))
    requested_by: Mapped[int | None] = mapped_column(restrict("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now_utc, index=True)


class ValidationSettings(Base):
    """Reglas de Validacion (HU-06): datos de ULTRASIST y parametros del CFDI que compara el motor. Una sola fila
    (id = 1), creada por la migracion; `version` es el bloqueo optimista y `updated_by` es NULL si nunca se modifico.
    Las claves de regimen, metodo, forma y usos pertenecen a catalog_entries (el servicio exige que esten activas)."""

    __tablename__ = "validation_settings"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_validation_settings_single_row"),
        CheckConstraint("receiver_postal_code ~ '^[0-9]{5}$'", name="ck_validation_settings_postal_code"),
        CheckConstraint("cardinality(allowed_cfdi_uses) >= 1", name="ck_validation_settings_cfdi_uses"),
        CheckConstraint("version >= 1", name="ck_validation_settings_version_positive"),
    )
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    receiver_rfc: Mapped[str] = mapped_column(String(13))
    receiver_name: Mapped[str] = mapped_column(String(254))
    receiver_address: Mapped[str] = mapped_column(String(300), default="")
    receiver_postal_code: Mapped[str] = mapped_column(String(5))
    receiver_tax_regime: Mapped[str] = mapped_column(String(10))
    payment_method: Mapped[str] = mapped_column(String(10))
    payment_form: Mapped[str] = mapped_column(String(10))
    allowed_cfdi_uses: Mapped[list[str]] = mapped_column(ARRAY(String(10)))
    check_receiver_rfc: Mapped[bool] = mapped_column(Boolean, default=True)
    check_receiver_name: Mapped[bool] = mapped_column(Boolean, default=True)
    check_receiver_postal_code: Mapped[bool] = mapped_column(Boolean, default=True)
    check_payment_method: Mapped[bool] = mapped_column(Boolean, default=True)
    check_payment_form: Mapped[bool] = mapped_column(Boolean, default=True)
    check_cfdi_use: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(default=1)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now_utc)
    updated_by: Mapped[int | None] = mapped_column(restrict("users.id"))


class CatalogEntry(Base):
    """Clave de un catalogo de referencia (HU-07). Nunca se borra: se desactiva. El formato de la clave por catalogo
    lo valida el servicio; la base de datos acota su alfabeto y longitud."""

    __tablename__ = "catalog_entries"
    __table_args__ = (
        UniqueConstraint("catalog", "code", name="uq_catalog_entries_catalog_code"),
        CheckConstraint("code ~ '^[A-Z0-9]{1,10}$'", name="ck_catalog_entries_code"),
        CheckConstraint("char_length(name) BETWEEN 1 AND 150", name="ck_catalog_entries_name_length"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    catalog: Mapped[CatalogType] = mapped_column(enum_column(CatalogType))
    code: Mapped[str] = mapped_column(String(10))
    name: Mapped[str] = mapped_column(String(150))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now_utc, onupdate=now_utc)
    updated_by: Mapped[int | None] = mapped_column(restrict("users.id"))


__all__ = [
    "User",
    "Supplier",
    "Contract",
    "ContractAmendment",
    "Invoice",
    "Document",
    "InvoiceDocumentType",
    "ValidationResult",
    "AuditLog",
    "LoginAttempt",
    "Review",
    "UserSession",
    "NotificationTemplate",
    "NotificationMailbox",
    "NotificationCopy",
    "EmailDelivery",
    "ValidationSettings",
    "CatalogEntry",
]
