## ADDED Requirements

### Requirement: Integridad referencial enforzada
Toda conexión a SQLite abierta por la aplicación, por Alembic y por los scripts SHALL ejecutar `PRAGMA foreign_keys=ON` antes de cualquier otra sentencia. Las llaves foráneas hacia facturas, proveedores, usuarios, contratos y documentos SHALL declarar `ON DELETE RESTRICT`.

#### Scenario: Factura con proveedor inexistente
- **WHEN** se intenta insertar una factura con `supplier_id = 9999`, inexistente en `suppliers`
- **THEN** la base de datos rechaza la inserción con un error de integridad

#### Scenario: PRAGMA activo en cada conexión
- **WHEN** se abre una conexión nueva desde el engine de la aplicación y se consulta `PRAGMA foreign_keys`
- **THEN** el resultado es `1`

#### Scenario: Borrado SQL de una factura con documentos
- **WHEN** se ejecuta `DELETE FROM invoices WHERE id = X` y la factura X tiene documentos asociados
- **THEN** la base de datos rechaza la operación y no quedan documentos huérfanos

### Requirement: Configuración de concurrencia de SQLite
Toda conexión a SQLite SHALL configurar `journal_mode=WAL`, `busy_timeout=5000` y `synchronous=NORMAL`.

#### Scenario: PRAGMAs de concurrencia
- **WHEN** se abre una conexión desde el engine y se consultan `PRAGMA journal_mode` y `PRAGMA busy_timeout`
- **THEN** los resultados son `wal` y `5000`

#### Scenario: Lectura durante una escritura
- **WHEN** una transacción de escritura está abierta y otra conexión lee `invoices`
- **THEN** la lectura se completa sin error `database is locked`

### Requirement: Montos monetarios exactos
Los montos (`invoices.subtotal`, `invoices.tax`, `invoices.total`, `contracts.authorized_amount` y los montos de enmiendas de contrato) SHALL almacenarse como enteros en centavos, en columnas con sufijo `_cents`. `validation_results.confidence` SHALL almacenarse como entero en diezmilésimas (`confidence_bp`, 0 a 10000). La aplicación SHALL seguir leyendo y escribiendo estos valores como `Decimal`. La capa de persistencia MUST rechazar un valor que no sea representable exactamente en la escala de su columna, en lugar de redondearlo en silencio.

#### Scenario: Almacenamiento exacto
- **WHEN** se guarda una factura con `subtotal = Decimal("100000.10")`
- **THEN** la columna `subtotal_cents` contiene el entero `10000010` (`typeof = 'integer'`) y al leerla se obtiene exactamente `Decimal("100000.10")`

#### Scenario: Valor con precisión excesiva
- **WHEN** se intenta persistir `total = Decimal("10.005")`
- **THEN** la operación falla con un error explícito de precisión y no se escribe nada

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
- `authorized_amount_cents <= 0`;
- `end_date < start_date` en contratos;
- `validation_score` fuera de 0..100;
- `confidence_bp` fuera de 0..10000.

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

El índice simple `ix_invoices_supplier_id` SHALL eliminarse por quedar cubierto por el compuesto.

#### Scenario: Plan de consulta del listado de un proveedor
- **WHEN** se ejecuta `EXPLAIN QUERY PLAN` sobre el listado de facturas de un proveedor ordenado por `created_at DESC`
- **THEN** el plan usa el índice `(supplier_id, created_at)` y no incluye `USE TEMP B-TREE FOR ORDER BY`

### Requirement: Prohibición de borrado físico de evidencia fiscal
El sistema MUST NOT permitir el borrado físico de facturas. Las relaciones de `Invoice` con documentos, validaciones y revisiones MUST NOT declarar `delete-orphan`. Un intento de borrar una factura mediante el ORM SHALL fallar con un error explícito.

#### Scenario: Borrado por ORM
- **WHEN** el código ejecuta `db.delete(invoice)` y hace flush
- **THEN** se lanza un error que indica que el borrado físico de facturas está prohibido y no se elimina ninguna fila

#### Scenario: Quitar un documento de la colección
- **WHEN** el código elimina un documento de `invoice.documents` y hace commit
- **THEN** la fila del documento no se borra

### Requirement: Fechas-hora en UTC con zona horaria explícita
Las columnas de fecha-hora SHALL almacenarse normalizadas a UTC y SHALL leerse como `datetime` con `tzinfo=UTC`.

#### Scenario: Lectura de created_at
- **WHEN** se lee `invoice.created_at` desde SQLite
- **THEN** el valor es un `datetime` con `tzinfo` UTC

#### Scenario: Escritura con otra zona
- **WHEN** se guarda un `datetime` con zona `America/Mexico_City` a las 19:00 del 20 de agosto
- **THEN** se almacena como 01:00 UTC del 21 de agosto y se lee con `tzinfo` UTC
