# motor-validacion Specification

## Purpose
Fuente única de reglas de negocio (Reglas de Validación editables por el administrador), comparaciones del receptor y del CFDI, reglas de calendario en la zona horaria de negocio y detección de UUID duplicados coherente con la unicidad de la base de datos.
## Requirements
### Requirement: Fuente única de reglas de negocio
Los parámetros de negocio que usa el motor de validación SHALL tener una sola fuente: el catálogo de Reglas de Validación en la base de datos. En cada prevalidación, el motor SHALL tomar sólo las reglas activas del origen del proveedor de la factura: las `NATIONAL` para un proveedor nacional y las `INTERNATIONAL` para uno internacional. MUST NOT usar las reglas del otro origen. Una regla eliminada de ese origen MUST NOT aplicarse.

Las monedas aceptadas SHALL ser las claves activas del catálogo de monedas (HU-07). El motor SHALL leer las reglas en cada prevalidación, sin caché, con el mismo servicio que alimenta las páginas `/admin/rules/national` y `/admin/rules/international`. Los pesos del score SHALL seguir definidos en `BUSINESS_RULES`, que MUST NOT contener otros parámetros. El archivo `app/rules/business_rules.json` MUST NOT existir.

#### Scenario: Vista de reglas coincide con el motor
- **WHEN** un Administrador abre `/admin/rules/national`
- **THEN** ve, para cada regla activa, el mismo valor esperado que usa el motor en la siguiente prevalidación nacional, y los pesos `CRITICAL`, `ERROR`, `WARNING` e `INFO`

#### Scenario: Cambio de un parámetro
- **WHEN** el Administrador cambia la forma de pago esperada de XML-004 a `03` en `/admin/rules/national`
- **THEN** la regla XML-004 de la siguiente prevalidación nacional espera `03` y la vista muestra `03`, sin editar ningún archivo ni reiniciar la aplicación

#### Scenario: Factura internacional con reglas internacionales
- **WHEN** la Razón Social de XML-009 (nacional) es "ULTRASIST" y la de INT-002 (internacional) es "ULTRASIST SA DE CV", y se valida una factura internacional cuyo Invoice dice "ULTRASIST SA DE CV"
- **THEN** INT-002 resulta `PASS` con el valor esperado "ULTRASIST SA DE CV", y ninguna regla de la factura usa los valores de las reglas nacionales

#### Scenario: Factura nacional con reglas nacionales
- **WHEN** INT-003 (internacional) espera `06600`, XML-010 (nacional) espera `03930` y se valida una factura nacional cuyo XML trae `DomicilioFiscalReceptor="03930"`
- **THEN** XML-010 resulta `PASS` con el valor esperado `03930` y la factura no tiene resultados INT

#### Scenario: Regla eliminada en un solo origen
- **WHEN** el Administrador elimina INT-002 y mantiene activa XML-009
- **THEN** la siguiente prevalidación internacional deja INT-002 como `NOT_APPLICABLE` y la siguiente nacional sigue evaluando XML-009

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
- DOC-005 se evalúa conforme a "Contrato y anexos disponibles según los requisitos del contrato"; DOC-006 y DOC-007 no cambian.

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
Las reglas XML SHALL comparar el CFDI con el valor esperado de su regla nacional activa así:
- XML-002 (`CRITICAL`): `Receptor.Rfc` con el RFC;
- XML-003 (`ERROR`): `MetodoPago` con el método esperado;
- XML-004 (`ERROR`): `FormaPago` con la forma esperada;
- XML-005 (`ERROR`): `UsoCFDI` con los usos permitidos;
- XML-007 (`ERROR`): `Moneda` con las monedas activas del catálogo de monedas; no es una regla del catálogo de Reglas de Validación y siempre se evalúa;
- XML-009 (`ERROR`): `Receptor.Nombre` con la Razón Social, sin distinguir mayúsculas, acentos ni espacios repetidos;
- XML-010 (`ERROR`): `Receptor.DomicilioFiscalReceptor` con el Código Postal;
- XML-011 (`ERROR`, nueva): `Receptor.RegimenFiscalReceptor` con el régimen fiscal.

Cuando su regla está eliminada, XML-002, XML-003, XML-004, XML-005, XML-009, XML-010 y XML-011 SHALL resultar `NOT_APPLICABLE` con el mensaje "Regla inactiva en Reglas de Validación", conservando su severidad y sin afectar el score. El mensaje de falla SHALL indicar el valor esperado.

Si el XML del CFDI no está activo y Obligatorio para Nacional en Archivos mínimos y la factura no tiene un XML vigente, XML-001 a XML-011 SHALL resultar `NOT_APPLICABLE` con "El XML del CFDI no se exige en Archivos mínimos", sin intentar leer un XML. Si la factura sí tiene un XML vigente, las reglas se evalúan.

