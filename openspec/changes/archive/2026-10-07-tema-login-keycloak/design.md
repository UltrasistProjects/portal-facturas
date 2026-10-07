> Rutas relativas a la raíz de la PoC (`PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress-V1/PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress/`), salvo `openspec/` y `docs/`.

## Context

### Hallazgos de la investigación (2026-10-06, sin modificar nada)

**Keycloak y despliegue**
- **Versión y modo:** Keycloak **26.7.4** (`quay.io/keycloak/keycloak:26.7.4`), servicio `keycloak` de `compose.yaml`. Arranca con `start-dev --import-realm`, que desactiva la caché de temas.
- **Datos y realm:** el volumen `keycloak-data` guarda la base dev-file en `data/h2`. El realm versionado está en `infra/keycloak/realm-ultrasist-portal.json`.
- **Lo que no hay:** ningún Dockerfile, ningún directorio de temas ni proveedores, y ningún despliegue de QA o producción en el repo (D3 de `add-keycloak-authentication`: instancia dedicada).
- **Arranque local:** `run_local.*` ejecuta `docker compose up -d --wait db keycloak`.

**Realm `ultrasist-portal`.** Se revisaron el JSON y el realm vivo, consultado con GET a la API de administración; coinciden.

| Atributo | Valor | Efecto |
|---|---|---|
| `loginTheme` | ausente | Se usa el tema por defecto `keycloak.v2` (PatternFly 5). La página de login carga `/resources/…/login/keycloak.v2/css/styles.css` y `patternfly-v5`. |
| `internationalizationEnabled` / `supportedLocales` / `defaultLocale` | `true` / `["es"]` / `"es"` | El español ya es el único idioma y el idioma por defecto: no hay nada que cambiar ni selector de idioma que mostrar. |
| `resetPasswordAllowed` | **`false`** | **Falta.** "Olvidé mi contraseña" está deshabilitado: no aparece el enlace y Keycloak rechaza el flujo. |
| `smtpServer` | **ausente** (`{}` en el realm vivo) | **Falta.** Keycloak no puede enviar correos. |
| `passwordPolicy` | `length(8)`, `maxLength(128)`, `digits(1)`, `specialChars(1)`, `regexPattern(.*\p{L}.*)`, `notUsername`, `notEmail`, `passwordHistory(1)`, `passwordBlacklist(common_passwords.txt)` | **Coincide con RF-06** (8 caracteres, letra, número y carácter especial) y es más estricta. No hay conflicto que reportar. |
| `actionTokenGeneratedByUserLifespan` | 300 s (por defecto) | El enlace de restablecimiento vence a los **5 minutos**. |
| `browserFlow` / `resetCredentialsFlow` | `browser` / `reset credentials` (integrados) | No se modifican. |
| `enabledEventTypes` | login, logout, código a token y `UPDATE_PASSWORD` (con sus errores), y el bloqueo temporal | **Falta:** no incluye los eventos del restablecimiento (`SEND_RESET_PASSWORD`, `RESET_PASSWORD` y sus errores). Se agregan en D10. |
| Cliente `portal-facturas-web` | `directAccessGrantsEnabled: false`, PKCE `S256`, `baseUrl: http://127.0.0.1:8000/` | ROPC ya está deshabilitado. "Volver a la aplicación" de las páginas genéricas tendrá destino. |
| `displayName` | "Portal de Proveedores ULTRASIST" | Título de la página. |

**Mensajes en español de Keycloak 26.7.4** (`base/login/messages/messages_es.properties`)
- Son de España y mezclan "tú" y "usted". Ejemplos: "¿Has olvidado tu contraseña?", "Email", "Volver a la identificación", "identificate".
- El error de la expresión que exige una letra es opaco: "Contraseña incorrecta: no cumple la expresión regular."

