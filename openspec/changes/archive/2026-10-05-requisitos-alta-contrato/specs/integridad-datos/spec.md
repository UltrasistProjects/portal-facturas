## MODIFIED Requirements

### Requirement: Restricciones CHECK sobre estados, montos y vigencias
La base de datos SHALL rechazar:
- valores de estado, rol, tipo de proveedor, origen de proveedor, nivel de exigencia de archivo, de requisito de alta o de requisito del contrato, evento de notificación, buzón de notificación, resultado de envío de correo, tipo de catálogo, severidad, estado de regla, decisión de revisión o estado de procesamiento que no pertenezcan a su enumeración;
- montos negativos en factura;
- `authorized_amount <= 0` en contratos y `new_amount <= 0` en enmiendas;
- `end_date < start_date` en contratos;
- `validation_score` fuera de 0..100;
- `confidence` fuera de 0..1;
- una factura `CANCELLED` sin `cancelled_at`, `cancelled_by` o `cancellation_deadline`, con `cancellation_deadline` no posterior a `cancelled_at`, o una factura en otro estatus con alguno de esos datos.

`invoices.status` SHALL ser una enumeración tipada (`DRAFT`, `UPLOADED`, `UNDER_REVIEW`, `ACCEPTED`, `REJECTED`, `REQUIRES_CORRECTION`, `CANCELLED`), `suppliers.status` SHALL ser una enumeración tipada (`REGISTERED`, `ACTIVE`, `INACTIVE`), `suppliers.origin` SHALL ser una enumeración tipada (`NATIONAL`, `INTERNATIONAL`), `invoice_document_types.national_requirement` e `invoice_document_types.international_requirement` SHALL ser enumeraciones tipadas (`REQUIRED`, `OPTIONAL`, `NOT_APPLICABLE`), `supplier_document_types.persona_moral_requirement`, `supplier_document_types.persona_fisica_requirement` y `supplier_document_types.international_requirement` SHALL ser enumeraciones tipadas (`REQUIRED`, `OPTIONAL`, `NOT_APPLICABLE`), `contract_document_types.requirement` SHALL ser una enumeración tipada (`REQUIRED`, `OPTIONAL`, `NOT_APPLICABLE`), `notification_templates.event`, `notification_copies.event` y `email_deliveries.event` SHALL ser enumeraciones tipadas (`INVOICE_AUTHORIZED`, `INVOICE_REJECTED`, `INVOICE_OBSERVATIONS`, `INVOICE_CANCELLED`, `SUPPLIER_CREDENTIALS`), `notification_mailboxes.code` SHALL ser una enumeración tipada (`INVOICE_RECEPTION`), `email_deliveries.status` SHALL ser una enumeración tipada (`SENT`, `FAILED`), `catalog_entries.catalog` SHALL ser una enumeración tipada (`CURRENCY`, `CFDI_USE`, `PAYMENT_FORM`, `PAYMENT_METHOD`, `TAX_REGIME`, `INDUSTRY`) y `contracts.status` SHALL ser una enumeración tipada (`REGISTERED`, `ACTIVE`, `INACTIVE`).

#### Scenario: Estado inválido por SQL directo
- **WHEN** se ejecuta `UPDATE invoices SET status = 'APROBADA'`
- **THEN** la base de datos rechaza la operación

#### Scenario: Estatus de factura retirado
- **WHEN** se ejecuta `UPDATE invoices SET status = 'PREVALIDATED'` o `UPDATE invoices SET status = 'READY_FOR_CLICKBALANCE'`
- **THEN** la base de datos rechaza la operación

#### Scenario: Estatus de proveedor fuera de catálogo
- **WHEN** se ejecuta `UPDATE suppliers SET status = 'PENDIENTE'`
- **THEN** la base de datos rechaza la operación

#### Scenario: Nivel de exigencia fuera de catálogo
- **WHEN** se ejecuta `UPDATE invoice_document_types SET national_requirement = 'MANDATORY' WHERE code = 'ADDITIONAL'`
- **THEN** la base de datos rechaza la operación

