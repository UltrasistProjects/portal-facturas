# acceso-proveedores Specification

## Purpose
Autorización de proveedores y credenciales de acceso al portal (HU-02 y HU-03, RF-02, RF-03, RN-HU03-01): estatus "Autorizado", alta individual en "Registrado" por origen (Nacional o Internacional), autorización masiva exclusiva del Administrador, selección en el listado, reglas de la autorización, usuario y contraseña temporal, correo de credenciales, resumen, acceso en el expediente, reenvío de credenciales y auditoría.
## Requirements
### Requirement: Estatus "Autorizado"
El estatus operativo `ACTIVE` de un proveedor SHALL mostrarse como "Autorizado" en el listado y en el expediente. La interfaz SHALL ofrecer como única transición de estatus el paso de "Registrado" (`REGISTERED`) a "Autorizado", mediante la autorización: masiva desde el listado o individual desde el expediente. Un proveedor SHALL pasar a "Autorizado" sólo con sus requisitos de alta exigibles completos (capacidad `requisitos-alta-proveedor`). Un proveedor autorizado cumple la regla SUP-001.

#### Scenario: Etiqueta del estatus
- **WHEN** el Administrador abre el listado de proveedores de la demo
- **THEN** los proveedores con estatus `ACTIVE` se muestran como "Autorizado"

### Requirement: Alta individual en "Registrado"
`POST /suppliers` SHALL crear el proveedor con estatus `REGISTERED`, sin usuario del portal y sin enviar correos.

El campo **Origen** (`origin`: `NATIONAL`, el valor por omisión, o `INTERNATIONAL`) SHALL decidir la identidad fiscal, con las reglas de la carga masiva:
- **Nacional:** RFC obligatorio, guardado en mayúsculas; sin identificador fiscal extranjero; país vacío o `MX`, que se guarda como `MX`.
- **Internacional:** identificador fiscal extranjero obligatorio, de hasta 40 caracteres (letras, dígitos, espacios, puntos, guiones o diagonales). Se guarda en mayúsculas y con los espacios internos colapsados. País obligatorio, con código ISO de dos letras distinto de `MX`. Sin RFC.

Una combinación incongruente o un valor inválido SHALL responder HTTP 400 con el motivo de cada campo, y nada se crea. Cada origen se compara sólo por su identidad:
- un RFC ya registrado SHALL responder HTTP 409 "Ya existe un proveedor con ese RFC.";
- un par (país, identificador fiscal extranjero) ya registrado SHALL responder HTTP 409 "Ya existe un proveedor con ese identificador fiscal extranjero en ese pais."; el mismo identificador en otro país es otro proveedor;
- si el correo, sin distinguir mayúsculas, ya lo usa otro proveedor o un usuario, la respuesta SHALL ser HTTP 409 "El correo ya lo usa otro proveedor o usuario.".

Un alta rechazada SHALL volver a mostrar el formulario con lo capturado, incluidos el origen y el país. El selector de país MUST NOT ofrecer México, que corresponde al origen Nacional. El origen y el tipo de persona no se editan después del alta.

**Campos según el origen y el tipo de persona.** Con JavaScript (`supplier_form.js`), el formulario de alta SHALL mostrar sólo los campos que aplican:
- el RFC, con el origen Nacional;
- el identificador fiscal extranjero y el país, con el Internacional;
- la fecha de constitución, sólo con persona moral.

Un campo que deja de aplicar SHALL ocultarse, limpiarse y deshabilitarse, de modo que el navegador no lo valida ni lo envía. Al volver a aplicar, SHALL recuperar su obligatoriedad. Sin JavaScript se muestran todos los campos y el servidor valida la combinación. La página de edición MUST NOT ofrecer el origen ni el tipo de persona: el servidor muestra sólo los campos que aplican, y la fecha de constitución de la persona moral es obligatoria sin depender del script.

#### Scenario: Proveedor nuevo registrado
- **WHEN** el Administrador da de alta un proveedor con el formulario
- **THEN** el proveedor queda "Registrado", no existe ningún usuario con su `supplier_id` y no se registra ningún envío de correo

