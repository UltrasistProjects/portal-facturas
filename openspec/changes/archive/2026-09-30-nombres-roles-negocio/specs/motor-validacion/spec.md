## MODIFIED Requirements

### Requirement: Fuente única de reglas de negocio
Los parámetros de negocio que usa el motor de validación SHALL tener una sola fuente: la configuración de Reglas de Validación en la base de datos (HU-06). Esos parámetros son:
- los datos del receptor: RFC, Razón Social, Código Postal y régimen;
- el método de pago y la forma de pago;
- los usos de CFDI permitidos;
- los interruptores de cada comparación.

Las monedas aceptadas SHALL ser las claves activas del catálogo de monedas (HU-07). El motor SHALL leer esta configuración en cada prevalidación, sin caché. Los pesos del score SHALL seguir definidos en `BUSINESS_RULES`, que MUST NOT contener otros parámetros. La vista `/admin/rules` SHALL mostrar exactamente los valores que usa el motor, incluidos los pesos del score por severidad. El archivo `app/rules/business_rules.json` MUST NOT existir.

#### Scenario: Vista de reglas coincide con el motor
- **WHEN** un Administrador abre `/admin/rules`
- **THEN** ve el RFC, la razón social, el código postal, el régimen, el método y la forma de pago, los usos de CFDI y los pesos `CRITICAL`, `ERROR`, `WARNING` e `INFO`, con los mismos valores que usa el motor

#### Scenario: Cambio de un parámetro
- **WHEN** el Administrador cambia la forma de pago esperada a `03` en `/admin/rules`
- **THEN** la regla XML-004 de la siguiente prevalidación espera `03` y la vista muestra `03`, sin editar ningún archivo ni reiniciar la aplicación
