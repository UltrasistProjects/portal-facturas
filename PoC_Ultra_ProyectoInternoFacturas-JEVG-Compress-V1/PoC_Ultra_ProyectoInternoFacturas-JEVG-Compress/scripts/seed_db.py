from __future__ import annotations

import hashlib
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import fitz
from sqlalchemy import select

from app.core.config import settings
from app.core.constants import (
    CANCELLATION_WINDOW,
    PAYMENT_COMPLEMENT_WINDOW,
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
from app.models import AuditLog, Document, Invoice, Review, Supplier, User
from app.services import identity_service as identity
from app.services import invoice_extraction_service as extraction
from app.services import purchase_order_service as purchase_orders
from app.services import supplier_requirements_service as requirements
from app.services.file_service import LocalFileStorage
from app.services.keycloak_admin import IdentityAdmin, IdentityProviderError, get_identity_admin
from app.services.pdf_service import analyze_pdf
from app.services.validation_engine import run_validation
from scripts import cfdi_demo

# Observaciones del PMO de la factura demo OBSERVACIONES-001: las ve el proveedor para corregir y reenviar.
OBSERVATIONS_NOTE = "Falta el Vo.Bo. firmado del lider de proyecto."

# --- Ordenes de compra demo (HU-24) ------------------------------------------------------------------------------
# Las ordenes vienen de SAP: aqui se siembran con sus etiquetas. Las nacionales se ligan al proveedor por RFC; la del
# proveedor internacional, por supplier_id (su RFC en SAP es generico).
MORAL_RFC, MORAL_NAME = "TIC210101ABC", "TECNOLOGIA INTEGRAL DEL CENTRO SA DE CV"
# Convenio de la orden de cada factura demo del proveedor moral: SCENARIO_ORDER_BASE + numero de escenario.
SCENARIO_ORDER_BASE = 45001000
WITHOUT_DELIVERY_ORDER, TWO_ITEMS_ORDER, FOREIGN_ORDER = 45001101, 45001102, 45009042
# Recorrido manual de data/pruebas-ferromex: proveedor que se da de alta en el recorrido (sin supplier_id al sembrar).
WALKTHROUGH_RFC, WALKTHROUGH_NAME = "GAVH810417Q42", "HECTOR GARZA VILLARREAL"
WALKTHROUGH_ORDERS = {"A-1001": 45000451, "A-1002": 45000452}
# Set de prueba de data/pruebas-pdf-orden-compra (extraccion del PDF y comparacion contra la orden): proveedor moral
# que tambien se da de alta en la prueba. Una orden por caso; la 45000611 la citan el caso 1 y el 4 (ya facturada).
PDF_TEST_RFC, PDF_TEST_NAME = "MFB140325AB1", "MANTENIMIENTO FERROVIARIO DEL BAJIO"
PDF_TEST_ORDERS = {
    "correcta": 45000611,
    "monto": 45000612,
    "sin-entrada": 45000613,
    "receptor": 45000614,
    "escaneada": 45000615,
    "sin-orden": 45000616,
}


def order_item(
    text: str,
    price: str,
    *,
    material: str,
    quantity: str = "1",
    unit: str = "SER",
    currency="MXN",
    delivered: tuple[str, str] | None = ("5000527001", "31.07.2026"),
    group: str = "SERVICIOS TI",
    store: str = "CDMX_CORP",
    due: str = "31.07.2026",
) -> dict:
    item = {
        "Material": material,
        "Txt.brv": text,
        "Ctd.Pedido": quantity,
        "Unidad.Pedido": unit,
        "Fe.Entrega": due,
        "Prc.Neto": price,
        "Moneda": currency,
        "Grupo.Art": group,
        "Almacen": store,
        "Docto Material": delivered[0] if delivered else "",
        "Fecha Conta": delivered[1] if delivered else "",
    }
    return item


# Orden del ejemplo de la solicitud (convenio 25704872, seccion 2 de la HU-24).
EXAMPLE_ORDER = {
    "convenio": 25704872,
    "rfc": "GOHS60031745A",
    "supplier_name": "SOCORRO PATRICIA GONZALEZ HERNANDEZ",
    "order_date": date(2025, 12, 9),
    "total": Decimal("3559.05"),
    "taxes": Decimal("569.45"),
    "items": [
        order_item(
            "LTH TIPO L-31 T-900 AR",
            "3559.05",
            material="E20080",
            unit="PZA",
            delivered=("5000527117", "16.12.2025"),
            group="ELECTRICO",
            store="GUADALAJARA_1 STATION 1",
            due="30.12.2025",
        )
    ],
}
POWER_AUTOMATE = "SERVICIOS DESARROLLO POWER AUTOMATE"


def moral_order(convenio: int, **changes) -> dict:
    """Orden de servicios del proveedor moral que cuadra con cfdi_demo.DEMO_MORAL (100,000.00 + IVA)."""
    return {
        "convenio": convenio,
        "rfc": MORAL_RFC,
        "supplier_name": MORAL_NAME,
        "order_date": date(2026, 7, 20),
        "total": Decimal("100000.00"),
        "taxes": Decimal("16000.00"),
        "items": [order_item(POWER_AUTOMATE, "100000.00", material="S-PA-0800")],
        **changes,
    }


def pdf_test_orders() -> list[dict]:
    """Ordenes del set de prueba de extraccion del PDF (data/pruebas-pdf-orden-compra/INSTRUCTIVO.md)."""

    def order(key: str, day: date, total: str, items: list[dict]) -> dict:
        amount = Decimal(total)
        return {
            "convenio": PDF_TEST_ORDERS[key],
            "rfc": PDF_TEST_RFC,
            "supplier_name": PDF_TEST_NAME,
            "order_date": day,
            "total": amount,
            "taxes": (amount * Decimal("0.16")).quantize(Decimal("0.01")),
            "items": items,
        }

    service = {"group": "MANTTO EQUIPO", "store": "QRO_PATIO"}
    parts = {"unit": "PZA", "group": "REFACCIONES", "store": "QRO_ALMACEN"}
    return [
        order(
            "correcta",
            date(2026, 10, 6),
            "123000.00",
            [
                order_item(
                    "MANTENIMIENTO PREVENTIVO LOCOMOTORA",
                    "85000.00",
                    material="S-MPL-4400",
                    delivered=("5000540611", "30.10.2026"),
                    due="31.10.2026",
                    **service,
                ),
                order_item(
                    "ZAPATA DE FRENO COMPOSITE",
                    "950.00",
                    material="R-ZFC-0950",
                    quantity="40",
                    delivered=("5000540612", "28.10.2026"),
                    due="31.10.2026",
                    **parts,
                ),
            ],
        ),
        order(
            "monto",
            date(2026, 10, 13),
            "60000.00",
            [
                order_item(
                    "REVISION SISTEMA DE FRENOS DE AIRE",
                    "60000.00",
                    material="S-RFA-0600",
                    delivered=("5000540613", "06.11.2026"),
                    due="07.11.2026",
                    **service,
                )
            ],
        ),
        order(
            "sin-entrada",
            date(2026, 10, 20),
            "33600.00",
            [
                order_item(
                    "RODAMIENTO PARA EJE DE CARRO TOLVA",
                    "4200.00",
                    material="R-RET-4200",
                    quantity="8",
                    delivered=None,
                    due="15.12.2026",
                    **parts,
                )
            ],
        ),
        order(
            "receptor",
            date(2026, 10, 27),
            "42000.00",
            [
                order_item(
                    "INSPECCION ULTRASONICA DE RUEDAS",
                    "42000.00",
                    material="S-IUR-4200",
                    delivered=("5000540614", "12.11.2026"),
                    due="14.11.2026",
                    **service,
                )
            ],
        ),
        order(
            "escaneada",
            date(2026, 11, 3),
            "27500.00",
            [
                order_item(
                    "CALIBRACION DE BASCULA DE VIA",
                    "27500.00",
                    material="S-CBV-2750",
                    delivered=("5000540615", "14.11.2026"),
                    due="14.11.2026",
                    **service,
                )
            ],
        ),
        order(
            "sin-orden",
            date(2026, 11, 4),
            "38000.00",
            [
                order_item(
                    "MANTENIMIENTO CORRECTIVO LOCOMOTORA",
                    "38000.00",
                    material="S-MCL-4400",
                    delivered=("5000540616", "13.11.2026"),
                    due="14.11.2026",
                    **service,
                )
            ],
        ),
    ]


def demo_orders() -> list[dict]:
    """Ordenes que no dependen de una factura demo: la del ejemplo, una sin entrada de mercancia, una con dos partidas,
    las del recorrido manual y las del set de prueba de extraccion del PDF."""
    walkthrough = {
        "rfc": WALKTHROUGH_RFC,
        "supplier_name": WALKTHROUGH_NAME,
        "order_date": date(2026, 10, 1),
        "total": Decimal("45000.00"),
        "taxes": Decimal("7200.00"),
    }
    monitoring = "MONITOREO DE FLOTA FERROVIARIA"
    return [
        EXAMPLE_ORDER,
        moral_order(
            WITHOUT_DELIVERY_ORDER,
            items=[order_item(POWER_AUTOMATE, "100000.00", material="S-PA-0800", delivered=None, due="30.11.2026")],
        ),
        moral_order(
            TWO_ITEMS_ORDER,
            total=Decimal("8000.00"),
            taxes=Decimal("1280.00"),
            items=[
                order_item("LICENCIAS POWER APPS PREMIUM", "500.00", material="L-PAP-01", quantity="10", unit="PZA"),
                order_item("CAPACITACION POWER APPS", "3000.00", material="S-CAP-01"),
            ],
        ),
        {
            **walkthrough,
            "convenio": WALKTHROUGH_ORDERS["A-1001"],
            "items": [order_item(monitoring, "45000.00", material="S-MFF-10", delivered=("5000531451", "31.10.2026"))],
        },
        {
            **walkthrough,
            "convenio": WALKTHROUGH_ORDERS["A-1002"],
            "order_date": date(2026, 11, 3),
            "items": [order_item(monitoring, "45000.00", material="S-MFF-11", delivered=("5000531452", "18.11.2026"))],
        },
        *pdf_test_orders(),
    ]


def create_foreign_invoice_pdf(path: Path) -> None:
    """Invoice demo del proveedor internacional: su texto trae los datos que buscan las reglas INT (HU-16)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    page = doc.new_page()
    lines = [
        ("INVOICE INV-2026-0042 - FICTITIOUS DEMO DOCUMENT, NO FISCAL VALIDITY", 12),
        ("From: Global Data Services Inc. (DEMO) - Tax ID 98-7654321 - Austin, TX, USA", 11),
        ("Bill to: INTERMODAL MEXICO - Ciudad de Mexico, C.P. 11700, Mexico", 11),
        ("Invoice date: 2026-08-31 / Service period: August 2026", 11),
        ("Data analytics consulting - PO: OC/45009042", 11),
        ("Subtotal USD 18,000.00 / Tax USD 0.00 / Total USD 18,000.00", 11),
    ]
    for index, (text, size) in enumerate(lines):
        page.insert_text((72, 90 + 25 * index), text, fontsize=size)
    doc.save(path)
    doc.close()


def create_cancellation_ack_pdf(path: Path) -> None:
    """Acuse de cancelacion demo de la factura CANCELADA-001 (HU-14)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 90), "ACUSE DE CANCELACION FICTICIO - SIN VALIDEZ FISCAL", fontsize=12)
    page.insert_text((72, 125), "Factura CANCELADA-001 / Tecnologia Integral del Centro SA de CV", fontsize=11)
    page.insert_text((72, 150), "Estatus de la solicitud: En proceso (aceptacion del receptor pendiente)", fontsize=11)
    doc.save(path)
    doc.close()


