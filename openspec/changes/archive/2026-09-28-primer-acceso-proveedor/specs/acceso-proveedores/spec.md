## MODIFIED Requirements

### Requirement: Usuario y contraseña temporal al autorizar
Por cada proveedor que pasa a "Autorizado" y no tiene un usuario `PROVIDER` propio con su correo, el sistema SHALL crear, en la misma transacción, un usuario activo con:
- rol `PROVIDER` y el `supplier_id` del proveedor;
- el correo del proveedor en minúsculas como usuario;
- la razón social como nombre, recortada a 150 caracteres;
- una contraseña temporal aleatoria de 20 caracteres que cumple la política de contraseñas;
- la marca de contraseña asignada activa, para que el proveedor la cambie en su primer acceso.

El sistema SHALL guardar sólo el hash de la contraseña. SHALL entregar la contraseña en claro únicamente al punto de integración del gestor de secretos, antes de confirmar la transacción, y al correo de credenciales. La contraseña MUST NOT escribirse en la base de datos en claro, en la auditoría, en el log ni en la bitácora de envíos.

Un proveedor que ya tiene su propio usuario `PROVIDER` con su correo SHALL autorizarse sin crear otro usuario ni generar credenciales.

#### Scenario: Usuario creado al autorizar
- **WHEN** el Administrador autoriza un proveedor "Registrado" con el correo "Contacto@Proveedor.mx"
- **THEN** existe un usuario `PROVIDER` activo con el correo "contacto@proveedor.mx", el `supplier_id` del proveedor y la marca de contraseña asignada activa, cuyo hash verifica la contraseña del correo de credenciales

#### Scenario: Inicio de sesión con la contraseña temporal
- **WHEN** el proveedor inicia sesión con el usuario y la contraseña del correo de credenciales
- **THEN** el inicio de sesión es exitoso y redirige a `/account/password`

#### Scenario: Contraseña temporal fuera de registros
- **WHEN** se autoriza un proveedor y se busca su contraseña temporal en `users`, `audit_logs`, `email_deliveries` y el log de la aplicación
- **THEN** no aparece en ninguno

#### Scenario: Proveedor con usuario propio
- **WHEN** se autoriza un proveedor "Registrado" que ya tiene un usuario `PROVIDER` con su correo
- **THEN** el proveedor queda "Autorizado", no se crea otro usuario, su contraseña y su marca no cambian y no se envía correo de credenciales

#### Scenario: Resguardo en el gestor de secretos
- **WHEN** se autoriza un proveedor
- **THEN** el punto de integración del gestor de secretos recibe el identificador del proveedor, el usuario y la contraseña temporal antes de confirmar la transacción

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
- tiene su usuario `PROVIDER` con su correo;
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
