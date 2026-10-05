# requisitos-alta-contrato Specification

## Purpose
Requisitos de alta del contrato (HU-22, RF-20 propuesto, RN-HU22-01 a RN-HU22-04): catálogo de documentos del contrato con un solo nivel y si admite varios archivos (el Contrato es Obligatorio fijo), configuración exclusiva del Administrador en Requisitos mínimos, requisitos definidos por el Administrador, estatus del contrato (Registrado, Activo, Inactivo), expediente, carga y descarga de documentos del contrato, activación condicionada, requisitos en el listado de contratos, protección contra ediciones concurrentes y auditoría. DOC-005 (motor-validacion) exige estos requisitos.
## Requirements
### Requirement: Catálogo de requisitos del contrato
El sistema SHALL mantener un catálogo persistente de los documentos que forman el expediente de un contrato (requisitos del contrato). Cada requisito SHALL tener:
- una clave inmutable, que es el valor que se guarda en `documents.document_type` de los documentos del contrato;
- un nombre en español y una descripción opcional, que se muestran en el expediente del contrato;
- si es un requisito del sistema o uno definido por el Administrador;
- si está activo;
- si admite varios archivos;
- un nivel: `REQUIRED` ("Obligatorio"), `OPTIONAL` ("Opcional") o `NOT_APPLICABLE` ("No aplica"), igual para todos los contratos.

El catálogo SHALL incluir estos requisitos del sistema con estos valores iniciales (clave · nombre · nivel · varios archivos):
- `SIGNED_CONTRACT` · Contrato · Obligatorio · No;
- `CONTRACT_PURCHASE_ORDER` · Orden de compra · Opcional · Sí;
- `CONTRACT_ANNEXES` · Anexos · Opcional · Sí.

#### Scenario: Catálogo inicial tras la migración
- **WHEN** se aplica la migración sobre una base con contratos existentes
- **THEN** el catálogo contiene los 3 requisitos del sistema, activos y con sus valores iniciales, y ningún contrato cambia de estatus

#### Scenario: Nombres en español
- **WHEN** el Administrador abre el expediente de un contrato
- **THEN** los requisitos se muestran por su nombre del catálogo (por ejemplo "Orden de compra" y "Anexos"), no por su clave

### Requirement: Configuración exclusiva del Administrador
La página `GET /admin/contract-requirements` y las operaciones `POST /admin/contract-requirements`, `POST /admin/contract-requirements/types`, `POST /admin/contract-requirements/types/{type_id}` y `POST /admin/contract-requirements/types/{type_id}/status` SHALL estar disponibles únicamente para el rol `Administrador`. Toda operación `POST` MUST exigir un token CSRF válido.

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
La página de configuración SHALL mostrar una fila por cada requisito activo, con su nombre, su descripción, si admite varios archivos y un selector de nivel. Primero aparecen los requisitos del sistema, en el orden del catálogo, y después los del Administrador, por nombre.

El nivel de `SIGNED_CONTRACT` SHALL ser fijo en Obligatorio: la página lo muestra como texto con el ícono de candado y el motivo "Todo contrato activo tiene su contrato firmado", sin selector. Una petición que intente cambiarlo SHALL rechazarse con HTTP 409 y el mensaje "Contrato tiene un nivel fijo", sin guardar ningún cambio.

Al guardar, el sistema SHALL validar todos los niveles recibidos y actualizar en una sola transacción los que cambiaron. Un nivel distinto de `REQUIRED`, `OPTIONAL` o `NOT_APPLICABLE`, o la falta del nivel de un requisito activo con nivel editable, SHALL rechazar el guardado completo con HTTP 400. Si ningún nivel cambió, el sistema SHALL informar "Sin cambios" sin modificar nada.

#### Scenario: Hacer obligatoria la orden de compra
- **WHEN** el Administrador cambia "Orden de compra" a Obligatorio y guarda
- **THEN** la página muestra "Configuración guardada", y el expediente de un contrato "Registrado" sin orden de compra la muestra como "Obligatorio · Pendiente" y la cuenta entre los obligatorios pendientes

#### Scenario: Dejar de pedir los anexos
- **WHEN** el Administrador cambia "Anexos" a No aplica y guarda
- **THEN** el expediente de un contrato ya no ofrece "Anexos" en el formulario de carga

#### Scenario: Contrato con nivel fijo
- **WHEN** el Administrador abre la configuración
- **THEN** la fila "Contrato" muestra "Obligatorio" con candado y el motivo "Todo contrato activo tiene su contrato firmado", sin selector

