## ADDED Requirements

### Requirement: Acciones Editar y Eliminar en la configuración
Cada fila de requisitos definidos por el Administrador, en la tabla de configuración y en la de tipos inactivos, SHALL mostrar las acciones "Editar" y "Eliminar". "Editar" SHALL abrir el formulario de edición del tipo con sus valores actuales. "Eliminar" SHALL pedir una confirmación que nombre el tipo antes de enviar la eliminación, y la eliminación SHALL enviarse por POST con token CSRF. Las filas de los tipos del sistema MUST NOT mostrar ninguna de las dos acciones. Sólo el Administrador SHALL poder editar o eliminar; cualquier otro rol recibe HTTP 403.

#### Scenario: Acciones de un tipo definido por el Administrador
- **WHEN** el Administrador abre la pantalla y existe "Convenio de confidencialidad"
- **THEN** su fila muestra "Editar" y "Eliminar"; "Editar" abre el formulario con su nombre y su descripción

#### Scenario: Tipo del sistema sin acciones
- **WHEN** el Administrador abre la pantalla
- **THEN** la fila de "Anexos" no muestra "Editar" ni "Eliminar"

#### Scenario: Confirmación antes de eliminar
- **WHEN** el Administrador pulsa "Eliminar" en "Convenio de confidencialidad" y cancela la confirmación
- **THEN** no se envía ninguna petición y el tipo no cambia

#### Scenario: Eliminación sin CSRF o con otro rol
- **WHEN** se envía la eliminación sin token CSRF, o la envía un usuario PMO o Proveedor
- **THEN** la respuesta es HTTP 403 y el tipo no cambia

## MODIFIED Requirements

### Requirement: Requisitos del contrato definidos por el Administrador
El Administrador SHALL poder dar de alta requisitos con un nombre de 3 a 80 caracteres, una descripción opcional de hasta 300 caracteres, un nivel (preseleccionado en "No aplica") y si admite varios archivos (preseleccionado en "No"). El sistema SHALL:
- normalizar el nombre, recortando los espacios de los extremos y colapsando los internos repetidos;
- rechazar con HTTP 409 un nombre que ya use otro requisito del contrato, sin distinguir mayúsculas;
- asignar al requisito la clave `REQ_CONTRATO_<id>`, que no cambia.

El Administrador SHALL poder editar el nombre y la descripción de estos requisitos, desactivarlos o reactivarlos, y eliminarlos mientras ningún documento use su clave. Si admite varios archivos MUST NOT cambiar después del alta. Un requisito inactivo MUST NOT ofrecerse en el expediente del contrato ni exigirse al activar o en DOC-005, y SHALL conservar su nivel para cuando se reactive. Los requisitos del sistema MUST NOT editarse, desactivarse ni eliminarse; sólo cambia su nivel, salvo el de `SIGNED_CONTRACT`.

#### Scenario: Alta de un requisito
- **WHEN** el Administrador da de alta "Convenio de confidencialidad", Obligatorio y de un solo archivo
- **THEN** existe un requisito activo con clave `REQ_CONTRATO_<id>` que aparece en la configuración, y el expediente de un contrato "Registrado" lo muestra como "Obligatorio · Pendiente"

#### Scenario: Nombre repetido
- **WHEN** el Administrador da de alta un requisito con el nombre "  ORDEN de   compra "
- **THEN** la respuesta es HTTP 409 con el mensaje "Ya existe un requisito con ese nombre" y no se crea ningún requisito

#### Scenario: Desactivación y reactivación
- **WHEN** el Administrador desactiva "Convenio de confidencialidad", que era Obligatorio
- **THEN** el expediente ya no lo pide, la activación y DOC-005 ya no lo exigen, y los documentos ya cargados de ese tipo siguen listados y descargables; al reactivarlo vuelve a ser Obligatorio

