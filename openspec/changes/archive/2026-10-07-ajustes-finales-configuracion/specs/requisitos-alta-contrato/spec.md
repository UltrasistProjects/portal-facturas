## ADDED Requirements

### Requirement: Edición y eliminación lógica de los requisitos del contrato
El Administrador SHALL poder editar el nombre y la descripción de cualquier requisito del contrato, del sistema o definido por el Administrador, activo o eliminado. La clave y si admite varios archivos MUST NOT cambiar.

El Administrador SHALL poder eliminar cualquier requisito con `POST /admin/contract-requirements/types/{type_id}/delete`, aunque tenga documentos cargados. La eliminación SHALL ser lógica: `is_active = false`, `deleted_at` y `deleted_by`, sin borrar la fila. `POST /admin/contract-requirements/types/{type_id}/restore` SHALL reactivarlo con el nivel que tenía. Un requisito eliminado:
- MUST NOT pedirse en el expediente del contrato ni exigirse en las activaciones siguientes ni en DOC-005;
- SHALL conservar su nivel, y sus documentos ya cargados SHALL seguir listados y descargables.

Eliminar un requisito ya eliminado, o restaurar uno activo, SHALL redirigir con "Sin cambios" sin auditar. Un id inexistente SHALL responder HTTP 404. Eliminar o agregar requisitos MUST NOT cambiar el estatus de ningún contrato.

#### Scenario: Eliminación del Contrato firmado
- **WHEN** el Administrador elimina "Contrato" (`SIGNED_CONTRACT`) y confirma
- **THEN** la fila sigue con `is_active = false` y `deleted_at`, un contrato "Registrado" sin contrato firmado y con los demás requisitos completos puede activarse, y los contratos firmados ya cargados siguen descargables

#### Scenario: Edición de un requisito del sistema
- **WHEN** el Administrador cambia el nombre de "Anexos" a "Anexos técnicos"
- **THEN** el expediente del contrato muestra "Anexos técnicos" y la clave sigue siendo `CONTRACT_ANNEXES`

#### Scenario: Restauración
- **WHEN** el Administrador restaura "Contrato", que era Obligatorio
- **THEN** el expediente de un contrato "Registrado" lo vuelve a pedir como Obligatorio

#### Scenario: Eliminación de un requisito inexistente
- **WHEN** el Administrador envía la eliminación de un id que no existe
- **THEN** la respuesta es HTTP 404 y no se agrega ningún registro a `audit_logs`

## MODIFIED Requirements

### Requirement: Configuración exclusiva del Administrador
La página `GET /admin/contract-requirements` y las operaciones `POST /admin/contract-requirements`, `POST /admin/contract-requirements/types`, `POST /admin/contract-requirements/types/{type_id}`, `POST /admin/contract-requirements/types/{type_id}/delete` y `POST /admin/contract-requirements/types/{type_id}/restore` SHALL estar disponibles únicamente para el rol `Administrador`. Toda operación `POST` MUST exigir un token CSRF válido.

El menú de Administración SHALL agrupar bajo el título "Requisitos mínimos" las tres configuraciones de documentos: "Archivos de factura" (`/admin/required-documents`), "Alta de proveedor" (`/admin/supplier-requirements`) y "Alta de contrato" (`/admin/contract-requirements`). El grupo SHALL mostrarse sólo al rol `Administrador`.

#### Scenario: PMO sin acceso
- **WHEN** un usuario `PMO` solicita la página de configuración o envía cualquiera de sus operaciones
- **THEN** la respuesta es HTTP 403 y la configuración no cambia

#### Scenario: Proveedor sin acceso
- **WHEN** un usuario `Proveedor` solicita la página de configuración o envía cualquiera de sus operaciones
- **THEN** la respuesta es HTTP 403 y la configuración no cambia

#### Scenario: Envío sin token CSRF
- **WHEN** un Administrador envía `POST /admin/contract-requirements` sin token CSRF o con uno inválido
- **THEN** la respuesta es HTTP 403 y la configuración no cambia

#### Scenario: Menú de Requisitos mínimos
- **WHEN** un Administrador abre cualquier página del portal
- **THEN** el menú muestra el grupo "Requisitos mínimos" con "Archivos de factura", "Alta de proveedor" y "Alta de contrato", y un PMO no ve el grupo

### Requirement: Configuración de los requisitos del contrato
La página de configuración SHALL mostrar una fila por cada requisito activo, con su nombre, su descripción, si admite varios archivos y un selector de nivel, incluidos los requisitos del sistema. Primero aparecen los requisitos del sistema, en el orden del catálogo, y después los del Administrador, por nombre.

Al guardar, el sistema SHALL validar todos los niveles recibidos y actualizar en una sola transacción los que cambiaron. Un nivel distinto de `REQUIRED`, `OPTIONAL` o `NOT_APPLICABLE`, o la falta del nivel de un requisito activo, SHALL rechazar el guardado completo con HTTP 400. Si ningún nivel cambió, el sistema SHALL informar "Sin cambios" sin modificar nada.

#### Scenario: Hacer obligatoria la orden de compra
- **WHEN** el Administrador cambia "Orden de compra" a Obligatorio y guarda
- **THEN** la página muestra "Configuración guardada", y el expediente de un contrato "Registrado" sin orden de compra la muestra como "Obligatorio · Pendiente" y la cuenta entre los obligatorios pendientes

#### Scenario: Dejar de pedir los anexos
- **WHEN** el Administrador cambia "Anexos" a No aplica y guarda
- **THEN** el expediente de un contrato ya no ofrece "Anexos" en el formulario de carga

