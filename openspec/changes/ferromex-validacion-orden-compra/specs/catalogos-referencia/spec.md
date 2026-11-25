## MODIFIED Requirements

### Requirement: Desactivación con protección de claves en uso
El Administrador SHALL poder desactivar y reactivar claves. Una clave inactiva MUST NOT ofrecerse en las Reglas de Validación ni en el registro de la factura internacional y, en el caso de las monedas, MUST NOT aceptarse en XML-007. El sistema MUST NOT desactivar una clave que usa el valor esperado de una regla activa de Reglas de Validación, de cualquier origen (régimen de XML-011, método de pago de XML-003, forma de pago de XML-004 o uso de CFDI de XML-005), ni la última moneda activa: responde HTTP 409 con el motivo. Una clave que sólo usa una regla eliminada no está en uso.

#### Scenario: Clave en uso
- **WHEN** el Administrador intenta desactivar el uso de CFDI `G03`, permitido en XML-005 activa
- **THEN** la respuesta es HTTP 409 con "La clave G03 está en uso en Reglas de Validación." y sigue activa

#### Scenario: Clave de una regla eliminada
- **WHEN** XML-011 está eliminada con el régimen `601` y el Administrador desactiva `601`
- **THEN** `601` queda inactiva

#### Scenario: Desactivar una moneda
- **WHEN** el Administrador desactiva la moneda `EUR`
- **THEN** `EUR` queda inactiva, deja de ofrecerse en el registro de la factura internacional y una factura con `Moneda="EUR"` falla XML-007 en su siguiente prevalidación

### Requirement: Moneda de contratos y facturas del catálogo
La moneda de una factura SHALL ser una clave del catálogo de monedas (el portal ya no da de alta contratos; spec `orden-compra`):
- el registro de la factura internacional SHALL ofrecer un selector con las monedas activas;
- el servidor SHALL rechazar con HTTP 400 y "Moneda: la clave no está activa en el catálogo" una moneda de factura internacional inactiva o inexistente, también en una petición directa, sin crear ni cambiar nada;
- la moneda del XML de una factura nacional se guarda sólo si está activa (capacidad `motor-validacion`).

La migración `0021_currency_catalog_mapping` (anterior a este cambio) SHALL normalizar `invoices.currency` y `contracts.currency`: recorta espacios, convierte a mayúsculas y aplica los alias `MN` y `MXP` → `MXN`, `DLS`, `DLL` y `US` → `USD`, y `EU` → `EUR`, siempre que el resultado sea una clave del catálogo. Cada valor cambiado SHALL auditarse como `CURRENCY_NORMALIZED`, con el valor anterior y el nuevo y sin usuario. Un valor que no se puede mapear MUST NOT descartarse ni cambiarse: SHALL conservarse y registrarse en el log de la migración. `scripts/reporte_monedas.py` SHALL listar, sin modificar nada, las facturas (folio, proveedor, estatus y moneda) cuya moneda no es una clave del catálogo; los contratos ya no se reportan porque el portal no los usa.

#### Scenario: Factura internacional con moneda del catálogo
- **WHEN** un proveedor internacional abre el registro de su factura
- **THEN** el campo Moneda es un selector con `MXN`, `USD` y `EUR`

#### Scenario: Factura internacional con moneda inválida por petición directa
- **WHEN** una petición directa registra una factura internacional con `currency = "XYZ"` o con una moneda desactivada
- **THEN** la respuesta es HTTP 400 con "Moneda: la clave no está activa en el catálogo" y no se crea la factura

#### Scenario: Normalización de monedas existentes
- **WHEN** se aplica la migración sobre una base con un contrato en `"usd "` y una factura en `MN`
- **THEN** el contrato queda en `USD`, la factura en `MXN` y `audit_logs` tiene un `CURRENCY_NORMALIZED` por cada uno

#### Scenario: Moneda que no se puede mapear
- **WHEN** se aplica la migración sobre una base con una factura en `PES`
- **THEN** la factura conserva `PES`, el log de la migración la menciona y `scripts/reporte_monedas.py` la lista con su folio