#### Scenario: Petición manipulada sobre el Contrato
- **WHEN** la petición trae `OPTIONAL` como nivel de `SIGNED_CONTRACT`, junto con otros cambios válidos
- **THEN** la respuesta es HTTP 409 con el mensaje "Contrato tiene un nivel fijo" y no se guarda ningún cambio

#### Scenario: Guardar sin cambios
- **WHEN** el Administrador guarda la configuración sin modificar ningún nivel
- **THEN** la página muestra "Sin cambios" y no se agrega ningún registro de auditoría

#### Scenario: Nivel inválido
- **WHEN** la petición trae `MANDATORY` como nivel de un requisito, junto con otros cambios válidos
- **THEN** la respuesta es HTTP 400 con el mensaje "Nivel de exigencia inválido" y no se guarda ningún cambio

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

### Requirement: Estatus del contrato
Un contrato SHALL tener uno de estos estatus, que la interfaz muestra en español: `REGISTERED` ("Registrado"), `ACTIVE` ("Activo") o `INACTIVE` ("Inactivo"). El alta de un contrato SHALL crearlo "Registrado". La única transición SHALL ser de "Registrado" a "Activo", mediante la activación. Un contrato "Registrado" MUST NOT ofrecerse en el formulario de alta de factura ni aceptarse en él, y no cumple SUP-002.

#### Scenario: Alta de contrato
- **WHEN** el Administrador crea un contrato
- **THEN** el contrato queda "Registrado", el sistema redirige a `/contracts/{contract_id}` con el aviso "Contrato creado. Cargue sus requisitos para activarlo." y se registra `CONTRACT_CREATED`

#### Scenario: Contrato registrado al facturar
- **WHEN** el proveedor de un contrato "Registrado" abre el formulario de alta de factura
- **THEN** el contrato no se ofrece; si el proveedor envía su identificador, la respuesta es HTTP 400 "El contrato no está activo" y no se crea la factura

#### Scenario: Contratos existentes
- **WHEN** se aplica la migración sobre una base con contratos `ACTIVE` sin documentos
- **THEN** los contratos siguen "Activo" y sus proveedores pueden seguir registrando facturas con ellos

### Requirement: Expediente del contrato
`GET /contracts/{contract_id}` SHALL mostrar a los roles `Administrador` y `PMO` el expediente del contrato:
- sus datos: proveedor (con liga a su expediente y su estatus), proyecto, líder, tecnología autorizada, monto, moneda, vigencia y estatus;
- el panel "Requisitos del contrato" con los requisitos que aplican (activos con nivel Obligatorio u Opcional), primero los obligatorios y después los opcionales, cada grupo en el orden del catálogo. De cada requisito SHALL mostrar su nombre, su nivel, su descripción si la tiene y sus documentos vigentes (nombre del archivo, fecha de carga y liga de descarga), o "Pendiente";
- el aviso "Falta 1 requisito obligatorio", "Faltan N requisitos obligatorios" o "Requisitos del contrato completos";
- "Otros documentos del contrato": los documentos vigentes de tipos que ya no aplican, descargables y sin contar para los requisitos;
- el historial de enmiendas del monto.

Un requisito SHALL cumplirse con al menos un documento vigente (`is_current`) de su tipo ligado al contrato. Para el rol `Proveedor`, la página y la descarga SHALL responder HTTP 403. Un contrato inexistente SHALL responder HTTP 404. El listado de contratos SHALL ligar cada proyecto a su expediente.

`GET /contracts/{contract_id}/documents/{document_id}/download` SHALL descargar un documento del contrato con las reglas de "Descarga segura de documentos" (spec `almacenamiento-documentos`), y SHALL responder HTTP 404 si el documento no pertenece al contrato de la URL.

#### Scenario: Requisitos pendientes
- **WHEN** el Administrador abre el expediente de un contrato "Registrado" sin documentos, con la configuración inicial
- **THEN** el panel muestra "Contrato" como "Obligatorio · Pendiente" e indica "Falta 1 requisito obligatorio", y muestra "Orden de compra" y "Anexos" como "Opcional · Pendiente"

#### Scenario: Requisitos completos con varios anexos
- **WHEN** el contrato tiene cargados el contrato firmado y dos anexos
- **THEN** el panel indica "Requisitos del contrato completos" y lista los dos archivos bajo "Anexos"