#### Scenario: Nivel del Contrato editable
- **WHEN** el Administrador cambia "Contrato" a Opcional y guarda
- **THEN** la página muestra "Configuración guardada" y un contrato "Registrado" sin contrato firmado puede activarse si no le falta otro requisito obligatorio

#### Scenario: Guardar sin cambios
- **WHEN** el Administrador guarda la configuración sin modificar ningún nivel
- **THEN** la página muestra "Sin cambios" y no se agrega ningún registro de auditoría

#### Scenario: Nivel inválido
- **WHEN** la petición trae `MANDATORY` como nivel de un requisito, junto con otros cambios válidos
- **THEN** la respuesta es HTTP 400 con el mensaje "Nivel de exigencia inválido" y no se guarda ningún cambio

### Requirement: Requisitos del contrato definidos por el Administrador
El Administrador SHALL poder dar de alta requisitos con un nombre de 3 a 80 caracteres, una descripción opcional de hasta 300 caracteres, un nivel (preseleccionado en "No aplica") y si admite varios archivos (preseleccionado en "No"). El sistema SHALL:
- normalizar el nombre, recortando los espacios de los extremos y colapsando los internos repetidos;
- rechazar con HTTP 409 un nombre que ya use otro requisito del contrato, activo o eliminado, sin distinguir mayúsculas;
- asignar al requisito la clave `REQ_CONTRATO_<id>`, que no cambia.

La edición, la eliminación y la restauración de estos requisitos SHALL seguir "Edición y eliminación lógica de los requisitos del contrato".

#### Scenario: Alta de un requisito
- **WHEN** el Administrador da de alta "Convenio de confidencialidad", Obligatorio y de un solo archivo
- **THEN** existe un requisito activo con clave `REQ_CONTRATO_<id>` que aparece en la configuración, y el expediente de un contrato "Registrado" lo muestra como "Obligatorio · Pendiente"

#### Scenario: Nombre repetido
- **WHEN** el Administrador da de alta un requisito con el nombre "  ORDEN de   compra "
- **THEN** la respuesta es HTTP 409 con el mensaje "Ya existe un requisito con ese nombre" y no se crea ningún requisito

### Requirement: Auditoría de los requisitos del contrato
Cada cambio guardado SHALL generar un registro de auditoría con el `user_id` del Administrador:
- `CONTRACT_REQUIREMENTS_UPDATED` al guardar la configuración, con el nivel anterior y el nuevo de cada requisito que cambió;
- `CONTRACT_DOCUMENT_TYPE_CREATED` al dar de alta un requisito, con su clave, nombre, nivel y si admite varios archivos;
- `CONTRACT_DOCUMENT_TYPE_UPDATED` al editar un requisito, con los valores anteriores y nuevos de los campos que cambiaron;
- `CONTRACT_DOCUMENT_TYPE_DELETED` al eliminar un requisito, con `old_value = {"is_active": true}` y `new_value = {"is_active": false}`;
- `CONTRACT_DOCUMENT_TYPE_RESTORED` al restaurar un requisito, con `old_value = {"is_active": false}` y `new_value = {"is_active": true}`;
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
- **WHEN** una operación de configuración, de carga o de activación se rechaza con HTTP 400, 403, 404 o 409
- **THEN** no se agrega ningún registro a `audit_logs`

#### Scenario: Eliminación auditada
- **WHEN** el Administrador elimina "Convenio de confidencialidad"
- **THEN** `audit_logs` contiene un registro `CONTRACT_DOCUMENT_TYPE_DELETED` con su `user_id`, el id del requisito, `old_value = {"is_active": true}` y `new_value = {"is_active": false}`

### Requirement: Acciones Editar y Eliminar en la configuración
Cada fila de la tabla de configuración, de un requisito del sistema o del Administrador, SHALL mostrar las acciones "Editar" y "Eliminar". "Editar" SHALL abrir el formulario de edición del requisito con sus valores actuales. "Eliminar" SHALL pedir, sin diálogos nativos del navegador, una confirmación que nombre el requisito y explique que dejará de exigirse en las activaciones siguientes y que sus documentos se conservan. La eliminación SHALL enviarse por POST con token CSRF.

Por omisión, la página SHALL listar sólo los requisitos activos. El enlace "Mostrar eliminados (N)" SHALL listar los eliminados con su fecha de eliminación y las acciones "Editar" y "Restaurar". Sólo el Administrador SHALL poder editar, eliminar o restaurar; cualquier otro rol recibe HTTP 403.

#### Scenario: Acciones de un requisito del sistema
- **WHEN** el Administrador abre la pantalla
- **THEN** la fila de "Anexos" muestra "Editar" y "Eliminar"; "Editar" abre el formulario con su nombre y su descripción

#### Scenario: Confirmación antes de eliminar
- **WHEN** el Administrador pulsa "Eliminar" en "Anexos" y cancela la confirmación
- **THEN** no se envía ninguna petición y el requisito no cambia

#### Scenario: Eliminados ocultos por omisión
- **WHEN** "Anexos" está eliminado y el Administrador abre la pantalla
- **THEN** el requisito no aparece; tras pulsar "Mostrar eliminados (1)" aparece con "Restaurar"

#### Scenario: Eliminación sin CSRF o con otro rol
- **WHEN** se envía la eliminación o la restauración sin token CSRF, o la envía un usuario PMO o Proveedor
- **THEN** la respuesta es HTTP 403 y el requisito no cambia