**Login personalizado anterior**
- **Dónde estaba:** se eliminó en `c5f389f` (`add-keycloak-authentication`) y se recupera de `c5f389f^`:
  - `app/templates/auth/login.html`: dos columnas, con un panel azul marino de marca (logo, "Invoice Portal / Portal de proveedores", titular, texto y tarjeta de principios) y la tarjeta del formulario;
  - el bloque `anonymous` de `app/templates/base.html`;
  - sus reglas de `app/static/css/app.css` (`.login-page`, `.login-panel`, `.login-copy`, `.principle-card`, `.login-form-wrap`, `.login-card`, `.brand`, `.brand-logo` y las *media queries* de 700 px), que ya no existen en el `app.css` actual.
- **Dependencias:** Bootstrap 5.3.3 y Bootstrap Icons 1.11.3, locales en `app/static/vendor/`, más `img/Ultrasistlogo.png` y `img/favicon.png`.
- **Lo que no se migra:** el bloque `demo-credentials` (`data-demo="correo|contraseña"`) y el acceso rápido de `app/static/js/app.js` (SEC-03).
- **Textos:** no llevaban acentos ("Recepcion", "Contrasena") y el subtítulo decía "PoC LOCAL · ULTRASIST".

**Correo**
- **Portal:** el `.env` local usa SMTP real (Gmail), y la suite `tests/hu` arranca el portal con `MAIL_BACKEND=file`.
- **Sin SMTP de pruebas:** no existe en el proyecto (ni Mailpit, ni MailHog, ni smtp4dev). El transporte `file` es del portal y Keycloak no puede usarlo.

**Pruebas que dependen del marcado de Keycloak**
- **Suite `tests/hu`:** `#username`, `#password`, `#kc-login`, `#password-new`, `#password-confirm`, `#kc-submit` y, para leer errores, `.kc-feedback-text`, `#input-error` e `#input-error-username`.
- **Origen de esos IDs:** `#kc-submit` y `.kc-feedback-text` vienen del tema `keycloak.v2`, no de `base`.

**Alcance y calidad**
- **EP-01:** su tabla "Fuera del alcance" incluye "Recuperación de contraseña ('olvidé mi contraseña') | Fuera del MVP".
- **README:** ya prevé el SMTP de Keycloak "para funciones futuras como la recuperación de contraseña".
- **SonarQube:** `sonar.sources=app` y `sonar.exclusions=app/static/vendor/**`. Nada de `infra/` se analiza hoy.

### Restricciones (del pedido)
- **Sin ROPC:** el portal nunca recibe contraseñas, y no vuelve el login local.
- **Integración OIDC y flujos intactos:** no se tocan el cliente, las redirect URIs, los tokens, los roles ni los flujos del realm. Del realm sólo se cambian el tema de login y, si hiciera falta, el idioma por defecto.
- **Plantillas y textos:** FreeMarker, con los assets en `resources/` del tema y sin CDN. Textos en `messages_es.properties`.
- **Sin dependencias ni herramientas nuevas** sin consulta previa.
- **Sin secretos en el repo**, y el quality gate de SonarQube debe pasar.

## Goals / Non-Goals

**Goals:**
- Que el login, la solicitud de restablecimiento, la nueva contraseña (enlace del correo, primer acceso y cambio voluntario) y las páginas genéricas de Keycloak usen el diseño del login anterior, en escritorio y en móvil.
- Que ninguna de esas páginas muestre el diseño por defecto de Keycloak.
- Que el tema y su asignación al realm sean código: se reproducen en una máquina limpia y en el realm existente sin borrar datos.
- Que el restablecimiento por correo se pueda probar en local sin enviar correos reales (si se aprueban las decisiones 1 y 2 del proposal).
- No romper la suite `tests/hu` ni el comportamiento del login, los roles y las sesiones.

**Non-Goals:**
- Los temas `account`, `admin` y `email`. El correo de restablecimiento usará la plantilla por defecto de Keycloak, en español.
- Cambios en los clientes, los roles, los flujos del realm, la política de contraseñas o la vigencia de los enlaces.
- La autorización del portal y cualquier ruta o plantilla de `app/`.
- Un despliegue de Keycloak para QA o producción como código; sólo se documenta.
- Validar la contraseña en el navegador (ver D6).

## Decisions

