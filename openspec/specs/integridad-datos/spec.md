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

### Requirement: Restricciones CHECK sobre estados, montos y vigencias
La base de datos SHALL rechazar:
- valores de estado, rol, tipo de proveedor, severidad, estado de regla, decisión de revisión o estado de procesamiento que no pertenezcan a su enumeración;
- montos negativos en factura;
- `authorized_amount <= 0` en contratos y `new_amount <= 0` en enmiendas;
- `end_date < start_date` en contratos;
- `validation_score` fuera de 0..100;
- `confidence` fuera de 0..1.

`suppliers.status` y `contracts.status` SHALL ser enumeraciones tipadas (`ACTIVE`, `INACTIVE`).

#### Scenario: Estado inválido por SQL directo
- **WHEN** se ejecuta `UPDATE invoices SET status = 'APROBADA'`
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

