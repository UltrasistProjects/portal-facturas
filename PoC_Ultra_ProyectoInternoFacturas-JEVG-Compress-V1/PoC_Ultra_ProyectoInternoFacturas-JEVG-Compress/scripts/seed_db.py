from __future__ import annotations

import hashlib
import re
import shutil
import sys
import tempfile
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import fitz
from sqlalchemy import select

from app.core.config import settings
from app.core.constants import (
    SUPPLIER_REQUIREMENTS,
    DocumentType,
    InvoiceStatus,
    Role,
    SupplierClassification,
    SupplierOrigin,
    SupplierType,
)
from app.core.database import SessionLocal
from app.core.demo import DEMO_ACCOUNTS
from app.core.passwords import generate_password
from app.core.security import hash_password
from app.models import AuditLog, Contract, Document, Invoice, Review, Supplier, User
from app.services.file_service import LocalFileStorage
from app.services.pdf_service import analyze_pdf
from app.services.validation_engine import run_validation

# Observaciones del PMO de la factura demo OBSERVACIONES-001: las ve el proveedor para corregir y reenviar.
OBSERVATIONS_NOTE = "Falta el Vo.Bo. firmado del lider de proyecto."


def create_demo_pdf(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 90), "DOCUMENTO FICTICIO DE PRUEBA - SIN VALIDEZ FISCAL", fontsize=12)
    page.insert_text((72, 125), "Factura PDF demo / Proyecto Automatizacion Operativa 2026", fontsize=11)
    page.insert_text((72, 150), "08 Servicios desarrollo Power Automate / Total MXN 116,000.00", fontsize=11)
    doc.save(path)
    doc.close()


