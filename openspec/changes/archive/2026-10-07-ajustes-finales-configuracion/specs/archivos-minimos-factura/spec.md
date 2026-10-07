## ADDED Requirements

### Requirement: Edición y eliminación lógica de los tipos
El Administrador SHALL poder editar el nombre, la descripción y los formatos de cualquier tipo de documento de factura, sea del sistema o definido por el Administrador, activo o eliminado. La clave MUST NOT cambiar.

El Administrador SHALL poder eliminar cualquier tipo con `POST /admin/required-documents/types/{type_id}/delete`, aunque tenga documentos cargados. La eliminación SHALL ser lógica: `is_active = false`, `deleted_at` y `deleted_by`, sin borrar la fila. `POST /admin/required-documents/types/{type_id}/restore` SHALL reactivarlo con los niveles que tenía. Un tipo eliminado:
- MUST NOT ofrecerse en la carga documental, exigirse en la prevalidación ni en el envío;
- SHALL conservar sus niveles, y sus documentos ya cargados SHALL seguir listados con el nombre del tipo y descargables en el detalle de la factura.

Eliminar un tipo ya eliminado, o restaurar uno activo, SHALL redirigir con "Sin cambios" sin auditar. Un id inexistente SHALL responder HTTP 404. Los flujos que usan un tipo del sistema SHALL tolerar que esté eliminado: las reglas del CFDI (capacidad `motor-validacion`), el acuse de cancelación (`cancelacion-facturas`) y el Complemento de Pago (`pago-facturas`).

#### Scenario: Edición de un tipo del sistema
- **WHEN** el Administrador cambia el nombre de "Orden de compra" a "Orden de compra firmada"
- **THEN** la carga documental muestra "Orden de compra firmada", la clave sigue siendo `PURCHASE_ORDER` y los documentos ya cargados muestran el nombre nuevo

#### Scenario: Cambio de formatos
- **WHEN** el Administrador edita "Reporte de horas" para admitir PDF y PNG
- **THEN** la siguiente carga de `horas.png` como "Reporte de horas" se acepta, y los documentos ya cargados de ese tipo no cambian

#### Scenario: Eliminación de un tipo con documentos
- **WHEN** el Administrador elimina "Orden de compra", que tiene documentos cargados, y confirma
- **THEN** la fila sigue en `invoice_document_types` con `is_active = false` y `deleted_at`, el tipo desaparece de la configuración y de la carga documental, la prevalidación deja de exigirlo y los documentos ya cargados siguen descargables en el detalle

#### Scenario: Restauración
- **WHEN** el Administrador restaura "Orden de compra", que era Obligatorio para Nacional
- **THEN** vuelve a la configuración como Obligatorio para Nacional y la carga documental lo vuelve a pedir

#### Scenario: Eliminación de un tipo inexistente
- **WHEN** el Administrador envía la eliminación de un id que no existe
- **THEN** la respuesta es HTTP 404 y no se agrega ningún registro a `audit_logs`

## MODIFIED Requirements

### Requirement: Configuración exclusiva del Administrador
La página `GET /admin/required-documents` y las operaciones `POST /admin/required-documents`, `POST /admin/required-documents/types`, `POST /admin/required-documents/types/{type_id}`, `POST /admin/required-documents/types/{type_id}/delete` y `POST /admin/required-documents/types/{type_id}/restore` SHALL estar disponibles únicamente para el rol `Administrador`. Toda operación `POST` MUST exigir un token CSRF válido.

#### Scenario: PMO sin acceso
- **WHEN** un usuario con rol `PMO` solicita la página de configuración o envía cualquiera de sus operaciones
- **THEN** la respuesta es HTTP 403 y la configuración no cambia

#### Scenario: Proveedor sin acceso
- **WHEN** un usuario con rol `Proveedor` solicita la página de configuración o envía cualquiera de sus operaciones
- **THEN** la respuesta es HTTP 403 y la configuración no cambia

#### Scenario: Envío sin token CSRF
- **WHEN** un Administrador envía `POST /admin/required-documents` sin token CSRF o con uno inválido
- **THEN** la respuesta es HTTP 403 y la configuración no cambia

### Requirement: Configuración de los archivos mínimos por origen
La página de configuración SHALL mostrar una fila por cada tipo activo, con su nombre, sus formatos y un selector de nivel para Nacional y otro para Internacional, incluidos los tipos del sistema. Primero aparecen los tipos del sistema, en el orden del catálogo, y después los del Administrador, por nombre.

