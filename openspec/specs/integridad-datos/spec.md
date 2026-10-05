# integridad-datos Specification

## Purpose
Integridad referencial enforzada, dinero exacto, unicidad fiscal, restricciones `CHECK`, índices, concurrencia de SQLite y prohibición del borrado físico de evidencia fiscal.
## Requirements
### Requirement: Integridad referencial enforzada
PostgreSQL SHALL enforzar todas las llaves foráneas del esquema. Las llaves foráneas hacia facturas, proveedores, usuarios, contratos y documentos SHALL declarar `ON DELETE RESTRICT`.

#### Scenario: Factura con proveedor inexistente
- **WHEN** se intenta insertar una factura con `supplier_id = 9999`, inexistente en `suppliers`
- **THEN** la base de datos rechaza la inserción con un error de integridad

#### Scenario: Acción de borrado declarada
- **WHEN** se consulta `pg_constraint` para las llaves foráneas del esquema
- **THEN** todas tienen `confdeltype = 'r'` (RESTRICT)

#### Scenario: Borrado SQL de una factura con documentos
- **WHEN** se ejecuta `DELETE FROM invoices WHERE id = X` y la factura X tiene documentos asociados
- **THEN** la base de datos rechaza la operación y no quedan documentos huérfanos

### Requirement: Montos monetarios exactos
Los montos (`invoices.subtotal`, `invoices.tax`, `invoices.total`, `contracts.authorized_amount`, `contract_amendments.previous_amount` y `contract_amendments.new_amount`) SHALL almacenarse como `NUMERIC(16,2)`. `validation_results.confidence` SHALL almacenarse como `NUMERIC(5,4)`. La aplicación SHALL leer y escribir estos valores como `Decimal`. PostgreSQL redondea al guardar en una columna `NUMERIC` con escala fija, así que la capa de persistencia MUST rechazar, antes de enviarlo, un valor que no sea representable exactamente en la escala de su columna.

#### Scenario: Almacenamiento exacto
- **WHEN** se guarda una factura con `subtotal = Decimal("100000.10")`
- **THEN** la columna `subtotal` es de tipo `numeric` y al leerla se obtiene exactamente `Decimal("100000.10")`

#### Scenario: Valor con precisión excesiva
- **WHEN** se intenta persistir `total = Decimal("10.005")`
- **THEN** la operación falla con un error explícito de precisión y no se escribe nada (no se guarda `10.01`)

#### Scenario: Agregación exacta en SQL
- **WHEN** se suman en SQL los totales de facturas con valores `0.10`, `0.20` y `0.30`
- **THEN** el resultado es exactamente `0.60`

#### Scenario: Límite exacto de FIN-001
- **WHEN** el subtotal de una factura es idéntico al monto autorizado del contrato, ambos con centavos
- **THEN** FIN-001 resulta `PASS` de forma determinista

### Requirement: Unicidad fiscal en la base de datos
La base de datos SHALL imponer unicidad sobre `invoices.uuid` (se permiten múltiples `NULL` para facturas sin XML validado) y sobre `(invoices.supplier_id, invoices.invoice_number)`.

#### Scenario: UUID duplicado
- **WHEN** se intenta persistir una segunda factura con un `uuid` ya existente
- **THEN** la base de datos rechaza la operación con un error de integridad

#### Scenario: Borradores sin UUID
- **WHEN** existen varias facturas con `uuid = NULL`
- **THEN** la restricción no las rechaza

#### Scenario: Número de factura repetido por proveedor
- **WHEN** se intenta crear una factura con el mismo `invoice_number` que otra del mismo proveedor
- **THEN** la base de datos rechaza la operación

#### Scenario: Mismo número en proveedores distintos
- **WHEN** dos proveedores distintos registran el mismo `invoice_number`
- **THEN** ambas facturas se aceptan

### Requirement: Identidad fiscal única de proveedores
La base de datos SHALL imponer unicidad sobre `suppliers.rfc` (se permiten múltiples `NULL`) y sobre `(suppliers.country, suppliers.foreign_tax_id)`. Una restricción `CHECK` SHALL exigir coherencia con el origen: un proveedor `NATIONAL` MUST tener `rfc` no nulo, `foreign_tax_id` nulo y `country = 'MX'`; un proveedor `INTERNATIONAL` MUST tener `rfc` nulo, `foreign_tax_id` no nulo y `country` distinto de `'MX'`. Los proveedores existentes antes del cambio SHALL quedar como `NATIONAL` con `country = 'MX'`.

#### Scenario: Varios internacionales sin RFC
- **WHEN** existen varios proveedores `INTERNATIONAL` con `rfc = NULL`
- **THEN** la restricción de unicidad no los rechaza

#### Scenario: Identificador fiscal repetido en el mismo país
- **WHEN** se inserta un segundo proveedor con `country = 'US'` y `foreign_tax_id = '12-3456789'`
- **THEN** la base de datos rechaza la operación

#### Scenario: Mismo identificador fiscal en países distintos
- **WHEN** se insertan dos proveedores con `foreign_tax_id = '12-3456789'`, uno con `country = 'US'` y otro con `country = 'CA'`
- **THEN** ambos se aceptan