### D1. Tema de login de Keycloak, no un formulario propio en el portal

**Decisión:** un tema de login de Keycloak (FreeMarker), servido por el propio Keycloak.

**Alternativas descartadas:**
- **Formulario del portal que envía usuario y contraseña a Keycloak** (Resource Owner Password Credentials / *Direct Access Grants*):
  - el portal recibiría contraseñas, lo que contradice RN-HU03-01 y el requisito "Inicio de sesión mediante Keycloak (OIDC)" ("MUST NOT aceptar credenciales en un formulario propio");
  - el *grant* está desaconsejado (OAuth 2.0 Security BCP) y desaparece en OAuth 2.1;
  - obligaría a habilitarlo en el cliente, que hoy tiene `directAccessGrantsEnabled: false`;
  - no soporta las acciones interactivas de Keycloak: `UPDATE_PASSWORD` del primer acceso (RF-06), el restablecimiento por correo, los mensajes de bloqueo por fuerza bruta ni un segundo factor futuro. Habría que reimplementarlas en el portal.
- **Keycloakify** (temas en React compilados a un JAR):
  - agrega una cadena de build (Node y empaquetado del JAR) y una dependencia, para sólo cuatro plantillas;
  - el pedido exige consultar antes de usarlo, y FreeMarker alcanza.

### D2. El tema hereda de `base`

**Decisión:** `parent=base` e `import=common/keycloak`. `base` es el tema abstracto de Keycloak 26.7.4, con plantillas sin estilos que leen sus clases CSS de las propiedades `kc*` de `theme.properties`.

**Cómo funciona:**
- **Páginas no sobrescritas** (`error.ftl`, `info.ftl`, `login-page-expired.ftl`, `logout-confirm.ftl` y las demás): las sirve `base`, envueltas en nuestro `template.ftl`. Sus clases `kc*` se asignan en `theme.properties` a clases de Bootstrap (`kcInputClass=form-control`, `kcButtonClass=btn`, `kcButtonPrimaryClass=btn-primary`, `kcButtonBlockClass=w-100`, `kcInputErrorMessageClass=invalid-feedback d-block`, `kcFormGroupClass=mb-3`…), así que todas comparten el diseño.
- **Recursos de JavaScript:** `base` aporta `passwordVisibility.js`, `authChecker.js` y `menu-button-links.js`, y Keycloak los resuelve desde el tema padre.

**Alternativas descartadas:**
- **`parent=keycloak.v2`:** sus páginas usan las macros `field.ftl` y `buttons.ftl` y las clases de PatternFly 5. Las páginas v2 que no sobrescribiéramos (`login-password`, `login-otp`, `select-authenticator`…) mezclarían PatternFly con el diseño del portal, o habría que cargar PatternFly y volveríamos al diseño por defecto.
- **`parent=keycloak`** (v1, PatternFly 4): el mismo problema.

### D3. Diseño, assets y textos

**Marcado**
- El de `login.html` anterior pasa a `template.ftl`: `main.login-page` › `section.login-panel` (marca, titular, texto y tarjeta de principios) + `section.login-form-wrap` › tarjeta.
- La tarjeta contiene el `header` (`h1#kc-page-title`), las alertas, el bloque `form` y el bloque `info` de cada página.
- `template.ftl` parte de `base/login/template.ftl` 26.7.4 y conserva intacta su lógica:
  - scripts de `authChecker` y de enlaces de un solo uso, e *importmap*;
  - mensajes con `kcSanitize` y la regla de `isAppInitiatedAction`;
  - bloque `show-username` / reinicio del flujo;
  - "probar otra forma", cambio de organización, `socialProviders`, `info` y pie.
- Sólo cambian los envoltorios y las clases.