#### Scenario: Correo en uso
- **WHEN** el Administrador da de alta un proveedor con el correo "Proveedor1@poc.local", que ya usa un usuario
- **THEN** la respuesta es HTTP 409 con el mensaje del correo en uso y no se crea el proveedor

#### Scenario: Alta nacional por omisión
- **WHEN** el alta llega sin origen y con un RFC válido
- **THEN** el proveedor es Nacional, con país `MX` y sin identificador fiscal extranjero

#### Scenario: Alta de proveedor internacional
- **WHEN** el Administrador da de alta un proveedor Internacional con el identificador " pco-00  01 " y el país "us"
- **THEN** el proveedor queda "Registrado" sin RFC, con el identificador "PCO-00 01" y el país "US"

#### Scenario: Identificador fiscal extranjero repetido
- **WHEN** ya existe un proveedor de "US" con el identificador "PCO-0001" y se da de alta otro con el mismo par
- **THEN** la respuesta es HTTP 409 "Ya existe un proveedor con ese identificador fiscal extranjero en ese pais."; con el país "CA", el alta procede

#### Scenario: Identidad fiscal incongruente
- **WHEN** el alta Internacional trae el país "MX", o el alta Nacional trae un identificador fiscal extranjero
- **THEN** la respuesta es HTTP 400 con "Pais: un proveedor internacional no puede tener pais MX" o "Identificador fiscal extranjero: debe quedar vacio para proveedores nacionales", y no se crea el proveedor

#### Scenario: Alta rechazada conserva lo capturado
- **WHEN** un alta Internacional con el país "CA" se rechaza por falta del identificador
- **THEN** el formulario vuelve con el origen Internacional y el país "CA" seleccionados, y el selector de país no ofrece México

#### Scenario: Campos que no aplican
- **WHEN** con JavaScript el Administrador elige el origen Internacional y el tipo persona física
- **THEN** el RFC y la fecha de constitución se ocultan, se limpian y no se envían, y el identificador fiscal y el país se vuelven obligatorios

#### Scenario: Edición sin selectores de identidad
- **WHEN** el Administrador abre el expediente de una persona moral para editarla
- **THEN** el formulario no tiene los campos de origen ni de tipo de persona, y la fecha de constitución es obligatoria

### Requirement: Autorización masiva exclusiva del Administrador
`POST /suppliers/authorize` y `POST /suppliers/{supplier_id}/credentials` SHALL estar disponibles únicamente para el rol `Administrador` y MUST exigir un token CSRF válido. Las casillas de selección, el botón "Autorizar seleccionados" y la sección de acceso al portal del expediente SHALL mostrarse sólo al rol `Administrador`.

#### Scenario: PMO sin acceso
- **WHEN** un usuario `PMO` envía `POST /suppliers/authorize` o `POST /suppliers/{id}/credentials`
- **THEN** la respuesta es HTTP 403, ningún proveedor cambia de estatus, no se crea ningún usuario y no se envía ningún correo

#### Scenario: Proveedor sin acceso
- **WHEN** un usuario `Proveedor` envía `POST /suppliers/authorize`
- **THEN** la respuesta es HTTP 403 y nada cambia

#### Scenario: Autorización sin token CSRF
- **WHEN** un Administrador envía `POST /suppliers/authorize` sin token CSRF o con uno inválido
- **THEN** la respuesta es HTTP 403 y nada cambia

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

### Requirement: Usuario y contraseña temporal al autorizar
Por cada proveedor que pasa a "Autorizado" y no tiene un usuario `Proveedor` propio con su correo, el sistema SHALL crear, en la misma transacción, un usuario local activo con:
- rol `Proveedor` y el `supplier_id` del proveedor;
- el correo del proveedor en minúsculas como usuario;
- la razón social como nombre, recortada a 150 caracteres;
- sin contraseña ni hash.

Antes de confirmar, SHALL aprovisionar al usuario en Keycloak:
- crear el usuario con usuario y correo iguales al correo del proveedor en minúsculas, habilitado; o enlazar el existente según las reglas de enlace;
- asignarle el realm role `Proveedor`;
- registrar una contraseña temporal aleatoria de 20 caracteres que cumple la política, con `temporary=true`;
- agregar la acción requerida `UPDATE_PASSWORD`;
- guardar el `sub` resultante en `users.keycloak_sub`.

