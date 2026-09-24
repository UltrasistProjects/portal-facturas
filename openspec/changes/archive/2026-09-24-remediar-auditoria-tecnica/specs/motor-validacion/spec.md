## ADDED Requirements

### Requirement: Fuente única de reglas de negocio
Los parámetros de negocio que usa el motor de validación SHALL tener una sola fuente: `BUSINESS_RULES`. Esos parámetros son el receptor (razón social, RFC, código postal, régimen), el método de pago, la forma de pago, los usos de CFDI permitidos y los pesos del score. La vista `/admin/rules` SHALL renderizar exactamente esos valores, incluidos los pesos del score por severidad. El archivo `app/rules/business_rules.json` MUST NOT existir.

#### Scenario: Vista de reglas coincide con el motor
- **WHEN** un ADMIN abre `/admin/rules`
- **THEN** ve el RFC receptor, la razón social, el código postal, el régimen, el método y la forma de pago, los usos de CFDI y los pesos `CRITICAL`, `ERROR`, `WARNING` e `INFO`, con los mismos valores que usa el motor

#### Scenario: Cambio de un parámetro
- **WHEN** se modifica `BUSINESS_RULES["payment_form"]`
- **THEN** tanto la regla XML-004 como la vista `/admin/rules` reflejan el nuevo valor sin editar ningún otro archivo

### Requirement: Reglas de calendario en la zona horaria de negocio
La zona horaria de negocio SHALL configurarse con `BUSINESS_TIMEZONE` (por defecto `America/Mexico_City`). La regla DAT-001 SHALL evaluar el día de recepción convirtiendo `created_at` de UTC a esa zona antes de compararlo con el día 20.

#### Scenario: Último minuto del día 20
- **WHEN** una factura se recibe el 20 de agosto a las 23:00 en `America/Mexico_City` (21 de agosto 05:00 UTC)
- **THEN** DAT-001 resulta `PASS`

#### Scenario: Primer minuto del día 21
- **WHEN** una factura se recibe el 21 de agosto a las 00:30 en `America/Mexico_City`
- **THEN** DAT-001 resulta `WARNING` con el mensaje de siguiente ciclo

#### Scenario: Zona configurable
- **WHEN** `BUSINESS_TIMEZONE=UTC` y la factura se recibe el 21 de agosto a las 05:00 UTC
- **THEN** DAT-001 resulta `WARNING`

### Requirement: Detección de UUID duplicado coherente con la unicidad en BD
Antes de asignar el UUID del CFDI a una factura, el motor SHALL verificar si ya pertenece a otra factura. Si es duplicado, SHALL registrar FIN-004 como `FAIL` de severidad `CRITICAL`, conservar el UUID detectado en los metadatos del documento XML y dejar `invoices.uuid` sin asignar, completando la validación sin error. Si la restricción de unicidad detecta una carrera, la petición SHALL responder HTTP 409 sin persistir resultados parciales.

#### Scenario: CFDI ya registrado en otra factura
- **WHEN** se valida una factura cuyo XML tiene un UUID que ya tiene otra factura
- **THEN** la validación termina, FIN-004 es `FAIL`/`CRITICAL`, la factura queda en `REQUIRES_CORRECTION`, `invoices.uuid` de esta factura es `NULL` y el UUID detectado figura en `metadata_json` del documento XML

#### Scenario: Validaciones concurrentes del mismo CFDI
- **WHEN** dos facturas con el mismo UUID se validan simultáneamente y ambas superan la comprobación previa
- **THEN** una de ellas se confirma y la otra recibe HTTP 409 sin resultados de validación ni cambios de estado persistidos

#### Scenario: Revalidación de la misma factura
- **WHEN** se revalida una factura que ya tiene asignado su propio UUID
- **THEN** FIN-004 resulta `PASS`
