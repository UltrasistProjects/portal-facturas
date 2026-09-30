## MODIFIED Requirements

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
