# autenticacion-sesiones Specification

## Purpose
Inicio y cierre de sesión con Keycloak (OIDC Authorization Code + PKCE): enlace del usuario por `sub`, roles del token, primer acceso y cambio de contraseña en Keycloak, política de contraseñas y detección de fuerza bruta del realm, sesiones revocables del lado del servidor, auditoría del acceso, validación de correo y cuentas demo sólo en el realm de desarrollo.
## Requirements
### Requirement: Credenciales demo restringidas a desarrollo
Las cuentas demo SHALL existir sólo como usuarios del realm de Keycloak de desarrollo, creados por el seed.
- En `development`, el seed SHALL asignarles la contraseña `DEMO_PASSWORD` del `.env`, sin acción requerida.
- En cualquier otro entorno, SHALL asignarles contraseñas aleatorias temporales y mostrarlas una única vez en consola.

El código de la aplicación, los scripts, el README, las plantillas y el realm versionado MUST NOT contener contraseñas demo. Ninguna página del portal SHALL contener atributos `data-demo`.

#### Scenario: Seed en desarrollo
- **WHEN** se ejecuta el seed con `APP_ENV=development` y `DEMO_PASSWORD` definida
- **THEN** cada cuenta demo existe en Keycloak con esa contraseña, sin acción requerida, y enlazada por `sub` a su usuario local

#### Scenario: Seed fuera de desarrollo
- **WHEN** se ejecuta el seed con `APP_ENV=test` o `production`
- **THEN** cada usuario sembrado recibe en Keycloak una contraseña aleatoria temporal que se imprime una sola vez y no se persiste en ningún archivo

#### Scenario: Repositorio sin contraseñas demo
- **WHEN** se buscan las contraseñas demo anteriores (`Admin#Demo2026`, `Pmo#Demo2026`, `Proveedor#Demo2026`) en `app/`, `scripts/`, `infra/` y `README.md`
- **THEN** no hay coincidencias

#### Scenario: Sin acceso rápido en las páginas
- **WHEN** se solicita cualquier página del portal en cualquier entorno
- **THEN** la respuesta no contiene `data-demo`

### Requirement: Validación de correo en altas
Las altas de usuario y de proveedor SHALL validar en el servidor que el correo tenga formato válido (`EmailStr`) antes de persistir.

#### Scenario: Correo inválido en alta de usuario
- **WHEN** un Administrador da de alta un usuario con correo `no-es-correo`
- **THEN** la respuesta es HTTP 400 con el motivo y no se crea el usuario

#### Scenario: Correo inválido en alta de proveedor
- **WHEN** un Administrador da de alta un proveedor con correo `proveedor@`
- **THEN** la respuesta es HTTP 400 y no se crea el proveedor

### Requirement: Sesiones revocables del lado del servidor
Cada inicio de sesión completado en `/auth/callback` SHALL crear un registro de sesión en el servidor, identificado por un identificador aleatorio opaco.
- La cookie SHALL contener únicamente ese identificador y el token CSRF, más `state`, `nonce` y `code_verifier` mientras dura el flujo de autorización.
- La base de datos SHALL guardar sólo el hash SHA-256 del identificador, y el ID token como `id_token_hint` para el logout.

Una sesión SHALL expirar tras 60 minutos sin actividad o 8 horas desde su creación, lo que ocurra primero.

La sesión SHALL revocarse en el servidor en estos casos:
- al cerrar sesión;
- al deshabilitar al usuario; en ese caso el sistema SHALL además deshabilitar al usuario en Keycloak y cerrar allí sus sesiones.

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
- **THEN** todas las sesiones locales de ese usuario quedan revocadas, y el usuario queda deshabilitado en Keycloak con sus sesiones cerradas

#### Scenario: Fijación de sesión
- **WHEN** un usuario completa el callback con una cookie de sesión preexistente
- **THEN** se emite un identificador de sesión nuevo y un token CSRF nuevo, y el identificador anterior no autentica

#### Scenario: Sin tokens en la cookie
- **WHEN** se decodifica la cookie de sesión después de un inicio de sesión
- **THEN** sólo contiene el identificador de sesión y el token CSRF

