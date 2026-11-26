## MODIFIED Requirements

### Requirement: Prohibición de borrado físico de evidencia fiscal
El sistema MUST NOT permitir el borrado físico de facturas, salvo la eliminación de una factura desde su detalle (spec `flujo-facturas`: el Administrador en cualquier estatus, el proveedor en "Borrador" o "Cancelada"). Esa eliminación SHALL hacerse sólo en su servicio, con sentencias `DELETE` explícitas, y SHALL dejar `INVOICE_DELETED` en la bitácora. Las relaciones de `Invoice` con documentos, validaciones y revisiones MUST NOT declarar `delete-orphan`. Un intento de borrar una factura mediante la unidad de trabajo del ORM SHALL fallar con un error explícito. Las llaves foráneas hacia `invoices` SHALL seguir siendo `RESTRICT`.

#### Scenario: Borrado por ORM
- **WHEN** el código ejecuta `db.delete(invoice)` y hace flush
- **THEN** se lanza un error que indica que el borrado físico de facturas está prohibido y no se elimina ninguna fila

#### Scenario: Quitar un documento de la colección
- **WHEN** el código elimina un documento de `invoice.documents` y hace commit
- **THEN** la fila del documento no se borra

#### Scenario: Eliminación de una factura en Borrador
- **WHEN** el proveedor elimina su factura en "Borrador" desde el detalle
- **THEN** la factura y lo que depende de ella se borran, y la bitácora conserva sus entradas y agrega `INVOICE_DELETED`