#### Scenario: Requisito del sistema
- **WHEN** el Administrador envía la edición o la desactivación de "Anexos"
- **THEN** la respuesta es HTTP 409 con el mensaje "Los requisitos del sistema no se pueden editar ni desactivar" y el requisito no cambia

#### Scenario: Eliminación de un tipo sin documentos
- **WHEN** el Administrador elimina "Convenio de confidencialidad", que ningún documento usa, y confirma
- **THEN** el tipo desaparece de la configuración, de los tipos inactivos y de la carga documental, y la pantalla muestra el aviso "Tipo eliminado"

#### Scenario: Eliminación de un tipo con documentos
- **WHEN** el Administrador elimina "Convenio de confidencialidad" y existe al menos un documento, vigente o reemplazado, con su clave
- **THEN** la respuesta es HTTP 409 con el mensaje "El tipo ya tiene documentos cargados; desactívelo en su lugar" y el tipo no cambia

#### Scenario: Eliminación de un tipo del sistema
- **WHEN** el Administrador envía la eliminación de "Anexos"
- **THEN** la respuesta es HTTP 409 con el mensaje "Los elementos del sistema no se pueden eliminar" y el tipo no cambia

#### Scenario: Eliminación de un tipo inexistente
- **WHEN** el Administrador envía la eliminación de un id que no existe o que ya se eliminó
- **THEN** la respuesta es HTTP 404 y no se agrega ningún registro a `audit_logs`

### Requirement: Auditoría de los requisitos del contrato
Cada cambio guardado SHALL generar un registro de auditoría con el `user_id` del Administrador:
- `CONTRACT_REQUIREMENTS_UPDATED` al guardar la configuración, con el nivel anterior y el nuevo de cada requisito que cambió;
- `CONTRACT_DOCUMENT_TYPE_CREATED` al dar de alta un requisito, con su clave, nombre, nivel y si admite varios archivos;
- `CONTRACT_DOCUMENT_TYPE_UPDATED` al editar un requisito, con los valores anteriores y nuevos de los campos que cambiaron;
- `CONTRACT_DOCUMENT_TYPE_DELETED` al eliminar un tipo, con su clave, nombre, descripción y niveles en `old_value`;
- `CONTRACT_DOCUMENT_TYPE_STATUS_CHANGED` al desactivar o reactivar un requisito;
- `CONTRACT_DOCUMENT_UPLOADED` o `CONTRACT_DOCUMENT_REPLACED` al cargar un documento, con su tipo y el contrato;
- `CONTRACT_STATUS_CHANGED` al activar un contrato, con `old_value = {"status": "REGISTERED"}` y `new_value = {"status": "ACTIVE"}`.

Una operación rechazada o un guardado sin cambios MUST NOT generar registros de auditoría.

#### Scenario: Cambio de nivel auditado
- **WHEN** el Administrador cambia "Orden de compra" de Opcional a Obligatorio y guarda
- **THEN** `audit_logs` contiene un registro `CONTRACT_REQUIREMENTS_UPDATED` con su `user_id`, `old_value = {"CONTRACT_PURCHASE_ORDER": "OPTIONAL"}` y `new_value = {"CONTRACT_PURCHASE_ORDER": "REQUIRED"}`

#### Scenario: Activación auditada
- **WHEN** el Administrador activa un contrato
- **THEN** `audit_logs` contiene `CONTRACT_STATUS_CHANGED` sobre ese contrato, con su `user_id`

#### Scenario: Operación rechazada sin auditoría
- **WHEN** una operación de configuración, de carga o de activación se rechaza con HTTP 400, 403 o 409
- **THEN** no se agrega ningún registro a `audit_logs`

#### Scenario: Eliminación auditada
- **WHEN** el Administrador elimina "Convenio de confidencialidad"
- **THEN** `audit_logs` contiene un registro `CONTRACT_DOCUMENT_TYPE_DELETED` con su `user_id`, el id del tipo y, en `old_value`, la clave, el nombre y los niveles que tenía
