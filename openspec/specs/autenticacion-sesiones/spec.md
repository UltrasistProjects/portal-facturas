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

### Requirement: Pantallas de Keycloak con el diseño del portal
Las páginas de login que Keycloak muestra a los usuarios del realm `ultrasist-portal` SHALL usar el tema de login `ultrasist`, con el diseño del login anterior del portal: panel de marca con el logo de ULTRASIST y tarjeta del formulario.

**Páginas que cubre:**
- inicio de sesión;
- solicitud de restablecimiento;
- nueva contraseña, tanto la del enlace del correo como la del primer acceso con contraseña temporal y la del cambio voluntario;
- páginas genéricas: error, información, enlace expirado o ya usado, página expirada y confirmación de cierre de sesión.

**Presentación**
- Los recursos SHALL servirse desde el tema. Ninguna de esas páginas MUST cargar recursos de un CDN ni hojas de estilo del tema por defecto (`keycloak.v2`, PatternFly).
- Los textos visibles SHALL estar en `messages/messages_es.properties` del tema, en español de México y con un solo tratamiento ("usted"). Las plantillas MUST NOT fijar texto visible.
- Las páginas MUST NOT contener atributos `data-demo` ni credenciales.
- Las páginas SHALL ser usables sin desplazamiento horizontal desde 360 px de ancho y en escritorio. En pantallas angostas, el panel de marca SHALL reducirse a un encabezado con el logo.

**Comportamiento**
- El tema sólo cambia la presentación. Keycloak SHALL seguir procesando las credenciales, las sesiones, la política de contraseñas, el correo, los tokens y las redirecciones.
- Cada formulario SHALL enviar a `url.loginAction` los mismos campos que su plantilla en Keycloak 26.7.4.
- El portal MUST NOT recibir contraseñas: el cliente `portal-facturas-web` SHALL seguir con `directAccessGrantsEnabled: false`.

**Ayuda de RF-06:** la pantalla de nueva contraseña SHALL mostrar los requisitos de RF-06 como ayuda (al menos 8 caracteres, una letra, un número y un carácter especial). Los errores que SHALL mostrar son los que devuelve Keycloak, sin validación propia en el navegador.

#### Scenario: Login válido
- **WHEN** un usuario habilitado con un rol del portal escribe su correo y su contraseña en la pantalla de inicio de sesión con el diseño del portal
- **THEN** entra al portal con el mismo rol, sesión y página de inicio que antes del tema

#### Scenario: Credenciales inválidas
- **WHEN** un usuario escribe una contraseña incorrecta
- **THEN** la pantalla con el diseño del portal muestra "Correo o contraseña incorrectos.", en español y sin indicar cuál de los dos datos falló

#### Scenario: Cuenta bloqueada temporalmente
- **WHEN** una cuenta bloqueada por fuerza bruta intenta iniciar sesión
- **THEN** ve el mismo mensaje que con credenciales inválidas, en la pantalla con el diseño del portal

#### Scenario: Usuario con contraseña temporal
- **WHEN** un usuario inicia sesión con una contraseña temporal
- **THEN** Keycloak le exige el cambio en la pantalla de nueva contraseña con el diseño del portal, que muestra los requisitos de RF-06, y al guardar una contraseña válida entra al portal

#### Scenario: Error de política visible
- **WHEN** en la pantalla de nueva contraseña el usuario escribe `Password123`
- **THEN** la misma pantalla, con el diseño del portal, muestra en español el error de Keycloak por falta de carácter especial (en la alerta de la página o junto al campo, donde Keycloak lo informe), y la contraseña no cambia

#### Scenario: Cambio voluntario con cancelación
- **WHEN** un usuario con sesión elige "Cambiar contraseña" en el menú del portal
- **THEN** ve la pantalla de nueva contraseña con el diseño del portal y un botón para cancelar, que lo devuelve al portal sin cambiar la contraseña

#### Scenario: Sin diseño por defecto de Keycloak
- **WHEN** se recorren el inicio de sesión, el restablecimiento, el primer acceso y el enlace expirado o ya usado
- **THEN** ninguna página carga hojas de estilo de `keycloak.v2` ni de PatternFly, todas las hojas de estilo vienen del tema `ultrasist` y todas muestran el logo del portal

