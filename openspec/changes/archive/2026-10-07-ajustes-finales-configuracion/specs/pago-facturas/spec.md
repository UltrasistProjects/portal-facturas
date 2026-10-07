## MODIFIED Requirements

### Requirement: Factura que requiere Complemento de Pago
Una factura SHALL requerir Complemento de Pago si y sólo si su proveedor es nacional (`NATIONAL`), el método de pago (`MetodoPago`) de su XML del CFDI vigente es `PPD` y el tipo "Complemento de pago (XML)" (`PAYMENT_COMPLEMENT_XML`) está activo en Archivos mínimos. El método de pago SHALL leerse de los datos que el motor de validación extrajo del XML (`payment_method`). Si no hay XML vigente o no tiene método de pago, la factura no lo requiere. El requisito SHALL determinarse una sola vez, al marcar la factura como pagada, y SHALL quedar fijo en `payment_complement_due_at`. Un cambio posterior en el catálogo o en las Reglas de Validación MUST NOT cambiarlo.

Si al marcar la factura como pagada ya tiene un XML del Complemento de Pago vigente y válido, el sistema SHALL registrar también `payment_complement_received_at` con la fecha de esa carga, y el complemento no queda pendiente.

#### Scenario: Nacional PPD
- **WHEN** el PMO marca como pagada el 01/10/2026 a las 10:00 (hora de negocio) la factura nacional "A-1024", cuyo XML trae `MetodoPago="PPD"`
- **THEN** la factura requiere Complemento de Pago con fecha límite 04/10/2026 10:00

#### Scenario: Nacional PUE
- **WHEN** el PMO marca como pagada una factura nacional cuyo XML trae `MetodoPago="PUE"`
- **THEN** la factura no requiere Complemento de Pago y `payment_complement_due_at` es nulo

#### Scenario: Internacional
- **WHEN** el PMO marca como pagada una factura de un proveedor internacional
- **THEN** la factura no requiere Complemento de Pago

#### Scenario: Tipo del complemento eliminado
- **WHEN** el Administrador eliminó "Complemento de pago (XML)" y el PMO marca como pagada una factura nacional PPD
- **THEN** la factura no requiere Complemento de Pago y `payment_complement_due_at` es nulo

### Requirement: Bloqueo del envío por complementos vencidos
`POST /invoices/{invoice_id}/submit` SHALL verificar, después de comprobar que la factura está en un estatus que se puede enviar y antes de recalcular "Borrador"/"Cargada" y ejecutar el motor, si el proveedor de la factura tiene complementos vencidos. Si los tiene, la respuesta SHALL ser HTTP 409 con "No puede enviar facturas a validación: tiene complementos de pago vencidos de las facturas <números>. Adjúntelos para continuar.", con los números de factura en orden de fecha límite. El estatus de la factura MUST NOT cambiar y no se registran resultados de validación. Un complemento pendiente pero no vencido MUST NOT bloquear el envío. El bloqueo SHALL levantarse en cuanto el proveedor adjunta todos sus complementos vencidos. El bloqueo MUST NOT impedir el alta de facturas, la carga de documentos ni "Verificar". Mientras el tipo "Complemento de pago (XML)" esté eliminado, los complementos vencidos MUST NOT bloquear el envío, porque no hay forma de adjuntarlos.

#### Scenario: Envío bloqueado
- **WHEN** el proveedor tiene la factura "A-1024" pagada hace 73 horas sin complemento y envía a validación su factura "Cargada" "A-1030"
- **THEN** la respuesta es HTTP 409 con "No puede enviar facturas a validación: tiene complementos de pago vencidos de las facturas A-1024. Adjúntelos para continuar.", "A-1030" sigue "Cargada" y no se registran resultados de validación

#### Scenario: Dentro del plazo
- **WHEN** la factura "A-1024" se pagó hace 71 horas sin complemento y el proveedor envía "A-1030"
- **THEN** el envío se procesa con normalidad

#### Scenario: Bloqueo levantado
- **WHEN** el proveedor bloqueado adjunta el complemento de "A-1024" y vuelve a enviar "A-1030"
- **THEN** el envío se procesa con normalidad

#### Scenario: Reenvío desde Observaciones bloqueado
- **WHEN** el proveedor con un complemento vencido reenvía una factura en "Observaciones"
- **THEN** la respuesta es HTTP 409 con el mensaje de complementos vencidos y la factura sigue en "Observaciones"

#### Scenario: Sólo los complementos del proveedor
- **WHEN** otro proveedor tiene un complemento vencido y este proveedor envía su factura
- **THEN** el envío se procesa con normalidad

#### Scenario: Alta permitida
- **WHEN** el proveedor con un complemento vencido da de alta una factura y carga sus documentos
- **THEN** la factura se crea y sus documentos se guardan

#### Scenario: Tipo del complemento eliminado
- **WHEN** el proveedor tiene "A-1024" con el complemento vencido, el Administrador elimina "Complemento de pago (XML)" y el proveedor envía "A-1030"
- **THEN** el envío se procesa con normalidad