**Estilos**
- `resources/css/ultrasist.css` lleva las reglas del login de `c5f389f^:app/static/css/app.css`, los *tokens* `:root` del portal y sus ajustes de Bootstrap (`.btn`, `.btn-primary`, `.form-control`, `.alert`).
- Bootstrap 5.3.3 y Bootstrap Icons 1.11.3 (CSS y fuentes) se copian **idénticos** de `app/static/vendor/` a `resources/vendor/`, con su README de licencias (MIT). Así el diseño es exactamente el anterior.
- Una prueba exige que las copias sean idénticas byte a byte a las del portal, para que no se desincronicen.
- No se incluye `bootstrap.bundle.min.js`: ninguna página usa componentes con JavaScript.
- **Iconos:** los de la tarjeta de principios (`bi-diagram-3`, `bi-arrow-right`), los de las alertas y el de mostrar u ocultar la contraseña (`kcFormPasswordVisibilityIconShow=bi bi-eye`, `…Hide=bi bi-eye-slash`) son de Bootstrap Icons.
- **Alternativas:**
  - CSS propio sin Bootstrap (unas 80 líneas): sin duplicar 600 KB, pero el diseño ya no sería exactamente el mismo;
  - montar `app/static/vendor` en el contenedor: evita duplicar, pero el tema deja de ser autocontenido y no se puede copiar tal cual a la instancia de QA o producción.

**Móvil**
- Se conserva el corte de 700 px del diseño anterior: el panel de marca se oculta y la tarjeta ocupa el ancho.
- **Mejora:** en móvil la tarjeta muestra arriba un encabezado compacto con el logo. Antes no se veía ninguna marca.
- Los campos usan 16 px (`1rem` de Bootstrap) para que iOS no haga zoom.
- Sin desplazamiento horizontal desde 360 px.

**Textos**
- Todos están en `messages/messages_es.properties`. Las claves propias llevan el prefijo `ultrasist` (marca, titular, texto, pasos de la tarjeta y ayuda de RF-06).
- Se migran los del login anterior **con acentos**.
- "PoC LOCAL · ULTRASIST" se cambia por "PORTAL DE PROVEEDORES · ULTRASIST": el tema también se usará en QA y producción, donde "PoC LOCAL" sería falso. Se puede revertir en una línea.
- Las plantillas no fijan texto visible; una prueba lo verifica (ver D9).

### D4. Contrato de los formularios intacto

Cada plantilla sobrescrita parte de la de `base` 26.7.4 y conserva sin cambios:

| Plantilla | Se conserva |
|---|---|
| `login.ftl` | `form#kc-form-login` con `action="${url.loginAction}"` y `method="post"`; `username` (oculto si `usernameHidden`), `password`, `credentialId` (oculto), `rememberMe` (si el realm lo activa), `login`; el enlace `${url.loginResetCredentialsUrl}` sólo con `realm.resetPasswordAllowed`; el registro, sólo si el realm lo permite; los proveedores sociales; `passkeys.conditionalUIData`; errores con `messagesPerField.existsError('username','password')` y `displayMessage`. |
| `login-reset-password.ftl` | `form#kc-reset-password-form` → `url.loginAction`; `username` con `auth.attemptedUsername`; `${url.loginUrl}` para volver; errores `messagesPerField('username')`; texto `emailInstruction` / `emailInstructionUsername` según `realm.duplicateEmailsAllowed`. |
| `login-update-password.ftl` | `form#kc-passwd-update-form` → `url.loginAction`; `password-new`, `password-confirm`, `logout-sessions` (`password-commons.ftl` de `base`), `login`; con `isAppInitiatedAction`, el botón `cancel-aia`; errores `messagesPerField('password','password-confirm')`. |

**IDs para la suite `tests/hu`:** se mantienen `#username`, `#password`, `#kc-login`, `#password-new`, `#password-confirm` y los `#input-error*`. Se agregan `#kc-submit` y `#kc-cancel` en la nueva contraseña, y la clase `kc-feedback-text` en el texto de la alerta, como en `keycloak.v2`. Es marcado, no comportamiento.

**Scripts en línea:** se conservan los `onsubmit` de `base` (impiden el doble envío).

**Cabecera de versión:** cada plantilla abre con un comentario FreeMarker (`<#-- Basado en base/login/<archivo> de Keycloak 26.7.4 -->`) que permite revisarla al actualizar Keycloak (ver Riesgos).

### D5. Mensajes en español de México