Al guardar, el sistema SHALL validar todos los niveles recibidos y actualizar en una sola transacción los que cambiaron. Un nivel distinto de `REQUIRED`, `OPTIONAL` o `NOT_APPLICABLE`, o la falta de un nivel de un tipo activo, SHALL rechazar el guardado completo con HTTP 400. Si ningún nivel cambió, el sistema SHALL informar "Sin cambios" sin modificar nada.

#### Scenario: Exigir un documento al proveedor internacional
- **WHEN** el Administrador cambia "Contrato" a Obligatorio en la columna Internacional y guarda
- **THEN** la página muestra "Configuración guardada" y la carga documental de una factura de un proveedor internacional muestra "Contrato" como Obligatorio

#### Scenario: Dejar de exigir la orden de compra al proveedor nacional
- **WHEN** el Administrador cambia "Orden de compra" a Opcional en la columna Nacional y guarda
- **THEN** la carga documental de una factura de un proveedor nacional muestra "Orden de compra" como Opcional

#### Scenario: Nivel de un tipo del sistema
- **WHEN** el Administrador cambia "XML del CFDI" a Opcional en la columna Nacional y guarda
- **THEN** la página muestra "Configuración guardada" y la carga documental de una factura nacional muestra "XML del CFDI" como Opcional

#### Scenario: Guardar sin cambios
- **WHEN** el Administrador guarda la configuración sin modificar ningún nivel
- **THEN** la página muestra "Sin cambios" y no se agrega ningún registro de auditoría

#### Scenario: Nivel inválido
- **WHEN** la petición trae `MANDATORY` como nivel de un tipo, junto con otros cambios válidos
- **THEN** la respuesta es HTTP 400 con el mensaje "Nivel de exigencia inválido" y no se guarda ningún cambio

### Requirement: Tipos de documento soporte definidos por el Administrador
El Administrador SHALL poder dar de alta tipos de documento soporte con un nombre de 3 a 80 caracteres, una descripción opcional de hasta 300 caracteres, al menos un formato y un nivel para cada origen, preseleccionado en "No aplica". El sistema SHALL:
- normalizar el nombre, recortando los espacios de los extremos y colapsando los internos repetidos;
- rechazar un nombre que ya use otro tipo, activo o eliminado, sin distinguir mayúsculas;
- asignar al tipo la clave `SOPORTE_<id>`, que no cambia.

La edición, la eliminación y la restauración de estos tipos SHALL seguir "Edición y eliminación lógica de los tipos".

#### Scenario: Alta de un tipo soporte
- **WHEN** el Administrador da de alta "Reporte de horas" con formato PDF, Obligatorio para Internacional y No aplica para Nacional
- **THEN** existe un tipo activo con clave `SOPORTE_<id>` que aparece en la configuración; la carga documental de una factura internacional lo muestra como Obligatorio y la de una nacional no lo ofrece

#### Scenario: Nombre repetido
- **WHEN** el Administrador da de alta un tipo con el nombre "  orden   de COMPRA "
- **THEN** la respuesta es HTTP 409 con el mensaje "Ya existe un tipo de documento con ese nombre" y no se crea ningún tipo

#### Scenario: Sin formatos
- **WHEN** el Administrador da de alta un tipo sin seleccionar ningún formato
- **THEN** la respuesta es HTTP 400 con el mensaje "Seleccione al menos un formato" y no se crea ningún tipo

### Requirement: Auditoría de la configuración de archivos mínimos
Cada cambio guardado SHALL generar un registro de auditoría con el `user_id` del Administrador:
- `INVOICE_DOCUMENT_REQUIREMENTS_UPDATED` al guardar la configuración, con el nivel anterior y el nuevo de cada tipo y origen que cambió;
- `INVOICE_DOCUMENT_TYPE_CREATED` al dar de alta un tipo, con su clave, nombre, formatos y niveles;
- `INVOICE_DOCUMENT_TYPE_UPDATED` al editar un tipo, con los valores anteriores y nuevos de los campos que cambiaron;
- `INVOICE_DOCUMENT_TYPE_DELETED` al eliminar un tipo, con `old_value = {"is_active": true}` y `new_value = {"is_active": false}`;
- `INVOICE_DOCUMENT_TYPE_RESTORED` al restaurar un tipo, con `old_value = {"is_active": false}` y `new_value = {"is_active": true}`.

