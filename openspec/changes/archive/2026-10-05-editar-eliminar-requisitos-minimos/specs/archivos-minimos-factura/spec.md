## ADDED Requirements

### Requirement: Acciones Editar y Eliminar en la configuración
Cada fila de tipos definidos por el Administrador, en la tabla de configuración y en la de tipos inactivos, SHALL mostrar las acciones "Editar" y "Eliminar". "Editar" SHALL abrir el formulario de edición del tipo con sus valores actuales. "Eliminar" SHALL pedir una confirmación que nombre el tipo antes de enviar la eliminación, y la eliminación SHALL enviarse por POST con token CSRF. Las filas de los tipos del sistema MUST NOT mostrar ninguna de las dos acciones. Sólo el Administrador SHALL poder editar o eliminar; cualquier otro rol recibe HTTP 403.

#### Scenario: Acciones de un tipo definido por el Administrador
- **WHEN** el Administrador abre la pantalla y existe "Reporte de horas"
- **THEN** su fila muestra "Editar" y "Eliminar"; "Editar" abre el formulario con su nombre y su descripción

#### Scenario: Tipo del sistema sin acciones
- **WHEN** el Administrador abre la pantalla
- **THEN** la fila de "Orden de compra" no muestra "Editar" ni "Eliminar"

#### Scenario: Confirmación antes de eliminar
- **WHEN** el Administrador pulsa "Eliminar" en "Reporte de horas" y cancela la confirmación
- **THEN** no se envía ninguna petición y el tipo no cambia

#### Scenario: Eliminación sin CSRF o con otro rol
- **WHEN** se envía la eliminación sin token CSRF, o la envía un usuario PMO o Proveedor
- **THEN** la respuesta es HTTP 403 y el tipo no cambia

## MODIFIED Requirements

### Requirement: Tipos de documento soporte definidos por el Administrador
El Administrador SHALL poder dar de alta tipos de documento soporte con un nombre de 3 a 80 caracteres, una descripción opcional de hasta 300 caracteres, al menos un formato y un nivel para cada origen, preseleccionado en "No aplica". El sistema SHALL:
- normalizar el nombre, recortando los espacios de los extremos y colapsando los internos repetidos;
- rechazar un nombre que ya use otro tipo, sin distinguir mayúsculas;
- asignar al tipo la clave `SOPORTE_<id>`, que no cambia.

El Administrador SHALL poder editar el nombre, la descripción y los formatos de estos tipos, desactivarlos o reactivarlos, y eliminarlos mientras ningún documento use su clave. Un tipo inactivo MUST NOT ofrecerse en la carga documental ni exigirse en la prevalidación, y SHALL conservar sus niveles para cuando se reactive. Los tipos del sistema MUST NOT editarse, desactivarse ni eliminarse.

#### Scenario: Alta de un tipo soporte
- **WHEN** el Administrador da de alta "Reporte de horas" con formato PDF, Obligatorio para Internacional y No aplica para Nacional
- **THEN** existe un tipo activo con clave `SOPORTE_<id>` que aparece en la configuración; la carga documental de una factura internacional lo muestra como Obligatorio y la de una nacional no lo ofrece

#### Scenario: Nombre repetido
- **WHEN** el Administrador da de alta un tipo con el nombre "  orden   de COMPRA "
- **THEN** la respuesta es HTTP 409 con el mensaje "Ya existe un tipo de documento con ese nombre" y no se crea ningún tipo

#### Scenario: Sin formatos
- **WHEN** el Administrador da de alta un tipo sin seleccionar ningún formato
- **THEN** la respuesta es HTTP 400 con el mensaje "Seleccione al menos un formato" y no se crea ningún tipo

#### Scenario: Cambio de formatos
- **WHEN** el Administrador edita "Reporte de horas" para admitir PDF y PNG
- **THEN** la siguiente carga de `horas.png` como "Reporte de horas" se acepta, y los documentos ya cargados de ese tipo no cambian