`messages_es.properties` del tema sobrescribe las claves de Keycloak que aparecen en estos flujos, en un registro único ("usted", ver decisión 4 del proposal) y con el vocabulario del portal ("correo electrónico", no "email"). Ejemplos:

| Clave | Texto propuesto |
|---|---|
| `loginAccountTitle` | Iniciar sesión |
| `doLogIn` | Ingresar al portal (botón del login anterior) |
| `usernameOrEmail` | Correo electrónico |
| `invalidUserMessage` / `accountTemporarilyDisabledMessage` | Correo o contraseña incorrectos. (el bloqueo no se revela, como hoy) |
| `doForgotPassword` | ¿Olvidó su contraseña? |
| `emailForgotTitle` / `emailInstruction` | Restablecer contraseña / Escriba su correo electrónico y le enviaremos un enlace para crear una contraseña nueva. |
| `emailSentMessage` | Si el correo está registrado, en unos minutos recibirá un enlace para restablecer su contraseña. |
| `invalidPasswordRegexPatternMessage` | Contraseña no válida: debe incluir al menos una letra. |
| `expiredActionTokenNoSessionMessage` y afines | El enlace expiró o ya se usó. Solicite uno nuevo. |

- **Mensaje de la letra:** reescribir `invalidPasswordRegexPatternMessage` es correcto porque la política tiene **una sola** expresión, la que exige una letra. Una prueba lo exige; si algún día se agrega otra expresión, la prueba falla y obliga a revisar el texto.
- **Resto de claves:** la lista completa (longitud, dígitos, caracteres especiales, historial, lista de comunes, usuario o correo, no coinciden, página expirada, error, volver al portal, etc.) se define al implementar.
- **Claves no sobrescritas:** caen en `messages_es` de `base`.

### D6. Ayuda de RF-06 sin validación propia

- **Ayuda:** la pantalla de nueva contraseña muestra los requisitos como lista estática asociada al campo con `aria-describedby`:
  - al menos 8 caracteres;
  - una letra;
  - un número;
  - un carácter especial;
  - "tampoco se aceptan contraseñas comunes, su correo ni su contraseña anterior", porque Keycloak también rechaza esos casos.
- **Validación:** la hace sólo Keycloak al enviar. Sus errores aparecen junto al campo (`messagesPerField`) y en la alerta (`message`).
- **Sin validación en el navegador:** no se incluye `password-policy.js` de `keycloak.v2`. Duplicaría las reglas y podría contradecir a la política del realm.
- **Política vs. RF-06:** coinciden (ver Context); no hay nada que avisar.

### D7. Tema y configuración del realm como código

**Tema**
- Vive en `infra/keycloak/themes/ultrasist/login/`.
- Se monta en el servicio `keycloak`: `./infra/keycloak/themes/ultrasist:/opt/keycloak/themes/ultrasist:ro`.
- Con `start-dev`, los cambios se ven al recargar la página.

**Asignación al realm**
- **Realm nuevo:** el JSON versionado declara `"loginTheme": "ultrasist"` (y `"resetPasswordAllowed": true` si se aprueba).
- **Realm existente:** `--import-realm` omite un realm que ya existe, así que el JSON no basta. `infra/keycloak/configure-realm.sh` se monta en `/opt/keycloak/scripts/configure-realm.sh:ro` y se ejecuta con `docker compose exec -T keycloak bash /opt/keycloak/scripts/configure-realm.sh`:
  - autentica `kcadm.sh` (de la misma imagen) con `KC_BOOTSTRAP_ADMIN_USERNAME` y `KC_BOOTSTRAP_ADMIN_PASSWORD`, que ya están en el entorno del contenedor;
  - guarda la configuración de `kcadm` en un archivo temporal, que se borra al salir;
  - aplica `loginTheme` (y `resetPasswordAllowed`) con `update realms/ultrasist-portal`;
  - si se aprueba la decisión 2, aplica el `smtpServer` (ver D8);
  - es idempotente: repetirlo deja el mismo estado;
  - termina con un mensaje claro si Keycloak no responde o el realm no existe.
