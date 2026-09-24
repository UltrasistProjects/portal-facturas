from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Numeric, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.core.constants import InvoiceStatus, Role, SupplierType
from app.core.database import Base


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(512))
    role: Mapped[Role] = mapped_column(SAEnum(Role), index=True)
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"), nullable=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    supplier: Mapped[Supplier | None] = relationship(back_populates="users")


class Supplier(Base):
    __tablename__ = "suppliers"
    id: Mapped[int] = mapped_column(primary_key=True)
    business_name: Mapped[str] = mapped_column(String(250))
    rfc: Mapped[str] = mapped_column(String(13), unique=True, index=True)
    supplier_type: Mapped[SupplierType] = mapped_column(SAEnum(SupplierType))
    email: Mapped[str] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(30), default="ACTIVE")
    confidentiality_agreement: Mapped[bool] = mapped_column(Boolean, default=False)
    economic_proposal: Mapped[bool] = mapped_column(Boolean, default=False)
    bank_information: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)
    users: Mapped[list[User]] = relationship(back_populates="supplier")
    contracts: Mapped[list[Contract]] = relationship(back_populates="supplier")
    invoices: Mapped[list[Invoice]] = relationship(back_populates="supplier")


class Contract(Base):
    __tablename__ = "contracts"
    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), index=True)
    project_name: Mapped[str] = mapped_column(String(200))
    project_leader: Mapped[str] = mapped_column(String(150))
    authorized_technology: Mapped[str] = mapped_column(String(250))
    authorized_amount: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    currency: Mapped[str] = mapped_column(String(3), default="MXN")
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(30), default="ACTIVE")
    notes: Mapped[str | None] = mapped_column(Text)
    supplier: Mapped[Supplier] = relationship(back_populates="contracts")


class Invoice(Base):
    __tablename__ = "invoices"
    # (supplier_id, created_at) cubre el listado de un proveedor ordenado por fecha; created_at, el listado interno.
    __table_args__ = (Index("ix_invoices_supplier_created", "supplier_id", "created_at"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    internal_folio: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"))
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    contract_id: Mapped[int | None] = mapped_column(ForeignKey("contracts.id"), index=True)
    invoice_number: Mapped[str] = mapped_column(String(100), index=True)
    uuid: Mapped[str | None] = mapped_column(String(50), index=True)
    invoice_date: Mapped[date | None] = mapped_column(Date)
    service_period: Mapped[str] = mapped_column(String(20))
    purchase_order_number: Mapped[str | None] = mapped_column(String(100))
    project_name: Mapped[str] = mapped_column(String(200))
    project_leader: Mapped[str | None] = mapped_column(String(150))
    subtotal: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=Decimal("0"))
    tax: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=Decimal("0"))
    total: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=Decimal("0"))
    currency: Mapped[str] = mapped_column(String(3), default="MXN")
    status: Mapped[InvoiceStatus] = mapped_column(SAEnum(InvoiceStatus), default=InvoiceStatus.DRAFT, index=True)
    validation_score: Mapped[int | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    comments: Mapped[str | None] = mapped_column(Text)
    supplier: Mapped[Supplier] = relationship(back_populates="invoices")
    contract: Mapped[Contract | None] = relationship()
    documents: Mapped[list[Document]] = relationship(back_populates="invoice", cascade="all, delete-orphan")
    validations: Mapped[list[ValidationResult]] = relationship(back_populates="invoice", cascade="all, delete-orphan")
    reviews: Mapped[list[Review]] = relationship(back_populates="invoice", cascade="all, delete-orphan")


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int | None] = mapped_column(ForeignKey("invoices.id"), index=True)
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"), index=True)
    document_type: Mapped[str] = mapped_column(String(60), index=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    stored_filename: Mapped[str] = mapped_column(String(255))
    path: Mapped[str] = mapped_column(String(500))
    mime_type: Mapped[str] = mapped_column(String(120))
    file_size: Mapped[int]
    sha256: Mapped[str] = mapped_column(String(64))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    processing_status: Mapped[str] = mapped_column(String(30), default="PENDING")
    page_count: Mapped[int | None]
    document_date: Mapped[date | None] = mapped_column(Date)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    replaced_document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"), index=True)
    invoice: Mapped[Invoice | None] = relationship(back_populates="documents", foreign_keys=[invoice_id])


class ValidationResult(Base):
    __tablename__ = "validation_results"
    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), index=True)
    rule_code: Mapped[str] = mapped_column(String(20), index=True)
    category: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(30))
    severity: Mapped[str] = mapped_column(String(20))
    expected_value: Mapped[str | None] = mapped_column(Text)
    detected_value: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    message: Mapped[str] = mapped_column(Text)
    source_document: Mapped[str | None] = mapped_column(String(255))
    source_reference: Mapped[str | None] = mapped_column(String(255))
    evidence_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    invoice: Mapped[Invoice] = relationship(back_populates="validations")


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(80), index=True)
    entity: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[str | None] = mapped_column(String(80))
    old_value: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    new_value: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)
    ip_address: Mapped[str | None] = mapped_column(String(50))
    user: Mapped[User | None] = relationship()


class Review(Base):
    __tablename__ = "reviews"
    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), index=True)
    reviewer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    decision: Mapped[str] = mapped_column(String(40))
    comments: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    invoice: Mapped[Invoice] = relationship(back_populates="reviews")
    reviewer: Mapped[User] = relationship()


__all__ = ["User", "Supplier", "Contract", "Invoice", "Document", "ValidationResult", "AuditLog", "Review"]
