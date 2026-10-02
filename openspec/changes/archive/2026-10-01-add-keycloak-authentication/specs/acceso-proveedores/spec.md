## ADDED Requirements

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

## MODIFIED Requirements

### Requirement: Reglas de la autorización masiva
`POST /suppliers/authorize` SHALL recibir de 1 a 100 identificadores `supplier_ids` distintos. En estos casos nada cambia:
- sin selección: HTTP 400 "Seleccione al menos un proveedor.";
- con más de 100: HTTP 400 "Autorice hasta 100 proveedores por operación.";
- con un identificador inexistente: HTTP 404.

Con una selección válida, el sistema SHALL procesar los proveedores seleccionados en una transacción, con sus filas bloqueadas y un punto de guardado por proveedor:
- un proveedor que no está "Registrado" SHALL omitirse sin cambios;
- un proveedor cuyo correo usa un usuario distinto de su propio usuario `Proveedor`, en el portal o en Keycloak según las reglas de enlace, MUST NOT autorizarse;
- un proveedor cuyo aprovisionamiento en Keycloak falla MUST NOT autorizarse: se revierte sólo su punto de guardado y los demás se procesan;
- los demás SHALL pasar a "Autorizado".

Si la transacción no puede confirmarse, ningún proveedor SHALL cambiar en el portal.

#### Scenario: Autorización de proveedores registrados
- **WHEN** el Administrador autoriza 3 proveedores "Registrado"
- **THEN** los 3 quedan "Autorizado" y cumplen la regla SUP-001

#### Scenario: Proveedor ya autorizado en la selección
- **WHEN** la selección incluye un proveedor "Registrado" y uno "Autorizado"
- **THEN** el registrado queda "Autorizado", el otro se omite sin cambios y no recibe credenciales

#### Scenario: Correo usado por otro usuario
- **WHEN** existe un usuario `PMO` con el correo de un proveedor "Registrado" seleccionado
- **THEN** ese proveedor sigue "Registrado", no se crea usuario ni se envía correo, y el resumen lo muestra como no autorizado por correo en uso

#### Scenario: Fallo parcial al aprovisionar
- **WHEN** el Administrador autoriza 3 proveedores y Keycloak rechaza la creación de uno de ellos
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

### Requirement: Resumen de la autorización
Tras la autorización, el sistema SHALL redirigir al listado con un resumen que muestre:
- los proveedores autorizados, cada uno con el resultado de su correo de credenciales ("Credenciales enviadas", o "Envío fallido" con el error), o "Ya tenía usuario" si no se generaron credenciales;
- los omitidos por no estar "Registrado";
- los no autorizados por correo en uso;
- los no autorizados porque el servicio de identidad no pudo crear su cuenta.

El resumen SHALL reconstruirse con el registro de auditoría de la operación y la bitácora de envíos. Un parámetro que no corresponde a una autorización MUST NOT mostrar ningún resumen.

#### Scenario: Resumen con un envío fallido
- **WHEN** el Administrador autoriza 2 proveedores y el correo de uno falla
- **THEN** el resumen lista los 2 proveedores autorizados, uno con "Credenciales enviadas" y el otro con "Envío fallido" y el error técnico

#### Scenario: Resumen con un aprovisionamiento fallido
- **WHEN** el Administrador autoriza 2 proveedores y Keycloak rechaza uno
- **THEN** el resumen lista uno como autorizado y el otro como no autorizado porque el servicio de identidad no pudo crear su cuenta

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
- por cada operación: `SUPPLIER_BULK_AUTHORIZED`, con las listas de autorizados, con usuario previo, omitidos, no autorizados por correo en uso y no autorizados por fallo de aprovisionamiento;
- por cada reenvío: `SUPPLIER_CREDENTIALS_RESENT`, con el usuario.

Estos registros MUST NOT contener la contraseña temporal, tokens ni secretos. Las operaciones rechazadas (HTTP 400, 404, 409 o 503) MUST NOT generar registros, salvo `SUPPLIER_PROVISIONING_FAILED`.

#### Scenario: Auditoría de una autorización
- **WHEN** el Administrador autoriza un proveedor "Registrado" sin usuario
- **THEN** `audit_logs` contiene `SUPPLIER_STATUS_CHANGED`, `USER_CREATED` con `idp_account = "created"` y `SUPPLIER_BULK_AUTHORIZED` con su `user_id`, y ninguno contiene la contraseña temporal

#### Scenario: Auditoría de un aprovisionamiento fallido
- **WHEN** Keycloak rechaza la creación del usuario de un proveedor
- **THEN** `audit_logs` contiene `SUPPLIER_PROVISIONING_FAILED` para ese proveedor, y no contiene `SUPPLIER_STATUS_CHANGED` ni `USER_CREATED` para él
