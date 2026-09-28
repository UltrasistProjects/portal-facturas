## ADDED Requirements

### Requirement: La validación no cambia el estatus de la factura
`run_validation` SHALL guardar los resultados, el score, el UUID, la fecha y los importes del XML, y auditar `VALIDATION_STARTED` y `VALIDATION_COMPLETED`, sin cambiar el estatus de la factura. Decidir si una factura pasa a "Enviada" SHALL corresponder al envío: cualquier resultado `FAIL` lo impide. El evento de log `validation.completed` SHALL incluir `duration_ms`, `score`, `blockers` y `failures` (número de resultados `FAIL`).

#### Scenario: Validación con fallas
- **WHEN** se ejecuta `run_validation` sobre una factura "Cargada" cuyo XML falla XML-002
- **THEN** los resultados quedan guardados, la factura sigue "Cargada" y `validation.completed` registra `failures` mayor que cero

## MODIFIED Requirements

### Requirement: Detección de UUID duplicado coherente con la unicidad en BD
Antes de asignar el UUID del CFDI a una factura, el motor SHALL verificar si ya pertenece a otra factura, en cualquier estatus y de cualquier proveedor. Si es duplicado, SHALL registrar FIN-004 como `FAIL` de severidad `CRITICAL`, conservar el UUID detectado en los metadatos del documento XML y dejar `invoices.uuid` sin asignar, completando la validación sin error. El resultado SHALL impedir el envío. Su mensaje y sus valores SHALL NOT incluir el folio, el número, el proveedor ni ningún otro dato de la otra factura. Si la restricción de unicidad detecta una carrera, la petición SHALL responder HTTP 409 sin persistir resultados parciales.

#### Scenario: CFDI ya registrado en otra factura
- **WHEN** el proveedor envía una factura cuyo XML tiene un UUID que ya tiene otra factura
- **THEN** la validación termina, FIN-004 es `FAIL`/`CRITICAL`, el envío no procede, la factura conserva su estatus, `invoices.uuid` de esta factura es `NULL` y el UUID detectado figura en `metadata_json` del documento XML

#### Scenario: Duplicado de otro proveedor
- **WHEN** el UUID del XML pertenece a una factura de otro proveedor y el proveedor envía su factura
- **THEN** la respuesta no contiene el folio interno, el número de factura ni la razón social de la otra factura

#### Scenario: Duplicado de una factura rechazada
- **WHEN** el UUID del XML pertenece a una factura "Rechazada" del mismo proveedor
- **THEN** FIN-004 es `FAIL`/`CRITICAL` y el envío no procede

#### Scenario: Validaciones concurrentes del mismo CFDI
- **WHEN** dos facturas con el mismo UUID se validan simultáneamente y ambas superan la comprobación previa
- **THEN** una de ellas se confirma y la otra recibe HTTP 409 sin resultados de validación ni cambios de estado persistidos

#### Scenario: Revalidación de la misma factura
- **WHEN** se revalida una factura que ya tiene asignado su propio UUID
- **THEN** FIN-004 resulta `PASS`

### Requirement: Reglas documentales según los archivos mínimos configurados
En cada validación, el motor SHALL leer la configuración vigente de archivos mínimos para el origen del proveedor de la factura. Un tipo está presente cuando la factura tiene un documento vigente (`is_current`) de ese tipo. Las reglas documentales SHALL evaluarse así:
- DOC-001 (XML del CFDI, `CRITICAL`), DOC-002 (PDF del CFDI, `ERROR`), DOC-003 (Orden de compra, `ERROR`), DOC-004 (Vo.Bo. del líder de proyecto, `ERROR`) y DOC-008 (Invoice (PDF), `CRITICAL`) resultan `PASS` o `FAIL` cuando su tipo es Obligatorio para ese origen, y `NOT_APPLICABLE` en otro caso;
- DOC-009 (`ERROR`) genera un resultado por cada otro tipo activo que sea Obligatorio para ese origen, con la clave del tipo en `source_document`;
- los mensajes usan el nombre del tipo: "<nombre> presente" o "Falta <nombre>"; en `NOT_APPLICABLE`, "No requerido para proveedores nacionales" o "No requerido para proveedores internacionales";
- DOC-005, DOC-006 y DOC-007 no cambian.

