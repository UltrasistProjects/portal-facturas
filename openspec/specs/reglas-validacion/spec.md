# reglas-validacion Specification

## Purpose
Reglas de Validación (HU-06, RF-11): acceso exclusivo del Administrador, datos de ULTRASIST (RFC, Razón Social, Dirección y Código Postal) y parámetros del CFDI, comparaciones activables, validación, guardado con control de edición concurrente y auditoría.
## Requirements
### Requirement: Configuración exclusiva del Administrador
`GET /admin/rules/{origen}` y los `POST` de edición, eliminación y restauración de reglas SHALL estar disponibles únicamente para el rol `Administrador`; todo `POST` MUST exigir un token CSRF válido. `{origen}` SHALL ser `national` o `international`; otro valor responde HTTP 404. `GET /admin/rules` SHALL redirigir (303) a `/admin/rules/national`. El menú Administración SHALL mostrar al rol `Administrador`, bajo "Reglas de validación", las opciones "Nacionales" e "Internacionales". Las páginas MUST NOT usar scripts ni estilos en línea.

#### Scenario: PMO sin acceso
- **WHEN** un usuario `PMO` solicita `/admin/rules/national` o envía una edición, una eliminación o una restauración
- **THEN** la respuesta es HTTP 403 y ninguna regla cambia

#### Scenario: Proveedor sin acceso
- **WHEN** un usuario `Proveedor` solicita `/admin/rules/international` o envía una edición, una eliminación o una restauración
- **THEN** la respuesta es HTTP 403 y ninguna regla cambia

#### Scenario: Guardado sin token CSRF
- **WHEN** un Administrador envía la edición o la eliminación de una regla sin token CSRF o con uno inválido
- **THEN** la respuesta es HTTP 403 y la regla no cambia

#### Scenario: Origen desconocido
- **WHEN** el Administrador solicita `/admin/rules/foreign`
- **THEN** la respuesta es HTTP 404

#### Scenario: Ruta anterior
- **WHEN** el Administrador solicita `/admin/rules`
- **THEN** la respuesta redirige a `/admin/rules/national`

### Requirement: Validación de la configuración
Al editar o restaurar una regla, el sistema SHALL recortar los espacios de los extremos y validar el nombre (de 3 a 80 caracteres) y el parámetro según la regla:
- RFC: se convierte a mayúsculas y debe ser de persona moral, con 12 caracteres, el patrón del SAT y una fecha válida;
- Razón Social: obligatoria, de hasta 254 caracteres;
- Dirección: obligatoria, de hasta 300 caracteres;
- Código Postal: exactamente 5 dígitos;
- método de pago, forma de pago y régimen fiscal: clave activa de su catálogo;
- usos de CFDI: al menos uno, todos claves activas de su catálogo.

El sistema SHALL reportar todos los errores juntos con HTTP 400, cada uno con la forma "<Campo>: <mensaje>", y conservar en el formulario lo capturado. Un guardado con errores MUST NOT cambiar la regla.

#### Scenario: Varios errores
- **WHEN** el Administrador guarda XML-002 con el RFC "ULT94" y el nombre "R"
- **THEN** la respuesta es HTTP 400 con "RFC: no es un RFC de persona moral válido" y "Nombre: debe tener de 3 a 80 caracteres", y el formulario conserva "ULT94"

#### Scenario: Clave inactiva
- **WHEN** el Administrador guarda en XML-004 la forma de pago `98`, que no existe en el catálogo, o una clave desactivada
- **THEN** la respuesta es HTTP 400 con "Forma de pago: la clave no está activa en el catálogo"

#### Scenario: Sin usos de CFDI
- **WHEN** el Administrador guarda XML-005 sin ningún uso de CFDI
- **THEN** la respuesta es HTTP 400 con "Usos de CFDI: seleccione al menos uno"

### Requirement: Guardado con control de edición concurrente
El formulario de cada regla SHALL enviar la versión de la regla que se abrió. Si coincide con la vigente y hay cambios, el sistema SHALL guardarlos y aumentar la versión en 1. Si no coincide, SHALL responder HTTP 409 con "Otro administrador modificó esta regla mientras usted la editaba. Recargue la página." sin guardar. La eliminación y la restauración también SHALL aumentar la versión.

#### Scenario: Edición concurrente
- **WHEN** dos Administradores abren XML-009 en la versión 1, el primero guarda y el segundo guarda después con la versión 1
- **THEN** el segundo recibe HTTP 409 y la regla conserva el cambio del primero en la versión 2

#### Scenario: Sin cambios
- **WHEN** el Administrador guarda una regla sin modificar nada
- **THEN** la respuesta redirige con "Sin cambios", la versión no cambia y no se agrega auditoría

