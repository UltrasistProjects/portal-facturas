# acceso-proveedores Specification

## Purpose
Autorización de proveedores y credenciales de acceso al portal (HU-02 y HU-03, RF-02, RF-03, RN-HU03-01): estatus "Autorizado", alta individual en "Registrado", autorización masiva exclusiva del Administrador, selección en el listado, reglas de la autorización, usuario y contraseña temporal, correo de credenciales, resumen, acceso en el expediente, reenvío de credenciales y auditoría.
## Requirements
### Requirement: Estatus "Autorizado"
El estatus operativo `ACTIVE` de un proveedor SHALL mostrarse como "Autorizado" en el listado y en el expediente. La interfaz SHALL ofrecer como única transición de estatus el paso de "Registrado" (`REGISTERED`) a "Autorizado", mediante la autorización masiva. Un proveedor autorizado cumple la regla SUP-001.

#### Scenario: Etiqueta del estatus
- **WHEN** el Administrador abre el listado de proveedores de la demo
- **THEN** los proveedores con estatus `ACTIVE` se muestran como "Autorizado"

### Requirement: Alta individual en "Registrado"
`POST /suppliers` SHALL crear el proveedor con estatus `REGISTERED`, sin usuario del portal y sin enviar correos. Si el correo, sin distinguir mayúsculas, ya lo usa otro proveedor o un usuario, la respuesta SHALL ser HTTP 409 con el mensaje "El correo ya lo usa otro proveedor o usuario." y nada se crea.

#### Scenario: Proveedor nuevo registrado
- **WHEN** el Administrador da de alta un proveedor con el formulario
- **THEN** el proveedor queda "Registrado", no existe ningún usuario con su `supplier_id` y no se registra ningún envío de correo

#### Scenario: Correo en uso
- **WHEN** el Administrador da de alta un proveedor con el correo "Proveedor1@poc.local", que ya usa un usuario
- **THEN** la respuesta es HTTP 409 con el mensaje del correo en uso y no se crea el proveedor

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
`GET /suppliers` SHALL aceptar `?status=` con `REGISTERED`, `ACTIVE` o `INACTIVE` para filtrar el listado, e ignorar cualquier otro valor. Para el Administrador, cada proveedor "Registrado" SHALL tener una casilla de selección; los demás MUST NOT tenerla. Con JavaScript, la página SHALL ofrecer "seleccionar todos", mantener deshabilitado el botón "Autorizar seleccionados" mientras no haya selección y pedir confirmación con el texto "Se autorizarán N proveedores y se enviará a cada uno su usuario y contraseña temporal por correo." La página MUST NOT usar scripts ni estilos en línea.

#### Scenario: Filtro por estatus
- **WHEN** el Administrador abre `/suppliers?status=REGISTERED`
- **THEN** el listado muestra sólo proveedores "Registrado", cada uno con su casilla

#### Scenario: Sin casilla para autorizados
- **WHEN** el Administrador abre `/suppliers`
- **THEN** los proveedores "Autorizado" no tienen casilla de selección

### Requirement: Reglas de la autorización masiva
`POST /suppliers/authorize` SHALL recibir de 1 a 100 identificadores `supplier_ids` distintos. Sin selección, la respuesta SHALL ser HTTP 400 "Seleccione al menos un proveedor."; con más de 100, HTTP 400 "Autorice hasta 100 proveedores por operación."; con un identificador inexistente, HTTP 404. En estos casos nada cambia.

Con una selección válida, el sistema SHALL procesar todos los proveedores seleccionados en una sola transacción y con sus filas bloqueadas:
- un proveedor que no está "Registrado" SHALL omitirse sin cambios;
- un proveedor cuyo correo usa un usuario distinto de su propio usuario `Proveedor` MUST NOT autorizarse;
- los demás SHALL pasar a "Autorizado".

Si la transacción no puede completarse, ningún proveedor SHALL cambiar.

#### Scenario: Autorización de proveedores registrados
- **WHEN** el Administrador autoriza 3 proveedores "Registrado"
- **THEN** los 3 quedan "Autorizado" y cumplen la regla SUP-001

