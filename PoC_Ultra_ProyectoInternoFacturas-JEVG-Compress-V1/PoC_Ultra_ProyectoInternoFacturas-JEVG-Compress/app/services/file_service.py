from __future__ import annotations

import codecs
import hashlib
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile
from sqlalchemy import select

from app.core.config import settings
from app.core.database import SessionLocal
from app.models import FileContent

logger = logging.getLogger(__name__)


def _is_pdf(content: bytes) -> bool:
    return content.startswith(b"%PDF-")


def _is_png(content: bytes) -> bool:
    return content.startswith(b"\x89PNG\r\n\x1a\n")


def _is_jpeg(content: bytes) -> bool:
    return content.startswith(b"\xff\xd8\xff")


def _is_xml(content: bytes) -> bool:
    return content.removeprefix(codecs.BOM_UTF8).lstrip().startswith(b"<")


def _is_text(content: bytes) -> bool:
    if b"\x00" in content:
        return False
    try:
        content.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


# Extension -> (MIME canonico, verificador de contenido, nombre para el mensaje). El Content-Type que declara el
# cliente no se usa: la aceptacion y el MIME almacenado dependen del contenido verificado.
FILE_TYPES: dict[str, tuple[str, Callable[[bytes], bool], str]] = {
    ".pdf": ("application/pdf", _is_pdf, "un PDF"),
    ".png": ("image/png", _is_png, "una imagen PNG"),
    ".jpg": ("image/jpeg", _is_jpeg, "una imagen JPEG"),
    ".jpeg": ("image/jpeg", _is_jpeg, "una imagen JPEG"),
    ".xml": ("application/xml", _is_xml, "un XML"),
    ".txt": ("text/plain", _is_text, "un texto UTF-8"),
}
ALLOWED_EXTENSIONS = set(FILE_TYPES)


@dataclass
class StoredFile:
    original_filename: str
    stored_filename: str
    path: Path
    mime_type: str
    file_size: int
    sha256: str
    # Lo que se persiste en documents.path: relativo a la raiz de almacenamiento, con "/".
    relative_path: str


class LocalFileStorage:
    """Archivos bajo la raiz de almacenamiento. Con STORAGE_BACKEND=database el contenido se guarda ademas en
    stored_files y la copia local se rehace al leerla: en Vercel el disco es efimero y no se comparte entre
    instancias. Los lectores reciben siempre una ruta local."""

    def __init__(self, root: Path | None = None, backend: str | None = None):
        self.root = (root or settings.storage_path).resolve()
        self.backend = backend or settings.storage_backend
        self.root.mkdir(parents=True, exist_ok=True)

    def relative_path(self, path: Path) -> str:
        return path.resolve().relative_to(self.root).as_posix()

    def resolve(self, relative_path: str) -> Path:
        """Ruta absoluta de un documento; rechaza rutas que salgan de la raiz (FileNotFoundError)."""
        path = (self.root / relative_path).resolve()
        if self.root not in path.parents:
            raise FileNotFoundError(relative_path)
        if self.backend == "database" and not path.is_file():
            self._restore(path)
        return path

    def store(self, destination: Path, content: bytes) -> None:
        """Escribe el archivo y, con STORAGE_BACKEND=database, guarda su contenido en stored_files."""
        destination.write_bytes(content)
        if self.backend == "database":
            with SessionLocal() as db, db.begin():
                db.add(
                    FileContent(
                        path=self.relative_path(destination),
                        content=content,
                        size=len(content),
                        sha256=hashlib.sha256(content).hexdigest(),
                    )
                )

    def _restore(self, path: Path) -> None:
        """Rehace la copia local desde stored_files; sin contenido guardado, FileNotFoundError."""
        relative = self.relative_path(path)
        with SessionLocal() as db:
            content = db.scalar(select(FileContent.content).where(FileContent.path == relative))
        if content is None:
            raise FileNotFoundError(relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Se escribe aparte y se renombra: otra peticion de la misma instancia puede estar leyendo el mismo archivo.
        partial = path.with_name(f".{uuid4().hex}.partial")
        partial.write_bytes(content)
        partial.replace(path)

    async def save_invoice_file(self, invoice_id: int, upload: UploadFile) -> StoredFile:
        return await self._save("invoices", invoice_id, upload)

    async def save_supplier_file(self, supplier_id: int, upload: UploadFile) -> StoredFile:
        return await self._save("suppliers", supplier_id, upload)

    async def save_contract_file(self, contract_id: int, upload: UploadFile) -> StoredFile:
        return await self._save("contracts", contract_id, upload)

    async def _save(self, scope: str, entity_id: int, upload: UploadFile) -> StoredFile:
        original = Path(upload.filename or "archivo").name
        extension = Path(original).suffix.lower()
        if extension not in ALLOWED_EXTENSIONS:
            raise ValueError("Extension no permitida")
        mime, matches_content, description = FILE_TYPES[extension]
        content = await upload.read(settings.max_upload_mb * 1024 * 1024 + 1)
        if not content:
            raise ValueError("El archivo esta vacio")
        if len(content) > settings.max_upload_mb * 1024 * 1024:
            raise ValueError(f"El archivo excede {settings.max_upload_mb} MB")
        if not matches_content(content):
            raise ValueError(f"El contenido no corresponde a {description}")
        stored = f"{uuid4().hex}{extension}"
        folder = (self.root / scope / str(int(entity_id))).resolve()
        if self.root not in folder.parents:
            raise ValueError("Ruta de almacenamiento invalida")
        folder.mkdir(parents=True, exist_ok=True)
        destination = folder / stored
        self.store(destination, content)
        return StoredFile(
            original,
            stored,
            destination,
            mime,
            len(content),
            hashlib.sha256(content).hexdigest(),
            self.relative_path(destination),
        )


def log_upload(document_type: str, stored: StoredFile, **owner) -> None:
    """Evento document.uploaded sin nombre original ni contenido: solo tipo, extension y tamano."""
    logger.info(
        "document.uploaded",
        extra={
            "event": "document.uploaded",
            **owner,
            "document_type": document_type,
            "extension": stored.path.suffix,
            "size_bytes": stored.file_size,
        },
    )


def safe_download_name(name: str) -> str:
    return re.sub(r"[^\w. -]", "_", Path(name).name, flags=re.UNICODE)
