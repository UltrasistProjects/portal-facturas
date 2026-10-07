## MODIFIED Requirements

### Requirement: Restricciones CHECK sobre estados, montos y vigencias
La base de datos SHALL rechazar:
- valores de estado, rol, tipo de proveedor, origen de proveedor, nivel de exigencia de archivo, evento de notificación, buzón de notificación, resultado de envío de correo, severidad, estado de regla, decisión de revisión o estado de procesamiento que no pertenezcan a su enumeración;
- montos negativos en factura;
- `authorized_amount <= 0` en contratos y `new_amount <= 0` en enmiendas;
- `end_date < start_date` en contratos;
- `validation_score` fuera de 0..100;
- `confidence` fuera de 0..1.

`suppliers.status` SHALL ser una enumeración tipada (`REGISTERED`, `ACTIVE`, `INACTIVE`), `suppliers.origin` SHALL ser una enumeración tipada (`NATIONAL`, `INTERNATIONAL`), `invoice_document_types.national_requirement` e `invoice_document_types.international_requirement` SHALL ser enumeraciones tipadas (`REQUIRED`, `OPTIONAL`, `NOT_APPLICABLE`), `notification_templates.event`, `notification_copies.event` y `email_deliveries.event` SHALL ser enumeraciones tipadas (`INVOICE_AUTHORIZED`, `INVOICE_REJECTED`, `INVOICE_OBSERVATIONS`, `INVOICE_CANCELLED`), `notification_mailboxes.code` SHALL ser una enumeración tipada (`INVOICE_RECEPTION`), `email_deliveries.status` SHALL ser una enumeración tipada (`SENT`, `FAILED`) y `contracts.status` SHALL ser una enumeración tipada (`ACTIVE`, `INACTIVE`).

#### Scenario: Estado inválido por SQL directo
- **WHEN** se ejecuta `UPDATE invoices SET status = 'APROBADA'`
- **THEN** la base de datos rechaza la operación

#### Scenario: Estatus de proveedor fuera de catálogo
- **WHEN** se ejecuta `UPDATE suppliers SET status = 'PENDIENTE'`
- **THEN** la base de datos rechaza la operación

#### Scenario: Nivel de exigencia fuera de catálogo
- **WHEN** se ejecuta `UPDATE invoice_document_types SET national_requirement = 'MANDATORY' WHERE code = 'ADDITIONAL'`
- **THEN** la base de datos rechaza la operación

#### Scenario: Evento de notificación fuera de catálogo
- **WHEN** se ejecuta `UPDATE notification_templates SET event = 'INVOICE_PAID' WHERE event = 'INVOICE_CANCELLED'`
- **THEN** la base de datos rechaza la operación

#### Scenario: Resultado de envío fuera de catálogo
- **WHEN** se inserta en `email_deliveries` una fila con `status = 'QUEUED'`
- **THEN** la base de datos rechaza la operación

#### Scenario: Monto negativo
- **WHEN** se intenta guardar una factura con `total = -1.00`
- **THEN** la base de datos rechaza la operación

#### Scenario: Vigencia invertida
- **WHEN** se intenta crear un contrato con `end_date` anterior a `start_date`
- **THEN** la base de datos rechaza la operación y el formulario muestra el error sin HTTP 500

#### Scenario: Score fuera de rango
- **WHEN** se intenta guardar `validation_score = 101`
- **THEN** la base de datos rechaza la operación

## ADDED Requirements

### Requirement: Integridad de la configuración de notificaciones
La base de datos SHALL imponer:
- unicidad de `notification_mailboxes.code` y de `notification_copies.event`;
- de 1 a 10 direcciones en `notification_mailboxes.addresses` y de 0 a 10 en `notification_copies.addresses`;
- en `email_deliveries`, al menos una dirección en `to_addresses` y un `error` no nulo cuando `status = 'FAILED'`.

`updated_by` de `notification_mailboxes` y `notification_copies`, y `requested_by` de `email_deliveries`, SHALL referenciar a `users` con `ON DELETE RESTRICT` y admitir `NULL` (configuración nunca modificada o envío sin usuario).

#### Scenario: Buzón sin direcciones por SQL directo
- **WHEN** se ejecuta `UPDATE notification_mailboxes SET addresses = '{}'`
- **THEN** la base de datos rechaza la operación

#### Scenario: Segunda lista de copias para un evento
- **WHEN** se inserta una fila en `notification_copies` con `event = 'INVOICE_REJECTED'` y ya existe una para ese evento
- **THEN** la base de datos rechaza la operación

#### Scenario: Envío fallido sin error
- **WHEN** se inserta en `email_deliveries` una fila con `status = 'FAILED'` y `error` nulo
- **THEN** la base de datos rechaza la operación
