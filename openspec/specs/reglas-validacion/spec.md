# reglas-validacion Specification

## Purpose
Reglas de Validación (HU-06, RF-11): acceso exclusivo del Administrador, datos de ULTRASIST (RFC, Razón Social, Dirección y Código Postal) y parámetros del CFDI, comparaciones activables, validación, guardado con control de edición concurrente y auditoría.
## Requirements
### Requirement: Configuración exclusiva del Administrador
`GET /admin/rules` y `POST /admin/rules` SHALL estar disponibles únicamente para el rol `Administrador`; el `POST` MUST exigir un token CSRF válido. El menú Administración SHALL mostrar la opción "Reglas de validación" sólo al rol `Administrador`. La página MUST NOT usar scripts ni estilos en línea.

#### Scenario: PMO sin acceso
- **WHEN** un usuario `PMO` solicita `/admin/rules` o envía un guardado
- **THEN** la respuesta es HTTP 403 y la configuración no cambia

#### Scenario: Proveedor sin acceso
- **WHEN** un usuario `Proveedor` solicita `/admin/rules` o envía un guardado
- **THEN** la respuesta es HTTP 403 y la configuración no cambia

#### Scenario: Guardado sin token CSRF
- **WHEN** un Administrador envía `POST /admin/rules` sin token CSRF o con uno inválido
- **THEN** la respuesta es HTTP 403 y la configuración no cambia

### Requirement: Datos de ULTRASIST y parámetros del CFDI
El sistema SHALL mantener una única configuración de Reglas de Validación con:
- los datos de ULTRASIST: RFC, Razón Social, Dirección y Código Postal;
- el régimen fiscal de ULTRASIST como dato de referencia;
- los parámetros del CFDI: método de pago esperado, forma de pago esperada y usos de CFDI permitidos.

Desde la instalación SHALL contener RFC `ULT940623AG0`, Razón Social "ULTRASIST", Dirección vacía, Código Postal `03930`, régimen `601`, método `PPD`, forma `99` y usos `G03` e `I04`, en la versión 1. `/admin/rules` SHALL mostrar estos valores en un formulario editable. El régimen, el método y la forma SHALL elegirse de las claves activas de su catálogo, y los usos de CFDI, con casillas sobre las claves activas del catálogo de usos. La página SHALL mostrar en solo lectura los pesos del score por severidad.

#### Scenario: Valores iniciales
- **WHEN** el Administrador abre `/admin/rules` en una instalación nueva
- **THEN** el formulario muestra RFC `ULT940623AG0`, Razón Social "ULTRASIST", Código Postal `03930`, método `PPD`, forma `99`, usos `G03` e `I04` marcados, y los pesos `CRITICAL`, `ERROR`, `WARNING` e `INFO`

#### Scenario: Cambio de la razón social y la dirección
- **WHEN** el Administrador guarda la Razón Social "ULTRASIST SA DE CV" y la Dirección "Av. Insurgentes Sur 1, Ciudad de México"
- **THEN** la respuesta redirige a `/admin/rules` con el aviso "Reglas de validación guardadas", la configuración queda en la versión 2 y la siguiente prevalidación compara la nueva razón social

### Requirement: Comparaciones activables
La configuración SHALL tener un interruptor "Comparar" por cada comparación: RFC, Razón Social, Código Postal, método de pago, forma de pago y uso de CFDI. Todas SHALL estar activas desde la instalación. La Dirección y el régimen fiscal MUST NOT tener interruptor: se guardan como datos de referencia. La página SHALL listar las reglas XML con su código, lo que comparan, su severidad y si están activas.

#### Scenario: Desactivar una comparación
- **WHEN** el Administrador desactiva la comparación del Código Postal
- **THEN** la tabla de reglas muestra XML-010 como inactiva y la siguiente prevalidación deja XML-010 como `NOT_APPLICABLE`

### Requirement: Validación de la configuración
Al guardar, el sistema SHALL recortar los espacios de los extremos, convertir el RFC a mayúsculas y validar:
- RFC de persona moral: 12 caracteres con el patrón del SAT y una fecha válida;
- Razón Social obligatoria, de hasta 254 caracteres;
- Dirección de hasta 300 caracteres;
- Código Postal de exactamente 5 dígitos;
- régimen, método y forma: claves activas de su catálogo;
- al menos un uso de CFDI, todos claves activas de su catálogo.

El sistema SHALL reportar todos los errores juntos con HTTP 400, cada uno con la forma "<Campo>: <mensaje>", y conservar en el formulario lo capturado. Un guardado con errores MUST NOT cambiar la configuración.

#### Scenario: Varios errores
- **WHEN** el Administrador guarda el RFC "ULT94", el Código Postal "0393" y ningún uso de CFDI
- **THEN** la respuesta es HTTP 400 con "RFC: no es un RFC de persona moral válido", "Código postal: debe tener 5 dígitos" y "Usos de CFDI: seleccione al menos uno", y el formulario conserva "ULT94"

#### Scenario: Clave inactiva
- **WHEN** el Administrador guarda la forma de pago `98`, que no existe en el catálogo, o una clave desactivada
- **THEN** la respuesta es HTTP 400 con "Forma de pago: la clave no está activa en el catálogo"

### Requirement: Guardado con control de edición concurrente
El formulario SHALL enviar la versión de la configuración que se abrió. Si coincide con la vigente y hay cambios, el sistema SHALL guardarlos, aumentar la versión en 1, registrar la fecha y el Administrador, y redirigir con HTTP 303. Si la versión no coincide, SHALL responder HTTP 409 con "Otro administrador modificó las Reglas de Validación mientras usted las editaba. Recargue la página." sin guardar. Un guardado sin cambios SHALL redirigir con el aviso "Sin cambios" y MUST NOT aumentar la versión ni auditar.

#### Scenario: Edición concurrente
- **WHEN** dos Administradores abren la configuración en la versión 1, el primero guarda y el segundo guarda después con la versión 1
- **THEN** el segundo recibe HTTP 409 y la configuración conserva el cambio del primero en la versión 2

#### Scenario: Sin cambios
- **WHEN** el Administrador guarda sin modificar nada
- **THEN** la respuesta redirige con "Sin cambios", la versión no cambia y no se agrega auditoría

### Requirement: Auditoría de las Reglas de Validación
Cada guardado que cambia la configuración SHALL generar un registro `VALIDATION_SETTINGS_UPDATED`, con el Administrador, y en `old_value` y `new_value` sólo los campos que cambiaron más la versión. Los guardados rechazados y los guardados sin cambios MUST NOT generar registros.

#### Scenario: Auditoría de un cambio
- **WHEN** el Administrador cambia sólo la forma de pago de `99` a `03`
- **THEN** `audit_logs` contiene `VALIDATION_SETTINGS_UPDATED` con `old_value = {"payment_form": "99", "version": 1}` y `new_value = {"payment_form": "03", "version": 2}`

