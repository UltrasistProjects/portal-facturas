from __future__ import annotations

import hashlib
import mimetypes
import re
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.core.config import settings

ALLOWED_EXTENSIONS = {".xml", ".pdf", ".txt", ".png", ".jpg", ".jpeg"}
ALLOWED_MIMES = {
    "application/xml",
    "text/xml",
    "application/pdf",
    "text/plain",
    "image/png",
    "image/jpeg",
    "application/octet-stream",
}


@dataclass
class StoredFile:
    original_filename: str
    stored_filename: str
    path: Path
    mime_type: str
    file_size: int
    sha256: str


class LocalFileStorage:
    def __init__(self, root: Path | None = None):
        self.root = (root or settings.storage_path).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    async def save_invoice_file(self, invoice_id: int, upload: UploadFile) -> StoredFile:
        return await self._save("invoices", invoice_id, upload)

    async def save_supplier_file(self, supplier_id: int, upload: UploadFile) -> StoredFile:
        return await self._save("suppliers", supplier_id, upload)

    async def _save(self, scope: str, entity_id: int, upload: UploadFile) -> StoredFile:
        original = Path(upload.filename or "archivo").name
        extension = Path(original).suffix.lower()
        if extension not in ALLOWED_EXTENSIONS:
            raise ValueError("Extension no permitida")
        mime = (upload.content_type or mimetypes.guess_type(original)[0] or "application/octet-stream").lower()
        if mime not in ALLOWED_MIMES:
            raise ValueError("Tipo MIME no permitido")
        content = await upload.read(settings.max_upload_mb * 1024 * 1024 + 1)
        if not content:
            raise ValueError("El archivo esta vacio")
        if len(content) > settings.max_upload_mb * 1024 * 1024:
            raise ValueError(f"El archivo excede {settings.max_upload_mb} MB")
        if extension == ".xml" and not content.lstrip().startswith(b"<"):
            raise ValueError("Contenido XML invalido")
        stored = f"{uuid4().hex}{extension}"
        folder = (self.root / scope / str(int(entity_id))).resolve()
        if self.root not in folder.parents:
            raise ValueError("Ruta de almacenamiento invalida")
        folder.mkdir(parents=True, exist_ok=True)
        destination = folder / stored
        destination.write_bytes(content)
        return StoredFile(original, stored, destination, mime, len(content), hashlib.sha256(content).hexdigest())


def safe_download_name(name: str) -> str:
    return re.sub(r"[^\w. -]", "_", Path(name).name, flags=re.UNICODE)
