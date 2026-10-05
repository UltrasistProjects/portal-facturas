## MODIFIED Requirements

### Requirement: Estatus "Autorizado"
El estatus operativo `ACTIVE` de un proveedor SHALL mostrarse como "Autorizado" en el listado y en el expediente. La interfaz SHALL ofrecer como única transición de estatus el paso de "Registrado" (`REGISTERED`) a "Autorizado", mediante la autorización: masiva desde el listado o individual desde el expediente. Un proveedor SHALL pasar a "Autorizado" sólo con sus requisitos de alta exigibles completos (capacidad `requisitos-alta-proveedor`). Un proveedor autorizado cumple la regla SUP-001.

#### Scenario: Etiqueta del estatus
- **WHEN** el Administrador abre el listado de proveedores de la demo
- **THEN** los proveedores con estatus `ACTIVE` se muestran como "Autorizado"

### Requirement: Selección de proveedores en el listado
`GET /suppliers` SHALL aceptar `?status=` con `REGISTERED`, `ACTIVE` o `INACTIVE` para filtrar el listado, e ignorar cualquier otro valor. El listado SHALL mostrar la columna "Requisitos de alta" con "Completos" o "Faltan N" para cada proveedor, calculada con la configuración vigente. Para el Administrador, cada proveedor "Registrado" con sus requisitos de alta exigibles completos SHALL tener una casilla de selección; un "Registrado" con requisitos pendientes MUST NOT tenerla y SHALL mostrar "Faltan N requisitos" con una liga a su expediente; los demás MUST NOT tenerla. Con JavaScript, la página SHALL ofrecer "seleccionar todos", mantener deshabilitado el botón "Autorizar seleccionados" mientras no haya selección y pedir confirmación con el texto "Se autorizarán N proveedores y se enviará a cada uno su usuario y contraseña temporal por correo." La página MUST NOT usar scripts ni estilos en línea.

#### Scenario: Filtro por estatus
- **WHEN** el Administrador abre `/suppliers?status=REGISTERED`
- **THEN** el listado muestra sólo proveedores "Registrado", y cada uno con sus requisitos de alta completos tiene su casilla

#### Scenario: Sin casilla para autorizados
- **WHEN** el Administrador abre `/suppliers`
- **THEN** los proveedores "Autorizado" no tienen casilla de selección

#### Scenario: Registrado con requisitos pendientes
- **WHEN** el Administrador abre `/suppliers` y un proveedor "Registrado" no tiene cargados 3 requisitos obligatorios
- **THEN** ese proveedor no tiene casilla, muestra "Faltan 3 requisitos" con la liga a su expediente, y su columna "Requisitos de alta" dice "Faltan 3"

### Requirement: Reglas de la autorización masiva
`POST /suppliers/authorize` SHALL recibir de 1 a 100 identificadores `supplier_ids` distintos. En estos casos nada cambia:
- sin selección: HTTP 400 "Seleccione al menos un proveedor.";
- con más de 100: HTTP 400 "Autorice hasta 100 proveedores por operación.";
- con un identificador inexistente: HTTP 404.

Con una selección válida, el sistema SHALL procesar los proveedores seleccionados en una transacción, con sus filas bloqueadas y un punto de guardado por proveedor:
- un proveedor que no está "Registrado" SHALL omitirse sin cambios;
- un proveedor al que le falta algún requisito de alta exigible, evaluado con la configuración vigente en la misma transacción, MUST NOT autorizarse: no se crea su usuario ni su cuenta en Keycloak y no se le envía correo;
- un proveedor cuyo correo usa un usuario distinto de su propio usuario `Proveedor`, en el portal o en Keycloak según las reglas de enlace, MUST NOT autorizarse;
- un proveedor cuyo aprovisionamiento en Keycloak falla MUST NOT autorizarse: se revierte sólo su punto de guardado y los demás se procesan;
- los demás SHALL pasar a "Autorizado".

Si la transacción no puede confirmarse, ningún proveedor SHALL cambiar en el portal.

