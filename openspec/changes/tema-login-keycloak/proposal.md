## Why

Desde `add-keycloak-authentication`, el usuario ve las pantallas del tema por defecto de Keycloak 26 (`keycloak.v2`, PatternFly 5) al iniciar sesión y al cambiar su contraseña temporal (RF-06, HU-10). Sus textos están en español de España y mezclan "tú" y "usted". Se pierde la continuidad visual con el portal y con el login propio que existía antes.

Este cambio recupera ese diseño con un tema de login de Keycloak y lo extiende al restablecimiento de contraseña. Quien autentica no cambia: Keycloak sigue procesando credenciales, sesiones, política de contraseñas, correo, tokens y redirecciones. Sólo cambia la capa de presentación.

## What Changes

- **Tema de login `ultrasist`** (FreeMarker, hereda de `base` de Keycloak 26.7.4), versionado en `infra/keycloak/themes/ultrasist/`, con todos sus assets dentro del tema y sin CDN:
  - `template.ftl`: el layout del login anterior (panel de marca y tarjeta). También envuelve las páginas que no se personalizan: error, información, enlace expirado o usado, página expirada y confirmación de logout.
  - `login.ftl`, `login-reset-password.ftl` y `login-update-password.ftl` con el diseño anterior. Conservan el `action`, los nombres de campo, los campos ocultos, el manejo de mensajes (`message`, `messagesPerField`) y los IDs que usa la suite `tests/hu`.
  - `messages/messages_es.properties`: todos los textos visibles, en español de México. Incluye la ayuda de RF-06 en la pantalla de nueva contraseña; la validación la sigue haciendo Keycloak.
  - No se migran los botones de acceso rápido demo (`data-demo`) ni su JS (SEC-03).
- **Realm:** `loginTheme: "ultrasist"` (el español ya es el único idioma y el idioma por defecto). **Pendiente de aprobación:** `resetPasswordAllowed: true` y un `smtpServer` para Keycloak (ver "Decisiones pendientes").
- **Registro de los restablecimientos** (pedido después de la propuesta, el 2026-10-06): los eventos del restablecimiento se agregan a los que registra el realm (`SEND_RESET_PASSWORD`, `RESET_PASSWORD`, `EXECUTE_ACTION_TOKEN` y sus errores). Keycloak los conserva 30 días. La vigencia del enlace (5 minutos) no cambia.
- **Tema y configuración del realm como código:** `--import-realm` no reimporta un realm que ya existe. El script idempotente `infra/keycloak/configure-realm.sh` usa `kcadm.sh` de la misma imagen para aplicar esos ajustes al realm ya importado, y `run_local.*` lo ejecuta después de levantar Keycloak. El servicio `keycloak` monta el tema y el script en modo sólo lectura.
- **Correo de pruebas:** servicio `mailpit` (`axllent/mailpit:v1.31.4`) en `compose.yaml`. El proyecto no tiene un SMTP de pruebas: el portal usa el transporte `file` en las pruebas, y Keycloak no puede usarlo. El Keycloak de desarrollo envía a Mailpit y nunca al SMTP real del `.env`.
- **Pruebas:**
  - pytest estático, sin Keycloak ni red: tema, contrato de los formularios, textos fuera de las plantillas, sin CDN ni `data-demo`, realm, compose y script;
  - recorrido E2E en `tests/hu` contra Keycloak real, con capturas en escritorio y móvil.
- **SonarQube:** `infra/keycloak/themes` se agrega a `sonar.sources`, sin `vendor/`. Hoy sólo se analiza `app/`.
- **No cambia:**
  - la integración OIDC del portal (cliente, redirect URIs, tokens, roles);
  - los flujos de autenticación del realm y la política de contraseñas;
  - los temas `account`, `admin` y `email`;
  - la lógica de autorización.

  Ningún formulario del portal recibe contraseñas: el cliente sigue con `directAccessGrantsEnabled: false` y la autenticación local no se reactiva.

## Decisiones pendientes (requieren aprobación antes de implementar)

