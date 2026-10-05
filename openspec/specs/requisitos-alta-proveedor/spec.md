# requisitos-alta-proveedor Specification

## Purpose
Requisitos de alta del proveedor (HU-21, RF-19 propuesto, RN-HU21-01 a RN-HU21-03): catálogo de documentos del expediente con un nivel por tipo de proveedor (persona moral, persona física e internacional), configuración exclusiva del Administrador, requisitos definidos por el Administrador, requisitos que aplican a cada proveedor y validación de la carga, checklist del expediente, protección contra ediciones concurrentes y auditoría. La autorización (acceso-proveedores) y SUP-003 (motor-validacion) exigen estos requisitos.
## Requirements
### Requirement: Catálogo de requisitos de alta
El sistema SHALL mantener un catálogo persistente de los documentos que forman el expediente del proveedor (requisitos de alta). Cada requisito SHALL tener:
- una clave inmutable, que es el valor que se guarda en `documents.document_type` de los documentos del expediente;
- un nombre en español y una descripción opcional, que se muestran en el expediente;
- si es un requisito del sistema o uno definido por el Administrador;
- si está activo;
- un nivel para cada tipo de proveedor (persona moral, persona física e internacional): `REQUIRED` ("Obligatorio"), `OPTIONAL` ("Opcional") o `NOT_APPLICABLE` ("No aplica").

El tipo de proveedor SHALL determinarse así: un proveedor con `origin = INTERNATIONAL` es Internacional, sin importar su tipo de persona; uno nacional es Persona moral o Persona física según su `supplier_type`.

El catálogo SHALL incluir estos requisitos del sistema con estos valores (clave · nombre · persona moral · persona física · internacional):
- `INCORPORATION_ACT` · Acta constitutiva · Obligatorio · No aplica · No aplica;
- `POWER_OF_ATTORNEY` · Poderes · Obligatorio · No aplica · No aplica;
- `TAX_STATUS` · Cédula fiscal · Obligatorio · Obligatorio · No aplica;
- `LEGAL_REP_ID` · Identificación del representante legal · Obligatorio · No aplica · No aplica;
- `LEGAL_REP_ADDRESS_PROOF` · Comprobante de domicilio del representante legal · Obligatorio · No aplica · No aplica;
- `ADDRESS_PROOF` · Comprobante de domicilio · Obligatorio · Obligatorio · No aplica;
- `BANK_STATEMENT` · Estado de cuenta bancario · Obligatorio · Obligatorio · No aplica;
- `OFFICIAL_ID` · Identificación oficial · No aplica · Obligatorio · No aplica;
- `SAT_OPINION` · Opinión de cumplimiento · Opcional · Opcional · No aplica;
- `ECONOMIC_PROPOSAL` · Propuesta económica · Opcional · Opcional · No aplica;
- `DUE_DILIGENCE` · Debida diligencia · Opcional · No aplica · No aplica;
- `LOCATION` · Ubicación · Opcional · Opcional · No aplica;
- `SUPPLIER_CONTRACT` · Contrato · No aplica · No aplica · No aplica, fijo: el contrato firmado se carga en cada contrato (capacidad `requisitos-alta-contrato`).

#### Scenario: Catálogo inicial tras la migración
- **WHEN** se aplican las migraciones sobre una base con proveedores y documentos de expediente existentes
- **THEN** el catálogo contiene los 13 requisitos del sistema, activos y con los valores anteriores; ningún proveedor cambia de estatus y cada documento conserva su `document_type`

#### Scenario: Nombres en español
- **WHEN** el Administrador abre el expediente de un proveedor
- **THEN** los requisitos se muestran por su nombre del catálogo (por ejemplo "Cédula fiscal" y "Poderes"), no por su clave

#### Scenario: Contrato cargado antes en el expediente
- **WHEN** un proveedor tenía cargado un documento `SUPPLIER_CONTRACT` antes de la migración de `requisitos-alta-contrato`
- **THEN** su expediente ya no lista "Contrato" entre los requisitos, y "Otros documentos del expediente" lo lista y permite descargarlo