#### Scenario: Autorización de proveedores registrados
- **WHEN** el Administrador autoriza 3 proveedores "Registrado" con sus requisitos de alta completos
- **THEN** los 3 quedan "Autorizado" y cumplen la regla SUP-001

#### Scenario: Proveedor ya autorizado en la selección
- **WHEN** la selección incluye un proveedor "Registrado" con sus requisitos completos y uno "Autorizado"
- **THEN** el registrado queda "Autorizado", el otro se omite sin cambios y no recibe credenciales

#### Scenario: Proveedor con requisitos incompletos
- **WHEN** el Administrador autoriza 2 proveedores "Registrado" y a uno le falta "Poderes", obligatorio para su tipo
- **THEN** el otro queda "Autorizado"; el que no tiene poderes sigue "Registrado", sin usuario local ni cuenta en Keycloak y sin correo de credenciales

#### Scenario: Correo usado por otro usuario
- **WHEN** existe un usuario `PMO` con el correo de un proveedor "Registrado" seleccionado con sus requisitos completos
- **THEN** ese proveedor sigue "Registrado", no se crea usuario ni se envía correo, y el resumen lo muestra como no autorizado por correo en uso

#### Scenario: Fallo parcial al aprovisionar
- **WHEN** el Administrador autoriza 3 proveedores con sus requisitos completos y Keycloak rechaza la creación de uno de ellos
- **THEN** los otros 2 quedan "Autorizado" con su usuario en Keycloak, el fallido sigue "Registrado" sin usuario local, y el error queda en la auditoría

#### Scenario: Selección vacía
- **WHEN** el Administrador envía la autorización sin proveedores seleccionados
- **THEN** la respuesta es HTTP 400 con "Seleccione al menos un proveedor."

#### Scenario: Demasiados proveedores
- **WHEN** el Administrador envía 101 identificadores
- **THEN** la respuesta es HTTP 400 con "Autorice hasta 100 proveedores por operación." y ningún proveedor cambia

### Requirement: Resumen de la autorización
Tras la autorización, el sistema SHALL redirigir al listado con un resumen que muestre:
- los proveedores autorizados, cada uno con el resultado de su correo de credenciales ("Credenciales enviadas", o "Envío fallido" con el error), o "Ya tenía usuario" si no se generaron credenciales;
- los omitidos por no estar "Registrado";
- los no autorizados por requisitos de alta incompletos, cada uno con los nombres de sus requisitos exigibles pendientes al consultar el resumen y una liga a su expediente;
- los no autorizados por correo en uso;
- los no autorizados porque el servicio de identidad no pudo crear su cuenta.

El resumen SHALL reconstruirse con el registro de auditoría de la operación, la bitácora de envíos y el expediente vigente. Un parámetro que no corresponde a una autorización MUST NOT mostrar ningún resumen.

#### Scenario: Resumen con un envío fallido
- **WHEN** el Administrador autoriza 2 proveedores y el correo de uno falla
- **THEN** el resumen lista los 2 proveedores autorizados, uno con "Credenciales enviadas" y el otro con "Envío fallido" y el error técnico

#### Scenario: Resumen con un aprovisionamiento fallido
- **WHEN** el Administrador autoriza 2 proveedores y Keycloak rechaza uno
- **THEN** el resumen lista uno como autorizado y el otro como no autorizado porque el servicio de identidad no pudo crear su cuenta

#### Scenario: Resumen con requisitos incompletos
- **WHEN** el Administrador autoriza un proveedor "Registrado" al que le faltan "Poderes" y "Estado de cuenta bancario"
- **THEN** el resumen lo lista con "No autorizado: faltan requisitos de alta (Poderes, Estado de cuenta bancario)" y la liga a su expediente

