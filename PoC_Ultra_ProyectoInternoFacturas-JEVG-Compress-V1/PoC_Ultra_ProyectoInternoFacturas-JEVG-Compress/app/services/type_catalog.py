"""Operaciones comunes de los catalogos de Requisitos minimos: archivos de factura (HU-04), requisitos de alta del
proveedor (HU-21) y del contrato (HU-22).

Cualquier tipo, del sistema o del Administrador, se edita y se elimina (ajustes-finales-configuracion). Eliminar es
una baja logica: is_active = false con la fecha y el autor de la baja; la fila se conserva, de modo que los documentos
ya cargados y el historial siguen resolviendo su clave. Restaurar la revierte con los niveles que tenia.

Toda escritura toma el bloqueo consultivo de su catalogo. Estas funciones no confirman la transaccion.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import violates
from app.core.errors import BusinessRuleError, NotFoundError
from app.models import now_utc
from app.services.audit_service import audit


def share_lock(db: Session, model, type_id: int) -> None:
    """Bloqueo compartido de la fila del tipo durante una carga: una eliminacion concurrente espera al commit."""
    db.execute(select(model.id).where(model.id == type_id).with_for_update(key_share=True, read=True))


@dataclass(frozen=True)
class TypeCatalog:
    """Un catalogo de tipos de documento: su modelo, su bloqueo y los textos y acciones de auditoria que usa."""

    model: Any
    entity: str
    action_prefix: str
    lock_key: int
    name_index: str
    duplicate_message: str
    not_found_message: str

    def lock(self, db: Session) -> None:
        db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": self.lock_key})

    def get(self, db: Session, type_id: int, *, for_update: bool = False):
        document_type = db.get(self.model, type_id, with_for_update=for_update)
        if document_type is None:
            raise NotFoundError(self.not_found_message)
        return document_type

    def ensure_unique_name(self, db: Session, name: str, exclude_id: int | None = None) -> None:
        """Nombre unico sin distinguir mayusculas, entre todos los tipos (tambien los eliminados)."""
        stmt = select(self.model.id).where(func.lower(self.model.name) == name.lower())
        if exclude_id is not None:
            stmt = stmt.where(self.model.id != exclude_id)
        if db.scalar(stmt) is not None:
            raise BusinessRuleError(self.duplicate_message)

    def flush(self, db: Session) -> None:
        """flush que traduce la unicidad del nombre a 409 (la BD es la autoridad aunque el servicio ya lo verifico)."""
        try:
            db.flush()
        except IntegrityError as exc:
            db.rollback()
            if violates(exc, self.name_index):
                raise BusinessRuleError(self.duplicate_message) from exc
            raise

    def update(self, db: Session, type_id: int, user_id: int, values: Mapping[str, Any]) -> bool:
        """Edita los campos de un tipo (con `name`) y audita los que cambiaron. True si hubo cambios."""
        self.lock(db)
        document_type = self.get(db, type_id)
        self.ensure_unique_name(db, values["name"], exclude_id=document_type.id)
        old, new = {}, {}
        for attr, after in values.items():
            before = getattr(document_type, attr)
            if before != after:
                old[attr], new[attr] = before, after
        if not new:
            return False
        for attr, value in new.items():
            setattr(document_type, attr, value)
        self.flush(db)
        audit(db, f"{self.action_prefix}_UPDATED", self.entity, document_type.id, user_id, old, new)
        return True

    def delete(self, db: Session, type_id: int, user_id: int) -> bool:
        """Baja logica. False, sin auditar, si ya estaba eliminado."""
        return self._set_deleted(db, type_id, user_id, deleted=True)

    def restore(self, db: Session, type_id: int, user_id: int) -> bool:
        """Revierte la baja logica. False, sin auditar, si el tipo esta activo."""
        return self._set_deleted(db, type_id, user_id, deleted=False)

    def _set_deleted(self, db: Session, type_id: int, user_id: int, *, deleted: bool) -> bool:
        self.lock(db)
        # FOR UPDATE: una carga concurrente tiene la fila FOR KEY SHARE (share_lock) y termina antes de la baja.
        document_type = self.get(db, type_id, for_update=True)
        if document_type.is_active != deleted:
            return False
        document_type.is_active = not deleted
        document_type.deleted_at, document_type.deleted_by = (now_utc(), user_id) if deleted else (None, None)
        action = "DELETED" if deleted else "RESTORED"
        audit(
            db,
            f"{self.action_prefix}_{action}",
            self.entity,
            document_type.id,
            user_id,
            {"is_active": deleted},
            {"is_active": not deleted},
        )
        return True