#### Scenario: Proveedor nacional sin RFC
- **WHEN** se ejecuta `UPDATE suppliers SET rfc = NULL` sobre un proveedor `NATIONAL`
- **THEN** la base de datos rechaza la operación

#### Scenario: Proveedores previos al cambio
- **WHEN** se aplica la migración sobre una base con proveedores existentes
- **THEN** todos quedan con `origin = 'NATIONAL'` y `country = 'MX'` y conservan su RFC y su estatus

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

### Requirement: Índices para las consultas frecuentes
La base de datos SHALL tener índices sobre:
- `invoices(supplier_id, created_at)`
- `invoices(created_at)`
- `invoices(uploaded_by)`, `invoices(reviewed_by)`, `invoices(contract_id)`
- `documents(uploaded_by)`, `documents(replaced_document_id)`
- `reviews(reviewer_id)`
- `users(supplier_id)`

MUST NOT existir un índice simple sobre `invoices(supplier_id)`, porque el compuesto lo cubre.

#### Scenario: Plan de consulta del listado de un proveedor
- **WHEN** con `enable_seqscan = off` se ejecuta `EXPLAIN` sobre el listado de facturas de un proveedor ordenado por `created_at DESC`
- **THEN** el plan usa `ix_invoices_supplier_created` y no incluye un nodo `Sort`

### Requirement: Prohibición de borrado físico de evidencia fiscal
El sistema MUST NOT permitir el borrado físico de facturas. Las relaciones de `Invoice` con documentos, validaciones y revisiones MUST NOT declarar `delete-orphan`. Un intento de borrar una factura mediante el ORM SHALL fallar con un error explícito.

#### Scenario: Borrado por ORM
- **WHEN** el código ejecuta `db.delete(invoice)` y hace flush
- **THEN** se lanza un error que indica que el borrado físico de facturas está prohibido y no se elimina ninguna fila

#### Scenario: Quitar un documento de la colección
- **WHEN** el código elimina un documento de `invoice.documents` y hace commit
- **THEN** la fila del documento no se borra

### Requirement: Fechas-hora en UTC con zona horaria explícita
Las columnas de fecha-hora SHALL ser `TIMESTAMPTZ`, SHALL almacenar el instante normalizado a UTC y SHALL leerse como `datetime` con `tzinfo=UTC`.

#### Scenario: Lectura de created_at
- **WHEN** se lee `invoice.created_at` desde PostgreSQL
- **THEN** el valor es un `datetime` con `tzinfo` UTC

#### Scenario: Escritura con otra zona
- **WHEN** se guarda un `datetime` con zona `America/Mexico_City` a las 19:00 del 20 de agosto
- **THEN** se almacena como 01:00 UTC del 21 de agosto y se lee con `tzinfo` UTC

### Requirement: Conexiones a PostgreSQL
El engine de la aplicación SHALL conectarse con el driver `psycopg` (v3), verificar las conexiones del pool antes de usarlas (`pool_pre_ping`) y fijar la zona horaria de cada sesión en `UTC`. Las lecturas MUST NOT bloquearse por escrituras en curso (MVCC de PostgreSQL).

#### Scenario: Zona horaria de la sesión
- **WHEN** se abre una conexión desde el engine y se ejecuta `SHOW TimeZone`
- **THEN** el resultado es `UTC`

#### Scenario: Lectura durante una escritura
- **WHEN** una transacción modifica filas de `invoices` sin confirmar y otra conexión lee esas filas
- **THEN** la lectura se completa de inmediato con los valores confirmados previamente

### Requirement: Integridad del catálogo de tipos de documento de factura
La base de datos SHALL imponer sobre `invoice_document_types`:
- unicidad de `code` y de `lower(name)`;
- `formats` con al menos un elemento, todos dentro de (`PDF`, `PNG`, `JPEG`, `XML`, `TXT`);
- que un tipo del sistema (`is_system`) esté siempre activo;
- los niveles fijos: `INVOICE_XML` e `INVOICE_PDF` con `national_requirement = 'REQUIRED'` e `international_requirement = 'NOT_APPLICABLE'`; `FOREIGN_INVOICE` con `national_requirement = 'NOT_APPLICABLE'` e `international_requirement = 'REQUIRED'`; `CANCELLATION_ACK` con ambos niveles en `NOT_APPLICABLE`.

#### Scenario: Nivel fijo cambiado por SQL
- **WHEN** se ejecuta `UPDATE invoice_document_types SET national_requirement = 'OPTIONAL' WHERE code = 'INVOICE_XML'`
- **THEN** la base de datos rechaza la operación

#### Scenario: Tipo del sistema desactivado por SQL
- **WHEN** se ejecuta `UPDATE invoice_document_types SET is_active = false WHERE code = 'PURCHASE_ORDER'`
- **THEN** la base de datos rechaza la operación

#### Scenario: Nombre repetido con otra capitalización
- **WHEN** se inserta un tipo con `name = 'ORDEN DE COMPRA'`
- **THEN** la base de datos rechaza la operación

#### Scenario: Formatos inválidos
- **WHEN** se inserta un tipo con `formats` vacío o con `formats = '{DOCX}'`
- **THEN** la base de datos rechaza la operación

