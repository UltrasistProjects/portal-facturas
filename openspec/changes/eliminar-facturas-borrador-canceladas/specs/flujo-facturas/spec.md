## ADDED Requirements

### Requirement: Eliminación de una factura
El Administrador SHALL poder eliminar cualquier factura, en cualquier estatus, y el proveedor, las de su proveedor en "Borrador" o "Cancelada", con `POST /invoices/{id}/delete`. El PMO SHALL recibir HTTP 403 y un proveedor sobre la factura de otro proveedor, HTTP 404. El sistema SHALL bloquear la fila de la factura antes de comprobar su estatus: si el proveedor la intenta eliminar en otro estatus SHALL responder HTTP 409 "Sólo se puede eliminar una factura en Borrador o Cancelada" sin borrar nada. Sin la casilla de confirmación SHALL volver al detalle con HTTP 400 "Confirme que desea eliminar la factura" y el panel abierto.

La eliminación SHALL borrar la factura, sus documentos (también los reemplazados y su contenido en `stored_files`), sus resultados de validación y sus revisiones, y SHALL registrar en la bitácora `INVOICE_DELETED` con el folio interno, el número, el UUID, el estatus, el proveedor, el total, la moneda y el número de documentos. Las entradas anteriores de la bitácora y el registro de correos MUST NOT borrarse. Los archivos SHALL borrarse del disco después de confirmar la transacción. Después SHALL redirigir al listado con el aviso "Factura <folio interno> eliminada".

El detalle SHALL mostrar "Eliminar" en la cabecera y el panel "Eliminar factura", con la casilla "Confirmo que se elimina la factura <número> (<folio interno>) con sus documentos", sólo a quien puede eliminarla: al Administrador en cualquier estatus y al proveedor sólo en "Borrador" o "Cancelada". Fuera de esos dos estatus el panel SHALL advertir que la factura sale del flujo de validación y pago y que el proveedor no recibe aviso.

#### Scenario: El proveedor elimina su borrador
- **WHEN** el proveedor confirma la eliminación de su factura "3668" en "Borrador"
- **THEN** la factura, sus documentos, sus archivos y sus validaciones se borran, la bitácora registra `INVOICE_DELETED` y el listado muestra "Factura <folio> eliminada"

#### Scenario: La misma factura se vuelve a registrar
- **WHEN** después de eliminarla el proveedor registra otra vez el mismo CFDI
- **THEN** el registro procede: el UUID y el número quedaron libres

#### Scenario: El Administrador elimina una factura cancelada
- **WHEN** el Administrador confirma la eliminación de una factura "Cancelada" con su acuse y una revisión del PMO
- **THEN** se borran también el acuse y la revisión

#### Scenario: El PMO no elimina
- **WHEN** el PMO abre el detalle de una factura en "Borrador" o envía `POST /invoices/{id}/delete`
- **THEN** el detalle no muestra "Eliminar" y la petición responde HTTP 403

#### Scenario: El Administrador elimina una factura programada para pago
- **WHEN** el Administrador confirma la eliminación de una factura en "Programado para pago"
- **THEN** el panel advierte que la factura sale del flujo, la factura y lo que depende de ella se borran y la bitácora registra `INVOICE_DELETED` con el estatus `PAID`

#### Scenario: Factura enviada
- **WHEN** el proveedor envía `POST /invoices/{id}/delete` sobre su factura "Enviada"
- **THEN** la respuesta es HTTP 409 y la factura no cambia

#### Scenario: Sin confirmación
- **WHEN** el proveedor pulsa "Eliminar factura" sin marcar la casilla
- **THEN** la respuesta es HTTP 400 con "Confirme que desea eliminar la factura" y la factura no se borra