def demo_user(
    db,
    idp: IdentityAdmin,
    *,
    name: str,
    email: str,
    role: Role,
    password: str,
    temporary: bool,
    supplier_id: int | None = None,
) -> User:
    """Usuario demo del portal enlazado a su cuenta de Keycloak, creada o reutilizada (add-keycloak-authentication).
    Sin password_hash: la credencial vive solo en Keycloak (RN-HU03-01)."""
    existing = idp.find_by_email(email)
    if existing is not None:
        # Al reconstruir la demo (reset_demo) la cuenta ya tiene esta contrasena, y la politica passwordHistory del
        # realm rechaza volver a ponerla: primero pasa por una aleatoria.
        idp.set_password(existing.id, generate_password(), temporary=True)
    account = identity.provision(db, idp, email=email, role=role, password=password, temporary=temporary)
    return User(name=name, email=email, role=role, supplier_id=supplier_id, keycloak_sub=account.sub)


def seed_international(
    db, workdir: Path, demo: Path, account: tuple[IdentityAdmin, str, bool], admin_id: int, folio: str
) -> None:
    """Proveedor internacional autorizado con su usuario, una orden de compra en USD y la factura INV-2026-0042 en
    "Cargada": Invoice en PDF con los importes capturados, su orden de compra y Vo.Bo. Su envio procede (HU-15/16,
    HU-24)."""
    supplier = Supplier(
        business_name="Global Data Services Inc. (DEMO)",
        rfc=None,
        origin=SupplierOrigin.INTERNATIONAL,
        foreign_tax_id="98-7654321",
        country="US",
        supplier_type=SupplierType.PERSONA_MORAL,
        # Demo: el proveedor nace "Registrado" (Supplier.status); el seed lo deja autorizado de forma explicita.
        status="ACTIVE",
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
    idp, password, temporary = account
    user = demo_user(
        db,
        idp,
        name="Proveedor Internacional Demo",
        email="proveedor3@poc.local",
        role=Role.PROVEEDOR,
        password=password,
        temporary=temporary,
        supplier_id=supplier.id,
    )
    db.add(user)
    purchase_orders.create(
        db,
        convenio=FOREIGN_ORDER,
        rfc="XEXX010101000",
        supplier_name=supplier.business_name,
        order_date=date(2026, 8, 1),
        total=Decimal("18000.00"),
        taxes=Decimal("0.00"),
        items=[
            order_item(
                "DATA ANALYTICS CONSULTING",
                "18000.00",
                material="S-DAC-01",
                currency="USD",
                delivered=("5000529042", "31.08.2026"),
            )
        ],
        supplier_id=supplier.id,
    )
    invoice = Invoice(
        internal_folio=folio,
        supplier_id=supplier.id,
        uploaded_by=user.id,
        invoice_number="INV-2026-0042",
        invoice_date=date(2026, 8, 31),
        service_period="08/2026",
        purchase_order_number=str(FOREIGN_ORDER),
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
    sources = [(DocumentType.FOREIGN_INVOICE, invoice_pdf), (DocumentType.APPROVAL, demo / "vobo_demo.txt")]
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
            new_value={"scenario": "Caso internacional: Invoice en PDF listo para enviar contra su orden de compra"},
        )
    )
    db.commit()


