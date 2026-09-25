## MODIFIED Requirements

### Requirement: Fuente única de reglas de negocio
Los parámetros de negocio que usa el motor de validación SHALL tener una sola fuente: la configuración de Reglas de Validación en la base de datos (HU-06). Esos parámetros son:
- los datos del receptor: RFC, Razón Social, Código Postal y régimen;
- el método de pago y la forma de pago;
- los usos de CFDI permitidos;
- los interruptores de cada comparación.

Las monedas aceptadas SHALL ser las claves activas del catálogo de monedas (HU-07). El motor SHALL leer esta configuración en cada prevalidación, sin caché. Los pesos del score SHALL seguir definidos en `BUSINESS_RULES`, que MUST NOT contener otros parámetros. La vista `/admin/rules` SHALL mostrar exactamente los valores que usa el motor, incluidos los pesos del score por severidad. El archivo `app/rules/business_rules.json` MUST NOT existir.

#### Scenario: Vista de reglas coincide con el motor
- **WHEN** un ADMIN abre `/admin/rules`
- **THEN** ve el RFC, la razón social, el código postal, el régimen, el método y la forma de pago, los usos de CFDI y los pesos `CRITICAL`, `ERROR`, `WARNING` e `INFO`, con los mismos valores que usa el motor

#### Scenario: Cambio de un parámetro
- **WHEN** el Administrador cambia la forma de pago esperada a `03` en `/admin/rules`
- **THEN** la regla XML-004 de la siguiente prevalidación espera `03` y la vista muestra `03`, sin editar ningún archivo ni reiniciar la aplicación

## ADDED Requirements

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
- **THEN** XML-010 es `FAIL` con severidad `ERROR`, valor esperado `03930` y detectado `06600`, y la factura queda en "Requiere corrección"

#### Scenario: Comparación desactivada
- **WHEN** la comparación de la Razón Social está desactivada y el XML trae otra razón social
- **THEN** XML-009 es `NOT_APPLICABLE` con "Comparación desactivada en Reglas de Validación" y el score no la considera

#### Scenario: Factura demo correcta
- **WHEN** se prevalida la factura demo con `cfdi_demo_correcto.xml` y la configuración inicial
- **THEN** XML-009 y XML-010 son `PASS`
