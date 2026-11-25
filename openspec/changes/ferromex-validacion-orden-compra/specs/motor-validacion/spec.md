## MODIFIED Requirements

### Requirement: Fuente única de reglas de negocio
Los parámetros de negocio que usa el motor de validación SHALL tener una sola fuente: el catálogo de Reglas de Validación en la base de datos. En cada prevalidación, el motor SHALL tomar sólo las reglas activas del origen del proveedor de la factura: las `NATIONAL` para un proveedor nacional y las `INTERNATIONAL` para uno internacional. MUST NOT usar las reglas del otro origen. Una regla eliminada de ese origen MUST NOT aplicarse.

Las monedas aceptadas SHALL ser las claves activas del catálogo de monedas (HU-07), y los regímenes fiscales válidos del emisor (PRV-003), las claves activas del catálogo de regímenes fiscales. El motor SHALL leer las reglas y los catálogos en cada prevalidación, sin caché, con el mismo servicio que alimenta las páginas `/admin/rules/national` y `/admin/rules/international`. Los pesos del score SHALL seguir definidos en `BUSINESS_RULES`, que MUST NOT contener otros parámetros. El archivo `app/rules/business_rules.json` MUST NOT existir.

Las familias de reglas del motor SHALL ser DOC, XML, PRV, SUP, DAT, FIN y OC, más INT para la factura internacional. Las reglas CON-001 a CON-004, SEM-001, SUP-002, DOC-005, FIN-001, FIN-003 y FIN-006 MUST NOT evaluarse.

#### Scenario: Vista de reglas coincide con el motor
- **WHEN** un Administrador abre `/admin/rules/national`
- **THEN** ve, para cada regla activa, el mismo valor esperado que usa el motor en la siguiente prevalidación nacional, y los pesos `CRITICAL`, `ERROR`, `WARNING` e `INFO`

#### Scenario: Cambio de un parámetro
- **WHEN** el Administrador cambia la forma de pago esperada de XML-004 a `03` en `/admin/rules/national`
- **THEN** la regla XML-004 de la siguiente prevalidación nacional espera `03` y la vista muestra `03`, sin editar ningún archivo ni reiniciar la aplicación

#### Scenario: Factura internacional con reglas internacionales
- **WHEN** la Razón Social de XML-009 (nacional) es "INTERMODAL MEXICO" y la de INT-002 (internacional) es "INTERMODAL MEXICO SA DE CV", y se valida una factura internacional cuyo Invoice dice "INTERMODAL MEXICO SA DE CV"
- **THEN** INT-002 resulta `PASS` con el valor esperado "INTERMODAL MEXICO SA DE CV", y ninguna regla de la factura usa los valores de las reglas nacionales

#### Scenario: Factura nacional con reglas nacionales
- **WHEN** INT-003 (internacional) espera `06600`, XML-010 (nacional) espera `11700` y se valida una factura nacional cuyo XML trae `DomicilioFiscalReceptor="11700"`
- **THEN** XML-010 resulta `PASS` con el valor esperado `11700` y la factura no tiene resultados INT

#### Scenario: Regla eliminada en un solo origen
- **WHEN** el Administrador elimina INT-002 y mantiene activa XML-009
- **THEN** la siguiente prevalidación internacional deja INT-002 como `NOT_APPLICABLE` y la siguiente nacional sigue evaluando XML-009

#### Scenario: Reglas retiradas
- **WHEN** se valida cualquier factura
- **THEN** sus resultados no incluyen CON-001 a CON-004, SEM-001, SUP-002, DOC-005, FIN-001, FIN-003 ni FIN-006

### Requirement: Reglas documentales según los archivos mínimos configurados
En cada validación, el motor SHALL leer la configuración vigente de archivos mínimos para el origen del proveedor de la factura. Un tipo está presente cuando la factura tiene un documento vigente (`is_current`) de ese tipo. Las reglas documentales SHALL evaluarse así:
- DOC-001 (XML del CFDI, `CRITICAL`), DOC-002 (PDF del CFDI, `ERROR`), DOC-003 (Orden de compra, `ERROR`), DOC-004 (Vo.Bo. del líder de proyecto, `ERROR`) y DOC-008 (Invoice (PDF), `CRITICAL`) resultan `PASS` o `FAIL` cuando su tipo es Obligatorio para ese origen, y `NOT_APPLICABLE` en otro caso;
- DOC-009 (`ERROR`) genera un resultado por cada otro tipo activo que sea Obligatorio para ese origen, con la clave del tipo en `source_document`;
- los mensajes usan el nombre del tipo: "<nombre> presente" o "Falta <nombre>"; en `NOT_APPLICABLE`, "No requerido para proveedores nacionales" o "No requerido para proveedores internacionales";
- DOC-006 y DOC-007 no cambian.