#### Scenario: PMO consulta
- **WHEN** un PMO abre el expediente de un contrato y descarga su contrato firmado
- **THEN** ve los datos, el panel y los documentos, descarga el archivo como adjunto, y no ve el formulario de carga ni el botón "Activar contrato"

#### Scenario: Proveedor sin acceso
- **WHEN** un usuario `Proveedor` solicita el expediente de un contrato propio o la descarga de uno de sus documentos
- **THEN** la respuesta es HTTP 403

#### Scenario: Documento de otro contrato
- **WHEN** se solicita `/contracts/{A}/documents/{D}/download` y `D` pertenece al contrato `B`
- **THEN** la respuesta es HTTP 404

### Requirement: Carga de documentos del contrato
`POST /contracts/{contract_id}/documents` SHALL estar disponible sólo para el rol `Administrador`, con token CSRF, para un contrato "Registrado" o "Activo". Recibe el tipo, el archivo y, para un requisito con varios archivos, opcionalmente el documento al que reemplaza. Antes de escribir el archivo, el sistema SHALL rechazar con HTTP 400:
- un tipo que no aplica al contrato (No aplica, inactivo o inexistente), con el mensaje "El documento no aplica a este contrato";
- un documento a reemplazar que no es un documento vigente del mismo tipo y del mismo contrato, con el mensaje "El documento a reemplazar no corresponde a este requisito".

Las verificaciones existentes de contenido y tamaño (spec `almacenamiento-documentos`) SHALL mantenerse. El archivo SHALL guardarse en `contracts/<contract_id>/<uuid>.<ext>` y el documento SHALL ligarse sólo al contrato (`contract_id`), sin `invoice_id` ni `supplier_id`. Al guardar:
- en un requisito de un solo archivo, el documento vigente de ese tipo, si existe, SHALL quedar con `is_current = false` y el nuevo SHALL guardar su id en `replaced_document_id`;
- en un requisito con varios archivos, el nuevo SHALL agregarse; si se indicó el documento a reemplazar, ése SHALL quedar con `is_current = false` y el nuevo SHALL guardar su id en `replaced_document_id`.

Ningún documento SHALL borrarse.

#### Scenario: Carga del contrato firmado
- **WHEN** el Administrador carga `contrato.pdf` como "Contrato" en un contrato "Registrado"
- **THEN** el documento queda vigente, ligado al contrato, en `contracts/<contract_id>/`, y el panel deja de mostrar "Contrato" como pendiente

#### Scenario: Reemplazo del contrato firmado
- **WHEN** el contrato ya tiene un "Contrato" vigente y el Administrador carga otro
- **THEN** el anterior queda con `is_current = false` y sigue en la base de datos, y el nuevo guarda su id en `replaced_document_id`

#### Scenario: Segundo anexo
- **WHEN** el contrato tiene un anexo vigente y el Administrador carga otro sin indicar a cuál reemplaza
- **THEN** los dos anexos quedan vigentes

#### Scenario: Anexo en un contrato activo
- **WHEN** el Administrador carga un anexo en un contrato "Activo"
- **THEN** el anexo se guarda y el contrato sigue "Activo"

#### Scenario: Tipo que no aplica
- **WHEN** se envía un documento con `document_type = INCORPORATION_ACT` a un contrato
- **THEN** la respuesta es HTTP 400 con el mensaje "El documento no aplica a este contrato" y no se escribe ningún archivo en `storage/`

#### Scenario: PMO intenta cargar
- **WHEN** un PMO envía `POST /contracts/{contract_id}/documents`
- **THEN** la respuesta es HTTP 403 y no se escribe ningún archivo en `storage/`

### Requirement: Activación del contrato
`POST /contracts/{contract_id}/activate` SHALL estar disponible sólo para el rol `Administrador`, con token CSRF. En una transacción, con la fila del contrato bloqueada, el sistema SHALL verificar con la configuración vigente:
- que el contrato esté "Registrado"; si no, HTTP 409 "Sólo se puede activar un contrato Registrado";
- que su proveedor esté "Autorizado"; si no, HTTP 409 "No se activó el contrato: el proveedor no está autorizado";
- que tenga cargados todos sus requisitos obligatorios; si no, HTTP 409 "No se activó el contrato: faltan requisitos obligatorios (<nombre>, <nombre>)", con los nombres en el orden del catálogo.

Si todo se cumple, el contrato SHALL pasar a "Activo", con `updated_at` y `updated_by` del Administrador, y el sistema SHALL redirigir a su expediente con el aviso "Contrato activado". Una activación rechazada MUST NOT cambiar el contrato.

