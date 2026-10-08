## ADDED Requirements

### Requirement: Edición y eliminación lógica de los requisitos
El Administrador SHALL poder editar el nombre y la descripción de cualquier requisito de alta, del sistema o definido por el Administrador, activo o eliminado. La clave MUST NOT cambiar.

El Administrador SHALL poder eliminar cualquier requisito con `POST /admin/supplier-requirements/types/{type_id}/delete`, aunque tenga documentos cargados. La eliminación SHALL ser lógica: `is_active = false`, `deleted_at` y `deleted_by`, sin borrar la fila. `POST /admin/supplier-requirements/types/{type_id}/restore` SHALL reactivarlo con los niveles que tenía. Un requisito eliminado:
- MUST NOT pedirse en el expediente ni exigirse en las autorizaciones siguientes ni en SUP-003;
- SHALL conservar sus niveles, y sus documentos ya cargados SHALL seguir listados y descargables en el expediente.

Eliminar un requisito ya eliminado, o restaurar uno activo, SHALL redirigir con "Sin cambios" sin auditar. Un id inexistente SHALL responder HTTP 404. Eliminar o agregar requisitos MUST NOT cambiar el estatus de ningún proveedor.

#### Scenario: Edición de un requisito del sistema
- **WHEN** el Administrador cambia la descripción de "Cédula fiscal"
- **THEN** el expediente muestra la descripción nueva y la clave sigue siendo `TAX_STATUS`

#### Scenario: Eliminación de un requisito del sistema con documentos
- **WHEN** el Administrador elimina "Poderes", que tiene documentos cargados, y confirma
- **THEN** la fila sigue en `supplier_document_types` con `is_active = false` y `deleted_at`, el expediente ya no lo pide, una persona moral "Registrado" sin poderes y con los demás requisitos completos puede autorizarse, y los poderes ya cargados siguen descargables

#### Scenario: Restauración
- **WHEN** el Administrador restaura "Poderes", que era Obligatorio para Persona moral
- **THEN** el expediente de una persona moral lo vuelve a pedir como Obligatorio

#### Scenario: Eliminación de un requisito inexistente
- **WHEN** el Administrador envía la eliminación de un id que no existe
- **THEN** la respuesta es HTTP 404 y no se agrega ningún registro a `audit_logs`

## MODIFIED Requirements

### Requirement: Catálogo de requisitos de alta
El sistema SHALL mantener un catálogo persistente de los documentos que forman el expediente del proveedor (requisitos de alta). Cada requisito SHALL tener:
- una clave inmutable, que es el valor que se guarda en `documents.document_type` de los documentos del expediente;
- un nombre en español y una descripción opcional, que se muestran en el expediente;
- si es un requisito del sistema o uno definido por el Administrador;
- si está activo, con la fecha y el Administrador de su eliminación cuando no lo está;
- un nivel para cada tipo de proveedor (persona moral, persona física e internacional): `REQUIRED` ("Obligatorio"), `OPTIONAL` ("Opcional") o `NOT_APPLICABLE` ("No aplica").

El tipo de proveedor SHALL determinarse así: un proveedor con `origin = INTERNATIONAL` es Internacional, sin importar su tipo de persona; uno nacional es Persona moral o Persona física según su `supplier_type`.

El catálogo SHALL incluir estos requisitos del sistema con estos valores iniciales (clave · nombre · persona moral · persona física · internacional):
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
- `SUPPLIER_CONTRACT` · Contrato · No aplica · No aplica · No aplica: el contrato firmado se carga en cada contrato (capacidad `requisitos-alta-contrato`).

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
La página `GET /admin/supplier-requirements` y las operaciones `POST /admin/supplier-requirements`, `POST /admin/supplier-requirements/types`, `POST /admin/supplier-requirements/types/{type_id}`, `POST /admin/supplier-requirements/types/{type_id}/delete` y `POST /admin/supplier-requirements/types/{type_id}/restore` SHALL estar disponibles únicamente para el rol `Administrador`. Toda operación `POST` MUST exigir un token CSRF válido. El menú "Requisitos de alta" SHALL mostrarse sólo al rol `Administrador`.

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
La página de configuración SHALL mostrar una fila por cada requisito activo, con su nombre, su descripción y un selector de nivel para Persona moral, otro para Persona física y otro para Internacional, incluidos los requisitos del sistema. Primero aparecen los requisitos del sistema, en el orden del catálogo, y después los del Administrador, por nombre.

