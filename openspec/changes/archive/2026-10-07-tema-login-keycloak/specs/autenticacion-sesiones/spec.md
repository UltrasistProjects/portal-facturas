## ADDED Requirements

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
