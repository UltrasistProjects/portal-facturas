## 1. Servicios

- [x] 1.1 `document_requirements_service.py`: `delete_type` con `_lock`, bloqueo de la fila, 404/409 del sistema ("Los elementos del sistema no se pueden eliminar"), 409 si hay documentos con la clave, auditoría `INVOICE_DOCUMENT_TYPE_DELETED` y borrado (D1, D2).
- [x] 1.2 `supplier_requirements_service.py`: `delete_type` equivalente con `SUPPLIER_DOCUMENT_TYPE_DELETED`.
- [x] 1.3 `contract_requirements_service.py`: `delete_type` equivalente con `CONTRACT_DOCUMENT_TYPE_DELETED`.
- [x] 1.4 Carga documental de factura, expediente y contrato: releer el tipo definido por el Administrador con bloqueo compartido para evitar la carrera con la eliminación (D2).
- [x] 1.5 Revisar otras referencias por clave a tipos definidos por el Administrador y sumarlas a la verificación de uso si existen.

## 2. Rutas

- [x] 2.1 `app/routers/admin.py`: `POST /admin/required-documents/types/{id}/delete`, `/admin/supplier-requirements/types/{id}/delete` y `/admin/contract-requirements/types/{id}/delete` con Administrador y CSRF; aviso "deleted" → "Tipo eliminado" (D3).

## 3. Vistas

- [x] 3.1 `admin/required_documents.html`: columna "Acciones" con "Editar" y "Eliminar" (confirmación con el nombre) en configuración e inactivos; formularios de edición también para inactivos; sin acciones en tipos del sistema (D4).
- [x] 3.2 `admin/supplier_requirements.html`: mismas acciones.
- [x] 3.3 `admin/contract_requirements.html`: mismas acciones.
- [x] 3.4 `app.css`: estilos de la columna de acciones y del bloque de confirmación, sin estilos en línea.

## 4. Pruebas

- [x] 4.1 `tests/test_archivos_minimos.py`: eliminación sin documentos, con documento vigente y reemplazado (409), tipo del sistema (409), inexistente (404), sin CSRF y con PMO/Proveedor (403), auditoría y ausencia de auditoría en rechazos, acciones visibles sólo en tipos del Administrador, edición de un tipo inactivo.
- [x] 4.2 `tests/test_requisitos_alta.py`: los mismos casos para requisitos de alta del proveedor.
- [x] 4.3 `tests/test_requisitos_contrato.py`: los mismos casos para requisitos del contrato.
- [x] 4.4 Suite Playwright de HUs (`tests/hu/specs`): editar y eliminar un tipo en cada pantalla, incluida la cancelación de la confirmación.

## 5. Documentación y verificación

- [x] 5.1 `README.md`: acciones Editar y Eliminar y la regla de eliminación.
- [ ] 5.2 `python scripts/check.py` en verde.