### Requirement: Inicio de sesión mediante Keycloak (OIDC)
El sistema SHALL autenticar a todos los usuarios con el flujo OIDC Authorization Code con PKCE (`S256`) contra Keycloak. MUST NOT aceptar credenciales en un formulario propio.

**Inicio:**
- `GET /login` SHALL redirigir al endpoint de autorización de Keycloak con `state`, `nonce`, `code_challenge` y `code_challenge_method=S256`.
- Una petición sin sesión a una ruta protegida SHALL redirigir a `/login`.

**Callback:** `GET /auth/callback` SHALL intercambiar el código y validar el ID token:
- firma con las claves JWKS del realm;
- `iss` igual al emisor del realm;
- `aud` que contiene el client id del portal;
- `exp` vigente con una tolerancia de 60 segundos;
- `nonce` y `state` iguales a los de la petición.

Sólo si todo es válido SHALL crear la sesión local. Con cualquier fallo SHALL responder HTTP 400 con la página de error genérica y MUST NOT crear sesión.

**Tokens:** los access y refresh tokens MUST NOT guardarse en la cookie ni en la base de datos.

**Keycloak no disponible:** si no se puede obtener la configuración del realm, `/login` SHALL responder HTTP 503 con "El servicio de autenticación no está disponible.", sin traceback.

#### Scenario: Usuario no autenticado accede a una ruta protegida
- **WHEN** un usuario sin sesión solicita `GET /invoices` y sigue la redirección a `/login`
- **THEN** es redirigido al endpoint de autorización de Keycloak con `state`, `nonce`, `code_challenge` y `code_challenge_method=S256`

#### Scenario: Callback válido
- **WHEN** Keycloak redirige a `/auth/callback` con un `code` y el `state` de la sesión, y el ID token está firmado por el realm con `iss`, `aud`, `exp` y `nonce` correctos
- **THEN** se crea la sesión local del usuario enlazado por `sub` y la respuesta redirige a `/`

#### Scenario: State inválido
- **WHEN** el callback llega con un `state` distinto del guardado
- **THEN** la respuesta es HTTP 400 y no se crea sesión

#### Scenario: Nonce inválido
- **WHEN** el ID token trae un `nonce` distinto del de la petición
- **THEN** la respuesta es HTTP 400 y no se crea sesión

#### Scenario: Token expirado
- **WHEN** el `exp` del ID token es 2 minutos anterior a la hora actual
- **THEN** la respuesta es HTTP 400 y no se crea sesión

#### Scenario: Audiencia incorrecta
- **WHEN** el `aud` del ID token no contiene el client id del portal
- **THEN** la respuesta es HTTP 400 y no se crea sesión

#### Scenario: Firma inválida
- **WHEN** el ID token está firmado con una clave que no pertenece al JWKS del realm
- **THEN** la respuesta es HTTP 400 y no se crea sesión

#### Scenario: Formulario local retirado
- **WHEN** se envía `POST /login` con correo y contraseña
- **THEN** la respuesta es HTTP 405 y no se crea sesión

#### Scenario: Keycloak no disponible
- **WHEN** el servidor de Keycloak no responde y un usuario solicita `GET /login`
- **THEN** la respuesta es HTTP 503 con "El servicio de autenticación no está disponible." y sin traceback

### Requirement: Usuario local enlazado por `sub`
El callback SHALL localizar al usuario local cuyo `keycloak_sub` es igual al `sub` del ID token. MUST NOT enlazar ni localizar usuarios por correo.
- Sin coincidencia, la respuesta SHALL ser HTTP 403 con "Su cuenta no está habilitada en el portal." y no se crea sesión.
- Un usuario con `is_active = false` SHALL recibir HTTP 403 en el callback.
- Sus sesiones abiertas MUST dejar de autenticar en la siguiente petición.

#### Scenario: Cuenta de Keycloak sin usuario en el portal
- **WHEN** el callback trae un `sub` que no tiene ningún usuario local
- **THEN** la respuesta es HTTP 403 con "Su cuenta no está habilitada en el portal." y no se crea sesión