### Requirement: Configuración exclusiva del Administrador
La página `GET /admin/supplier-requirements` y las operaciones `POST /admin/supplier-requirements`, `POST /admin/supplier-requirements/types`, `POST /admin/supplier-requirements/types/{type_id}` y `POST /admin/supplier-requirements/types/{type_id}/status` SHALL estar disponibles únicamente para el rol `Administrador`. Toda operación `POST` MUST exigir un token CSRF válido. El menú "Requisitos de alta" SHALL mostrarse sólo al rol `Administrador`.

#### Scenario: PMO sin acceso
- **WHEN** un usuario `PMO` solicita la página de configuración o envía cualquiera de sus operaciones
- **THEN** la respuesta es HTTP 403 y la configuración no cambia

#### Scenario: Proveedor sin acceso
- **WHEN** un usuario `Proveedor` solicita la página de configuración o envía cualquiera de sus operaciones
- **THEN** la respuesta es HTTP 403 y la configuración no cambia

#### Scenario: Envío sin token CSRF
- **WHEN** un Administrador envía `POST /admin/supplier-requirements` sin token CSRF o con uno inválido
- **THEN** la respuesta es HTTP 403 y la configuración no cambia

### Requirement: Configuración de los requisitos por tipo de proveedor
La página de configuración SHALL mostrar una fila por cada requisito activo, con su nombre, su descripción y un selector de nivel para Persona moral, otro para Persona física y otro para Internacional. Primero aparecen los requisitos del sistema, en el orden del catálogo, y después los del Administrador, por nombre.

Los tres niveles de `SUPPLIER_CONTRACT` SHALL ser fijos en No aplica: la página los muestra como texto con el ícono de candado y el motivo "Se carga en cada contrato", sin selectores. Una petición que intente cambiarlos SHALL rechazarse con HTTP 409 y el mensaje "Contrato tiene un nivel fijo para <tipo de proveedor en plural>" (por ejemplo, "personas morales"), sin guardar ningún cambio.

Al guardar, el sistema SHALL validar todos los niveles recibidos y actualizar en una sola transacción los que cambiaron. Un nivel distinto de `REQUIRED`, `OPTIONAL` o `NOT_APPLICABLE`, o la falta de un nivel editable de un requisito activo, SHALL rechazar el guardado completo con HTTP 400. Si ningún nivel cambió, el sistema SHALL informar "Sin cambios" sin modificar nada.

#### Scenario: Hacer opcional un requisito
- **WHEN** el Administrador cambia "Poderes" a Opcional en la columna Persona moral y guarda
- **THEN** la página muestra "Configuración guardada", y el expediente de una persona moral "Registrado" sin poderes muestra "Poderes" como "Opcional · Pendiente" y no lo cuenta entre los obligatorios pendientes

#### Scenario: Exigir un requisito al proveedor internacional
- **WHEN** el Administrador cambia "Estado de cuenta bancario" a Obligatorio en la columna Internacional y guarda
- **THEN** el expediente de un proveedor internacional muestra "Estado de cuenta bancario" como Obligatorio, y el proveedor no puede autorizarse sin ese documento

#### Scenario: Contrato con nivel fijo
- **WHEN** el Administrador abre la configuración
- **THEN** la fila "Contrato" muestra "No aplica" con candado en las tres columnas y el motivo "Se carga en cada contrato", sin selectores

#### Scenario: Petición manipulada sobre el Contrato
- **WHEN** la petición trae `OPTIONAL` como nivel de Persona moral de `SUPPLIER_CONTRACT`, junto con otros cambios válidos
- **THEN** la respuesta es HTTP 409 con el mensaje "Contrato tiene un nivel fijo para personas morales" y no se guarda ningún cambio

#### Scenario: Guardar sin cambios
- **WHEN** el Administrador guarda la configuración sin modificar ningún nivel
- **THEN** la página muestra "Sin cambios" y no se agrega ningún registro de auditoría

#### Scenario: Nivel inválido
- **WHEN** la petición trae `MANDATORY` como nivel de un requisito, junto con otros cambios válidos
- **THEN** la respuesta es HTTP 400 con el mensaje "Nivel de exigencia inválido" y no se guarda ningún cambio

