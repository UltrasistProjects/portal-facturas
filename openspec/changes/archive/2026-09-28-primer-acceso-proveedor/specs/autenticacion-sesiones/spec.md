## ADDED Requirements

### Requirement: Cambio obligatorio de la contraseña asignada
Cada usuario SHALL tener una marca de contraseña asignada (`must_change_password`). El sistema SHALL activarla cuando la contraseña la fija otra persona:
- al crear el usuario `PROVIDER` en la autorización de proveedores;
- al reenviar las credenciales de un proveedor;
- al dar de alta un usuario en `/admin/users`.

Los usuarios que crea el seed MUST NOT tener la marca activa.

Mientras la marca esté activa:
- un inicio de sesión exitoso SHALL redirigir (HTTP 303) a `/account/password`, no al tablero;
- toda petición autenticada SHALL responder HTTP 303 hacia `/account/password` sin ejecutar la acción pedida, excepto `GET /account/password`, `POST /account/password` y `POST /logout`.

#### Scenario: Primer acceso del proveedor
- **WHEN** un proveedor recién autorizado inicia sesión con la contraseña temporal del correo de credenciales
- **THEN** la respuesta redirige a `/account/password`

#### Scenario: Navegación bloqueada
- **WHEN** un usuario con la marca activa solicita `GET /invoices` o envía `POST /invoices/new` con datos válidos
- **THEN** la respuesta es HTTP 303 hacia `/account/password` y no se crea ninguna factura

#### Scenario: Cierre de sesión disponible
- **WHEN** un usuario con la marca activa envía `POST /logout`
- **THEN** la sesión se revoca y la respuesta redirige a `/login`

#### Scenario: Usuario creado por el Administrador
- **WHEN** el Administrador da de alta un usuario en `/admin/users` y ese usuario inicia sesión
- **THEN** la respuesta redirige a `/account/password`

#### Scenario: Usuario demo
- **WHEN** el usuario demo `admin@poc.local` inicia sesión
- **THEN** la respuesta redirige a `/` y puede navegar el portal

### Requirement: Cambio de contraseña
Todo usuario autenticado SHALL poder abrir `GET /account/password`, tenga o no la marca activa. El formulario pide la contraseña actual, la nueva contraseña y su confirmación. `POST /account/password` MUST exigir un token CSRF válido.

Al guardar, el sistema SHALL:
1. Aplicar la limitación de intentos al correo del usuario y a la IP, igual que en el inicio de sesión. Mientras exista un bloqueo, SHALL responder HTTP 429 sin verificar la contraseña actual.
2. Verificar la contraseña actual. Si no es correcta, SHALL responder HTTP 400 con "La contraseña actual no es correcta." y registrar un intento fallido para el correo del usuario.
3. Validar la nueva contraseña y reportar todos los errores juntos con HTTP 400:
   - la política de contraseñas;
   - "La confirmación no coincide con la nueva contraseña.";
   - "La nueva contraseña debe ser distinta de la actual.".

Si todo es válido, el sistema SHALL, en una sola transacción:
- guardar el hash Argon2 de la nueva contraseña y apagar la marca;
- revocar todas las sesiones del usuario, emitir un identificador de sesión nuevo y un token CSRF nuevo;
- redirigir con HTTP 303 al tablero, que muestra "Contraseña actualizada".

El menú lateral SHALL ofrecer la opción "Cambiar contraseña" a todos los roles. Con la marca activa, la página SHALL mostrarse sin el menú, con la opción de cerrar sesión y el texto de la política de contraseñas.

#### Scenario: Cambio exitoso en el primer acceso
- **WHEN** un proveedor con la marca activa cambia su contraseña temporal por `Portal#2026x`
- **THEN** la respuesta redirige a `/` con el aviso "Contraseña actualizada", la marca queda apagada, la contraseña temporal deja de funcionar y `Portal#2026x` inicia sesión en `/`

#### Scenario: Nueva contraseña sin carácter especial
- **WHEN** la nueva contraseña es `Password123`
- **THEN** la respuesta es HTTP 400, indica que falta un carácter especial y la contraseña no cambia

#### Scenario: Varios errores
- **WHEN** la nueva contraseña es `abc` y la confirmación es `abd`
- **THEN** la respuesta es HTTP 400 con el error de longitud mínima y "La confirmación no coincide con la nueva contraseña."