#### Scenario: Mismo correo, otra cuenta de Keycloak
- **WHEN** el ID token trae el correo de un usuario del portal pero un `sub` distinto del enlazado
- **THEN** la respuesta es HTTP 403 y el usuario local no cambia

#### Scenario: Usuario desactivado localmente
- **WHEN** un usuario con sesión válida pasa a `is_active = false`
- **THEN** su siguiente petición no ejecuta la acción, y al volver a autenticarse el callback responde HTTP 403

### Requirement: Autorización por roles de Keycloak
El rol del usuario SHALL leerse de los realm roles del ID token (`realm_access.roles`). Los roles reconocidos son `Administrador`, `Proveedor` y `PMO`; los demás roles se ignoran.

El inicio de sesión SHALL exigir exactamente un rol reconocido, igual al `role` del usuario local. Si falta, sobra o no coincide, la respuesta SHALL ser HTTP 403 y no se crea sesión.

El aislamiento por proveedor SHALL seguir basándose en el `supplier_id` del usuario local, nunca en un claim del token.

#### Scenario: Usuario sin rol reconocido
- **WHEN** el ID token sólo trae los roles `offline_access` y `default-roles-ultrasist-portal`
- **THEN** la respuesta es HTTP 403 y no se crea sesión

#### Scenario: Rol distinto del local
- **WHEN** el usuario local es `Proveedor` y el ID token trae el rol `Administrador`
- **THEN** la respuesta es HTTP 403 y no se crea sesión

#### Scenario: Dos roles reconocidos
- **WHEN** el ID token trae los roles `PMO` y `Administrador`
- **THEN** la respuesta es HTTP 403 y no se crea sesión

#### Scenario: Proveedor consulta la factura de otro proveedor
- **WHEN** un usuario `Proveedor` con sesión iniciada por Keycloak solicita una factura o un documento de otro proveedor
- **THEN** la respuesta es HTTP 404, igual que antes de la migración

### Requirement: Primer acceso y cambio de contraseña en Keycloak
Toda contraseña que asigna otra persona (autorización, reenvío de credenciales, alta en `/admin/users`, migración de usuarios) SHALL registrarse en Keycloak como temporal, con la acción requerida `UPDATE_PASSWORD`. Keycloak SHALL exigir la contraseña nueva antes de devolver al usuario al portal.

El portal MUST NOT mostrar formularios de contraseña. La opción "Cambiar contraseña" del menú, disponible para todos los roles, SHALL llevar a `GET /account/password`, que redirige al endpoint de autorización con `kc_action=UPDATE_PASSWORD`. Al volver con `kc_action_status=success`, el sistema SHALL registrar `PASSWORD_CHANGED` con `new_value = {"forced": false}`, sin la contraseña.

#### Scenario: Primer acceso con contraseña temporal
- **WHEN** un proveedor inicia sesión en Keycloak con su contraseña temporal
- **THEN** Keycloak le exige definir una contraseña nueva antes de volver al portal, y la temporal deja de funcionar

#### Scenario: Cambio voluntario
- **WHEN** un usuario con sesión elige "Cambiar contraseña" en el menú
- **THEN** es redirigido a Keycloak con `kc_action=UPDATE_PASSWORD` y, al volver con `kc_action_status=success`, `audit_logs` contiene `PASSWORD_CHANGED` con `{"forced": false}`

#### Scenario: Usuario demo en desarrollo
- **WHEN** en `development` un usuario demo inicia sesión con `DEMO_PASSWORD`
- **THEN** Keycloak no le exige cambiar la contraseña y llega al tablero

### Requirement: Política de contraseñas del realm
El realm versionado SHALL declarar la política de contraseñas de RF-06:
- entre 8 y 128 caracteres;
- al menos una letra, un dígito y un carácter especial;
- distinta del usuario y del correo;
- distinta de la contraseña actual;
- fuera de la lista de contraseñas comunes del proyecto (`common_passwords.txt`), que incluye las palabras comunes seguidas de dígitos y símbolos frecuentes.