#### Scenario: Móvil y escritorio
- **WHEN** cada página de esos flujos se muestra en una ventana de 390×844 y en una de 1440×900
- **THEN** no hay desplazamiento horizontal y los campos, botones y mensajes son visibles y usables; en 390 px el panel de marca se reduce a un encabezado con el logo

#### Scenario: Sin credenciales en las páginas del tema
- **WHEN** se solicita cualquier página del tema `ultrasist`
- **THEN** la respuesta no contiene `data-demo` ni contraseñas

### Requirement: Restablecimiento de contraseña por correo
El realm SHALL permitir el restablecimiento de contraseña (`resetPasswordAllowed: true`). La pantalla de inicio de sesión SHALL mostrar el enlace "¿Olvidó su contraseña?".

**Flujo** (lo ejecuta Keycloak con su flujo integrado `reset credentials`, sin modificarlo):
1. La solicitud recibe el correo.
2. Keycloak SHALL responder con el mismo mensaje de confirmación exista o no la cuenta.
3. Si la cuenta existe y está habilitada, Keycloak SHALL enviarle un correo con un enlace de un solo uso, vigente durante el tiempo que fija el realm.
4. El enlace SHALL llevar a la pantalla de nueva contraseña, que aplica la política del realm.

El portal MUST NOT participar en el flujo: ninguna de sus rutas recibe el correo ni la contraseña.

**Registro:** cada solicitud y cada intento SHALL quedar en los eventos de usuario del realm, con la fecha, el usuario o el correo escrito y, si falló, el motivo. Keycloak los conserva 30 días:
- la solicitud con el correo enviado (`SEND_RESET_PASSWORD`) o rechazada por correo no registrado, cuenta deshabilitada o enlace usado o vencido (`RESET_PASSWORD_ERROR`);
- la falla del envío (`SEND_RESET_PASSWORD_ERROR`) y el enlace alterado (`EXECUTE_ACTION_TOKEN_ERROR`);
- la contraseña nueva, guardada (`UPDATE_PASSWORD`) o rechazada por la política (`UPDATE_PASSWORD_ERROR`).

#### Scenario: Reset completo
- **WHEN** un usuario elige "¿Olvidó su contraseña?", escribe su correo, abre el enlace del correo recibido, escribe primero una contraseña que no cumple la política y después una válida, y luego inicia sesión con la nueva
- **THEN** ve el mensaje de confirmación, recibe un solo correo con el enlace, ve el error de política en la pantalla de nueva contraseña, la contraseña válida se guarda y el inicio de sesión con ella lo lleva al portal con su rol

#### Scenario: Correo no registrado
- **WHEN** se solicita el restablecimiento para un correo que no tiene cuenta
- **THEN** se muestra el mismo mensaje de confirmación que para un correo registrado y no se envía ningún correo

#### Scenario: Cuenta deshabilitada
- **WHEN** se solicita el restablecimiento para una cuenta deshabilitada
- **THEN** se muestra el mismo mensaje de confirmación y no se envía ningún correo

#### Scenario: Enlace ya usado
- **WHEN** el usuario abre por segunda vez un enlace con el que ya cambió su contraseña
- **THEN** ve una página con el diseño del portal que indica que el enlace expiró o ya se usó, y la contraseña no cambia

#### Scenario: Enlace expirado
- **WHEN** el usuario abre el enlace después de su vigencia
- **THEN** ve una página con el diseño del portal que indica que el enlace expiró o ya se usó, y puede solicitar uno nuevo

#### Scenario: Restablecimiento registrado en los eventos
- **WHEN** se recorren el restablecimiento completo, un correo no registrado, un enlace ya usado y una cuenta deshabilitada
- **THEN** los eventos del realm contienen `SEND_RESET_PASSWORD` con el correo del usuario, `UPDATE_PASSWORD_ERROR` y `UPDATE_PASSWORD` de su contraseña nueva, y `RESET_PASSWORD_ERROR` con `user_not_found` (el correo escrito), `expired_code` y `user_disabled`

#### Scenario: Contraseña anterior inválida tras el restablecimiento
- **WHEN** después de restablecer su contraseña el usuario intenta iniciar sesión con la anterior
- **THEN** ve "Correo o contraseña incorrectos." y no inicia sesión