Al guardar, el sistema SHALL validar todos los niveles recibidos y actualizar en una sola transacción los que cambiaron. Un nivel distinto de `REQUIRED`, `OPTIONAL` o `NOT_APPLICABLE`, o la falta de un nivel de un requisito activo, SHALL rechazar el guardado completo con HTTP 400. Si ningún nivel cambió, el sistema SHALL informar "Sin cambios" sin modificar nada.

#### Scenario: Hacer opcional un requisito
- **WHEN** el Administrador cambia "Poderes" a Opcional en la columna Persona moral y guarda
- **THEN** la página muestra "Configuración guardada", y el expediente de una persona moral "Registrado" sin poderes muestra "Poderes" como "Opcional · Pendiente" y no lo cuenta entre los obligatorios pendientes

#### Scenario: Exigir un requisito al proveedor internacional
- **WHEN** el Administrador cambia "Estado de cuenta bancario" a Obligatorio en la columna Internacional y guarda
- **THEN** el expediente de un proveedor internacional muestra "Estado de cuenta bancario" como Obligatorio, y el proveedor no puede autorizarse sin ese documento

#### Scenario: Nivel del Contrato editable
- **WHEN** el Administrador cambia "Contrato" a Opcional en la columna Persona moral y guarda
- **THEN** la página muestra "Configuración guardada" y el expediente de una persona moral muestra "Contrato" como Opcional

#### Scenario: Guardar sin cambios
- **WHEN** el Administrador guarda la configuración sin modificar ningún nivel
- **THEN** la página muestra "Sin cambios" y no se agrega ningún registro de auditoría

#### Scenario: Nivel inválido
- **WHEN** la petición trae `MANDATORY` como nivel de un requisito, junto con otros cambios válidos
- **THEN** la respuesta es HTTP 400 con el mensaje "Nivel de exigencia inválido" y no se guarda ningún cambio

### Requirement: Requisitos definidos por el Administrador
El Administrador SHALL poder dar de alta requisitos con un nombre de 3 a 80 caracteres, una descripción opcional de hasta 300 caracteres y un nivel para cada tipo de proveedor, preseleccionado en "No aplica". El sistema SHALL:
- normalizar el nombre, recortando los espacios de los extremos y colapsando los internos repetidos;
- rechazar con HTTP 409 un nombre que ya use otro requisito, activo o eliminado, sin distinguir mayúsculas;
- asignar al requisito la clave `REQUISITO_<id>`, que no cambia.

La edición, la eliminación y la restauración de estos requisitos SHALL seguir "Edición y eliminación lógica de los requisitos".

#### Scenario: Alta de un requisito
- **WHEN** el Administrador da de alta "Declaración de ISR por retenciones de salarios", Obligatorio para Persona moral y No aplica para los demás
- **THEN** existe un requisito activo con clave `REQUISITO_<id>` que aparece en la configuración, y el expediente de una persona moral lo muestra como "Obligatorio · Pendiente"

#### Scenario: Nombre repetido
- **WHEN** el Administrador da de alta un requisito con el nombre "  cédula   FISCAL "
- **THEN** la respuesta es HTTP 409 con el mensaje "Ya existe un requisito con ese nombre" y no se crea ningún requisito

