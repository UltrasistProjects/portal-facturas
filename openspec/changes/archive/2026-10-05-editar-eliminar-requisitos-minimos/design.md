## Context

Las tres pantallas de "Requisitos mínimos" comparten estructura: tabla de configuración por niveles, alta de tipos, lista desplegable de tipos definidos por el Administrador con edición y "Desactivar", y tabla "Tipos inactivos" con "Reactivar". Cada una tiene su servicio (`document_requirements_service`, `supplier_requirements_service`, `contract_requirements_service`) con `_lock` (advisory lock de la configuración), `_support_type`/`_admin_type` (404 / 409 de tipo del sistema), `update_type`, `set_active` y auditoría. `documents.document_type` guarda la clave del tipo sin FK, porque la columna mezcla claves de los tres catálogos.

## Goals / Non-Goals

**Goals:**
- Editar y Eliminar visibles en cada fila de las tres pantallas, con el mismo comportamiento.
- Eliminar sin dejar documentos con claves huérfanas.

**Non-Goals:**
- Borrado lógico nuevo (ya existe la desactivación).
- Editar o eliminar tipos del sistema; editar niveles fuera de la tabla de configuración.

## Decisions

**D1. Borrado físico sólo de tipos sin documentos.** `delete_type(db, type_id, user_id)` toma el `_lock`, obtiene el tipo con `_support_type`/`_admin_type` (404 si no existe; 409 si es del sistema, con el mensaje propio "Los elementos del sistema no se pueden eliminar") y revisa `EXISTS (SELECT 1 FROM documents WHERE document_type = :code)` sin filtrar por vigencia. Si existe, 409 "El tipo ya tiene documentos cargados; desactívelo en su lugar". Si no, audita `*_DOCUMENT_TYPE_DELETED` con la fotografía del tipo y hace `db.delete`.
- *Alternativa:* borrado lógico (`deleted_at`). Se descarta: duplicaría la desactivación y obligaría a filtrar en todas las consultas del catálogo.
- *Alternativa:* borrar también los documentos. Se descarta: pierde evidencia de facturas, expedientes y contratos.
- Como la clave es `SOPORTE_<id>` / `REQUISITO_<id>` / `REQ_CONTRATO_<id>` y los id no se reutilizan, una clave eliminada no vuelve a aparecer.

**D2. Carrera entre carga y eliminación.** La carga documental no toma el `_lock` de configuración. Para que una carga concurrente no deje un documento con una clave recién borrada, la carga de un tipo definido por el Administrador relee el tipo con `SELECT ... FOR SHARE` (o `FOR KEY SHARE`) y `delete_type` lo bloquea con `FOR UPDATE` antes de revisar los documentos. La carga que pierde la carrera responde como hoy con un tipo inexistente.

**D3. Rutas.** `POST /admin/<pantalla>/types/{id}/delete`, con `require_admin` y CSRF como las demás; redirección con `?ok=deleted` y el aviso "Tipo eliminado". Los errores reutilizan `_<pantalla>_error` para pintar la página con el código de estado.

**D4. Interfaz.** Se agrega una columna "Acciones" en la tabla de configuración y en la de inactivos. "Editar" es un enlace a `#editar-<id>` que abre el `<details id="editar-<id>">` del formulario existente (el bloque "Tipos soporte" pasa a incluir también los inactivos). "Eliminar" es un `<details>` con el texto "¿Eliminar «<nombre>»? Esta acción no se puede deshacer." y el botón de envío, sin JavaScript en línea, para respetar la CSP. Los estilos van en `app.css`.

## Risks / Trade-offs

- [El Administrador elimina un tipo que esperaba conservar] → confirmación con el nombre, auditoría con la fotografía completa y sólo procede si no hay documentos.
- [Tipos sin documentos referidos desde otra parte, p. ej. reglas o resultados de validación por clave] → revisar en la implementación las referencias por clave (`grep` de `SOPORTE_`, `REQUISITO_`, `REQ_CONTRATO_`) y, si existen, incluirlas en la revisión de uso de D1.
- [Cambio de `config_version`] → al borrar una fila cambia la versión de la configuración; un formulario de niveles abierto en otra pestaña recibe el 409 de edición concurrente que ya existe.

## Migration Plan

Sin migración de esquema. Despliegue normal; para revertir basta con retirar las rutas y los botones.