#### Scenario: Razón social con otro formato
- **WHEN** la Razón Social de XML-009 es "ULTRASIST" y el XML trae `Nombre="Ultrasist "`
- **THEN** XML-009 es `PASS`

#### Scenario: Código postal distinto
- **WHEN** XML-010 espera `03930` y el XML trae `DomicilioFiscalReceptor="06600"`
- **THEN** XML-010 es `FAIL` con severidad `ERROR`, valor esperado `03930` y detectado `06600`, y el envío no procede

#### Scenario: Regla eliminada
- **WHEN** XML-009 está eliminada y el XML trae otra razón social
- **THEN** XML-009 es `NOT_APPLICABLE` con "Regla inactiva en Reglas de Validación" y el score no la considera

#### Scenario: Régimen fiscal restaurado
- **WHEN** el Administrador restaura XML-011 con el régimen `601` y se valida un XML con `RegimenFiscalReceptor="603"`
- **THEN** XML-011 es `FAIL` con valor esperado `601` y detectado `603`

#### Scenario: Factura demo correcta
- **WHEN** se valida la factura demo con `cfdi_demo_correcto.xml` y la configuración inicial
- **THEN** XML-009 y XML-010 son `PASS` y XML-011 es `NOT_APPLICABLE`

#### Scenario: XML del CFDI eliminado de Archivos mínimos
- **WHEN** el Administrador elimina el tipo "XML del CFDI" y se valida una factura nacional sin XML
- **THEN** DOC-001 y XML-001 a XML-011 resultan `NOT_APPLICABLE`, y la validación termina sin error

### Requirement: La validación no cambia el estatus de la factura
`run_validation` SHALL guardar los resultados, el score, el UUID, la fecha y los importes del XML, y auditar `VALIDATION_STARTED` y `VALIDATION_COMPLETED`, sin cambiar el estatus de la factura. La moneda del XML SHALL guardarse en la factura sólo si es una clave activa del catálogo de monedas. Si no lo es, la factura conserva su moneda y XML-007 resulta `FAIL` con la moneda detectada. Decidir si una factura pasa a "Enviada" SHALL corresponder al envío: cualquier resultado `FAIL` lo impide. El evento de log `validation.completed` SHALL incluir `duration_ms`, `score`, `blockers` y `failures` (número de resultados `FAIL`).

#### Scenario: Validación con fallas
- **WHEN** se ejecuta `run_validation` sobre una factura "Cargada" cuyo XML falla XML-002
- **THEN** los resultados quedan guardados, la factura sigue "Cargada" y `validation.completed` registra `failures` mayor que cero

#### Scenario: Moneda del CFDI fuera del catálogo
- **WHEN** se valida una factura nacional cuyo contrato es en `MXN` y cuyo XML trae `Moneda="GBP"`, que no está en el catálogo
- **THEN** la factura conserva `currency = MXN`, XML-007 resulta `FAIL` con detectado `GBP` y el envío no procede

### Requirement: Reglas nacionales que no aplican a la factura internacional
Al validar una factura de un proveedor de origen Internacional, el motor SHALL reportar como `NOT_APPLICABLE`, con el mensaje "No aplica a proveedores internacionales" y conservando la severidad de cada regla:
- las reglas del CFDI, XML-001 a XML-011, sin intentar leer un XML;
- FIN-004 (UUID duplicado);
- SUP-003 (expediente mínimo), cuando el proveedor no tiene requisitos de alta exigibles; si los tiene, SUP-003 se evalúa conforme a "Expediente mínimo según los requisitos de alta configurados";
- SUP-004 (vigencia de los documentos del expediente).

SEM-001 SHALL resultar `NOT_EVALUATED` con "Sin conceptos que comparar: el Invoice no es un CFDI". Las demás reglas (DOC, SUP-001, SUP-002, CON, DAT y FIN-001, FIN-002, FIN-003, FIN-005 y FIN-006) SHALL evaluarse igual que para el proveedor nacional, con los importes y la moneda capturados. La validación de facturas de proveedores nacionales MUST NOT cambiar, salvo SUP-003, que sigue la configuración de requisitos de alta, y XML-011, que sigue su regla nacional.

#### Scenario: Factura internacional completa
- **WHEN** con la configuración inicial de requisitos de alta se valida una factura internacional con Invoice, orden de compra y Vo.Bo., importes que cuadran y dentro del monto de su contrato vigente
- **THEN** XML-001 a XML-011, FIN-004, SUP-003 y SUP-004 resultan `NOT_APPLICABLE`, ninguna regla resulta `FAIL` y la factura puede enviarse