def audit_entry(user_id: int, action: str, invoice_id: int, at: datetime) -> AuditLog:
    return AuditLog(user_id=user_id, action=action, entity="Invoice", entity_id=str(invoice_id), timestamp=at)


def add_document(
    db,
    *,
    user_id: int,
    supplier_id: int | None,
    invoice_id: int | None,
    doc_type: str,
    source: Path,
) -> Document:
    """Documento demo de una factura o del expediente de un proveedor."""
    content = source.read_bytes()
    storage = LocalFileStorage()
    scope, owner = ("invoices", invoice_id) if invoice_id else ("suppliers", supplier_id)
    folder = storage.root / scope / str(owner)
    folder.mkdir(parents=True, exist_ok=True)
    destination = (
        folder / f"demo_{hashlib.sha256((str(invoice_id) + doc_type).encode()).hexdigest()[:10]}{source.suffix}"
    )
    storage.store(destination, content)
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


def scenario_cfdi(index: int, kind: str, convenio: int) -> dict:
    """CFDI de la factura demo `index` del proveedor moral: un UUID y un folio propios y el convenio de su orden."""
    changes = dict(cfdi_demo.DEMO_FILES[kind])
    concept = {**changes.pop("concept", {}), "description": f"08 Servicios desarrollo Power Automate (OC/{convenio})"}
    changes.update(uuid=f"DEMO{index:04d}-0000-4000-8000-{index:012d}", folio=str(1000 + index), concept=concept)
    return cfdi_demo.variant(cfdi_demo.DEMO_MORAL, **changes)