#### Scenario: Estatus de contrato fuera de catálogo
- **WHEN** se ejecuta `UPDATE contracts SET status = 'PENDIENTE'`
- **THEN** la base de datos rechaza la operación

#### Scenario: Nivel de requisito de alta fuera de catálogo
- **WHEN** se ejecuta `UPDATE supplier_document_types SET persona_moral_requirement = 'MANDATORY' WHERE code = 'POWER_OF_ATTORNEY'`
- **THEN** la base de datos rechaza la operación

#### Scenario: Nivel de requisito del contrato fuera de catálogo
- **WHEN** se ejecuta `UPDATE contract_document_types SET requirement = 'MANDATORY' WHERE code = 'CONTRACT_ANNEXES'`
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

#### Scenario: Tipo de catálogo fuera de catálogo
- **WHEN** se ejecuta `UPDATE catalog_entries SET catalog = 'COUNTRY'`
- **THEN** la base de datos rechaza la operación

#### Scenario: Cancelada sin fecha límite
- **WHEN** se ejecuta `UPDATE invoices SET status = 'CANCELLED'` sobre una factura sin datos de cancelación
- **THEN** la base de datos rechaza la operación

### Requirement: Integridad del catálogo de requisitos de alta
La base de datos SHALL imponer sobre `supplier_document_types`:
- unicidad de `code` y de `lower(name)`;
- que un requisito del sistema (`is_system`) esté siempre activo;
- que `SUPPLIER_CONTRACT` tenga No aplica en sus tres niveles.

#### Scenario: Requisito del sistema desactivado por SQL
- **WHEN** se ejecuta `UPDATE supplier_document_types SET is_active = false WHERE code = 'TAX_STATUS'`
- **THEN** la base de datos rechaza la operación

#### Scenario: Nombre repetido con otra capitalización
- **WHEN** se inserta un requisito con `name = 'PODERES'`
- **THEN** la base de datos rechaza la operación

#### Scenario: Contrato devuelto al alta del proveedor por SQL
- **WHEN** se ejecuta `UPDATE supplier_document_types SET persona_moral_requirement = 'OPTIONAL' WHERE code = 'SUPPLIER_CONTRACT'`
- **THEN** la base de datos rechaza la operación

## ADDED Requirements

### Requirement: Integridad del catálogo de requisitos del contrato
La base de datos SHALL imponer sobre `contract_document_types`:
- unicidad de `code` y de `lower(name)`;
- que un requisito del sistema (`is_system`) esté siempre activo;
- que `SIGNED_CONTRACT` sea siempre `REQUIRED`.

#### Scenario: Contrato opcional por SQL
- **WHEN** se ejecuta `UPDATE contract_document_types SET requirement = 'OPTIONAL' WHERE code = 'SIGNED_CONTRACT'`
- **THEN** la base de datos rechaza la operación

#### Scenario: Requisito del sistema desactivado por SQL
- **WHEN** se ejecuta `UPDATE contract_document_types SET is_active = false WHERE code = 'CONTRACT_ANNEXES'`
- **THEN** la base de datos rechaza la operación

#### Scenario: Nombre repetido con otra capitalización
- **WHEN** se inserta un requisito del contrato con `name = 'ANEXOS'`
- **THEN** la base de datos rechaza la operación

### Requirement: Documentos del contrato con un solo dueño
`documents.contract_id` SHALL ser una llave foránea a `contracts` con `ON DELETE RESTRICT`. La base de datos SHALL rechazar un documento con `contract_id` que tenga también `invoice_id` o `supplier_id`.

#### Scenario: Documento de contrato y de factura
- **WHEN** se ejecuta `UPDATE documents SET invoice_id = 1 WHERE contract_id IS NOT NULL`
- **THEN** la base de datos rechaza la operación

#### Scenario: Borrado de un contrato con documentos
- **WHEN** se ejecuta `DELETE FROM contracts WHERE id = X` y el contrato X tiene documentos
- **THEN** la base de datos rechaza la operación