En el expediente de un contrato "Registrado", el Administrador SHALL ver el botón "Activar contrato":
- con el proveedor "Autorizado" y los requisitos completos, el botón SHALL pedir confirmación en un diálogo de la página con el texto "Se activará el contrato <proyecto> de <razón social>. El proveedor podrá registrar facturas con él.";
- con el proveedor sin autorizar, SHALL mostrarse deshabilitado con "Autorice al proveedor para activar el contrato" y la liga a su expediente;
- con requisitos pendientes, SHALL mostrarse deshabilitado con "Cargue los requisitos obligatorios para activar".

El botón MUST NOT mostrarse al rol `PMO` ni en un contrato que no está "Registrado". La página MUST NOT usar diálogos nativos, scripts ni estilos en línea.

#### Scenario: Activación
- **WHEN** el Administrador carga el contrato firmado de un contrato "Registrado" cuyo proveedor está "Autorizado", pulsa "Activar contrato" y confirma
- **THEN** el contrato queda "Activo", el expediente muestra "Contrato activado" y el proveedor ve el contrato en el formulario de alta de factura

#### Scenario: Requisitos incompletos
- **WHEN** el Administrador abre el expediente de un contrato "Registrado" sin contrato firmado
- **THEN** el botón "Activar contrato" está deshabilitado con "Cargue los requisitos obligatorios para activar"

#### Scenario: Petición manipulada
- **WHEN** el Administrador envía `POST /contracts/{contract_id}/activate` para un contrato sin contrato firmado
- **THEN** la respuesta es HTTP 409 con "No se activó el contrato: faltan requisitos obligatorios (Contrato)" y el contrato sigue "Registrado"

#### Scenario: Proveedor no autorizado
- **WHEN** el contrato tiene sus requisitos completos y su proveedor está "Registrado"
- **THEN** el botón está deshabilitado con "Autorice al proveedor para activar el contrato", y la petición directa responde HTTP 409 "No se activó el contrato: el proveedor no está autorizado"

#### Scenario: Requisito agregado mientras se activaba
- **WHEN** el Administrador A abre el expediente de un contrato con los requisitos completos, el Administrador B hace obligatoria la orden de compra y después A activa el contrato
- **THEN** la respuesta es HTTP 409 con "No se activó el contrato: faltan requisitos obligatorios (Orden de compra)" y el contrato sigue "Registrado"

#### Scenario: Contrato ya activo
- **WHEN** el Administrador envía la activación de un contrato "Activo"
- **THEN** la respuesta es HTTP 409 con "Sólo se puede activar un contrato Registrado" y no se agrega ningún registro de auditoría

#### Scenario: PMO intenta activar
- **WHEN** un PMO envía `POST /contracts/{contract_id}/activate`
- **THEN** la respuesta es HTTP 403 y el contrato no cambia

### Requirement: Requisitos en el listado de contratos
El listado de contratos SHALL mostrar el estatus de cada contrato en español, con un estilo distinto para "Registrado", "Activo" e "Inactivo", y la columna "Requisitos" con "Completos" o "Faltan N", calculada con la configuración vigente, también para los contratos activos. Los requisitos de los contratos de la página SHALL calcularse sin una consulta por contrato.

#### Scenario: Contrato por activar
- **WHEN** el Administrador abre `/contracts` y un contrato "Registrado" no tiene su contrato firmado
- **THEN** ese contrato muestra "Registrado" y "Faltan 1", y su proyecto liga a su expediente

#### Scenario: Contrato activo sin documentos
- **WHEN** existe un contrato "Activo" de antes de la migración, sin documentos
- **THEN** el listado lo muestra "Activo" con "Faltan 1"

### Requirement: Protección contra ediciones concurrentes
La página de configuración SHALL incluir la huella `config_version` de la configuración que muestra: el SHA-256 de la clave, el nivel y el estado activo de todos los requisitos del contrato. Si al guardar la huella recibida falta o no coincide con la de la configuración vigente, el sistema SHALL responder HTTP 409 sin guardar ningún cambio.

#### Scenario: Dos Administradores editan a la vez
- **WHEN** los Administradores A y B abren la configuración, A guarda un cambio y después B guarda el suyo
- **THEN** B recibe HTTP 409 con el mensaje "La configuración cambió mientras la editaba. Recargue la página." y sólo persiste el cambio de A

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