def seed_passwords(passwords: dict[str, str] | None = None) -> tuple[dict[str, str], bool]:
    """Contrasenas por correo y si son temporales. Explicitas (pruebas) o DEMO_PASSWORD del .env en development, sin
    accion requerida; en otro entorno, aleatorias temporales que se muestran una sola vez. Ninguna esta en el
    repositorio."""
    if passwords is not None:
        return {account.email: passwords[account.email] for account in DEMO_ACCOUNTS}, False
    if settings.app_env == "development":
        demo_password = settings.demo_password.get_secret_value()
        if not demo_password:
            raise SystemExit("DEMO_PASSWORD es obligatoria en development: ejecute python scripts/create_env.py.")
        return {account.email: demo_password for account in DEMO_ACCOUNTS}, False
    generated = {account.email: generate_password() for account in DEMO_ACCOUNTS}
    print("Contrasenas temporales de los usuarios sembrados (se muestran una sola vez; Keycloak pedira cambiarlas):")
    for email, password in generated.items():
        print(f"  {email}: {password}")
    return generated, True


def main(passwords: dict[str, str] | None = None) -> None:
    """Siembra la demo. `passwords` (correo -> contrasena) fija las contrasenas de los usuarios sembrados en Keycloak.
    Keycloak debe estar disponible: las cuentas demo se crean o se enlazan alli."""
    try:
        _seed(passwords)
    except IdentityProviderError as exc:
        raise SystemExit(
            f"Keycloak no respondio ({exc.operation}: {exc.code}). Levantelo con `docker compose up -d --wait keycloak`"
            " y vuelva a ejecutar el seed; la base no se modifico."
        ) from None
    except identity.AccountConflict as exc:
        raise SystemExit(f"{exc.message} Revise las cuentas @poc.local en Keycloak.") from None