#### Scenario: Desactivación y reactivación
- **WHEN** el Administrador desactiva "Reporte de horas", que era Obligatorio para Internacional
- **THEN** la carga documental ya no lo ofrece, la prevalidación ya no lo exige y los documentos ya cargados de ese tipo siguen listados y descargables en el detalle de la factura; al reactivarlo vuelve a ser Obligatorio para Internacional

#### Scenario: Tipo del sistema
- **WHEN** el Administrador envía la edición o la desactivación de "Orden de compra"
- **THEN** la respuesta es HTTP 409 con el mensaje "Los tipos de documento del sistema no se pueden editar ni desactivar" y el tipo no cambia

#### Scenario: Eliminación de un tipo sin documentos
- **WHEN** el Administrador elimina "Reporte de horas", que ningún documento usa, y confirma
- **THEN** el tipo desaparece de la configuración, de los tipos inactivos y de la carga documental, y la pantalla muestra el aviso "Tipo eliminado"

#### Scenario: Eliminación de un tipo con documentos
- **WHEN** el Administrador elimina "Reporte de horas" y existe al menos un documento, vigente o reemplazado, con su clave
- **THEN** la respuesta es HTTP 409 con el mensaje "El tipo ya tiene documentos cargados; desactívelo en su lugar" y el tipo no cambia

#### Scenario: Eliminación de un tipo del sistema
- **WHEN** el Administrador envía la eliminación de "Orden de compra"
- **THEN** la respuesta es HTTP 409 con el mensaje "Los elementos del sistema no se pueden eliminar" y el tipo no cambia

#### Scenario: Eliminación de un tipo inexistente
- **WHEN** el Administrador envía la eliminación de un id que no existe o que ya se eliminó
- **THEN** la respuesta es HTTP 404 y no se agrega ningún registro a `audit_logs`

### Requirement: Auditoría de la configuración de archivos mínimos
Cada cambio guardado SHALL generar un registro de auditoría con el `user_id` del Administrador:
- `INVOICE_DOCUMENT_REQUIREMENTS_UPDATED` al guardar la configuración, con el nivel anterior y el nuevo de cada tipo y origen que cambió;
- `INVOICE_DOCUMENT_TYPE_CREATED` al dar de alta un tipo, con su clave, nombre, formatos y niveles;
- `INVOICE_DOCUMENT_TYPE_UPDATED` al editar un tipo, con los valores anteriores y nuevos de los campos que cambiaron;
- `INVOICE_DOCUMENT_TYPE_DELETED` al eliminar un tipo, con su clave, nombre, descripción y niveles en `old_value`;
- `INVOICE_DOCUMENT_TYPE_STATUS_CHANGED` al desactivar o reactivar un tipo.

Una operación rechazada o un guardado sin cambios MUST NOT generar registros de auditoría.

#### Scenario: Cambio de nivel auditado
- **WHEN** el Administrador cambia "Orden de compra" de Obligatorio a Opcional en la columna Internacional y guarda
- **THEN** `audit_logs` contiene un registro `INVOICE_DOCUMENT_REQUIREMENTS_UPDATED` con su `user_id`, `old_value = {"PURCHASE_ORDER": {"international": "REQUIRED"}}` y `new_value = {"PURCHASE_ORDER": {"international": "OPTIONAL"}}`

#### Scenario: Alta auditada
- **WHEN** el Administrador da de alta "Reporte de horas"
- **THEN** `audit_logs` contiene un registro `INVOICE_DOCUMENT_TYPE_CREATED` con la clave `SOPORTE_<id>`, el nombre, los formatos y los dos niveles

#### Scenario: Operación rechazada sin auditoría
- **WHEN** una operación de configuración se rechaza con HTTP 400, 403 o 409
- **THEN** no se agrega ningún registro a `audit_logs`

#### Scenario: Eliminación auditada
- **WHEN** el Administrador elimina "Reporte de horas"
- **THEN** `audit_logs` contiene un registro `INVOICE_DOCUMENT_TYPE_DELETED` con su `user_id`, el id del tipo y, en `old_value`, la clave, el nombre y los niveles que tenía