### Requirement: Auditoría de las Reglas de Validación
El sistema SHALL registrar, con la entidad `ValidationRule`, el id de la regla y el Administrador:
- `VALIDATION_RULE_UPDATED` en cada edición con cambios, con sólo los campos que cambiaron más la versión en `old_value` y `new_value`;
- `VALIDATION_RULE_DELETED` en cada eliminación, con `old_value = {"is_active": true}` y `new_value = {"is_active": false}`;
- `VALIDATION_RULE_RESTORED` en cada restauración, con `old_value = {"is_active": false}` y `new_value = {"is_active": true}`.

Las operaciones rechazadas y las que no cambian nada MUST NOT generar registros.

#### Scenario: Auditoría de un cambio
- **WHEN** el Administrador cambia sólo la forma de pago de XML-004 de `99` a `03`
- **THEN** `audit_logs` contiene `VALIDATION_RULE_UPDATED` con `old_value = {"parameter": "99", "version": 1}` y `new_value = {"parameter": "03", "version": 2}`

#### Scenario: Auditoría de una eliminación
- **WHEN** el Administrador elimina INT-003
- **THEN** `audit_logs` contiene `VALIDATION_RULE_DELETED` con el id de INT-003, su `user_id`, `old_value = {"is_active": true}` y `new_value = {"is_active": false}`

### Requirement: Catálogo de reglas por origen
El sistema SHALL mantener un catálogo persistente de reglas de validación configurables, con un registro por regla y origen de proveedor (`NATIONAL` o `INTERNATIONAL`). Cada registro SHALL tener:
- su origen y su código de regla, únicos en conjunto e inmutables;
- un nombre editable de 3 a 80 caracteres;
- el valor esperado (parámetro) que la regla compara, cuando la regla lo tiene;
- su severidad, definida en el código y mostrada en solo lectura;
- si está activo, con la fecha y el Administrador de su eliminación cuando no lo está;
- una versión para el control de edición concurrente, que empieza en 1.

El catálogo SHALL contener exactamente estas reglas (código · nombre inicial · parámetro · severidad):
- Nacionales: XML-002 · RFC del receptor · RFC de persona moral · `CRITICAL`; XML-003 · Método de pago · clave del catálogo de métodos de pago · `ERROR`; XML-004 · Forma de pago · clave del catálogo de formas de pago · `ERROR`; XML-005 · Usos de CFDI · una o más claves del catálogo de usos de CFDI · `ERROR`; XML-009 · Razón social del receptor · texto de hasta 254 caracteres · `ERROR`; XML-010 · Código postal del receptor · 5 dígitos · `ERROR`; XML-011 · Régimen fiscal del receptor · clave del catálogo de regímenes fiscales · `ERROR`.
- Internacionales: INT-001 · Identificador fiscal del proveedor · sin parámetro · `WARNING`; INT-002 · Razón social de ULTRASIST · texto de hasta 254 caracteres · `WARNING`; INT-003 · Código postal de ULTRASIST · 5 dígitos · `WARNING`; INT-004 · Dirección de ULTRASIST · texto de hasta 300 caracteres · `WARNING`.

En una instalación nueva, las reglas nacionales SHALL tener RFC `ULT940623AG0`, método `PPD`, forma `99`, usos `G03` e `I04`, Razón Social "ULTRASIST", Código Postal `03930` y régimen `601`, todas activas salvo XML-011, que nace eliminada. Las internacionales SHALL tener Razón Social "ULTRASIST" y Código Postal `03930`, activas, INT-001 activa e INT-004 eliminada y sin dirección.

La migración desde la configuración única anterior SHALL marcar sus valores como reglas `NATIONAL`, con la regla activa sólo si su comparación estaba activa, y sembrar las reglas internacionales con los valores vigentes. INT-002 e INT-003 conservan el interruptor de la Razón Social y del Código Postal, e INT-004 queda activa sólo si había una Dirección. Así, ninguna validación cambia al migrar.

#### Scenario: Instalación nueva
- **WHEN** se ejecuta `alembic upgrade head` sobre una base vacía
- **THEN** existen 7 reglas `NATIONAL` y 4 `INTERNATIONAL` con los valores iniciales, XML-011 e INT-004 eliminadas y las demás activas

#### Scenario: Migración de una configuración modificada
- **WHEN** se migra una base cuya configuración tiene la Razón Social "ULTRASIST SA DE CV", la comparación del Código Postal desactivada y la Dirección "Av. Insurgentes Sur 1"
- **THEN** XML-009 e INT-002 esperan "ULTRASIST SA DE CV" y están activas, XML-010 e INT-003 están eliminadas, INT-004 está activa con "Av. Insurgentes Sur 1", y la tabla `validation_settings` ya no existe

#### Scenario: Validación igual tras migrar
- **WHEN** se valida la factura demo A-CORRECTA antes y después de la migración
- **THEN** obtiene los mismos estatus por regla; la única diferencia es el resultado nuevo XML-011 `NOT_APPLICABLE`

