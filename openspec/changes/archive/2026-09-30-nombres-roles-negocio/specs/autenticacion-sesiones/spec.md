## MODIFIED Requirements

### Requirement: Política de contraseñas en el servidor
Toda contraseña asignada por el sistema (alta de usuario y seed) y toda contraseña nueva elegida por el usuario en "Cambiar contraseña" SHALL validarse en el servidor conforme a la ERS RF-06. Debe tener entre 8 y 128 caracteres, al menos una letra, al menos un dígito y al menos un carácter especial (no alfanumérico), y no puede figurar en la lista de contraseñas comunes incluida en el proyecto. Una contraseña inválida MUST impedir el alta o el cambio y mostrar el motivo.

#### Scenario: Contraseña demasiado corta
- **WHEN** un Administrador da de alta un usuario con contraseña `Ab1!` mediante una petición directa sin pasar por el formulario
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

### Requirement: Validación de correo en altas
Las altas de usuario y de proveedor SHALL validar en el servidor que el correo tenga formato válido (`EmailStr`) antes de persistir.

#### Scenario: Correo inválido en alta de usuario
- **WHEN** un Administrador da de alta un usuario con correo `no-es-correo`
- **THEN** la respuesta es HTTP 400 con el motivo y no se crea el usuario

#### Scenario: Correo inválido en alta de proveedor
- **WHEN** un Administrador da de alta un proveedor con correo `proveedor@`
- **THEN** la respuesta es HTTP 400 y no se crea el proveedor

### Requirement: Sesiones revocables del lado del servidor
Cada inicio de sesión SHALL crear un registro de sesión en el servidor identificado por un identificador aleatorio opaco. La cookie SHALL contener únicamente ese identificador y el token CSRF, y la base de datos SHALL guardar sólo el hash SHA-256 del identificador. Una sesión SHALL expirar tras 60 minutos sin actividad o 8 horas desde su creación, lo que ocurra primero. El cierre de sesión y la desactivación del usuario SHALL revocar la sesión en el servidor.

#### Scenario: Cookie reutilizada tras logout
- **WHEN** un usuario cierra sesión y alguien reenvía la cookie capturada antes del logout
- **THEN** la petición se trata como no autenticada y redirige a `/login`

#### Scenario: Expiración por inactividad
- **WHEN** transcurren más de 60 minutos sin peticiones autenticadas en una sesión
- **THEN** la siguiente petición redirige a `/login`

#### Scenario: Expiración absoluta
- **WHEN** una sesión con actividad continua supera 8 horas desde el login
- **THEN** la siguiente petición redirige a `/login`

#### Scenario: Desactivación de usuario
- **WHEN** un Administrador deshabilita a un usuario con sesiones abiertas
- **THEN** todas las sesiones de ese usuario quedan revocadas

#### Scenario: Fijación de sesión
- **WHEN** un usuario inicia sesión con una cookie de sesión preexistente
- **THEN** se emite un identificador de sesión nuevo y el anterior no autentica

### Requirement: Cambio obligatorio de la contraseña asignada
Cada usuario SHALL tener una marca de contraseña asignada (`must_change_password`). El sistema SHALL activarla cuando la contraseña la fija otra persona:
- al crear el usuario `Proveedor` en la autorización de proveedores;
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