Un `FAIL` de cualquiera de estas reglas SHALL impedir el envío. Una factura que ya salió de los estados editables SHALL conservar sus resultados aunque la configuración cambie después. Una factura editable SHALL evaluarse con la configuración vigente al verificarse o enviarse.

#### Scenario: Proveedor nacional sin Vo.Bo.
- **WHEN** con la configuración inicial se valida una factura de un proveedor nacional con PDF y XML del CFDI, sin Vo.Bo.
- **THEN** DOC-002 resulta `PASS`, DOC-001 y DOC-003 resultan `NOT_APPLICABLE`, DOC-004 resulta `FAIL` con severidad `ERROR` y el mensaje "Falta Vo.Bo. del líder de proyecto", DOC-008 resulta `NOT_APPLICABLE` y la factura conserva su estatus

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
Las reglas XML SHALL comparar los datos del comprobante con el valor esperado de su regla nacional activa así:
- XML-002 (`CRITICAL`): `Receptor.Rfc` con el RFC;
- XML-003 (`ERROR`): `MetodoPago` con el método esperado;
- XML-004 (`ERROR`): `FormaPago` con la forma esperada;
- XML-005 (`ERROR`): `UsoCFDI` con los usos permitidos;
- XML-007 (`ERROR`): `Moneda` con las monedas activas del catálogo de monedas; no es una regla del catálogo de Reglas de Validación y siempre se evalúa;
- XML-009 (`ERROR`): `Receptor.Nombre` con la Razón Social, sin distinguir mayúsculas, acentos ni espacios repetidos;
- XML-010 (`ERROR`): `Receptor.DomicilioFiscalReceptor` con el Código Postal;
- XML-011 (`ERROR`): `Receptor.RegimenFiscalReceptor` con el régimen fiscal.

Los datos del comprobante SHALL salir del XML vigente o, si la factura nacional no tiene XML, de los datos extraídos de su PDF (spec `registro-factura-extraccion`):
- con datos del PDF, XML-001 SHALL resultar `NOT_APPLICABLE` con "Sin XML: datos tomados del PDF" y las demás reglas XML SHALL evaluarse igual, con `source_document = "CFDI.pdf"`;
- sin XML y sin datos legibles del PDF, XML-001 SHALL resultar `FAIL` con el motivo.

Cuando su regla está eliminada, XML-002, XML-003, XML-004, XML-005, XML-009, XML-010 y XML-011 SHALL resultar `NOT_APPLICABLE` con el mensaje "Regla inactiva en Reglas de Validación", conservando su severidad y sin afectar el score. El mensaje de falla SHALL indicar el valor esperado.

Si el XML del CFDI no está activo en Archivos mínimos y la factura no tiene XML vigente ni datos del PDF, XML-001 a XML-011 SHALL resultar `NOT_APPLICABLE` con "El XML del CFDI no se exige en Archivos mínimos", sin intentar leer un XML.

Los valores iniciales de las reglas del receptor SHALL ser los de INTERMODAL MEXICO (P-01 de la HU-24):
- XML-002: `IME010718PU3`;
- XML-009: "INTERMODAL MEXICO";
- XML-010: `11700`;
- XML-011: `601`, activa;
- XML-005: los usos `G03` e `I04`.

#### Scenario: Razón social con otro formato
- **WHEN** la Razón Social de XML-009 es "INTERMODAL MEXICO" y el XML trae `Nombre="Intermodal México "`
- **THEN** XML-009 es `PASS`

#### Scenario: Código postal distinto
- **WHEN** XML-010 espera `11700` y el XML trae `DomicilioFiscalReceptor="06600"`
- **THEN** XML-010 es `FAIL` con severidad `ERROR`, valor esperado `11700` y detectado `06600`, y el envío no procede

#### Scenario: Regla eliminada
- **WHEN** XML-009 está eliminada y el XML trae otra razón social
- **THEN** XML-009 es `NOT_APPLICABLE` con "Regla inactiva en Reglas de Validación" y el score no la considera

#### Scenario: Régimen fiscal distinto
- **WHEN** XML-011 espera el régimen `601` y se valida un XML con `RegimenFiscalReceptor="603"`
- **THEN** XML-011 es `FAIL` con valor esperado `601` y detectado `603`

#### Scenario: Factura demo correcta
- **WHEN** se valida la factura demo con `cfdi_demo_correcto.xml` y la configuración inicial
- **THEN** XML-002, XML-009, XML-010 y XML-011 son `PASS`

