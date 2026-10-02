## MODIFIED Requirements

### Requirement: Usuario y contraseña temporal al autorizar
Por cada proveedor que pasa a "Autorizado" y no tiene un usuario `Proveedor` propio con su correo, el sistema SHALL crear, en la misma transacción, un usuario activo con:
- rol `Proveedor` y el `supplier_id` del proveedor;
- el correo del proveedor en minúsculas como usuario;
- la razón social como nombre, recortada a 150 caracteres;
- una contraseña temporal aleatoria de 20 caracteres que cumple la política de contraseñas;
- la marca de contraseña asignada activa, para que el proveedor la cambie en su primer acceso.

El sistema SHALL guardar sólo el hash de la contraseña. SHALL entregar la contraseña en claro únicamente al punto de integración con el proveedor de identidad (Keycloak), antes de confirmar la transacción, y al correo de credenciales. La contraseña MUST NOT escribirse en la base de datos en claro, en la auditoría, en el log ni en la bitácora de envíos.

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

#### Scenario: Entrega al proveedor de identidad
- **WHEN** se autoriza un proveedor
- **THEN** el punto de integración con el proveedor de identidad recibe el identificador del proveedor, el usuario y la contraseña temporal antes de confirmar la transacción