#### Scenario: Proveedor ya autorizado en la selección
- **WHEN** la selección incluye un proveedor "Registrado" y uno "Autorizado"
- **THEN** el registrado queda "Autorizado", el otro se omite sin cambios y no recibe credenciales

#### Scenario: Correo usado por otro usuario
- **WHEN** existe un usuario `PMO` con el correo de un proveedor "Registrado" seleccionado
- **THEN** ese proveedor sigue "Registrado", no se crea usuario ni se envía correo, y el resumen lo muestra como no autorizado por correo en uso

#### Scenario: Selección vacía
- **WHEN** el Administrador envía la autorización sin proveedores seleccionados
- **THEN** la respuesta es HTTP 400 con "Seleccione al menos un proveedor."

#### Scenario: Demasiados proveedores
- **WHEN** el Administrador envía 101 identificadores
- **THEN** la respuesta es HTTP 400 con "Autorice hasta 100 proveedores por operación." y ningún proveedor cambia

### Requirement: Usuario y contraseña temporal al autorizar
Por cada proveedor que pasa a "Autorizado" y no tiene un usuario `Proveedor` propio con su correo, el sistema SHALL crear, en la misma transacción, un usuario activo con:
- rol `Proveedor` y el `supplier_id` del proveedor;
- el correo del proveedor en minúsculas como usuario;
- la razón social como nombre, recortada a 150 caracteres;
- una contraseña temporal aleatoria de 20 caracteres que cumple la política de contraseñas;
- la marca de contraseña asignada activa, para que el proveedor la cambie en su primer acceso.

El sistema SHALL guardar sólo el hash de la contraseña. SHALL entregar la contraseña en claro únicamente al punto de integración del gestor de secretos, antes de confirmar la transacción, y al correo de credenciales. La contraseña MUST NOT escribirse en la base de datos en claro, en la auditoría, en el log ni en la bitácora de envíos.

Un proveedor que ya tiene su propio usuario `Proveedor` con su correo SHALL autorizarse sin crear otro usuario ni generar credenciales.

#### Scenario: Usuario creado al autorizar
- **WHEN** el Administrador autoriza un proveedor "Registrado" con el correo "Contacto@Proveedor.mx"
- **THEN** existe un usuario `Proveedor` activo con el correo "contacto@proveedor.mx", el `supplier_id` del proveedor y la marca de contraseña asignada activa, cuyo hash verifica la contraseña del correo de credenciales

#### Scenario: Inicio de sesión con la contraseña temporal
- **WHEN** el proveedor inicia sesión con el usuario y la contraseña del correo de credenciales
- **THEN** el inicio de sesión es exitoso y redirige a `/account/password`

#### Scenario: Contraseña temporal fuera de registros
- **WHEN** se autoriza un proveedor y se busca su contraseña temporal en `users`, `audit_logs`, `email_deliveries` y el log de la aplicación
- **THEN** no aparece en ninguno

#### Scenario: Proveedor con usuario propio
- **WHEN** se autoriza un proveedor "Registrado" que ya tiene un usuario `Proveedor` con su correo
- **THEN** el proveedor queda "Autorizado", no se crea otro usuario, su contraseña y su marca no cambian y no se envía correo de credenciales

#### Scenario: Resguardo en el gestor de secretos
- **WHEN** se autoriza un proveedor
- **THEN** el punto de integración del gestor de secretos recibe el identificador del proveedor, el usuario y la contraseña temporal antes de confirmar la transacción

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
- los proveedores autorizados, cada uno con el resultado de su correo de credenciales ("Credenciales enviadas" o "Envío fallido" con el error), o "Ya tenía usuario" si no se generaron credenciales;
- los omitidos por no estar "Registrado";
- los no autorizados por correo en uso.

El resumen SHALL reconstruirse con el registro de auditoría de la operación y la bitácora de envíos. Un parámetro que no corresponde a una autorización MUST NOT mostrar ningún resumen.

#### Scenario: Resumen con un envío fallido
- **WHEN** el Administrador autoriza 2 proveedores y el correo de uno falla
- **THEN** el resumen lista los 2 proveedores autorizados, uno con "Credenciales enviadas" y el otro con "Envío fallido" y el error técnico