**Reglas de enlace:** si Keycloak ya tiene un usuario con ese correo, el sistema SHALL enlazarlo en lugar de crear otro, siempre que ningún usuario local tenga su `sub` y que sus roles reconocidos sean ninguno o sólo `Proveedor`. En otro caso, el proveedor se trata como correo en uso.

La contraseña temporal SHALL existir en claro sólo en memoria, en la llamada a Keycloak y en el correo de credenciales. MUST NOT escribirse en la base de datos, en la auditoría, en el log ni en la bitácora de envíos.

Un proveedor que ya tiene su propio usuario `Proveedor` enlazado SHALL autorizarse sin crear otro usuario ni generar credenciales.

#### Scenario: Usuario creado al autorizar
- **WHEN** el Administrador autoriza un proveedor "Registrado" con el correo "Contacto@Proveedor.mx"
- **THEN** existe un usuario local `Proveedor` activo con el correo "contacto@proveedor.mx", el `supplier_id` del proveedor, `keycloak_sub` y sin `password_hash`, y en Keycloak un usuario habilitado con el rol `Proveedor`, la contraseña del correo de credenciales como temporal y la acción `UPDATE_PASSWORD`

#### Scenario: Proveedor ya existente en Keycloak
- **WHEN** el correo del proveedor ya existe en Keycloak como usuario sin roles del portal y sin enlazar
- **THEN** el sistema enlaza ese usuario en lugar de duplicarlo, le asigna el rol `Proveedor`, una contraseña temporal nueva y `UPDATE_PASSWORD`

#### Scenario: Correo de un usuario interno en Keycloak
- **WHEN** el correo del proveedor pertenece en Keycloak a un usuario con el rol `PMO`
- **THEN** el proveedor sigue "Registrado", no se crea usuario local y el resumen lo muestra como no autorizado por correo en uso

#### Scenario: Contraseña temporal fuera de registros
- **WHEN** se autoriza un proveedor y se busca su contraseña temporal en `users`, `audit_logs`, `email_deliveries` y el log de la aplicación
- **THEN** no aparece en ninguno

#### Scenario: Proveedor con usuario propio
- **WHEN** se autoriza un proveedor "Registrado" que ya tiene un usuario `Proveedor` enlazado con su correo
- **THEN** el proveedor queda "Autorizado", no se crea otro usuario, su contraseña en Keycloak no cambia y no se envía correo de credenciales

### Requirement: Correo de credenciales
Después de confirmar la autorización, el sistema SHALL enviar a cada proveedor con credenciales nuevas el correo del evento `SUPPLIER_CREDENTIALS`, compuesto con su plantilla vigente, con:
- `proveedor`: la razón social;
- `usuario`: el correo del usuario;
- `contrasena_temporal`: la contraseña temporal;
- `url_portal`: la dirección de inicio de sesión del portal.

El correo SHALL dirigirse al correo del proveedor, sin copias, y registrarse en la bitácora con la entidad `Supplier` y el identificador del proveedor. Un envío fallido MUST NOT revertir la autorización ni el usuario creado.

#### Scenario: Credenciales enviadas
- **WHEN** con `MAIL_BACKEND=file` el Administrador autoriza un proveedor con el correo "contacto@proveedor.mx"
- **THEN** el buzón de salida contiene un correo para "contacto@proveedor.mx", sin `Cc`, con el asunto "Acceso al Portal de Proveedores ULTRASIST" y un cuerpo con el usuario, la contraseña temporal y la dirección `/login` del portal

#### Scenario: Servidor de correo caído
- **WHEN** el servidor SMTP rechaza la conexión y el Administrador autoriza un proveedor
- **THEN** el proveedor queda "Autorizado" con su usuario, y la bitácora registra el envío de credenciales como `FAILED`

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

### Requirement: Acceso al portal en el expediente
El expediente del proveedor SHALL mostrar al Administrador:
- el usuario del portal, o "Sin usuario del portal";
- el último acceso, o "Nunca";
- si tiene usuario, el estado de su contraseña leído de Keycloak:
  - "Temporal, pendiente de cambio" si su cuenta tiene la acción requerida `UPDATE_PASSWORD`;
  - "Cambiada por el proveedor" si no;
  - "No disponible" si Keycloak no responde, sin que la página falle;
