import asyncio
import codecs
import io

import pytest
from sqlalchemy import select
from starlette.datastructures import Headers, UploadFile

from app.core.config import settings
from app.core.database import SessionLocal
from app.models import Document
from app.services.file_service import LocalFileStorage
from tests.conftest import ROOT, csrf, invoice_by_number, login

PDF = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n%%EOF\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 16
XML = (ROOT / "data" / "demo_documents" / "cfdi_demo_correcto.xml").read_bytes()


class CountingBytes(io.BytesIO):
    """Registra cuantos bytes se leyeron del cliente."""

    bytes_read = 0

    def read(self, size=-1):
        chunk = super().read(size)
        self.bytes_read += len(chunk)
        return chunk


def upload(content: bytes, filename: str, content_type: str = "application/octet-stream") -> UploadFile:
    return UploadFile(file=CountingBytes(content), filename=filename, headers=Headers({"content-type": content_type}))


@pytest.fixture()
def storage(tmp_path):
    return LocalFileStorage(tmp_path / "storage")


def save(storage, content, filename, content_type="application/octet-stream"):
    return asyncio.run(storage.save_invoice_file(7, upload(content, filename, content_type)))


def stored_files(storage):
    return [path for path in storage.root.rglob("*") if path.is_file()]


def test_ejecutable_renombrado_como_pdf(storage):
    with pytest.raises(ValueError, match="El contenido no corresponde a un PDF"):
        save(storage, b"MZ\x90\x00" + b"\x00" * 64, "contrato.pdf", "application/pdf")
    assert stored_files(storage) == []


def test_pdf_valido_declarado_como_octet_stream(storage):
    stored = save(storage, PDF, "factura.pdf", "application/octet-stream")
    assert stored.mime_type == "application/pdf"
    assert stored.path.read_bytes() == PDF
    assert stored.stored_filename != "factura.pdf" and stored.stored_filename.endswith(".pdf")


@pytest.mark.parametrize(
    ("content", "filename", "mime"),
    [(PNG, "logo.png", "image/png"), (JPEG, "foto.jpg", "image/jpeg"), (JPEG, "foto.jpeg", "image/jpeg")],
)
def test_imagenes_validas(storage, content, filename, mime):
    assert save(storage, content, filename, "text/html").mime_type == mime


@pytest.mark.parametrize(
    ("content", "filename"),
    [
        (JPEG, "foto.png"),
        (PNG, "foto.jpg"),
        (b"hola\x00mundo", "nota.txt"),
        (b"\xff\xfe\xfd", "nota.txt"),
        (b"{}", "x.xml"),
    ],
)
def test_contenido_que_no_corresponde_a_la_extension(storage, content, filename):
    with pytest.raises(ValueError, match="El contenido no corresponde"):
        save(storage, content, filename)
    assert stored_files(storage) == []


def test_xml_con_bom(storage):
    stored = save(storage, codecs.BOM_UTF8 + XML, "cfdi.xml", "text/xml")
    assert stored.mime_type == "application/xml"
    from app.services.xml_service import parse_cfdi

    assert parse_cfdi(stored.path)["receiver_rfc"] == "ULT940623AG0"


@pytest.mark.parametrize("filename", ["script.html", "archivo.exe", "sin_extension"])
def test_extension_no_permitida(storage, filename):
    with pytest.raises(ValueError, match="Extension no permitida"):
        save(storage, PDF, filename)


def test_archivo_vacio(storage):
    with pytest.raises(ValueError, match="vacio"):
        save(storage, b"", "vacio.pdf")


def test_tamano_excedido_con_lectura_acotada(storage, monkeypatch):
    monkeypatch.setattr(settings, "max_upload_mb", 1)
    limit = 1024 * 1024
    file = upload(PDF + b"0" * (limit * 3), "grande.pdf")
    with pytest.raises(ValueError, match="excede 1 MB"):
        asyncio.run(storage.save_invoice_file(7, file))
    assert file.file.bytes_read == limit + 1
    assert stored_files(storage) == []


def test_nombre_del_cliente_no_define_la_ruta(storage):
    stored = save(storage, PDF, "../../../etc/passwd.pdf")
    assert stored.original_filename == "passwd.pdf"
    assert storage.root in stored.path.parents


def test_ruta_fuera_de_la_raiz_rechazada(storage):
    with pytest.raises(ValueError, match="Ruta de almacenamiento invalida"):
        asyncio.run(storage._save("../../fuera", 1, upload(PDF, "x.pdf")))


# --- Endpoints -------------------------------------------------------------------------------------------------


def post_document(client, invoice, content, filename, document_type="ADDITIONAL", content_type="application/pdf"):
    token = csrf(client, f"/invoices/{invoice.id}")
    return client.post(
        f"/invoices/{invoice.id}/documents",
        data={"document_type": document_type, "csrf_token": token},
        files={"upload": (filename, content, content_type)},
        follow_redirects=False,
    )


def test_subida_valida_desde_el_endpoint(client):
    invoice = invoice_by_number("BORRADOR-001")
    login(client, "proveedor1@poc.local")
    response = post_document(client, invoice, PDF, "soporte.pdf", content_type="application/octet-stream")
    assert response.status_code == 303
    with SessionLocal() as db:
        document = db.scalar(
            select(Document).where(Document.invoice_id == invoice.id, Document.original_filename == "soporte.pdf")
        )
    assert document.mime_type == "application/pdf"


def test_subida_rechazada_desde_el_endpoint(client):
    invoice = invoice_by_number("BORRADOR-001")
    login(client, "proveedor1@poc.local")
    response = post_document(client, invoice, b"MZ\x90\x00", "contrato.pdf")
    assert response.status_code == 400
    assert "El contenido no corresponde a un PDF" in response.text


def test_subida_en_estado_no_editable_responde_409(client):
    invoice = invoice_by_number("REVISION-001")
    login(client, "proveedor1@poc.local")
    assert post_document(client, invoice, PDF, "tarde.pdf").status_code == 409


def first_document(invoice):
    with SessionLocal() as db:
        return db.scalar(select(Document).where(Document.invoice_id == invoice.id).order_by(Document.id))


def test_descarga_forzada_como_octet_stream(client):
    invoice = invoice_by_number("A-CORRECTA")
    document = first_document(invoice)
    login(client)
    response = client.get(f"/invoices/{invoice.id}/documents/{document.id}/download")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/octet-stream"
    assert response.headers["content-disposition"].startswith("attachment;")
    assert response.headers["x-content-type-options"] == "nosniff"


def test_proveedor_no_descarga_documentos_ajenos(client):
    invoice = invoice_by_number("A-CORRECTA")  # de proveedor1
    document = first_document(invoice)
    login(client, "proveedor2@poc.local")
    assert client.get(f"/invoices/{invoice.id}/documents/{document.id}/download").status_code == 404


def test_documento_de_otra_factura(client):
    invoice_a = invoice_by_number("A-CORRECTA")
    document_b = first_document(invoice_by_number("ACEPTADA-001"))
    login(client)
    assert client.get(f"/invoices/{invoice_a.id}/documents/{document_b.id}/download").status_code == 404