Un `FAIL` de cualquiera de estas reglas SHALL impedir el envío. Una factura que ya salió de los estados editables SHALL conservar sus resultados aunque la configuración cambie después. Una factura editable SHALL evaluarse con la configuración vigente al verificarse o enviarse.

#### Scenario: Proveedor nacional sin Vo.Bo.
- **WHEN** con la configuración inicial se valida una factura de un proveedor nacional con XML del CFDI, PDF del CFDI y orden de compra, sin Vo.Bo.
- **THEN** DOC-001, DOC-002 y DOC-003 resultan `PASS`, DOC-004 resulta `FAIL` con severidad `ERROR` y el mensaje "Falta Vo.Bo. del líder de proyecto", DOC-008 resulta `NOT_APPLICABLE` y la factura conserva su estatus

#### Scenario: Proveedor internacional sin Invoice
- **WHEN** se valida una factura de un proveedor internacional que no tiene Invoice (PDF)
- **THEN** DOC-008 resulta `FAIL` con severidad `CRITICAL` y el mensaje "Falta Invoice (PDF)", y DOC-001 y DOC-002 resultan `NOT_APPLICABLE` con el mensaje "No requerido para proveedores internacionales"

#### Scenario: Orden de compra opcional
- **WHEN** "Orden de compra" es Opcional para el origen del proveedor y se valida una factura sin orden de compra
- **THEN** DOC-003 resulta `NOT_APPLICABLE` y no descuenta puntos del score

#### Scenario: Tipo soporte obligatorio
- **WHEN** "Reporte de horas" es Obligatorio para Internacional y se valida una factura internacional sin ese documento
- **THEN** existe un resultado DOC-009 `FAIL` con `source_document = SOPORTE_<id>` y el mensaje "Falta Reporte de horas"

#### Scenario: Factura ya enviada
- **WHEN** una factura está "Enviada" sin contrato cargado y el Administrador hace obligatorio "Contrato" para su origen
- **THEN** la factura sigue "Enviada" con los mismos resultados

#### Scenario: Factura en Observaciones enviada de nuevo
- **WHEN** una factura en "Observaciones" sin contrato cargado se envía después de que "Contrato" se hizo obligatorio para su origen
- **THEN** existe un resultado DOC-009 `FAIL` con el mensaje "Falta Contrato", el envío no procede y la factura sigue en "Observaciones"

### Requirement: Comparaciones del receptor y del CFDI según las Reglas de Validación
Las reglas XML SHALL comparar el CFDI con la configuración vigente así:
- XML-002 (`CRITICAL`): `Receptor.Rfc` con el RFC;
- XML-003 (`ERROR`): `MetodoPago` con el método esperado;
- XML-004 (`ERROR`): `FormaPago` con la forma esperada;
- XML-005 (`ERROR`): `UsoCFDI` con los usos permitidos;
- XML-007 (`ERROR`): `Moneda` con las monedas activas;
- XML-009 (`ERROR`, nueva): `Receptor.Nombre` con la Razón Social, sin distinguir mayúsculas, acentos ni espacios repetidos;
- XML-010 (`ERROR`, nueva): `Receptor.DomicilioFiscalReceptor` con el Código Postal.

Cuando su comparación está desactivada, XML-002, XML-003, XML-004, XML-005, XML-009 y XML-010 SHALL resultar `NOT_APPLICABLE` con el mensaje "Comparación desactivada en Reglas de Validación", conservando su severidad y sin afectar el score. El mensaje de falla SHALL indicar el valor esperado.

#### Scenario: Razón social con otro formato
- **WHEN** la Razón Social configurada es "ULTRASIST" y el XML trae `Nombre="Ultrasist "`
- **THEN** XML-009 es `PASS`

#### Scenario: Código postal distinto
- **WHEN** el Código Postal configurado es `03930` y el XML trae `DomicilioFiscalReceptor="06600"`
- **THEN** XML-010 es `FAIL` con severidad `ERROR`, valor esperado `03930` y detectado `06600`, y el envío no procede

#### Scenario: Comparación desactivada
- **WHEN** la comparación de la Razón Social está desactivada y el XML trae otra razón social
- **THEN** XML-009 es `NOT_APPLICABLE` con "Comparación desactivada en Reglas de Validación" y el score no la considera

#### Scenario: Factura demo correcta
- **WHEN** se valida la factura demo con `cfdi_demo_correcto.xml` y la configuración inicial
- **THEN** XML-009 y XML-010 son `PASS`