### Requirement: Auditoría del acceso de proveedores
El sistema SHALL registrar en `audit_logs`:
- por cada proveedor autorizado: `SUPPLIER_STATUS_CHANGED`, con `old_value = {"status": "REGISTERED"}` y `new_value = {"status": "ACTIVE"}`;
- por cada usuario creado: `USER_CREATED`, con el rol, el `supplier_id`, el origen `SUPPLIER_AUTHORIZATION` y si la cuenta de Keycloak se creó o se enlazó (`idp_account`: `created` o `linked`);
- por cada proveedor cuyo aprovisionamiento falló: `SUPPLIER_PROVISIONING_FAILED`, con el código del error y sin el cuerpo de la respuesta de Keycloak;
- por cada operación: `SUPPLIER_BULK_AUTHORIZED`, con las listas de autorizados, con usuario previo, omitidos, no autorizados por requisitos de alta incompletos (`requirements_incomplete`), no autorizados por correo en uso y no autorizados por fallo de aprovisionamiento;
- por cada reenvío: `SUPPLIER_CREDENTIALS_RESENT`, con el usuario.

Estos registros MUST NOT contener la contraseña temporal, tokens ni secretos. Las operaciones rechazadas (HTTP 400, 404, 409 o 503) MUST NOT generar registros, salvo `SUPPLIER_PROVISIONING_FAILED`.

#### Scenario: Auditoría de una autorización
- **WHEN** el Administrador autoriza un proveedor "Registrado" sin usuario y con sus requisitos completos
- **THEN** `audit_logs` contiene `SUPPLIER_STATUS_CHANGED`, `USER_CREATED` con `idp_account = "created"` y `SUPPLIER_BULK_AUTHORIZED` con su `user_id`, y ninguno contiene la contraseña temporal

#### Scenario: Auditoría de un aprovisionamiento fallido
- **WHEN** Keycloak rechaza la creación del usuario de un proveedor
- **THEN** `audit_logs` contiene `SUPPLIER_PROVISIONING_FAILED` para ese proveedor, y no contiene `SUPPLIER_STATUS_CHANGED` ni `USER_CREATED` para él

#### Scenario: Auditoría de una autorización con requisitos incompletos
- **WHEN** el Administrador autoriza un proveedor "Registrado" al que le falta un requisito obligatorio
- **THEN** `audit_logs` contiene `SUPPLIER_BULK_AUTHORIZED` con ese proveedor en `requirements_incomplete`, y no contiene `SUPPLIER_STATUS_CHANGED` ni `USER_CREATED` para él

## ADDED Requirements

### Requirement: Autorización desde el expediente
El expediente de un proveedor "Registrado" SHALL mostrar al Administrador el botón "Autorizar proveedor" en la sección de acceso al portal, en lugar de remitirlo al listado:
- con los requisitos de alta exigibles completos, el botón SHALL pedir confirmación en un diálogo de la página con el texto "Se autorizará a <razón social> y se le enviará su usuario y contraseña temporal por correo." y enviar `POST /suppliers/authorize` con su identificador, con las mismas reglas, auditoría y resumen que la autorización masiva;
- con requisitos pendientes, el botón SHALL mostrarse deshabilitado con el texto "Cargue los requisitos obligatorios para autorizar".

El botón MUST NOT mostrarse a los roles `PMO` ni `Proveedor`, ni en el expediente de un proveedor que no está "Registrado".

#### Scenario: Autorización individual
- **WHEN** el Administrador completa los requisitos de una persona moral "Registrado", pulsa "Autorizar proveedor" y confirma
- **THEN** el proveedor queda "Autorizado", recibe su correo de credenciales y el resumen del listado lo muestra con "Credenciales enviadas"

#### Scenario: Botón deshabilitado
- **WHEN** el Administrador abre el expediente de un proveedor "Registrado" con 2 requisitos obligatorios pendientes
- **THEN** el botón "Autorizar proveedor" está deshabilitado con "Cargue los requisitos obligatorios para autorizar", y el panel de requisitos indica "Faltan 2 requisitos obligatorios"

#### Scenario: Petición manipulada
- **WHEN** el Administrador envía `POST /suppliers/authorize` con el identificador de un proveedor con requisitos pendientes
- **THEN** el proveedor sigue "Registrado" y el resumen lo lista como no autorizado por requisitos de alta incompletos