### Requirement: Auditoría de la configuración de requisitos de alta
Cada cambio guardado SHALL generar un registro de auditoría con el `user_id` del Administrador:
- `SUPPLIER_REQUIREMENTS_UPDATED` al guardar la configuración, con el nivel anterior y el nuevo de cada requisito y tipo de proveedor que cambió, con las claves `persona_moral`, `persona_fisica` e `international`;
- `SUPPLIER_DOCUMENT_TYPE_CREATED` al dar de alta un requisito, con su clave, nombre y niveles;
- `SUPPLIER_DOCUMENT_TYPE_UPDATED` al editar un requisito, con los valores anteriores y nuevos de los campos que cambiaron;
- `SUPPLIER_DOCUMENT_TYPE_DELETED` al eliminar un requisito, con `old_value = {"is_active": true}` y `new_value = {"is_active": false}`;
- `SUPPLIER_DOCUMENT_TYPE_RESTORED` al restaurar un requisito, con `old_value = {"is_active": false}` y `new_value = {"is_active": true}`.

Una operación rechazada o un guardado sin cambios MUST NOT generar registros de auditoría.

#### Scenario: Cambio de nivel auditado
- **WHEN** el Administrador cambia "Poderes" de Obligatorio a Opcional en la columna Persona moral y guarda
- **THEN** `audit_logs` contiene un registro `SUPPLIER_REQUIREMENTS_UPDATED` con su `user_id`, `old_value = {"POWER_OF_ATTORNEY": {"persona_moral": "REQUIRED"}}` y `new_value = {"POWER_OF_ATTORNEY": {"persona_moral": "OPTIONAL"}}`

#### Scenario: Operación rechazada sin auditoría
- **WHEN** una operación de configuración se rechaza con HTTP 400, 403, 404 o 409
- **THEN** no se agrega ningún registro a `audit_logs`

#### Scenario: Eliminación auditada
- **WHEN** el Administrador elimina "Poderes"
- **THEN** `audit_logs` contiene un registro `SUPPLIER_DOCUMENT_TYPE_DELETED` con su `user_id`, el id del requisito, `old_value = {"is_active": true}` y `new_value = {"is_active": false}`

### Requirement: Acciones Editar y Eliminar en la configuración
Cada fila de la tabla de configuración, de un requisito del sistema o del Administrador, SHALL mostrar las acciones "Editar" y "Eliminar". "Editar" SHALL abrir el formulario de edición del requisito con sus valores actuales. "Eliminar" SHALL pedir, sin diálogos nativos del navegador, una confirmación que nombre el requisito y explique que dejará de exigirse en las autorizaciones siguientes y que sus documentos se conservan. La eliminación SHALL enviarse por POST con token CSRF.

Por omisión, la página SHALL listar sólo los requisitos activos. El enlace "Mostrar eliminados (N)" SHALL listar los eliminados con su fecha de eliminación y las acciones "Editar" y "Restaurar". Sólo el Administrador SHALL poder editar, eliminar o restaurar; cualquier otro rol recibe HTTP 403.

#### Scenario: Acciones de un requisito del sistema
- **WHEN** el Administrador abre la pantalla
- **THEN** la fila de "Cédula fiscal" muestra "Editar" y "Eliminar"; "Editar" abre el formulario con su nombre y su descripción

#### Scenario: Confirmación antes de eliminar
- **WHEN** el Administrador pulsa "Eliminar" en "Cédula fiscal" y cancela la confirmación
- **THEN** no se envía ninguna petición y el requisito no cambia

#### Scenario: Eliminados ocultos por omisión
- **WHEN** "Poderes" está eliminado y el Administrador abre la pantalla
- **THEN** el requisito no aparece; tras pulsar "Mostrar eliminados (1)" aparece con "Restaurar"

#### Scenario: Eliminación sin CSRF o con otro rol
- **WHEN** se envía la eliminación o la restauración sin token CSRF, o la envía un usuario PMO o Proveedor
- **THEN** la respuesta es HTTP 403 y el requisito no cambia
