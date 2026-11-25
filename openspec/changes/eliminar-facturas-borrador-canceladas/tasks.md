## 1. Eliminación

- [x] 1.1 `invoice_deletion_service`: bloqueo de la fila, estatus Borrador o Cancelada (409), confirmación (400), borrado de revisiones, validaciones, documentos, `stored_files` y factura con sentencias explícitas, y `INVOICE_DELETED` en la bitácora
- [x] 1.2 `LocalFileStorage.discard`: archivos y carpetas vacías, después del commit
- [x] 1.3 `POST /invoices/{id}/delete` para Administrador y Proveedor (PMO 403, otro proveedor 404) y redirección al listado con "Factura <folio> eliminada"
- [x] 1.4 Detalle: botón "Eliminar" en la cabecera (`?eliminar=1#deletion` abre el panel sin JavaScript) y panel con la casilla de confirmación
- [x] 1.5 `tests/test_eliminar_factura.py`