- el resultado del último envío de credenciales con su fecha, o "Sin envío registrado".

El listado SHALL marcar con "Credenciales no enviadas" a los proveedores autorizados cuyo último envío de credenciales falló.

#### Scenario: Expediente de un proveedor recién autorizado
- **WHEN** el Administrador abre el expediente de un proveedor autorizado cuyo correo de credenciales se envió
- **THEN** ve el usuario, "Nunca" como último acceso, "Temporal, pendiente de cambio" como estado de la contraseña y "Credenciales enviadas" con la fecha del envío

#### Scenario: Expediente después del primer cambio
- **WHEN** el proveedor cambió su contraseña temporal en Keycloak y el Administrador abre su expediente
- **THEN** ve la fecha de su último acceso y "Cambiada por el proveedor" como estado de la contraseña

#### Scenario: Keycloak no disponible
- **WHEN** Keycloak no responde y el Administrador abre el expediente
- **THEN** la página se muestra con "No disponible" como estado de la contraseña

### Requirement: Reenvío de credenciales
El Administrador SHALL poder reenviar las credenciales con `POST /suppliers/{supplier_id}/credentials` cuando se cumplan todas estas condiciones:
- el proveedor está "Autorizado";
- tiene su usuario `Proveedor` enlazado con su correo;
- el usuario está activo;
- su cuenta de Keycloak conserva la acción requerida `UPDATE_PASSWORD`.

Si alguna no se cumple, la respuesta SHALL ser HTTP 409 con el motivo y nada cambia. Si Keycloak no responde, la respuesta SHALL ser HTTP 503 y nada cambia.

El reenvío SHALL:
1. registrar en Keycloak una contraseña temporal nueva, que invalida la anterior, y mantener `UPDATE_PASSWORD`;
2. enviar el correo de credenciales;
3. redirigir al expediente con el resultado del envío.

El botón "Reenviar credenciales" SHALL mostrarse sólo cuando el reenvío es posible.

#### Scenario: Reenvío tras un envío fallido
- **WHEN** el correo de credenciales de un proveedor falló y el Administrador pulsa "Reenviar credenciales" con el transporte funcionando
- **THEN** el proveedor recibe un correo con una contraseña nueva, Keycloak deja de aceptar la anterior y el expediente muestra "Credenciales enviadas"

#### Scenario: Proveedor que ya cambió su contraseña
- **WHEN** el Administrador pide reenviar las credenciales de un proveedor cuya cuenta de Keycloak ya no tiene `UPDATE_PASSWORD`
- **THEN** la respuesta es HTTP 409 con "El proveedor ya cambió su contraseña temporal; no se generan credenciales nuevas." y su contraseña no cambia

#### Scenario: Keycloak no disponible en el reenvío
- **WHEN** Keycloak no responde y el Administrador pide reenviar credenciales
- **THEN** la respuesta es HTTP 503 con "El servicio de identidad no está disponible. Intente más tarde.", no se envía correo y no se registra `SUPPLIER_CREDENTIALS_RESENT`

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

### Requirement: Custodia de credenciales en el proveedor de identidad
Las credenciales de los usuarios del portal, incluida la contraseña temporal del proveedor, SHALL gestionarse exclusivamente en Keycloak (RN-HU03-01, corregida). El sistema MUST NOT persistir contraseñas ni hashes de contraseña en su base de datos:
- los usuarios creados por la autorización, el alta de usuarios o el seed SHALL tener `password_hash` nulo;
- el script de migración SHALL vaciar `password_hash` de cada usuario que enlaza.

#### Scenario: Alta de proveedor autorizado
- **WHEN** un proveedor pasa a "Autorizado"
- **THEN** su cuenta y su credencial temporal existen en Keycloak, y su usuario local tiene `keycloak_sub` y `password_hash` nulo

#### Scenario: Consulta de la tabla de usuarios
- **WHEN** después de ejecutar el script de migración se inspecciona la tabla `users`
- **THEN** ningún usuario enlazado tiene `password_hash`, y ninguna columna contiene un valor que permita autenticarse

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