### Requirement: Requisitos definidos por el Administrador
El Administrador SHALL poder dar de alta requisitos con un nombre de 3 a 80 caracteres, una descripción opcional de hasta 300 caracteres y un nivel para cada tipo de proveedor, preseleccionado en "No aplica". El sistema SHALL:
- normalizar el nombre, recortando los espacios de los extremos y colapsando los internos repetidos;
- rechazar con HTTP 409 un nombre que ya use otro requisito, sin distinguir mayúsculas;
- asignar al requisito la clave `REQUISITO_<id>`, que no cambia.

El Administrador SHALL poder editar el nombre y la descripción de estos requisitos, desactivarlos o reactivarlos, y eliminarlos mientras ningún documento use su clave. Un requisito inactivo MUST NOT ofrecerse en el expediente ni exigirse al autorizar o en SUP-003, y SHALL conservar sus niveles para cuando se reactive. Los requisitos del sistema MUST NOT editarse, desactivarse ni eliminarse; sólo cambian sus niveles.

#### Scenario: Alta de un requisito
- **WHEN** el Administrador da de alta "Declaración de ISR por retenciones de salarios", Obligatorio para Persona moral y No aplica para los demás
- **THEN** existe un requisito activo con clave `REQUISITO_<id>` que aparece en la configuración, y el expediente de una persona moral lo muestra como "Obligatorio · Pendiente"

#### Scenario: Nombre repetido
- **WHEN** el Administrador da de alta un requisito con el nombre "  cédula   FISCAL "
- **THEN** la respuesta es HTTP 409 con el mensaje "Ya existe un requisito con ese nombre" y no se crea ningún requisito

#### Scenario: Desactivación y reactivación
- **WHEN** el Administrador desactiva "Declaración de ISR por retenciones de salarios", que era Obligatorio para Persona moral
- **THEN** el expediente ya no lo pide, la autorización y SUP-003 ya no lo exigen, y los documentos ya cargados de ese tipo siguen listados y descargables; al reactivarlo vuelve a ser Obligatorio para Persona moral

#### Scenario: Requisito del sistema
- **WHEN** el Administrador envía la edición o la desactivación de "Cédula fiscal"
- **THEN** la respuesta es HTTP 409 con el mensaje "Los requisitos del sistema no se pueden editar ni desactivar" y el requisito no cambia

#### Scenario: Eliminación de un tipo sin documentos
- **WHEN** el Administrador elimina "Declaración de ISR por retenciones de salarios", que ningún documento usa, y confirma
- **THEN** el tipo desaparece de la configuración, de los tipos inactivos y de la carga documental, y la pantalla muestra el aviso "Tipo eliminado"

#### Scenario: Eliminación de un tipo con documentos
- **WHEN** el Administrador elimina "Declaración de ISR por retenciones de salarios" y existe al menos un documento, vigente o reemplazado, con su clave
- **THEN** la respuesta es HTTP 409 con el mensaje "El tipo ya tiene documentos cargados; desactívelo en su lugar" y el tipo no cambia

#### Scenario: Eliminación de un tipo del sistema
- **WHEN** el Administrador envía la eliminación de "Cédula fiscal"
- **THEN** la respuesta es HTTP 409 con el mensaje "Los elementos del sistema no se pueden eliminar" y el tipo no cambia

#### Scenario: Eliminación de un tipo inexistente
- **WHEN** el Administrador envía la eliminación de un id que no existe o que ya se eliminó
- **THEN** la respuesta es HTTP 404 y no se agrega ningún registro a `audit_logs`

### Requirement: Requisitos que aplican a cada proveedor
Los requisitos que aplican a un proveedor SHALL ser los requisitos activos cuyo nivel para su tipo de proveedor es Obligatorio u Opcional. Los requisitos exigibles SHALL ser los Obligatorios y, si el alta es por cotización o licitación (`economic_proposal`), también "Propuesta económica" cuando su nivel no es No aplica. Un requisito SHALL cumplirse con un documento vigente (`is_current`) de su tipo en el expediente del proveedor (`invoice_id` nulo); la antigüedad del documento no afecta el cumplimiento.

`POST /suppliers/{supplier_id}/documents` SHALL rechazar con HTTP 400 y el mensaje "El documento no aplica a este proveedor", antes de escribir el archivo, un tipo que no aplica al proveedor: con nivel No aplica para su tipo, inactivo o inexistente. Las verificaciones existentes de permisos, contenido y tamaño SHALL mantenerse.