#### Scenario: Acuse exigido por SQL
- **WHEN** se ejecuta `UPDATE invoice_document_types SET national_requirement = 'REQUIRED' WHERE code = 'CANCELLATION_ACK'`
- **THEN** la base de datos rechaza la operación

### Requirement: Una plantilla por evento de notificación
La base de datos SHALL imponer unicidad sobre `notification_templates.event`. Restricciones `CHECK` SHALL exigir que `subject` tenga de 1 a 200 caracteres, que `body` tenga de 1 a 5000 caracteres y que `version` sea mayor o igual que 1. `notification_templates.updated_by` SHALL referenciar a `users` con `ON DELETE RESTRICT` y admitir `NULL` para las plantillas que nunca se han modificado.

#### Scenario: Segunda plantilla para un evento
- **WHEN** se inserta una plantilla con `event = 'INVOICE_REJECTED'` y ya existe una para ese evento
- **THEN** la base de datos rechaza la operación

#### Scenario: Asunto vacío por SQL directo
- **WHEN** se ejecuta `UPDATE notification_templates SET subject = ''`
- **THEN** la base de datos rechaza la operación

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

### Requirement: Integridad de las Reglas de Validación y de los catálogos
La base de datos SHALL imponer:
- en `validation_settings`: una sola fila (`id = 1`), `receiver_postal_code` de 5 dígitos, al menos un uso de CFDI en `allowed_cfdi_uses` y `version >= 1`;
- en `catalog_entries`: unicidad de `(catalog, code)`, clave de 1 a 10 caracteres `[A-Z0-9]` y descripción de 1 a 150 caracteres.

`validation_settings.updated_by` y `catalog_entries.updated_by` SHALL referenciar a `users` con `ON DELETE RESTRICT` y admitir `NULL`.

#### Scenario: Segunda configuración por SQL directo
- **WHEN** se inserta una fila en `validation_settings` con `id = 2`
- **THEN** la base de datos rechaza la operación

#### Scenario: Código postal inválido por SQL directo
- **WHEN** se ejecuta `UPDATE validation_settings SET receiver_postal_code = '3930'`
- **THEN** la base de datos rechaza la operación

#### Scenario: Clave repetida en un catálogo
- **WHEN** se inserta en `catalog_entries` la clave `MXN` en el catálogo `CURRENCY`
- **THEN** la base de datos rechaza la operación

### Requirement: Rol del usuario y su proveedor
La base de datos SHALL rechazar, con `CHECK ck_users_provider_supplier`, un usuario `Proveedor` activo sin `supplier_id` y un usuario `PMO` o `Administrador` con `supplier_id`. Un usuario `Proveedor` deshabilitado sin proveedor SHALL admitirse: es el estado en que la migración deja los registros previos.

La migración `0013_provider_user_supplier` SHALL, antes de crear el `CHECK`:
- deshabilitar cada usuario `Proveedor` activo sin proveedor, revocar sus sesiones y auditar `USER_DEACTIVATED_WITHOUT_SUPPLIER`;
- quitar el proveedor a cada usuario `PMO` o `Administrador` que lo tenga, auditando `USER_SUPPLIER_CLEARED` con el id anterior.

El downgrade SHALL retirar el `CHECK` sin revertir los datos.

#### Scenario: Proveedor activo sin proveedor por SQL
- **WHEN** se ejecuta `UPDATE users SET supplier_id = NULL` sobre un usuario Proveedor activo
- **THEN** la base de datos rechaza la operación

#### Scenario: Migración de un usuario huérfano
- **WHEN** existe el usuario Proveedor activo `jobhdev@gmail.com` sin proveedor y se aplica `0013_provider_user_supplier`
- **THEN** el usuario queda deshabilitado, sin sesiones vigentes y con la auditoría `USER_DEACTIVATED_WITHOUT_SUPPLIER`

### Requirement: Nombres de los roles
Los roles del sistema SHALL ser exactamente `Administrador`, `Proveedor` y `PMO`, y `users.role` SHALL guardar esos nombres; la base de datos SHALL rechazar cualquier otro con el `CHECK role`. Ni el código ni la interfaz MUST usar nombres en inglés ni los nombres por defecto de la enumeración.

La migración `0014_business_role_names` SHALL renombrar `ADMIN` a `Administrador`, `PROVIDER` a `Proveedor` e `INTERNAL` a `PMO`, ampliar la columna a `VARCHAR(13)` y rehacer los `CHECK role` y `ck_users_provider_supplier` con los nombres nuevos. Los registros de auditoría previos MUST NOT modificarse. El downgrade SHALL restaurar los nombres, la longitud y los `CHECK` anteriores.

#### Scenario: Usuarios previos con los nombres anteriores
- **WHEN** se aplica la migración sobre usuarios `ADMIN`, `PROVIDER` e `INTERNAL`
- **THEN** quedan como `Administrador`, `Proveedor` y `PMO`, y conservan su proveedor

#### Scenario: Rol con nombre anterior
- **WHEN** se actualiza un usuario con rol `ADMIN` después de la migración
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