#### Scenario: Nueva contraseña igual a la actual
- **WHEN** la nueva contraseña y su confirmación son iguales a la contraseña actual
- **THEN** la respuesta es HTTP 400 con "La nueva contraseña debe ser distinta de la actual." y la marca sigue activa

#### Scenario: Contraseña actual incorrecta
- **WHEN** la contraseña actual enviada no es la del usuario
- **THEN** la respuesta es HTTP 400 con "La contraseña actual no es correcta.", se registra un intento fallido para su correo y la contraseña no cambia

#### Scenario: Intentos agotados
- **WHEN** el correo del usuario acumula 5 intentos fallidos consecutivos y se envía el formulario con la contraseña actual correcta
- **THEN** la respuesta es HTTP 429 y la contraseña no cambia

#### Scenario: Otras sesiones revocadas
- **WHEN** un usuario tiene dos sesiones abiertas y cambia su contraseña en una de ellas
- **THEN** la otra sesión redirige a `/login` en su siguiente petición, y la sesión donde cambió la contraseña sigue activa con un identificador nuevo

#### Scenario: Cambio voluntario
- **WHEN** un usuario sin la marca abre "Cambiar contraseña" desde el menú y guarda una contraseña válida
- **THEN** la contraseña cambia y la respuesta redirige al tablero con "Contraseña actualizada"

#### Scenario: Envío sin token CSRF
- **WHEN** se envía `POST /account/password` sin token CSRF o con uno inválido
- **THEN** la respuesta es HTTP 403 y la contraseña no cambia

### Requirement: Auditoría del cambio de contraseña
Cada cambio de contraseña exitoso SHALL registrar `PASSWORD_CHANGED` en `audit_logs`, con la entidad `User`, el `user_id` del usuario y `new_value = {"forced": true}` si la marca estaba activa, o `{"forced": false}` si no. El registro MUST NOT contener la contraseña ni su hash. Un cambio rechazado MUST NOT generar un registro `PASSWORD_CHANGED`.

#### Scenario: Primer cambio auditado
- **WHEN** un proveedor con la marca activa cambia su contraseña
- **THEN** `audit_logs` contiene `PASSWORD_CHANGED` con su `user_id` y `new_value = {"forced": true}`, y ningún registro contiene la contraseña nueva ni la anterior

#### Scenario: Cambio rechazado sin auditoría
- **WHEN** un cambio de contraseña se rechaza con HTTP 400, 403 o 429
- **THEN** no se agrega ningún registro `PASSWORD_CHANGED`

## MODIFIED Requirements

### Requirement: Política de contraseñas en el servidor
Toda contraseña asignada por el sistema (alta de usuario y seed) y toda contraseña nueva elegida por el usuario en "Cambiar contraseña" SHALL validarse en el servidor conforme a la ERS RF-06. Debe tener entre 8 y 128 caracteres, al menos una letra, al menos un dígito y al menos un carácter especial (no alfanumérico), y no puede figurar en la lista de contraseñas comunes incluida en el proyecto. Una contraseña inválida MUST impedir el alta o el cambio y mostrar el motivo.

#### Scenario: Contraseña demasiado corta
- **WHEN** un ADMIN da de alta un usuario con contraseña `Ab1!` mediante una petición directa sin pasar por el formulario
- **THEN** la respuesta es HTTP 400 con el motivo y no se crea el usuario

#### Scenario: Falta carácter especial
- **WHEN** la contraseña es `Password123`
- **THEN** el alta se rechaza indicando que falta un carácter especial

#### Scenario: Contraseña común
- **WHEN** la contraseña es `Password1!` y figura en la lista de contraseñas comunes
- **THEN** el alta se rechaza indicando que la contraseña es demasiado común

#### Scenario: Contraseña excesivamente larga
- **WHEN** la contraseña tiene 129 caracteres
- **THEN** el alta se rechaza sin calcular el hash

#### Scenario: Contraseña válida
- **WHEN** la contraseña es `Portal#2026x`
- **THEN** el usuario se crea con el hash Argon2 de esa contraseña

#### Scenario: Contraseña común en el cambio
- **WHEN** un usuario elige `Password1!` como nueva contraseña en "Cambiar contraseña"
- **THEN** el cambio se rechaza indicando que la contraseña es demasiado común