#### Scenario: Persona moral nacional
- **WHEN** con la configuración inicial se abre el expediente de una persona moral nacional
- **THEN** se piden como obligatorios Acta constitutiva, Poderes, Cédula fiscal, Identificación del representante legal, Comprobante de domicilio del representante legal, Comprobante de domicilio y Estado de cuenta bancario; se ofrecen como opcionales Opinión de cumplimiento, Propuesta económica, Debida diligencia y Ubicación; no se ofrecen Identificación oficial ni Contrato

#### Scenario: Persona física nacional
- **WHEN** con la configuración inicial se abre el expediente de una persona física nacional
- **THEN** se piden como obligatorios Identificación oficial, Cédula fiscal, Comprobante de domicilio y Estado de cuenta bancario, y no se ofrecen Acta constitutiva, Poderes ni Contrato

#### Scenario: Proveedor internacional con la configuración inicial
- **WHEN** con la configuración inicial se abre el expediente de un proveedor internacional
- **THEN** el panel muestra "Sin requisitos de alta configurados para proveedores internacionales" y el proveedor puede autorizarse sin documentos

#### Scenario: Alta por cotización
- **WHEN** una persona moral tiene `economic_proposal` y "Propuesta económica" es Opcional para Persona moral
- **THEN** su expediente muestra "Propuesta económica" como Obligatorio, con la nota "Alta por cotización o licitación", y el proveedor no puede autorizarse sin ella

#### Scenario: Documento que no aplica
- **WHEN** se envía un documento con `document_type = SUPPLIER_CONTRACT` al expediente de una persona moral
- **THEN** la respuesta es HTTP 400 con el mensaje "El documento no aplica a este proveedor" y no se escribe ningún archivo en `storage/`

### Requirement: Checklist de requisitos de alta en el expediente
El expediente del proveedor SHALL mostrar el panel "Requisitos de alta" con los requisitos que le aplican, primero los exigibles y después los opcionales, cada grupo en el orden del catálogo. De cada requisito SHALL mostrar su nombre, su nivel, su descripción si la tiene y su estado: el nombre del archivo y la fecha del documento vigente, o "Pendiente". Un documento con más de tres meses SHALL mostrar "Advertencia de vigencia (+3 meses)" y contar como cargado.

El panel SHALL indicar "Falta 1 requisito obligatorio", "Faltan N requisitos obligatorios" o "Requisitos de alta completos"; sin requisitos que apliquen, "Sin requisitos de alta configurados para <tipo de proveedor>". Los documentos de tipos que ya no aplican MUST NOT contarse y SHALL listarse, descargables, en "Otros documentos del expediente". El formulario "Agregar o reemplazar documento" SHALL ofrecer sólo los requisitos que aplican, con los exigibles marcados como obligatorios.

#### Scenario: Requisitos pendientes
- **WHEN** con la configuración inicial una persona moral "Registrado" sólo tiene cargados el acta constitutiva, la cédula fiscal y el estado de cuenta bancario
- **THEN** el panel muestra Poderes, Identificación del representante legal, Comprobante de domicilio del representante legal y Comprobante de domicilio como "Obligatorio · Pendiente" e indica "Faltan 4 requisitos obligatorios"

#### Scenario: Requisitos completos
- **WHEN** ese proveedor carga los cuatro documentos pendientes
- **THEN** el panel indica "Requisitos de alta completos"

#### Scenario: Documento con más de tres meses
- **WHEN** la cédula fiscal cargada de un proveedor tiene fecha de hace cuatro meses y los demás obligatorios están cargados
- **THEN** la cédula fiscal muestra "Advertencia de vigencia (+3 meses)" y el panel indica "Requisitos de alta completos"

#### Scenario: Documento de un tipo que dejó de aplicar
- **WHEN** una persona moral tiene cargada su ubicación y el Administrador cambia "Ubicación" a No aplica en la columna Persona moral
- **THEN** el panel ya no lista la ubicación entre los requisitos, y "Otros documentos del expediente" la lista y permite descargarla

### Requirement: Protección contra ediciones concurrentes
La página de configuración SHALL incluir la huella `config_version` de la configuración que muestra: el SHA-256 de la clave, los tres niveles y el estado activo de todos los requisitos. Si al guardar la huella recibida falta o no coincide con la de la configuración vigente, el sistema SHALL responder HTTP 409 sin guardar ningún cambio.