- **Ejecución:** `run_local.sh`, `.ps1` y `.bat` lo ejecutan después de `up --wait`.
- **Coherencia:** una prueba exige que los valores del script y los del JSON coincidan.

**Alternativas descartadas**
- **Borrar el volumen y reimportar:** se pierden las cuentas (hoy es la vía documentada para "aplicar cambios del JSON"; sigue siendo válida, pero es destructiva).
- **`kc.sh import --override true`:** exige el servidor detenido y otro *entrypoint*.
- **keycloak-config-cli:** es una dependencia nueva.
- **Opción de servidor `spi-theme--default`:** afecta a todos los tipos de tema y a todos los realms, y no deja la asignación en el realm.

**QA y producción (paso manual inevitable)**
- El repo no define ese despliegue. Se documenta en el README:
  - copiar `infra/keycloak/themes/ultrasist` a `/opt/keycloak/themes/` de la instancia (o empaquetarlo como JAR en `providers/` y ejecutar `kc.sh build`);
  - reiniciar, porque `start` guarda los temas en caché;
  - ejecutar el script con una cuenta administradora del realm (`KCADM_USER` y `KCADM_PASSWORD`, si se definen, tienen prioridad sobre las de *bootstrap*), o asignar el tema en "Realm settings → Themes".

### D8. Correo de pruebas con Mailpit (si se aprueban las decisiones 2 y 3)

**Servicio `mailpit`**
- Imagen `axllent/mailpit:v1.31.4` (estable vigente al 2026-10-03, versión fija).
- La interfaz web en `127.0.0.1:${MAILPIT_PORT:-58025}:8025`.
- El SMTP (1025) **no se publica**: sólo lo alcanza Keycloak por la red de compose.
- Healthcheck con `/mailpit readyz`.
- `run_local.*` lo levanta junto con `db` y `keycloak`.

**SMTP del realm**
- Lo aplica el script a partir de variables con valores por defecto en `compose.yaml`: `KEYCLOAK_SMTP_HOST` (`mailpit`), `KEYCLOAK_SMTP_PORT` (`1025`) y `KEYCLOAK_SMTP_FROM` (`no-reply@portal-facturas.local`).
- `KEYCLOAK_SMTP_SECURITY` (`none`, `starttls` o `ssl`, como `SMTP_SECURITY` del portal; `none` por defecto), `KEYCLOAK_SMTP_USER` y `KEYCLOAK_SMTP_PASSWORD` son opcionales y quedan vacíos en desarrollo.
- El prefijo no es `KC_`, porque Keycloak interpreta esas variables como opciones suyas.
- `Settings` del portal ignora variables desconocidas (`extra="ignore"`).

**Por qué el `smtpServer` no va en el JSON:** el JSON también se importa en QA, donde `mailpit` no existe. QA y producción siguen D2 de `add-keycloak-authentication`: el SMTP del portal, con la contraseña configurada en Keycloak.

**Verificación:** las pruebas leen el correo con la API de Mailpit (`GET /api/v1/messages`). Ningún correo de Keycloak sale a Internet: el `.env` local apunta a Gmail, pero eso es el SMTP del portal, no el de Keycloak.

**Alternativa descartada:** usar el SMTP real del `.env`. Enviaría correos reales en cada prueba y exigiría la contraseña de Gmail en Keycloak.

### D9. Verificación

**pytest, sin Keycloak ni red** (`tests/test_tema_keycloak.py`; se respeta "Pruebas sin Keycloak ni red")
- **Realm:** `loginTheme == "ultrasist"`, `resetPasswordAllowed` (si se aprueba), `defaultLocale == "es"`, sin `smtpServer`, y el cliente sigue con `directAccessGrantsEnabled: false`.
- **`compose.yaml`:**
  - montajes `:ro` del tema y del script;
  - `mailpit` con versión exacta, interfaz web en `127.0.0.1` y SMTP sin publicar;
  - la versión de la imagen de Keycloak igual a la anotada en el tema.
