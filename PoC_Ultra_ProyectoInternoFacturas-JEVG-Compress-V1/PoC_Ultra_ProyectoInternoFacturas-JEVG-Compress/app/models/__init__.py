from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, Index, String, Text, UniqueConstraint, event
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

from app.core.constants import (
    ContractStatus,
    InvoiceStatus,
    LoginResult,
    ProcessingStatus,
    ReviewDecision,
    Role,
    RuleStatus,
    Severity,
    SupplierStatus,
    SupplierType,
)
from app.core.database import Base
from app.core.errors import BusinessRuleError
from app.core.types import ExactNumeric, Money, UTCDateTime


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def enum_column(enum: type[StrEnum]) -> SAEnum:
    """Enumeracion como VARCHAR con CHECK: la BD rechaza valores fuera del catalogo (AUDITORIA BD-05)."""
    return SAEnum(enum, native_enum=False, create_constraint=True, validate_strings=True)


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
    supplier: Mapped[Supplier | None] = relationship(back_populates="users")


class Supplier(Base):
    __tablename__ = "suppliers"
    id: Mapped[int] = mapped_column(primary_key=True)
    business_name: Mapped[str] = mapped_column(String(250))
    rfc: Mapped[str] = mapped_column(String(13), unique=True, index=True)
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


__all__ = [
    "User",
    "Supplier",
    "Contract",
    "ContractAmendment",
    "Invoice",
    "Document",
    "ValidationResult",
    "AuditLog",
    "LoginAttempt",
    "Review",
    "UserSession",
]