#### Scenario: Factura registrada sólo con PDF
- **WHEN** se valida una factura nacional registrada sólo con el PDF de la factura 3668
- **THEN** XML-001 es `NOT_APPLICABLE` con "Sin XML: datos tomados del PDF" y XML-002 a XML-011 se evalúan con los datos del PDF y resultan `PASS`

### Requirement: La validación no cambia el estatus de la factura
`run_validation` SHALL guardar los resultados, el score, el UUID, la fecha, los importes del comprobante y el número de orden de compra detectado, y auditar `VALIDATION_STARTED` y `VALIDATION_COMPLETED`, sin cambiar el estatus de la factura ni ligarla a su orden. La moneda del comprobante SHALL guardarse en la factura sólo si es una clave activa del catálogo de monedas. Si no lo es, la factura conserva su moneda y XML-007 resulta `FAIL` con la moneda detectada. Decidir si una factura pasa a "Enviada" SHALL corresponder al envío: cualquier resultado `FAIL` lo impide. El evento de log `validation.completed` SHALL incluir `duration_ms`, `score`, `blockers` y `failures` (número de resultados `FAIL`).

#### Scenario: Validación con fallas
- **WHEN** se ejecuta `run_validation` sobre una factura "Cargada" cuyo XML falla XML-002
- **THEN** los resultados quedan guardados, la factura sigue "Cargada" y `validation.completed` registra `failures` mayor que cero

#### Scenario: Moneda del CFDI fuera del catálogo
- **WHEN** se valida una factura nacional en `MXN` cuyo XML se reemplazó por uno con `Moneda="GBP"`, que no está en el catálogo
- **THEN** la factura conserva `currency = MXN`, XML-007 resulta `FAIL` con detectado `GBP` y el envío no procede

### Requirement: Reglas nacionales que no aplican a la factura internacional
Al validar una factura de un proveedor de origen Internacional, el motor SHALL reportar como `NOT_APPLICABLE`, con el mensaje "No aplica a proveedores internacionales" y conservando la severidad de cada regla:
- las reglas del CFDI, XML-001 a XML-011, sin intentar leer un XML;
- PRV-001 a PRV-003 (datos del emisor del CFDI);
- FIN-004 (UUID duplicado);
- SUP-003 (expediente mínimo), cuando el proveedor no tiene requisitos de alta exigibles; si los tiene, SUP-003 se evalúa conforme a "Expediente mínimo según los requisitos de alta configurados";
- SUP-004 (vigencia de los documentos del expediente).

OC-003 SHALL resultar `NOT_APPLICABLE` con "No aplica para proveedores internacionales", y OC-007 a OC-009, con "Sin partidas en el Invoice". Las demás reglas `OC-*` SHALL evaluarse conforme a la spec `orden-compra` ("Factura internacional contra la orden de compra"). Las demás reglas (DOC, SUP-001, DAT, FIN-002 y FIN-005) SHALL evaluarse igual que para el proveedor nacional, con los importes y la moneda capturados.

#### Scenario: Factura internacional completa
- **WHEN** con la configuración inicial de requisitos de alta se valida una factura internacional con Invoice y Vo.Bo., importes que cuadran y una orden de compra propia con los mismos importes y entrada de mercancía
- **THEN** XML-001 a XML-011, PRV-001 a PRV-003, FIN-004, SUP-003, SUP-004, OC-003 y OC-007 a OC-009 resultan `NOT_APPLICABLE`, ninguna regla resulta `FAIL` y la factura puede enviarse

#### Scenario: Subtotal distinto del de la orden
- **WHEN** el subtotal capturado de una factura internacional no coincide con el total de su orden de compra
- **THEN** OC-005 resulta `FAIL` y el envío no procede

#### Scenario: Factura nacional sin reglas internacionales
- **WHEN** se valida la factura demo A-CORRECTA
- **THEN** sus resultados no incluyen reglas INT ni FIN-007

## REMOVED Requirements

### Requirement: Contrato y anexos disponibles según los requisitos del contrato
**Reason**: Se retira el módulo de contratos en la rama `ferromex` (HU-24).
**Migration**: La factura se controla contra su orden de compra (`OC-001` a `OC-012`, spec `orden-compra`).

### Requirement: Periodo del servicio dentro de la vigencia del contrato
**Reason**: Se retira el módulo de contratos en la rama `ferromex` (HU-24).
**Migration**: Sin sustituto en esta HU (P-14). El periodo de la factura se toma del mes de su fecha de emisión.