- **Tema:**
  - `parent=base`;
  - plantillas sin URLs externas (`http://`, `https://`, `//`) ni `data-demo`;
  - contrato de cada formulario (D4);
  - toda clave `msg("ultrasist…")` existe en `messages_es.properties`;
  - plantillas sin texto visible fijo: tras quitar etiquetas, directivas e interpolaciones no queda texto;
  - `vendor/` idéntico a `app/static/vendor/`.
- **Script:** sus valores coinciden con el JSON y no contiene secretos.

**E2E** (`tests/hu`, contra Keycloak real con el portal en transporte `file` y Mailpit), en dos tamaños de ventana, 1440×900 y 390×844, con captura de cada página:
1. el Administrador crea un usuario PMO;
2. primer acceso con la temporal → cambio obligatorio, con errores de política visibles (`Password123`, `Portal2026!`) → entra;
3. sale; contraseña incorrecta → error en español;
4. "¿Olvidó su contraseña?" con un correo inexistente → mismo mensaje y ningún correo en Mailpit;
5. con su correo → mismo mensaje → correo en Mailpit → enlace → nueva contraseña con errores de política → guarda;
6. reutilizar el enlace → página de enlace usado con el diseño del portal;
7. sale y entra con la contraseña nueva.

En cada página se verifica que no cargue hojas de estilo de `keycloak.v2` ni de PatternFly, que todas vengan de `/login/ultrasist/`, que aparezca el logo y que no haya desplazamiento horizontal.

**Enlace expirado:** se verifica una vez a mano esperando más de 5 minutos (la vigencia del realm no se cambia en esta tarea), con captura. Sigue la misma ruta de plantillas que el enlace usado.

**Regresión:** se ejecutan las especificaciones de `tests/hu` que inician sesión (HU-10 y las de cada rol) sin cambiar sus selectores.

**SonarQube:** `sonar.sources=app,infra/keycloak/themes` y `sonar.exclusions` agrega `infra/keycloak/themes/**/vendor/**`. El CSS propio se analiza; las plantillas `.ftl` no tienen analizador.

### D10. Eventos del restablecimiento (aprobado el 2026-10-06)

El usuario pidió que se guarden los registros de restablecimiento. Como el portal no participa en el flujo, se guardan en los eventos de usuario del realm. Se conservan 30 días (`eventsExpiration`), se consultan en la consola ("Events") o con `GET /admin/realms/ultrasist-portal/events`, y los errores también salen en el log del servidor (listener `jboss-logging`).

**Eventos agregados a `enabledEventTypes`** (en el JSON y en `configure-realm.sh`, que los aplica al realm existente; una prueba exige que coincidan): `SEND_RESET_PASSWORD`, `SEND_RESET_PASSWORD_ERROR`, `RESET_PASSWORD`, `RESET_PASSWORD_ERROR`, `EXECUTE_ACTION_TOKEN` y `EXECUTE_ACTION_TOKEN_ERROR`.

**Lo que registra cada caso** (observado con Keycloak 26.7.4):

| Caso | Evento |
|---|---|
| Solicitud con un correo registrado | `SEND_RESET_PASSWORD` (usuario y correo) |
| Correo no registrado | `RESET_PASSWORD_ERROR` / `user_not_found` (el correo escrito) |
| Cuenta deshabilitada | `RESET_PASSWORD_ERROR` / `user_disabled` |
| Falla del envío del correo | `SEND_RESET_PASSWORD_ERROR` |
| Contraseña rechazada o guardada desde el enlace | `UPDATE_PASSWORD_ERROR` (motivo de la política) y `UPDATE_PASSWORD`, que ya estaban habilitados |
| Enlace ya usado o vencido | `RESET_PASSWORD_ERROR` / `expired_code` (`action: reset-credentials`) |
| Enlace alterado | `EXECUTE_ACTION_TOKEN_ERROR` / `invalid_code` |

**Sin cambios:** la vigencia del enlace se mantiene en 5 minutos, por decisión del usuario. Los eventos quedan en Keycloak; el portal no los copia a `audit_logs`.

## Risks / Trade-offs

