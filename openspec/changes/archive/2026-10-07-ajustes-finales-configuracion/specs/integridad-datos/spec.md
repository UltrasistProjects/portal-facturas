## MODIFIED Requirements

### Requirement: Integridad del catálogo de tipos de documento de factura
La base de datos SHALL imponer sobre `invoice_document_types`:
- unicidad de `code` y de `lower(name)`;
- `formats` con al menos un elemento, todos dentro de (`PDF`, `PNG`, `JPEG`, `XML`, `TXT`);
- la baja lógica coherente: `is_active` es verdadero si y sólo si `deleted_at` es nulo;
- `deleted_by` referencia a `users` con `ON DELETE RESTRICT` y admite `NULL`.

Un tipo del sistema MAY eliminarse y sus niveles MAY cambiar: la base de datos no impone niveles fijos.

#### Scenario: Baja lógica incoherente por SQL
- **WHEN** se ejecuta `UPDATE invoice_document_types SET is_active = false WHERE code = 'PURCHASE_ORDER'` sin asignar `deleted_at`
- **THEN** la base de datos rechaza la operación

#### Scenario: Tipo del sistema eliminado por SQL
- **WHEN** se ejecuta `UPDATE invoice_document_types SET is_active = false, deleted_at = now() WHERE code = 'INVOICE_XML'`
- **THEN** la base de datos acepta la operación

#### Scenario: Nombre repetido con otra capitalización
- **WHEN** se inserta un tipo con `name = 'ORDEN DE COMPRA'`
- **THEN** la base de datos rechaza la operación

#### Scenario: Formatos inválidos
- **WHEN** se inserta un tipo con `formats` vacío o con `formats = '{DOCX}'`
- **THEN** la base de datos rechaza la operación

#### Scenario: Migración de tipos inactivos
- **WHEN** se aplica `0019_types_soft_delete` sobre una base con un tipo soporte inactivo
- **THEN** el tipo queda con `deleted_at` igual a su `updated_at` y `deleted_by` nulo

### Requirement: Integridad de las Reglas de Validación y de los catálogos
La base de datos SHALL imponer:
- en `validation_rules`: unicidad de `(origin, rule_code)`, `origin` en (`NATIONAL`, `INTERNATIONAL`), `version >= 1` y la baja lógica coherente (`is_active` si y sólo si `deleted_at` es nulo);
- en `catalog_entries`: unicidad de `(catalog, code)`, clave de 1 a 10 caracteres `[A-Z0-9]` y descripción de 1 a 150 caracteres.

`validation_rules.updated_by`, `validation_rules.deleted_by` y `catalog_entries.updated_by` SHALL referenciar a `users` con `ON DELETE RESTRICT` y admitir `NULL`. La tabla `validation_settings` MUST NOT existir.

#### Scenario: Regla repetida por SQL directo
- **WHEN** se inserta en `validation_rules` una segunda regla `XML-002` de origen `NATIONAL`
- **THEN** la base de datos rechaza la operación

#### Scenario: Origen inválido por SQL directo
- **WHEN** se inserta una regla con `origin = 'FOREIGN'`
- **THEN** la base de datos rechaza la operación

#### Scenario: Clave repetida en un catálogo
- **WHEN** se inserta en `catalog_entries` la clave `MXN` en el catálogo `CURRENCY`
- **THEN** la base de datos rechaza la operación

### Requirement: Integridad del catálogo de requisitos de alta
La base de datos SHALL imponer sobre `supplier_document_types`:
- unicidad de `code` y de `lower(name)`;
- la baja lógica coherente: `is_active` es verdadero si y sólo si `deleted_at` es nulo;
- `deleted_by` referencia a `users` con `ON DELETE RESTRICT` y admite `NULL`.

Un requisito del sistema MAY eliminarse y sus niveles MAY cambiar.

#### Scenario: Baja lógica incoherente por SQL
- **WHEN** se ejecuta `UPDATE supplier_document_types SET is_active = false WHERE code = 'TAX_STATUS'` sin asignar `deleted_at`
- **THEN** la base de datos rechaza la operación

#### Scenario: Nombre repetido con otra capitalización
- **WHEN** se inserta un requisito con `name = 'PODERES'`
- **THEN** la base de datos rechaza la operación

#### Scenario: Contrato con nivel editable por SQL
- **WHEN** se ejecuta `UPDATE supplier_document_types SET persona_moral_requirement = 'OPTIONAL' WHERE code = 'SUPPLIER_CONTRACT'`
- **THEN** la base de datos acepta la operación

### Requirement: Integridad del catálogo de requisitos del contrato
La base de datos SHALL imponer sobre `contract_document_types`:
- unicidad de `code` y de `lower(name)`;
- la baja lógica coherente: `is_active` es verdadero si y sólo si `deleted_at` es nulo;
- `deleted_by` referencia a `users` con `ON DELETE RESTRICT` y admite `NULL`.

Un requisito del sistema MAY eliminarse y su nivel MAY cambiar.

#### Scenario: Contrato opcional por SQL
- **WHEN** se ejecuta `UPDATE contract_document_types SET requirement = 'OPTIONAL' WHERE code = 'SIGNED_CONTRACT'`
- **THEN** la base de datos acepta la operación

#### Scenario: Baja lógica incoherente por SQL
- **WHEN** se ejecuta `UPDATE contract_document_types SET is_active = false WHERE code = 'CONTRACT_ANNEXES'` sin asignar `deleted_at`
- **THEN** la base de datos rechaza la operación

#### Scenario: Nombre repetido con otra capitalización
- **WHEN** se inserta un requisito del contrato con `name = 'ANEXOS'`
- **THEN** la base de datos rechaza la operación
