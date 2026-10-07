## MODIFIED Requirements

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