- **[Actualizar Keycloak puede romper las plantillas sobrescritas]** (cambian variables o campos de `base`).
  - Mitigaciones: el comentario de versión en cada plantilla, y la prueba que compara la versión del tema con la imagen de `compose.yaml`.
  - Al subir de versión: comparar con `diff` las cuatro plantillas contra las de `base` nuevas (procedimiento en el README) y repetir el E2E.
- **[Enlace de restablecimiento de 5 minutos]** (`actionTokenGeneratedByUserLifespan`, valor por defecto).
  - Puede ser corto para un proveedor que no revisa su correo de inmediato.
  - No se cambia aquí (es configuración del realm). Queda como pregunta abierta.
- **[Correo de restablecimiento con la plantilla por defecto de Keycloak]:** el tema `email` está fuera de alcance. Llega en español, pero sin la marca del portal.
- **[Abuso del restablecimiento]:**
  - Keycloak no revela si el correo existe: muestra el mismo mensaje.
  - Tampoco limita el envío repetido de correos a una cuenta. Lo cubre el *rate limiting* por IP en el proxy, ya pendiente en D3 de `add-keycloak-authentication`.
- **[Eventos del restablecimiento solo en Keycloak]** (D10): se guardan 30 días en el realm, no en `audit_logs` del portal. Si se necesitan más tiempo o junto a la auditoría del portal, habría que exportarlos o ampliar `eventsExpiration`, en otro cambio.
- **[Usuario deshabilitado]:** Keycloak no envía el correo a una cuenta deshabilitada, y el portal deshabilita también en Keycloak (D10 de `add-keycloak-authentication`). Se verifica en el E2E o a mano.
- **[Restablecimiento sin SMTP en QA]:** si el JSON lleva `resetPasswordAllowed: true` pero la instancia aún no tiene `smtpServer`, el usuario ve "No se pudo enviar el correo". El README lo incluye en los pasos de QA.
- **[Copias duplicadas de Bootstrap (~600 KB)]** → la prueba de igualdad byte a byte y la exclusión de `vendor/` en Sonar.
- **[Credenciales de *bootstrap* en `kcadm`]:**
  - la contraseña viaja como argumento dentro del contenedor y sólo se ve en sus procesos;
  - la configuración de `kcadm` va a un archivo temporal que se borra;
  - en QA se usa una cuenta propia (D7).
- **[Selectores de la suite `tests/hu`]** → se conservan los IDs (D4) y se ejecutan las especificaciones de inicio de sesión.

## Migration Plan

**Local**
1. Ejecutar `./run_local.sh` (o `.ps1` / `.bat`): levanta `db`, `keycloak` y `mailpit`, y aplica `configure-realm.sh` al realm existente.
2. No hay que borrar el volumen ni recrear usuarios.

**QA y producción**
1. Copiar el tema a la instancia y reiniciarla.
2. Ejecutar el script con una cuenta administradora, o asignar el tema en la consola.
3. Si se aprueba la decisión 1, configurar antes el `smtpServer` según D2.

**Rollback**
- Ejecutar `kcadm.sh update realms/ultrasist-portal -s loginTheme=keycloak.v2` (vuelve al tema por defecto; verificado: un valor vacío no lo cambia) y, si aplica, `-s resetPasswordAllowed=false`.
- O bien revertir el commit y volver a ejecutar el script.
- El portal no cambia, así que no hay migración de datos.

## Open Questions

1. ~~**Decisiones 1 a 4 del proposal**~~ — **Resuelta (2026-10-06):** se aprobaron las recomendaciones (restablecimiento, SMTP con Mailpit en local, Mailpit y "usted").
2. ~~**Vigencia del enlace**~~ — **Resuelta (2026-10-06):** el usuario acepta los 5 minutos; no se cambia.
3. **Tema `email`:** ¿se quiere después un tema `email` con la marca del portal para el correo de restablecimiento? Está fuera de alcance aquí.
4. ~~**Eventos del restablecimiento**~~ — **Resuelta (2026-10-06):** el usuario pidió guardarlos; se registran según D10.
