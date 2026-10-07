## Why

Las tres pantallas de "Requisitos mínimos" (Archivos de factura, Alta de proveedor y Alta de contrato) ya permiten editar los tipos que define el Administrador, pero la edición está escondida en una lista desplegable aparte de la tabla y no hay forma de eliminar un tipo dado de alta por error: sólo se puede desactivar, y queda para siempre en "Tipos inactivos". El Administrador necesita, en cada fila, las acciones **Editar** y **Eliminar**.

## What Changes

- **Acción "Editar" en cada fila** de las tres pantallas, para los tipos definidos por el Administrador, activos o inactivos. Abre el formulario de edición que ya existe (nombre, descripción y, en archivos de factura, formatos). Los tipos del sistema no muestran la acción.
- **Acción "Eliminar" en cada fila** de los tipos definidos por el Administrador, con un paso de confirmación. Nuevas rutas:
  - `POST /admin/required-documents/types/{id}/delete`
  - `POST /admin/supplier-requirements/types/{id}/delete`
  - `POST /admin/contract-requirements/types/{id}/delete`
- **Eliminación protegida:** un tipo sólo se elimina si ningún documento (vigente o reemplazado) usa su clave. Si ya tiene documentos, la respuesta es HTTP 409 con el mensaje "El tipo ya tiene documentos cargados; desactívelo en su lugar" y el tipo no cambia. Los tipos del sistema nunca se eliminan: HTTP 409 "Los elementos del sistema no se pueden eliminar".
- **Auditoría** de la eliminación: `INVOICE_DOCUMENT_TYPE_DELETED`, `SUPPLIER_DOCUMENT_TYPE_DELETED` y `CONTRACT_DOCUMENT_TYPE_DELETED`, con los datos del tipo eliminado.

**Fuera de alcance:** editar o eliminar tipos del sistema; eliminar documentos cargados; cambiar "admite varios archivos" de un requisito del contrato después del alta.

## Capabilities

### New Capabilities

_Ninguna._

### Modified Capabilities

- `archivos-minimos-factura`: los tipos soporte se pueden eliminar si no tienen documentos; acciones Editar/Eliminar en cada fila; auditoría de la eliminación.
- `requisitos-alta-proveedor`: los requisitos definidos por el Administrador se pueden eliminar si no tienen documentos; acciones Editar/Eliminar; auditoría.
- `requisitos-alta-contrato`: los requisitos del contrato definidos por el Administrador se pueden eliminar si no tienen documentos; acciones Editar/Eliminar; auditoría.

## Impact

- `app/services/document_requirements_service.py`, `supplier_requirements_service.py`, `contract_requirements_service.py`: nueva función `delete_type`.
- `app/routers/admin.py`: tres rutas `.../types/{id}/delete` y avisos "deleted".
- Plantillas `admin/required_documents.html`, `admin/supplier_requirements.html`, `admin/contract_requirements.html`: columna de acciones con Editar y Eliminar.
- Sin migración: la eliminación borra la fila del catálogo; `documents.document_type` no tiene FK y la regla impide borrar tipos en uso.
- Pruebas en `tests/test_archivos_minimos.py`, `tests/test_requisitos_alta.py`, `tests/test_requisitos_contrato.py` y suite Playwright de HUs.