1. **Habilitar el restablecimiento (`resetPasswordAllowed`).** Hoy vale `false`, en el JSON y en el realm vivo. Sin él, Keycloak no muestra el enlace y rechaza el flujo, así que el criterio "Reset completo" no se puede cumplir. Es un ajuste del realm, no un cambio de flujos: el flujo `reset credentials` ya existe y no se toca. Pero va más allá de lo autorizado (tema e idioma). Además, EP-01 deja la recuperación de contraseña **fuera del MVP** ("Validación de HUs, §3"); aprobarla amplía el alcance, y el cambio actualizaría esa tabla de EP-01.
2. **SMTP de Keycloak.** El realm no tiene `smtpServer` (`{}` en el realm vivo). Se propone:
   - **Desarrollo:** el script configura Mailpit, sin credenciales, con valores que se pueden cambiar por variables de entorno.
   - **QA y producción:** se aplica la decisión D2 de `add-keycloak-authentication`: el mismo servidor y remitente SMTP del portal, con la contraseña configurada en el servidor de Keycloak y nunca en el repo.

   El `smtpServer` no entra en el JSON versionado, porque ese realm también se importa en QA.
3. **Mailpit como dependencia nueva**, sólo de desarrollo (una imagen de contenedor; ningún paquete de Python ni de Node).
4. **Tratamiento de "usted".** El portal y el login anterior usan "usted"; el texto que se pidió para el enlace ("¿Olvidaste tu contraseña?") usa "tú". Se propone "¿Olvidó su contraseña?" para que todo quede consistente. Cambiarlo es una línea en `messages_es.properties`.

Recomendación: aprobar 1, 2 y 3, y usar "usted" en 4. Si 1 o 2 no se aprueban, se retira el requisito "Restablecimiento de contraseña por correo" y el tema cubre sólo el login, el primer acceso y el cambio voluntario.

## Capabilities

### New Capabilities
<!-- Ninguna: el cambio amplía capacidades existentes. -->

### Modified Capabilities
- `autenticacion-sesiones`: pantallas de Keycloak con el diseño del portal (tema `ultrasist`) y restablecimiento de contraseña por correo. Los criterios de aceptación pasan a ser escenarios.
- `infraestructura-local`:
  - el servicio Keycloak monta el tema y el script de configuración;
  - el realm declara el tema (y el restablecimiento, si se aprueba);
  - la configuración se aplica a un realm ya importado;
  - nuevo servicio de correo de pruebas (Mailpit).
- `calidad-y-pruebas`: verificación estática del tema sin Keycloak, recorrido E2E del tema y alcance de SonarQube.

## Impact

- **Nuevos** (relativos a la raíz de la PoC):
  - `infra/keycloak/themes/ultrasist/login/`:
    - `theme.properties`, `template.ftl`, `login.ftl`, `login-reset-password.ftl`, `login-update-password.ftl`;
    - `messages/messages_es.properties`;
    - `resources/css/ultrasist.css`;
    - `resources/img/` (logo y favicon del portal);
    - `resources/vendor/` (copia idéntica de Bootstrap 5.3.3 y Bootstrap Icons 1.11.3 de `app/static/vendor`).
  - `infra/keycloak/configure-realm.sh`.
  - `tests/test_tema_keycloak.py`.
  - `tests/hu/specs/` (recorrido del tema).
- **Modificados:**
  - `infra/keycloak/realm-ultrasist-portal.json`, `compose.yaml` (montajes del tema y del script, variables SMTP del realm y servicio `mailpit`);
  - `run_local.sh`, `run_local.ps1`, `run_local.bat`, `.env.example`, `sonar-project.properties`, `README.md`;
  - `docs/stories/epics/EP-01 Acceso y gestion de facturas del proveedor.md`, sólo si se aprueba la decisión 1.
- **Sin cambios:**
  - `app/`: rutas, OIDC, roles, sesiones y plantillas del portal;
  - el cliente `portal-facturas-web`, los flujos del realm y la política de contraseñas.
- **Dependencias:** la imagen `axllent/mailpit:v1.31.4`, sólo en desarrollo. Sin paquetes nuevos ni herramientas de build: no se usa Keycloakify.
- **Operación en QA y producción:** el repo no define ese despliegue (D3 de `add-keycloak-authentication`). Hay que copiar el tema a `/opt/keycloak/themes/` de la instancia dedicada y reiniciarla, porque en modo `start` Keycloak guarda los temas en caché. Después se ejecuta el script con una cuenta administradora del realm, o se asigna el tema en la consola. Quedará documentado en el README.

> Rutas relativas a la raíz de la PoC (`PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress-V1/PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress/`), salvo `openspec/` y `docs/`.