### Requirement: Acceso al portal en el expediente
El expediente del proveedor SHALL mostrar al Administrador:
- el usuario del portal, o "Sin usuario del portal";
- el último acceso, o "Nunca";
- si tiene usuario, el estado de su contraseña: "Temporal, pendiente de cambio" si la marca de contraseña asignada está activa, o "Cambiada por el proveedor" si no;
- el resultado del último envío de credenciales con su fecha, o "Sin envío registrado".

El listado SHALL marcar con "Credenciales no enviadas" a los proveedores autorizados cuyo último envío de credenciales falló.

#### Scenario: Expediente de un proveedor recién autorizado
- **WHEN** el Administrador abre el expediente de un proveedor autorizado cuyo correo de credenciales se envió
- **THEN** ve el usuario, "Nunca" como último acceso, "Temporal, pendiente de cambio" como estado de la contraseña y "Credenciales enviadas" con la fecha del envío

#### Scenario: Expediente después del primer cambio
- **WHEN** el proveedor cambió su contraseña temporal y el Administrador abre su expediente
- **THEN** ve la fecha de su último acceso y "Cambiada por el proveedor" como estado de la contraseña

### Requirement: Reenvío de credenciales
El Administrador SHALL poder reenviar las credenciales con `POST /suppliers/{supplier_id}/credentials` cuando se cumplan todas estas condiciones:
- el proveedor está "Autorizado";
- tiene su usuario `Proveedor` con su correo;
- el usuario está activo;
- el usuario conserva la contraseña temporal, es decir, su marca de contraseña asignada está activa.

Si alguna no se cumple, la respuesta SHALL ser HTTP 409 con el motivo y nada cambia. El reenvío SHALL generar una contraseña temporal nueva, que invalida la anterior, mantener activa la marca de contraseña asignada, resguardar la contraseña y enviar el correo de credenciales. Después SHALL redirigir al expediente con el resultado del envío. El botón "Reenviar credenciales" SHALL mostrarse sólo cuando el reenvío es posible.

#### Scenario: Reenvío tras un envío fallido
- **WHEN** el correo de credenciales de un proveedor falló y el Administrador pulsa "Reenviar credenciales" con el transporte funcionando
- **THEN** el proveedor recibe un correo con una contraseña nueva, la anterior deja de funcionar y el expediente muestra "Credenciales enviadas"

#### Scenario: Proveedor que entró sin cambiar la contraseña
- **WHEN** el proveedor inició sesión con la contraseña temporal pero no la cambió, y el Administrador pide reenviar sus credenciales
- **THEN** el proveedor recibe una contraseña temporal nueva, la anterior deja de funcionar y la marca sigue activa

#### Scenario: Proveedor que ya cambió su contraseña
- **WHEN** el Administrador pide reenviar las credenciales de un proveedor que ya cambió su contraseña temporal
- **THEN** la respuesta es HTTP 409 con "El proveedor ya cambió su contraseña temporal; no se generan credenciales nuevas." y su contraseña no cambia

### Requirement: Auditoría del acceso de proveedores
El sistema SHALL registrar en `audit_logs`:
- por cada proveedor autorizado: `SUPPLIER_STATUS_CHANGED`, con `old_value = {"status": "REGISTERED"}` y `new_value = {"status": "ACTIVE"}`;
- por cada usuario creado: `USER_CREATED`, con el rol, el `supplier_id` y el origen `SUPPLIER_AUTHORIZATION`;
- por cada operación: `SUPPLIER_BULK_AUTHORIZED`, con las listas de proveedores autorizados, con usuario previo, omitidos y no autorizados;
- por cada reenvío: `SUPPLIER_CREDENTIALS_RESENT`, con el usuario.

Estos registros MUST NOT contener la contraseña temporal ni su hash. Las operaciones rechazadas (HTTP 400, 404 o 409) MUST NOT generar registros.

#### Scenario: Auditoría de una autorización
- **WHEN** el Administrador autoriza un proveedor "Registrado" sin usuario
- **THEN** `audit_logs` contiene `SUPPLIER_STATUS_CHANGED`, `USER_CREATED` y `SUPPLIER_BULK_AUTHORIZED` con su `user_id`, y ninguno contiene la contraseña temporal