Keycloak SHALL rechazar la contraseña nueva que no la cumpla. Las contraseñas temporales que genera el portal SHALL cumplirla.

#### Scenario: Contraseña sin carácter especial
- **WHEN** en el primer acceso el proveedor elige `Password123`
- **THEN** Keycloak la rechaza y no completa el inicio de sesión

#### Scenario: Contraseña común
- **WHEN** el usuario elige `Password1!`, que figura en la lista de contraseñas comunes
- **THEN** Keycloak la rechaza

#### Scenario: Palabra común decorada
- **WHEN** en el primer acceso el proveedor elige `Portal2026!`
- **THEN** Keycloak la rechaza por figurar en la lista de contraseñas comunes

#### Scenario: Política declarada en el realm
- **WHEN** se inspecciona `infra/keycloak/realm-ultrasist-portal.json`
- **THEN** `passwordPolicy` contiene `length(8)`, `maxLength(128)`, `digits(1)`, `specialChars(1)`, una expresión que exige una letra, `notUsername`, `notEmail`, `passwordHistory(1)` y `passwordBlacklist(common_passwords.txt)`

#### Scenario: Temporal generada válida
- **WHEN** el portal genera 1000 contraseñas temporales
- **THEN** todas tienen 20 caracteres con al menos una letra, un dígito y un carácter especial

### Requirement: Protección contra fuerza bruta
El realm SHALL tener activa la detección de fuerza bruta con:
- bloqueo temporal tras 5 fallos consecutivos;
- espera creciente por múltiplos;
- tope de 60 minutos;
- ventana de 24 horas;
- sin bloqueo permanente.

#### Scenario: Intentos fallidos repetidos
- **WHEN** una cuenta acumula 5 intentos fallidos consecutivos en Keycloak
- **THEN** Keycloak bloquea temporalmente la cuenta y un sexto intento, incluso con la contraseña correcta, no inicia sesión

#### Scenario: Configuración declarada en el realm
- **WHEN** se inspecciona el realm versionado
- **THEN** contiene `bruteForceProtected: true`, `failureFactor: 5`, `bruteForceStrategy: MULTIPLE`, `maxFailureWaitSeconds: 3600`, `maxDeltaTimeSeconds: 86400` y `permanentLockout: false`

### Requirement: Cierre de sesión en Keycloak
`POST /logout` MUST exigir un token CSRF válido y SHALL:
1. revocar la sesión local y registrar `LOGOUT`;
2. redirigir (HTTP 303) al `end_session_endpoint` de Keycloak con `id_token_hint` y `post_logout_redirect_uri` igual a la raíz del portal.

Si la configuración del realm no está disponible, SHALL revocar igualmente la sesión local y redirigir a `/`.

#### Scenario: Logout
- **WHEN** el usuario cierra sesión
- **THEN** la sesión local queda revocada y el navegador es redirigido al `end_session_endpoint` de Keycloak con `id_token_hint` y `post_logout_redirect_uri`

#### Scenario: Nueva visita tras el logout
- **WHEN** después del logout el navegador solicita una ruta protegida
- **THEN** es redirigido a `/login` y de ahí a Keycloak, que pide credenciales de nuevo

#### Scenario: Logout sin token CSRF
- **WHEN** se envía `POST /logout` sin token CSRF
- **THEN** la respuesta es HTTP 403 y la sesión sigue activa

### Requirement: Auditoría del acceso
El sistema SHALL registrar en `audit_logs`:
- `LOGIN_SUCCESS` con el usuario;
- `LOGIN_DENIED` con el motivo `unknown_account`, `inactive`, `role_missing` o `role_mismatch`;
- `LOGIN_FAILED` con el motivo `state`, `nonce`, `token` o `idp_error`.

Ningún registro MUST contener tokens, códigos de autorización, `state`, `nonce` ni contraseñas.

#### Scenario: Acceso denegado por rol
- **WHEN** un callback válido se rechaza porque el rol del token no coincide con el local
- **THEN** `audit_logs` contiene `LOGIN_DENIED` con `reason = "role_mismatch"` y sin ningún token