#### Scenario: Dos Administradores editan a la vez
- **WHEN** los Administradores A y B abren la configuración, A guarda un cambio y después B guarda el suyo
- **THEN** B recibe HTTP 409 con el mensaje "La configuración cambió mientras la editaba. Recargue la página." y sólo persiste el cambio de A

### Requirement: Auditoría de la configuración de requisitos de alta
Cada cambio guardado SHALL generar un registro de auditoría con el `user_id` del Administrador:
- `SUPPLIER_REQUIREMENTS_UPDATED` al guardar la configuración, con el nivel anterior y el nuevo de cada requisito y tipo de proveedor que cambió, con las claves `persona_moral`, `persona_fisica` e `international`;
- `SUPPLIER_DOCUMENT_TYPE_CREATED` al dar de alta un requisito, con su clave, nombre y niveles;
- `SUPPLIER_DOCUMENT_TYPE_UPDATED` al editar un requisito, con los valores anteriores y nuevos de los campos que cambiaron;
- `SUPPLIER_DOCUMENT_TYPE_DELETED` al eliminar un tipo, con su clave, nombre, descripción y niveles en `old_value`;
- `SUPPLIER_DOCUMENT_TYPE_STATUS_CHANGED` al desactivar o reactivar un requisito.

Una operación rechazada o un guardado sin cambios MUST NOT generar registros de auditoría.

#### Scenario: Cambio de nivel auditado
- **WHEN** el Administrador cambia "Poderes" de Obligatorio a Opcional en la columna Persona moral y guarda
- **THEN** `audit_logs` contiene un registro `SUPPLIER_REQUIREMENTS_UPDATED` con su `user_id`, `old_value = {"POWER_OF_ATTORNEY": {"persona_moral": "REQUIRED"}}` y `new_value = {"POWER_OF_ATTORNEY": {"persona_moral": "OPTIONAL"}}`

#### Scenario: Operación rechazada sin auditoría
- **WHEN** una operación de configuración se rechaza con HTTP 400, 403 o 409
- **THEN** no se agrega ningún registro a `audit_logs`

#### Scenario: Eliminación auditada
- **WHEN** el Administrador elimina "Declaración de ISR por retenciones de salarios"
- **THEN** `audit_logs` contiene un registro `SUPPLIER_DOCUMENT_TYPE_DELETED` con su `user_id`, el id del tipo y, en `old_value`, la clave, el nombre y los niveles que tenía

### Requirement: Acciones Editar y Eliminar en la configuración
Cada fila de requisitos definidos por el Administrador, en la tabla de configuración y en la de tipos inactivos, SHALL mostrar las acciones "Editar" y "Eliminar". "Editar" SHALL abrir el formulario de edición del tipo con sus valores actuales. "Eliminar" SHALL pedir una confirmación que nombre el tipo antes de enviar la eliminación, y la eliminación SHALL enviarse por POST con token CSRF. Las filas de los tipos del sistema MUST NOT mostrar ninguna de las dos acciones. Sólo el Administrador SHALL poder editar o eliminar; cualquier otro rol recibe HTTP 403.

#### Scenario: Acciones de un tipo definido por el Administrador
- **WHEN** el Administrador abre la pantalla y existe "Declaración de ISR por retenciones de salarios"
- **THEN** su fila muestra "Editar" y "Eliminar"; "Editar" abre el formulario con su nombre y su descripción

#### Scenario: Tipo del sistema sin acciones
- **WHEN** el Administrador abre la pantalla
- **THEN** la fila de "Cédula fiscal" no muestra "Editar" ni "Eliminar"

#### Scenario: Confirmación antes de eliminar
- **WHEN** el Administrador pulsa "Eliminar" en "Declaración de ISR por retenciones de salarios" y cancela la confirmación
- **THEN** no se envía ninguna petición y el tipo no cambia

#### Scenario: Eliminación sin CSRF o con otro rol
- **WHEN** se envía la eliminación sin token CSRF, o la envía un usuario PMO o Proveedor
- **THEN** la respuesta es HTTP 403 y el tipo no cambia