#### Scenario: Monto excedido
- **WHEN** el subtotal capturado de una factura internacional excede el monto autorizado de su contrato
- **THEN** FIN-001 resulta `FAIL` con severidad `CRITICAL` y el envío no procede

#### Scenario: Factura nacional sin cambios
- **WHEN** se valida la factura demo A-CORRECTA
- **THEN** sus resultados son los mismos que antes de este cambio, más XML-011 `NOT_APPLICABLE`, y no incluyen reglas INT ni FIN-007

### Requirement: Expediente mínimo según los requisitos de alta configurados
Al validar una factura, SUP-003 (`ERROR`) SHALL evaluar los requisitos de alta exigibles del proveedor de la factura con la configuración vigente (capacidad `requisitos-alta-proveedor`):
- `PASS` con el mensaje "Expediente mínimo disponible" si cada requisito exigible tiene un documento vigente en el expediente;
- `FAIL` con el mensaje "Expediente del proveedor incompleto. Pendientes: <nombre>, <nombre>" en otro caso, con los nombres en el orden del catálogo;
- `NOT_APPLICABLE` con el mensaje "No aplica a proveedores internacionales" si el proveedor es Internacional y no tiene requisitos de alta exigibles.

La antigüedad de los documentos MUST NOT afectar SUP-003. SUP-004 no cambia.

#### Scenario: Proveedor demo con expediente completo
- **WHEN** se valida la factura demo A-CORRECTA después de la migración y de `reset_demo`
- **THEN** SUP-003 resulta `PASS` con "Expediente mínimo disponible"

#### Scenario: Requisito obligatorio agregado después de la autorización
- **WHEN** el Administrador da de alta "Declaración de ISR por retenciones de salarios", Obligatorio para Persona moral, y se valida una factura de una persona moral "Autorizado" que no tiene ese documento
- **THEN** SUP-003 resulta `FAIL` con "Expediente del proveedor incompleto. Pendientes: Declaración de ISR por retenciones de salarios", el envío no procede y el proveedor sigue "Autorizado"

#### Scenario: Opinión de cumplimiento opcional
- **WHEN** con la configuración inicial se valida una factura de una persona moral con todos sus requisitos obligatorios y sin opinión de cumplimiento
- **THEN** SUP-003 resulta `PASS`

#### Scenario: Proveedor internacional con un requisito configurado
- **WHEN** "Estado de cuenta bancario" es Obligatorio para Internacional y se valida una factura de un proveedor internacional sin ese documento
- **THEN** SUP-003 resulta `FAIL` con "Expediente del proveedor incompleto. Pendientes: Estado de cuenta bancario"

### Requirement: Contrato y anexos disponibles según los requisitos del contrato
Al validar una factura, DOC-005 (`ERROR`) SHALL evaluar los requisitos obligatorios del contrato de la factura con la configuración vigente (capacidad `requisitos-alta-contrato`):
- `PASS` con el mensaje "Contrato/anexo disponible" si cada requisito obligatorio activo tiene al menos un documento vigente ligado al contrato;
- `FAIL` con el mensaje "Faltan documentos del contrato: <nombre>, <nombre>" si falta alguno, con los nombres en el orden del catálogo;
- `FAIL` con el mensaje "Falta contrato/anexo" si la factura no tiene contrato.

Los documentos de la factura y del expediente del proveedor MUST NOT contar para DOC-005. Un `FAIL` SHALL impedir el envío. Una factura que ya salió de los estados editables SHALL conservar su resultado aunque la configuración o los documentos del contrato cambien después.

#### Scenario: Factura demo con contrato completo
- **WHEN** se valida la factura demo A-CORRECTA después de la migración y de `reset_demo`
- **THEN** DOC-005 resulta `PASS` con "Contrato/anexo disponible"

#### Scenario: Contrato activo sin contrato firmado
- **WHEN** se valida una factura editable cuyo contrato "Activo" existía antes de la migración y no tiene documentos
- **THEN** DOC-005 resulta `FAIL` con "Faltan documentos del contrato: Contrato" y el envío no procede

#### Scenario: Requisito obligatorio agregado después de la activación
- **WHEN** el Administrador hace obligatoria la orden de compra y se valida una factura editable de un contrato activo sin orden de compra
- **THEN** DOC-005 resulta `FAIL` con "Faltan documentos del contrato: Orden de compra", el envío no procede y el contrato sigue "Activo"

#### Scenario: Contrato cargado en la factura
- **WHEN** una factura tiene cargado un documento "Contrato" de los archivos de la factura (HU-04) y su contrato no tiene contrato firmado
- **THEN** DOC-005 resulta `FAIL` con "Faltan documentos del contrato: Contrato"