def create_foreign_invoice_pdf(path: Path) -> None:
    """Invoice demo del proveedor internacional: su texto trae los datos que buscan las reglas INT (HU-16)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    page = doc.new_page()
    lines = [
        ("INVOICE INV-2026-0042 - FICTITIOUS DEMO DOCUMENT, NO FISCAL VALIDITY", 12),
        ("From: Global Data Services Inc. (DEMO) - Tax ID 98-7654321 - Austin, TX, USA", 11),
        ("Bill to: ULTRASIST SA DE CV - Ciudad de Mexico, C.P. 03930, Mexico", 11),
        ("Invoice date: 2026-08-31 / Service period: August 2026", 11),
        ("Data analytics consulting - Analitica Global 2026", 11),
        ("Subtotal USD 18,000.00 / Tax USD 0.00 / Total USD 18,000.00", 11),
    ]
    for index, (text, size) in enumerate(lines):
        page.insert_text((72, 90 + 25 * index), text, fontsize=size)
    doc.save(path)
    doc.close()


def seed_international(db, workdir: Path, demo: Path, password: str, admin_id: int, folio: str) -> None:
    """Proveedor internacional autorizado con su usuario, un contrato en USD y la factura INV-2026-0042 en "Cargada":
    Invoice en PDF con los importes capturados, orden de compra y Vo.Bo. Su envio procede (HU-15/16)."""
    supplier = Supplier(
        business_name="Global Data Services Inc. (DEMO)",
        rfc=None,
        origin=SupplierOrigin.INTERNATIONAL,
        foreign_tax_id="98-7654321",
        country="US",
        supplier_type=SupplierType.PERSONA_MORAL,
        email="proveedor3@poc.local",
        phone="+1 512 555 0142",
        confidentiality_agreement=True,
        economic_proposal=True,
        notes="Proveedor extranjero completamente ficticio para demostracion.",
        classification=SupplierClassification.EXTERNAL,
        main_activity="54",
        website="https://www.globaldata.example",
        legal_rep_name="Jane Smith (DEMO)",
        legal_rep_phone="+1 512 555 0100",
        contact_name="John Doe (DEMO)",
        contact_phone="+1 512 555 0142",
    )
    db.add(supplier)
    db.flush()
    user = User(
        name="Proveedor Internacional Demo",
        email="proveedor3@poc.local",
        password_hash=hash_password(password),
        role=Role.PROVIDER,
        supplier_id=supplier.id,
    )
    contract = Contract(
        supplier_id=supplier.id,
        project_name="Analitica Global 2026",
        project_leader="Laura PMO (DEMO)",
        authorized_technology="Data Analytics",
        authorized_amount=Decimal("20000.00"),
        currency="USD",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        status="ACTIVE",
        notes="Contrato sintetico en dolares.",
    )
    db.add_all([user, contract])
    db.flush()
    invoice = Invoice(
        internal_folio=folio,
        supplier_id=supplier.id,
        uploaded_by=user.id,
        contract_id=contract.id,
        invoice_number="INV-2026-0042",
        invoice_date=date(2026, 8, 31),
        service_period="08/2026",
        purchase_order_number="PO-DEMO-042",
        project_name=contract.project_name,
        project_leader=contract.project_leader,
        subtotal=Decimal("18000.00"),
        tax=Decimal("0.00"),
        total=Decimal("18000.00"),
        currency="USD",
        status=InvoiceStatus.DRAFT,
    )
    db.add(invoice)
    db.flush()
    invoice_pdf = workdir / "INV-2026-0042.pdf"
    create_foreign_invoice_pdf(invoice_pdf)
    sources = [
        (DocumentType.FOREIGN_INVOICE, invoice_pdf),
        (DocumentType.PURCHASE_ORDER, demo / "orden_compra_demo.txt"),
        (DocumentType.APPROVAL, demo / "vobo_demo.txt"),
    ]
    for doc_type, source in sources:
        document = add_document(
            db, user_id=user.id, supplier_id=supplier.id, invoice_id=invoice.id, doc_type=doc_type.value, source=source
        )
        if doc_type == DocumentType.FOREIGN_INVOICE:
            # Como la carga documental: el detalle muestra si el texto del Invoice es legible.
            analysis = analyze_pdf(invoice_pdf)
            document.page_count = analysis["page_count"]
            document.metadata_json = {"demo": True, "has_extractable_text": analysis["has_extractable_text"]}
    db.commit()
    run_validation(db, invoice, user.id)
    invoice.status = InvoiceStatus.UPLOADED
    db.add(
        AuditLog(
            user_id=admin_id,
            action="DEMO_SEEDED",
            entity="Invoice",
            entity_id=str(invoice.id),
            new_value={"scenario": "Caso internacional: Invoice en PDF listo para enviar"},
        )
    )
    db.commit()


def add_document(
    db, *, user_id: int, supplier_id: int, invoice_id: int | None, doc_type: str, source: Path
) -> Document:
    content = source.read_bytes()
    storage = LocalFileStorage()
    folder = storage.root / ("invoices" if invoice_id else "suppliers") / str(invoice_id or supplier_id)
    folder.mkdir(parents=True, exist_ok=True)
    destination = (
        folder / f"demo_{hashlib.sha256((str(invoice_id) + doc_type).encode()).hexdigest()[:10]}{source.suffix}"
    )
    shutil.copyfile(source, destination)
    doc = Document(
        invoice_id=invoice_id,
        supplier_id=supplier_id,
        document_type=doc_type,
        original_filename=source.name,
        stored_filename=destination.name,
        path=storage.relative_path(destination),
        mime_type="application/pdf"
        if source.suffix == ".pdf"
        else ("application/xml" if source.suffix == ".xml" else "text/plain"),
        file_size=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        uploaded_by=user_id,
        processing_status="PROCESSED",
        document_date=date(2026, 8, 1),
        metadata_json={"demo": True},
    )
    db.add(doc)
    return doc


def seed_passwords(passwords: dict[str, str] | None = None) -> dict[str, str]:
    """Contrasenas por correo: explicitas, las demo documentadas en development o aleatorias en otro entorno."""
    if passwords is not None:
        return {account.email: passwords[account.email] for account in DEMO_ACCOUNTS}
    if settings.app_env == "development":
        return {account.email: account.password for account in DEMO_ACCOUNTS}
    generated = {account.email: generate_password() for account in DEMO_ACCOUNTS}
    print("Contrasenas generadas para los usuarios sembrados (se muestran una sola vez):")
    for email, password in generated.items():
        print(f"  {email}: {password}")
    return generated


def main(passwords: dict[str, str] | None = None) -> None:
    """Siembra la demo. `passwords` (correo -> contrasena) fija las contrasenas de los usuarios sembrados."""
    demo = ROOT / "data" / "demo_documents"
    with tempfile.TemporaryDirectory(prefix="seed_") as tmp, SessionLocal() as db:
        workdir = Path(tmp)
        pdf = demo / "factura_demo.pdf"
        if not pdf.is_file():
            pdf = workdir / "factura_demo.pdf"
            create_demo_pdf(pdf)
        if db.scalar(select(User.id).limit(1)):
            print("La base ya contiene datos; use scripts/reset_demo.py para reconstruirla.")
            return
        passwords = seed_passwords(passwords)
        moral = Supplier(
            business_name="Tecnologia Integral del Centro SA de CV",
            rfc="TIC210101ABC",
            supplier_type=SupplierType.PERSONA_MORAL,
            email="proveedor1@poc.local",
            phone="555-0101",
            status="ACTIVE",
            confidentiality_agreement=True,
            economic_proposal=True,
            bank_information="CLABE DEMO terminacion 0001",
            notes="Proveedor completamente ficticio para demostracion.",
            classification=SupplierClassification.EXTERNAL,
            main_activity="54",
            incorporation_date=date(2021, 1, 1),
            website="https://www.tecnologia-integral.example",
            legal_rep_name="Ana Martinez Ruiz (DEMO)",
            legal_rep_phone="555-0111",
            contact_name="Luis Gomez Ortiz (DEMO)",
            contact_phone="555-0101",
        )
        physical = Supplier(
            business_name="Carlos Hernandez Lopez (DEMO)",
            rfc="HELC900101XX1",
            supplier_type=SupplierType.PERSONA_FISICA,
            email="proveedor2@poc.local",
            phone="555-0102",
            status="ACTIVE",
            confidentiality_agreement=True,
            economic_proposal=True,
            bank_information="CLABE DEMO terminacion 0002",
            notes="Identidad y RFC ficticios para pruebas.",
            classification=SupplierClassification.EXTERNAL,
            main_activity="54",
            # Persona fisica: su representante legal es ella misma.
            legal_rep_name="Carlos Hernandez Lopez (DEMO)",
            legal_rep_phone="555-0102",
            contact_name="Carlos Hernandez Lopez (DEMO)",
            contact_phone="555-0102",
        )
        db.add_all([moral, physical])
        db.flush()
        users = [
            User(
                name="Administrador Demo",
                email="admin@poc.local",
                password_hash=hash_password(passwords["admin@poc.local"]),
                role=Role.ADMIN,
            ),
            User(
                name="PMO Demo",
                email="pmo@poc.local",
                password_hash=hash_password(passwords["pmo@poc.local"]),
                role=Role.INTERNAL,
            ),
            User(
                name="Proveedor Moral Demo",
                email="proveedor1@poc.local",
                password_hash=hash_password(passwords["proveedor1@poc.local"]),
                role=Role.PROVIDER,
                supplier_id=moral.id,
            ),
            User(
                name="Proveedor Fisico Demo",
                email="proveedor2@poc.local",
                password_hash=hash_password(passwords["proveedor2@poc.local"]),
                role=Role.PROVIDER,
                supplier_id=physical.id,
            ),
        ]
        db.add_all(users)
        db.flush()
        contracts = [
            Contract(
                supplier_id=moral.id,
                project_name="Automatizacion Operativa 2026",
                project_leader="Laura PMO (DEMO)",
                authorized_technology="Microsoft Power Platform",
                authorized_amount=Decimal("100000.00"),
                currency="MXN",
                start_date=date(2026, 1, 1),
                end_date=date(2026, 12, 31),
                status="ACTIVE",
                notes="Contrato sintetico.",
            ),
            Contract(
                supplier_id=physical.id,
                project_name="Servicios de Analitica 2026",
                project_leader="Miguel PMO (DEMO)",
                authorized_technology="Python Data Analytics",
                authorized_amount=Decimal("75000.00"),
                currency="MXN",
                start_date=date(2026, 1, 1),
                end_date=date(2026, 12, 31),
                status="ACTIVE",
                notes="Contrato sintetico.",
            ),
        ]
        db.add_all(contracts)
        db.flush()
        for supplier in (moral, physical):
            uploader = users[2] if supplier is moral else users[3]
            for requirement in SUPPLIER_REQUIREMENTS[supplier.supplier_type]:
                add_document(
                    db,
                    user_id=uploader.id,
                    supplier_id=supplier.id,
                    invoice_id=None,
                    doc_type=requirement,
                    source=demo / "contrato_demo.txt",
                )
        db.commit()

        # Modelo de estatus del ERS (HU-12/13): "Cargada" = obligatorios completos, lista para enviar; el envio de
        # B-EXCEDE no procede por FIN-001. Las facturas enviadas o posteriores llevan submitted_at.
        scenarios = [
            ("BORRADOR-001", None, InvoiceStatus.DRAFT, "Borrador sin documentos"),
            ("A-CORRECTA", "cfdi_demo_correcto.xml", InvoiceStatus.UPLOADED, "Caso A correcto"),
            ("REVISION-001", "cfdi_demo_correcto.xml", InvoiceStatus.UNDER_REVIEW, "Caso en revision"),
            ("ACEPTADA-001", "cfdi_demo_correcto.xml", InvoiceStatus.ACCEPTED, "Caso aceptado"),
            ("C-RFC-ERROR", "cfdi_demo_rfc_incorrecto.xml", InvoiceStatus.REJECTED, "Caso C RFC incorrecto"),
            ("D-SIN-VOBO", "cfdi_demo_correcto.xml", InvoiceStatus.DRAFT, "Caso D falta Vo.Bo."),
            # HU-20: devuelta por el PMO con observaciones, y una segunda factura por decidir.
            ("OBSERVACIONES-001", "cfdi_demo_correcto.xml", InvoiceStatus.REQUIRES_CORRECTION, OBSERVATIONS_NOTE),
            ("ENVIADA-002", "cfdi_demo_correcto.xml", InvoiceStatus.UNDER_REVIEW, "Caso por decidir"),
            ("B-EXCEDE", "cfdi_demo_monto_excedido.xml", InvoiceStatus.UPLOADED, "Caso B excede contrato"),
            ("E-SEMANTICO", "cfdi_demo_correcto.xml", InvoiceStatus.UPLOADED, "Caso E semantico mock 0.93"),
        ]
        submitted = {
            InvoiceStatus.UNDER_REVIEW,
            InvoiceStatus.ACCEPTED,
            InvoiceStatus.REJECTED,
            InvoiceStatus.REQUIRES_CORRECTION,
        }
        decided = {InvoiceStatus.ACCEPTED, InvoiceStatus.REJECTED, InvoiceStatus.REQUIRES_CORRECTION}
        for index, (number, xml_name, final_status, note) in enumerate(scenarios, 1):
            invoice = Invoice(
                internal_folio=f"FAC-2026-{index:05d}",
                supplier_id=moral.id,
                uploaded_by=users[2].id,
                contract_id=contracts[0].id,
                invoice_number=number,
                service_period="08/2026",
                purchase_order_number=f"OC-DEMO-{index:03d}",
                project_name=contracts[0].project_name,
                project_leader=contracts[0].project_leader,
                subtotal=Decimal("0"),
                tax=Decimal("0"),
                total=Decimal("0"),
                currency="MXN",
                status=InvoiceStatus.DRAFT,
                comments=note,
            )
            db.add(invoice)
            db.flush()
            if xml_name:
                xml_source = demo / xml_name
                custom_xml = workdir / f"_seed_{index}.xml"
                # Un UUID fiscal distinto por factura, sea cual sea el del XML de origen (UNIQUE en invoices.uuid).
                raw = re.sub(
                    r'UUID="[^"]*"',
                    f'UUID="DEMO{index:04d}-0000-4000-8000-{index:012d}"',
                    xml_source.read_text(encoding="utf-8"),
                )
                custom_xml.write_text(raw, encoding="utf-8")
                add_document(
                    db,
                    user_id=users[2].id,
                    supplier_id=moral.id,
                    invoice_id=invoice.id,
                    doc_type=DocumentType.INVOICE_XML.value,
                    source=custom_xml,
                )
                add_document(
                    db,
                    user_id=users[2].id,
                    supplier_id=moral.id,
                    invoice_id=invoice.id,
                    doc_type=DocumentType.INVOICE_PDF.value,
                    source=pdf,
                )
                add_document(
                    db,
                    user_id=users[2].id,
                    supplier_id=moral.id,
                    invoice_id=invoice.id,
                    doc_type=DocumentType.PURCHASE_ORDER.value,
                    source=demo / "orden_compra_demo.txt",
                )
                if number != "D-SIN-VOBO":
                    add_document(
                        db,
                        user_id=users[2].id,
                        supplier_id=moral.id,
                        invoice_id=invoice.id,
                        doc_type=DocumentType.APPROVAL.value,
                        source=demo / "vobo_demo.txt",
                    )
                db.commit()
                run_validation(db, invoice, users[2].id)
                invoice.status = final_status
                if final_status in submitted:
                    invoice.submitted_at = datetime.now(timezone.utc)
                if final_status in decided:
                    invoice.reviewed_by = users[1].id
                    invoice.reviewed_at = datetime.now(timezone.utc)
                    db.add(
                        Review(
                            invoice_id=invoice.id,
                            reviewer_id=users[1].id,
                            decision=final_status.value,
                            comments=note
                            if final_status == InvoiceStatus.REQUIRES_CORRECTION
                            else f"Decision demo: {note}",
                        )
                    )
            db.add(
                AuditLog(
                    user_id=users[0].id,
                    action="DEMO_SEEDED",
                    entity="Invoice",
                    entity_id=str(invoice.id),
                    new_value={"scenario": note},
                )
            )
            db.commit()
        seed_international(
            db, workdir, demo, passwords["proveedor3@poc.local"], users[0].id, f"FAC-2026-{len(scenarios) + 1:05d}"
        )
        print("Seed completo: 5 usuarios, 3 proveedores, 3 contratos y 11 facturas demo.")


if __name__ == "__main__":
    main()