def _seed(passwords: dict[str, str] | None) -> None:
    demo = ROOT / "data" / "demo_documents"
    with tempfile.TemporaryDirectory(prefix="seed_") as tmp, SessionLocal() as db:
        workdir = Path(tmp)
        if db.scalar(select(User.id).limit(1)):
            print("La base ya contiene datos; use scripts/reset_demo.py para reconstruirla.")
            return
        passwords, temporary = seed_passwords(passwords)
        idp = get_identity_admin()
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
            # Emisor de la factura 3668 del ejemplo de la solicitud (HU-24): la demo la registra con su PDF contra la
            # orden de compra 25704872.
            business_name=EXAMPLE_ORDER["supplier_name"],
            rfc=EXAMPLE_ORDER["rfc"],
            supplier_type=SupplierType.PERSONA_FISICA,
            email="proveedor2@poc.local",
            phone="555-0102",
            status="ACTIVE",
            confidentiality_agreement=True,
            economic_proposal=True,
            bank_information="CLABE DEMO terminacion 0002",
            notes="Proveedor de la factura de ejemplo de la solicitud (HU-24), para pruebas.",
            classification=SupplierClassification.EXTERNAL,
            main_activity="54",
            # Persona fisica: su representante legal es ella misma.
            legal_rep_name=EXAMPLE_ORDER["supplier_name"],
            legal_rep_phone="555-0102",
            contact_name=EXAMPLE_ORDER["supplier_name"],
            contact_phone="555-0102",
        )
        db.add_all([moral, physical])
        db.flush()
        users = [
            demo_user(
                db,
                idp,
                name="Administrador Demo",
                email="admin@poc.local",
                role=Role.ADMINISTRADOR,
                password=passwords["admin@poc.local"],
                temporary=temporary,
            ),
            demo_user(
                db,
                idp,
                name="Analista CxP Demo",
                email="pmo@poc.local",
                role=Role.PMO,
                password=passwords["pmo@poc.local"],
                temporary=temporary,
            ),
            demo_user(
                db,
                idp,
                name="Proveedor Moral Demo",
                email="proveedor1@poc.local",
                role=Role.PROVEEDOR,
                password=passwords["proveedor1@poc.local"],
                temporary=temporary,
                supplier_id=moral.id,
            ),
            demo_user(
                db,
                idp,
                name="Proveedor Fisico Demo",
                email="proveedor2@poc.local",
                role=Role.PROVEEDOR,
                password=passwords["proveedor2@poc.local"],
                temporary=temporary,
                supplier_id=physical.id,
            ),
        ]
        db.add_all(users)
        db.flush()
        # Ordenes de compra demo (HU-24): ejemplo, sin entrega, dos partidas, recorrido manual y set de prueba del PDF.
        for order in demo_orders():
            purchase_orders.create(db, **order)
        # Expediente completo: un documento por cada requisito de alta que aplica al proveedor, segun el catalogo que
        # siembra la migracion (HU-21), incluido Poderes.
        catalog = requirements.catalog(db)
        for supplier in (moral, physical):
            uploader = users[2] if supplier is moral else users[3]
            for requirement in requirements.applicable(catalog, requirements.profile(supplier)):
                add_document(
                    db,
                    user_id=uploader.id,
                    supplier_id=supplier.id,
                    invoice_id=None,
                    doc_type=requirement.code,
                    source=demo / "contrato_demo.txt",
                )
        db.commit()

        # Modelo de estatus del ERS (HU-12/13): "Cargada" = obligatorios completos, lista para enviar; el envio de
        # B-EXCEDE no procede por su orden de compra (OC-005). Cada factura cita su propia orden (HU-24); las enviadas o
        # posteriores llevan submitted_at y quedan ligadas a ella.
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
            ("B-EXCEDE", "cfdi_demo_monto_excedido.xml", InvoiceStatus.UPLOADED, "Caso B excede su orden de compra"),
            ("E-SEMANTICO", "cfdi_demo_correcto.xml", InvoiceStatus.UPLOADED, "Caso E cargada lista para enviar"),
            # HU-14: enviada y cancelada por el proveedor con su acuse; la siembra no envia el correo.
            ("CANCELADA-001", "cfdi_demo_correcto.xml", InvoiceStatus.CANCELLED, "Caso cancelado por el proveedor"),
            # HU Complemento de Pagos: autorizada, pagada (nacional PPD) y con su complemento ya adjuntado. Un
            # complemento pendiente venceria a las 72 horas y bloquearia los envios del proveedor demo.
            ("PAGADA-001", "cfdi_demo_correcto.xml", InvoiceStatus.PAID, "Caso pagado con complemento"),
        ]
        submitted = {
            InvoiceStatus.UNDER_REVIEW,
            InvoiceStatus.ACCEPTED,
            InvoiceStatus.REJECTED,
            InvoiceStatus.REQUIRES_CORRECTION,
            InvoiceStatus.CANCELLED,
            InvoiceStatus.PAID,
        }
        decided = {InvoiceStatus.ACCEPTED, InvoiceStatus.REJECTED, InvoiceStatus.REQUIRES_CORRECTION}
        paid = {InvoiceStatus.PAID}
        for index, (number, xml_name, final_status, note) in enumerate(scenarios, 1):
            convenio = SCENARIO_ORDER_BASE + index
            order = purchase_orders.create(db, **moral_order(convenio)) if xml_name else None
            invoice = Invoice(
                internal_folio=f"FAC-2026-{index:05d}",
                supplier_id=moral.id,
                uploaded_by=users[2].id,
                invoice_number=number,
                service_period="08/2026",
                purchase_order_number=str(convenio) if xml_name else None,
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
                # XML y representacion impresa del mismo CFDI (scripts/cfdi_demo.py), con un UUID fiscal distinto por
                # factura (UNIQUE en invoices.uuid) y el convenio de su orden en el concepto.
                data = scenario_cfdi(index, xml_name, convenio)
                custom_xml = workdir / f"CFDI-{number}.xml"
                custom_xml.write_text(cfdi_demo.invoice_xml(data), encoding="utf-8")
                custom_pdf = workdir / f"CFDI-{number}.pdf"
                custom_pdf.write_bytes(cfdi_demo.invoice_pdf(data))
                add_document(
                    db,
                    user_id=users[2].id,
                    supplier_id=moral.id,
                    invoice_id=invoice.id,
                    doc_type=DocumentType.INVOICE_XML.value,
                    source=custom_xml,
                )
                pdf_document = add_document(
                    db,
                    user_id=users[2].id,
                    supplier_id=moral.id,
                    invoice_id=invoice.id,
                    doc_type=DocumentType.INVOICE_PDF.value,
                    source=custom_pdf,
                )
                # Como el registro por archivos: paginas y datos leidos del PDF (la revision muestra su imagen).
                analysis, pdf_data, source = extraction.read_pdf(custom_pdf)
                pdf_document.page_count = analysis["page_count"]
                pdf_document.metadata_json = extraction.pdf_metadata(analysis, pdf_data, source)
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
                # Sin autoflush: ck_invoices_cancellation exige el estatus y los datos de la cancelacion juntos.
                with db.no_autoflush:
                    provider_id, pmo_id = users[2].id, users[1].id
                    now = datetime.now(timezone.utc)
                    invoice.status = final_status
                    if final_status in submitted:
                        # Envio con su auditoria: el "Seguimiento" (HU-17) lo muestra antes de la decision. La factura
                        # enviada queda ligada a su orden de compra (HU-24).
                        invoice.submitted_at = now - timedelta(hours=2)
                        invoice.purchase_order_id = order.id
                        db.add(audit_entry(provider_id, "INVOICE_SUBMITTED", invoice.id, invoice.submitted_at))
                    if final_status in decided | paid:
                        invoice.reviewed_by = pmo_id
                        invoice.reviewed_at = now - timedelta(hours=1) if final_status in paid else now
                        db.add(
                            Review(
                                invoice_id=invoice.id,
                                reviewer_id=pmo_id,
                                decision=InvoiceStatus.ACCEPTED.value if final_status in paid else final_status.value,
                                comments=note
                                if final_status == InvoiceStatus.REQUIRES_CORRECTION
                                else f"Decision demo: {note}",
                                created_at=now,
                            )
                        )
                    if final_status == InvoiceStatus.CANCELLED:
                        ack_pdf = workdir / "acuse_cancelacion_CANCELADA-001.pdf"
                        create_cancellation_ack_pdf(ack_pdf)
                        add_document(
                            db,
                            user_id=provider_id,
                            supplier_id=moral.id,
                            invoice_id=invoice.id,
                            doc_type=DocumentType.CANCELLATION_ACK.value,
                            source=ack_pdf,
                        )
                        invoice.cancelled_at = now
                        invoice.cancelled_by = provider_id
                        invoice.cancellation_deadline = now + CANCELLATION_WINDOW
                        db.add(audit_entry(provider_id, "INVOICE_CANCELLED", invoice.id, now))
                    if final_status in paid:
                        complement_xml = workdir / "complemento_pago_PAGADA-001.xml"
                        complement_xml.write_text(
                            (demo / "complemento_pago_demo.xml")
                            .read_text(encoding="utf-8")
                            .replace("DEMO0001-0000-4000-8000-000000000001", invoice.uuid),
                            encoding="utf-8",
                        )
                        complement = add_document(
                            db,
                            user_id=provider_id,
                            supplier_id=moral.id,
                            invoice_id=invoice.id,
                            doc_type=DocumentType.PAYMENT_COMPLEMENT_XML.value,
                            source=complement_xml,
                        )
                        invoice.paid_at = now - timedelta(minutes=30)
                        invoice.paid_by = pmo_id
                        invoice.payment_complement_due_at = invoice.paid_at + PAYMENT_COMPLEMENT_WINDOW
                        invoice.payment_complement_received_at = now
                        db.add(audit_entry(pmo_id, "INVOICE_PAID", invoice.id, invoice.paid_at))
                        db.add(audit_entry(provider_id, "PAYMENT_COMPLEMENT_UPLOADED", invoice.id, now))
                        complement.metadata_json = {
                            "voucher_type": "P",
                            "uuid": "DEMOPAGO-0000-4000-8000-000000000001",
                            "related_uuids": [invoice.uuid],
                        }
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
            db,
            workdir,
            demo,
            (idp, passwords["proveedor3@poc.local"], temporary),
            users[0].id,
            f"FAC-2026-{len(scenarios) + 1:05d}",
        )
        orders = len(demo_orders()) + sum(1 for scenario in scenarios if scenario[1]) + 1
        invoices = len(scenarios) + 1
        print(f"Seed completo: 5 usuarios, 3 proveedores, {orders} ordenes de compra y {invoices} facturas demo.")


if __name__ == "__main__":
    main()
