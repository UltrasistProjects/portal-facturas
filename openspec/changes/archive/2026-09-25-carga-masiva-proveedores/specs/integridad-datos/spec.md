## MODIFIED Requirements

### Requirement: Restricciones CHECK sobre estados, montos y vigencias
La base de datos SHALL rechazar:
- valores de estado, rol, tipo de proveedor, origen de proveedor, severidad, estado de regla, decisión de revisión o estado de procesamiento que no pertenezcan a su enumeración;
- montos negativos en factura;
- `authorized_amount <= 0` en contratos y `new_amount <= 0` en enmiendas;
- `end_date < start_date` en contratos;
- `validation_score` fuera de 0..100;
- `confidence` fuera de 0..1.

`suppliers.status` SHALL ser una enumeración tipada (`REGISTERED`, `ACTIVE`, `INACTIVE`), `suppliers.origin` SHALL ser una enumeración tipada (`NATIONAL`, `INTERNATIONAL`) y `contracts.status` SHALL ser una enumeración tipada (`ACTIVE`, `INACTIVE`).

#### Scenario: Estado inválido por SQL directo
- **WHEN** se ejecuta `UPDATE invoices SET status = 'APROBADA'`
- **THEN** la base de datos rechaza la operación

#### Scenario: Estatus de proveedor fuera de catálogo
- **WHEN** se ejecuta `UPDATE suppliers SET status = 'PENDIENTE'`
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