### Requirement: Secciones Nacionales e Internacionales
`GET /admin/rules/national` ("Reglas de validación — Nacionales") y `GET /admin/rules/international` ("Reglas de validación — Internacionales") SHALL listar las reglas activas de su origen, ordenadas por código, con su código, nombre, lo que comparan, su valor esperado, su severidad y las acciones "Editar" y "Eliminar". Un enlace "Mostrar eliminados (N)" SHALL listar además las reglas eliminadas de ese origen, con su fecha de eliminación y las acciones "Editar" y "Restaurar". La página nacional SHALL indicar que XML-007 compara la moneda del CFDI con las monedas activas del catálogo y que se administra en Catálogos. Ambas páginas SHALL mostrar en solo lectura los pesos del score por severidad.

La información de las páginas SHALL leerse con el mismo servicio que usa el motor, de modo que lo que muestran es exactamente lo que el motor aplica.

#### Scenario: Página nacional
- **WHEN** el Administrador abre `/admin/rules/national` en una instalación nueva
- **THEN** ve XML-002, XML-003, XML-004, XML-005, XML-009 y XML-010 con sus valores, la nota de XML-007, el enlace "Mostrar eliminados (1)" y los pesos del score

#### Scenario: Página internacional
- **WHEN** el Administrador abre `/admin/rules/international` en una instalación nueva
- **THEN** ve INT-001, INT-002 e INT-003, no ve ninguna regla XML y el enlace muestra "Mostrar eliminados (1)"

#### Scenario: Mostrar eliminados
- **WHEN** el Administrador pulsa "Mostrar eliminados" en la página nacional
- **THEN** XML-011 aparece como eliminada, con su fecha y las acciones "Editar" y "Restaurar"

### Requirement: Edición de una regla
`POST /admin/rules/{origen}/{rule_id}` SHALL editar el nombre y el parámetro de una regla de ese origen, esté activa o eliminada, con la versión que se abrió. Una regla de otro origen o inexistente SHALL responder HTTP 404. Un guardado sin cambios SHALL redirigir con "Sin cambios" sin aumentar la versión ni auditar. Un guardado válido SHALL aumentar la versión en 1, registrar la fecha y el Administrador, y redirigir con HTTP 303 y el aviso "Regla actualizada".

#### Scenario: Cambiar la forma de pago esperada
- **WHEN** el Administrador edita XML-004 en la página nacional y guarda la forma `03`
- **THEN** la página muestra "Regla actualizada" con XML-004 esperando `03` en la versión 2, y la siguiente prevalidación nacional compara `FormaPago` con `03`

#### Scenario: Regla de otro origen
- **WHEN** el Administrador envía la edición de INT-002 a `/admin/rules/national/{id de INT-002}`
- **THEN** la respuesta es HTTP 404 y la regla no cambia

#### Scenario: Editar una regla eliminada
- **WHEN** el Administrador captura "Av. Insurgentes Sur 1" como Dirección de INT-004, que está eliminada
- **THEN** INT-004 guarda la dirección y sigue eliminada hasta que se restaure

### Requirement: Eliminación lógica y restauración de una regla
`POST /admin/rules/{origen}/{rule_id}/delete` SHALL marcar la regla como eliminada (`is_active = false`, `deleted_at`, `deleted_by`) sin borrar su fila, después de una confirmación en la página que la nombra. `POST /admin/rules/{origen}/{rule_id}/restore` SHALL reactivarla y limpiar `deleted_at` y `deleted_by`, después de validar su parámetro como en la edición. Eliminar una regla ya eliminada, o restaurar una activa, SHALL redirigir con "Sin cambios" sin auditar. Una regla eliminada MUST NOT aplicarse en las prevalidaciones siguientes; las validaciones ya guardadas conservan sus resultados.

#### Scenario: Eliminar una regla
- **WHEN** el Administrador elimina XML-010 en la página nacional y confirma
- **THEN** XML-010 desaparece del listado, la fila sigue en `validation_rules` con `deleted_at`, y la siguiente prevalidación nacional deja XML-010 como `NOT_APPLICABLE`

#### Scenario: Cancelar la confirmación
- **WHEN** el Administrador pulsa "Eliminar" en XML-010 y cancela la confirmación
- **THEN** no se envía ninguna petición y la regla sigue activa

#### Scenario: Restaurar una regla sin parámetro válido
- **WHEN** el Administrador restaura INT-004 sin haber capturado la Dirección
- **THEN** la respuesta es HTTP 400 con "Dirección: es obligatoria" y la regla sigue eliminada

#### Scenario: Restaurar con una clave desactivada
- **WHEN** el Administrador restaura XML-011, cuyo régimen `601` se desactivó en el catálogo
- **THEN** la respuesta es HTTP 400 con "Régimen fiscal: la clave no está activa en el catálogo" y la regla sigue eliminada

