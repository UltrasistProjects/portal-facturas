# motor-validacion Specification

## Purpose
Fuente única de reglas de negocio visible para el administrador, reglas de calendario en la zona horaria de negocio y detección de UUID duplicados coherente con la unicidad de la base de datos.
## Requirements
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

### Requirement: Reglas documentales según los archivos mínimos configurados
En cada prevalidación, el motor SHALL leer la configuración vigente de archivos mínimos para el origen del proveedor de la factura. Un tipo está presente cuando la factura tiene un documento vigente (`is_current`) de ese tipo. Las reglas documentales SHALL evaluarse así:
- DOC-001 (XML del CFDI, `CRITICAL`), DOC-002 (PDF del CFDI, `ERROR`), DOC-003 (Orden de compra, `ERROR`), DOC-004 (Vo.Bo. del líder de proyecto, `ERROR`) y DOC-008 (Invoice (PDF), `CRITICAL`) resultan `PASS` o `FAIL` cuando su tipo es Obligatorio para ese origen, y `NOT_APPLICABLE` en otro caso;
- DOC-009 (`ERROR`) genera un resultado por cada otro tipo activo que sea Obligatorio para ese origen, con la clave del tipo en `source_document`;
- los mensajes usan el nombre del tipo: "<nombre> presente" o "Falta <nombre>"; en `NOT_APPLICABLE`, "No requerido para proveedores nacionales" o "No requerido para proveedores internacionales";
- DOC-005, DOC-006 y DOC-007 no cambian.

Un `FAIL` de cualquiera de estas reglas SHALL dejar la factura en `REQUIRES_CORRECTION`. Una factura que ya salió de los estados editables SHALL conservar sus resultados aunque la configuración cambie después. Una factura editable SHALL evaluarse con la configuración vigente al volver a prevalidarse.

#### Scenario: Proveedor nacional sin Vo.Bo.
- **WHEN** con la configuración inicial se prevalida una factura de un proveedor nacional con XML del CFDI, PDF del CFDI y orden de compra, sin Vo.Bo.
- **THEN** DOC-001, DOC-002 y DOC-003 resultan `PASS`, DOC-004 resulta `FAIL` con severidad `ERROR` y el mensaje "Falta Vo.Bo. del líder de proyecto", DOC-008 resulta `NOT_APPLICABLE` y la factura queda en `REQUIRES_CORRECTION`

#### Scenario: Proveedor internacional sin Invoice
- **WHEN** se prevalida una factura de un proveedor internacional que no tiene Invoice (PDF)
- **THEN** DOC-008 resulta `FAIL` con severidad `CRITICAL` y el mensaje "Falta Invoice (PDF)", y DOC-001 y DOC-002 resultan `NOT_APPLICABLE` con el mensaje "No requerido para proveedores internacionales"

#### Scenario: Orden de compra opcional
- **WHEN** "Orden de compra" es Opcional para el origen del proveedor y se prevalida una factura sin orden de compra
- **THEN** DOC-003 resulta `NOT_APPLICABLE` y no descuenta puntos del score

#### Scenario: Tipo soporte obligatorio
- **WHEN** "Reporte de horas" es Obligatorio para Internacional y se prevalida una factura internacional sin ese documento
- **THEN** existe un resultado DOC-009 `FAIL` con `source_document = SOPORTE_<id>` y el mensaje "Falta Reporte de horas"

#### Scenario: Factura ya prevalidada
- **WHEN** una factura está en `PREVALIDATED` sin contrato cargado y el Administrador hace obligatorio "Contrato" para su origen
- **THEN** la factura sigue en `PREVALIDATED` con los mismos resultados y puede enviarse a revisión

#### Scenario: Factura editable prevalidada de nuevo
- **WHEN** una factura en `REQUIRES_CORRECTION` sin contrato cargado se vuelve a prevalidar después de que "Contrato" se hizo obligatorio para su origen
- **THEN** existe un resultado DOC-009 `FAIL` con el mensaje "Falta Contrato"