Una operación rechazada o un guardado sin cambios MUST NOT generar registros de auditoría.

#### Scenario: Cambio de nivel auditado
- **WHEN** el Administrador cambia "Orden de compra" de Obligatorio a Opcional en la columna Internacional y guarda
- **THEN** `audit_logs` contiene un registro `INVOICE_DOCUMENT_REQUIREMENTS_UPDATED` con su `user_id`, `old_value = {"PURCHASE_ORDER": {"international": "REQUIRED"}}` y `new_value = {"PURCHASE_ORDER": {"international": "OPTIONAL"}}`

#### Scenario: Alta auditada
- **WHEN** el Administrador da de alta "Reporte de horas"
- **THEN** `audit_logs` contiene un registro `INVOICE_DOCUMENT_TYPE_CREATED` con la clave `SOPORTE_<id>`, el nombre, los formatos y los dos niveles

#### Scenario: Operación rechazada sin auditoría
- **WHEN** una operación de configuración se rechaza con HTTP 400, 403, 404 o 409
- **THEN** no se agrega ningún registro a `audit_logs`

#### Scenario: Eliminación auditada
- **WHEN** el Administrador elimina "Reporte de horas"
- **THEN** `audit_logs` contiene un registro `INVOICE_DOCUMENT_TYPE_DELETED` con su `user_id`, el id del tipo, `old_value = {"is_active": true}` y `new_value = {"is_active": false}`

### Requirement: Acciones Editar y Eliminar en la configuración
Cada fila de la tabla de configuración, de un tipo del sistema o del Administrador, SHALL mostrar las acciones "Editar" y "Eliminar". "Editar" SHALL abrir el formulario de edición del tipo con sus valores actuales. "Eliminar" SHALL pedir, sin diálogos nativos del navegador, una confirmación que nombre el tipo y explique que dejará de exigirse y que sus documentos se conservan. En un tipo del sistema, la confirmación SHALL explicar además qué deja de hacer el portal. La eliminación SHALL enviarse por POST con token CSRF.

Por omisión, la página SHALL listar sólo los tipos activos. El enlace "Mostrar eliminados (N)" SHALL listar los tipos eliminados con su fecha de eliminación y las acciones "Editar" y "Restaurar". Sólo el Administrador SHALL poder editar, eliminar o restaurar; cualquier otro rol recibe HTTP 403.

#### Scenario: Acciones de un tipo del sistema
- **WHEN** el Administrador abre la pantalla
- **THEN** la fila de "Orden de compra" muestra "Editar" y "Eliminar"; "Editar" abre el formulario con su nombre, su descripción y sus formatos

#### Scenario: Confirmación de un tipo atado al portal
- **WHEN** el Administrador pulsa "Eliminar" en "XML del CFDI"
- **THEN** la confirmación advierte que las facturas nacionales dejarán de exigir el CFDI y que sus reglas no se evaluarán sin XML

#### Scenario: Confirmación antes de eliminar
- **WHEN** el Administrador pulsa "Eliminar" en "Reporte de horas" y cancela la confirmación
- **THEN** no se envía ninguna petición y el tipo no cambia

#### Scenario: Eliminados ocultos por omisión
- **WHEN** "Reporte de horas" está eliminado y el Administrador abre la pantalla
- **THEN** el tipo no aparece; tras pulsar "Mostrar eliminados (1)" aparece con "Restaurar"

#### Scenario: Eliminación sin CSRF o con otro rol
- **WHEN** se envía la eliminación o la restauración sin token CSRF, o la envía un usuario PMO o Proveedor
- **THEN** la respuesta es HTTP 403 y el tipo no cambia

## REMOVED Requirements

### Requirement: Archivos fijos por origen
**Reason**: El usuario decidió que todos los registros, incluidos los precargados que usa el código, se puedan editar y eliminar. Los niveles de `INVOICE_XML`, `INVOICE_PDF`, `FOREIGN_INVOICE`, `CANCELLATION_ACK`, `PAYMENT_COMPLEMENT_XML` y `PAYMENT_COMPLEMENT_PDF` dejan de ser fijos.
**Migration**: La revisión `0019_types_soft_delete` retira `ck_invoice_document_types_fixed_levels` y `ck_invoice_document_types_system_active`. Los niveles actuales se conservan. Los flujos que dependen de esos tipos toleran sus nuevos niveles o su eliminación.
