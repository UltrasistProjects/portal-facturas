## Why

Una factura en "Borrador" nunca se envió y una "Cancelada" ya no sigue su curso, pero no había forma de quitarlas del portal: la regla de integridad prohíbe el borrado físico de facturas. En las pruebas, además, el UUID y el número de una factura quedan ocupados y la misma factura no se puede volver a registrar. Hasta ahora se borraban a mano en la base.

## What Changes

- Botón **Eliminar** en el detalle de una factura en "Borrador" o "Cancelada", para el Administrador (cualquier factura) y para el proveedor dueño. El PMO no lo tiene.
- `POST /invoices/{id}/delete` con confirmación obligatoria: borra la factura con sus documentos (y su contenido en `stored_files`), sus resultados de validación y sus revisiones, y los archivos del disco después de confirmar en la base.
- La bitácora conserva las entradas de la factura y agrega `INVOICE_DELETED` con sus datos. El registro de correos se conserva.
- El UUID y el número quedan libres.
- La prohibición de borrado físico se mantiene para todo lo demás: el borrado por la unidad de trabajo del ORM sigue fallando y las llaves foráneas siguen siendo RESTRICT.

## Capabilities

### New Capabilities

_Ninguna._

### Modified Capabilities

- `flujo-facturas`: eliminación de una factura en Borrador o Cancelada.
- `integridad-datos`: la prohibición de borrado físico admite esa única excepción.

## Impact

`app/services/invoice_deletion_service.py` (nuevo), `app/services/file_service.py` (`discard`), `app/routers/invoices.py`, `app/templates/invoices/detail.html` y `list.html`, `tests/test_eliminar_factura.py`. Sin migraciones.
