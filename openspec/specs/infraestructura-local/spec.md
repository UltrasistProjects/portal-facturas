# infraestructura-local Specification

## Purpose
Servicios PostgreSQL y Keycloak locales con Docker Compose: versiones fijadas, expuestos sólo en localhost, credenciales y secretos desde `.env`, volúmenes persistentes y healthchecks; realm de Keycloak versionado sin secretos.
## Requirements
### Requirement: Servicio PostgreSQL con Docker Compose
La raíz de la PoC SHALL incluir un `compose.yaml` con un servicio `db` basado en la imagen oficial de PostgreSQL 18, con una etiqueta de versión menor fija (nunca `latest` ni sólo la mayor). El servicio SHALL:
- tomar `POSTGRES_USER`, `POSTGRES_DB` y `POSTGRES_PASSWORD` del `.env` de la PoC;
- negarse a arrancar si `POSTGRES_PASSWORD` no está definida;
- persistir los datos en un volumen con nombre;
- declarar un healthcheck con `pg_isready`.

#### Scenario: Arranque del servicio
- **WHEN** se ejecuta `docker compose up -d --wait db` con un `.env` generado por `scripts/create_env.py`
- **THEN** el comando termina cuando el servicio está `healthy` y acepta conexiones con las credenciales de `.env`

#### Scenario: Persistencia entre reinicios
- **WHEN** se crea una factura, se ejecuta `docker compose down` (sin `-v`) y luego `docker compose up -d --wait db`
- **THEN** la factura sigue existiendo

#### Scenario: Contraseña ausente
- **WHEN** `POSTGRES_PASSWORD` no está definida en `.env`
- **THEN** `docker compose up` falla con un mensaje que indica definir `POSTGRES_PASSWORD`

#### Scenario: Versión fijada
- **WHEN** se inspecciona `docker compose config`
- **THEN** la imagen del servicio `db` tiene la forma `postgres:18.<menor>-alpine`

### Requirement: Exposición sólo local
El puerto de PostgreSQL SHALL publicarse únicamente en `127.0.0.1`, en el puerto del host `POSTGRES_PORT`, 55432 por defecto. En este equipo el 5432 y el 5433 ya los ocupan otras instancias.

#### Scenario: Enlace a localhost
- **WHEN** se inspecciona `docker compose config`
- **THEN** el puerto publicado del servicio `db` tiene `host_ip: 127.0.0.1`

#### Scenario: Puerto configurable
- **WHEN** `.env` define `POSTGRES_PORT=56000` y se levanta el servicio
- **THEN** PostgreSQL acepta conexiones en `127.0.0.1:56000` y `DATABASE_URL` apunta a ese puerto

### Requirement: Servicio Keycloak con Docker Compose
`compose.yaml` SHALL incluir un servicio `keycloak` con estas características:
- imagen oficial `quay.io/keycloak/keycloak` con una versión exacta fija, nunca `latest` ni sólo la mayor;
- arranque con `start-dev --import-realm`;
- el realm versionado montado en el directorio de importación, y la lista `infra/keycloak/common_passwords.txt` montada en `/opt/keycloak/data/password-blacklists/`;
- el tema `infra/keycloak/themes/ultrasist` montado en `/opt/keycloak/themes/ultrasist`, y el script `infra/keycloak/configure-realm.sh` montado en el contenedor, ambos en sólo lectura;
- los datos persistidos en un volumen con nombre montado en `/opt/keycloak/data`;
- el puerto publicado sólo en `127.0.0.1`, en `KEYCLOAK_PORT` (58080 por defecto);
- las credenciales del administrador inicial (`KC_BOOTSTRAP_ADMIN_USERNAME` y `KC_BOOTSTRAP_ADMIN_PASSWORD`) y los secretos de los clientes tomados del `.env`. El contenedor SHALL negarse a arrancar si falta alguno. La verificación MUST NOT impedir los comandos del servicio `db` con un `.env` sin esas variables;
- los datos del servidor de correo del realm (`KEYCLOAK_SMTP_HOST`, `KEYCLOAK_SMTP_PORT`, `KEYCLOAK_SMTP_FROM`) tomados del `.env`, con valores por defecto que apuntan al servicio `mailpit`. Las credenciales SMTP, si existen, SHALL venir sólo del entorno;
- un healthcheck.

Los scripts `run_local.*` SHALL levantar `db`, `keycloak` y `mailpit`, esperar a que estén sanos y aplicar después `configure-realm.sh` al realm.

#### Scenario: Arranque del servicio
- **WHEN** se ejecuta `docker compose up -d --wait keycloak` con un `.env` generado por `scripts/create_env.py`
- **THEN** el comando termina con el servicio sano y el realm `ultrasist-portal` importado

#### Scenario: Versión fijada y exposición local
- **WHEN** se inspecciona `docker compose config`
- **THEN** la imagen del servicio `keycloak` tiene una etiqueta `26.<menor>.<parche>` y su puerto publicado tiene `host_ip: 127.0.0.1`

#### Scenario: Secreto ausente
- **WHEN** `KEYCLOAK_CLIENT_SECRET` no está definida en `.env`
- **THEN** `docker compose up -d --wait keycloak` falla, el contenedor indica definir `KEYCLOAK_CLIENT_SECRET`, y `docker compose exec db` sigue funcionando

#### Scenario: Persistencia entre reinicios
- **WHEN** el seed crea las cuentas demo, se ejecuta `docker compose down` (sin `-v`) y luego `docker compose up -d --wait keycloak`
- **THEN** las cuentas demo siguen existiendo en Keycloak

#### Scenario: Tema montado en sólo lectura
- **WHEN** se inspecciona `docker compose config`
- **THEN** el servicio `keycloak` monta `infra/keycloak/themes/ultrasist` en `/opt/keycloak/themes/ultrasist` y `infra/keycloak/configure-realm.sh`, los dos con `read_only: true`

#### Scenario: Arranque local completo
- **WHEN** se ejecuta `run_local.sh` sobre un realm importado antes de este cambio
- **THEN** `db`, `keycloak` y `mailpit` quedan sanos, el realm usa el tema de login `ultrasist` y los usuarios existentes se conservan

### Requirement: Realm versionado sin secretos
El proyecto SHALL versionar el realm de desarrollo en `infra/keycloak/realm-ultrasist-portal.json` con:
- los realm roles `Administrador`, `Proveedor` y `PMO`;
- el cliente `portal-facturas-web`: confidencial, sólo Standard Flow, PKCE `S256` obligatorio, redirect URIs de `/auth/callback` y post-logout redirect URIs del portal local, y un *mapper* que incluye los realm roles en el ID token;
- el cliente `portal-facturas-admin`: sólo cuenta de servicio, con los roles de `realm-management` `manage-users`, `view-users` y `query-users` y ningún otro;
- la política de contraseñas, la detección de fuerza bruta, los eventos de inicio de sesión y de cambio de contraseña, y los tiempos de sesión SSO;
- el tema de login `ultrasist` (`loginTheme`), el español como idioma único y por defecto, y el restablecimiento de contraseña habilitado (`resetPasswordAllowed: true`);
- entre los eventos registrados, los del restablecimiento: `SEND_RESET_PASSWORD`, `RESET_PASSWORD`, `EXECUTE_ACTION_TOKEN` y sus errores, con la retención de 30 días.

El realm versionado MUST NOT declarar `smtpServer`: el servidor de correo depende del entorno y se aplica con `configure-realm.sh`.

Los secretos de los clientes SHALL escribirse como marcadores de variables de entorno (`${KEYCLOAK_CLIENT_SECRET}` y `${KEYCLOAK_ADMIN_CLIENT_SECRET}`). El archivo MUST NOT contener secretos ni contraseñas, y su único usuario SHALL ser la cuenta de servicio de `portal-facturas-admin`, sin credenciales.

La lista de contraseñas comunes SHALL generarse con `scripts/build_password_blacklist.py` a partir de la lista base `infra/keycloak/common_words.txt`. Incluye cada palabra común con sufijos frecuentes de dígitos y símbolos, porque la política exige ambos. Una prueba SHALL fallar si el archivo generado no corresponde a la lista base.

#### Scenario: Realm sin secretos
- **WHEN** se inspecciona el realm versionado
- **THEN** el `secret` de cada cliente es un marcador `${…}`, el único usuario es la cuenta de servicio sin credenciales y ningún valor coincide con un secreto del `.env`

#### Scenario: Lista de comunes al día
- **WHEN** se modifica `common_words.txt` y no se ejecuta `scripts/build_password_blacklist.py`
- **THEN** la prueba de la lista falla indicando regenerarla

#### Scenario: Cuenta de servicio mínima
- **WHEN** se inspecciona el realm versionado
- **THEN** la cuenta de servicio de `portal-facturas-admin` sólo tiene `manage-users`, `view-users` y `query-users` de `realm-management`

#### Scenario: PKCE obligatorio
- **WHEN** se inspecciona el cliente `portal-facturas-web`
- **THEN** tiene `publicClient: false`, `standardFlowEnabled: true`, `implicitFlowEnabled: false`, `directAccessGrantsEnabled: false` y el atributo `pkce.code.challenge.method` igual a `S256`

#### Scenario: Tema y restablecimiento declarados
- **WHEN** se inspecciona el realm versionado
- **THEN** tiene `loginTheme: "ultrasist"`, `resetPasswordAllowed: true`, `defaultLocale: "es"` y `supportedLocales: ["es"]`, y no tiene `smtpServer`

#### Scenario: Eventos del restablecimiento declarados
- **WHEN** se inspecciona el realm versionado
- **THEN** `enabledEventTypes` incluye `SEND_RESET_PASSWORD`, `SEND_RESET_PASSWORD_ERROR`, `RESET_PASSWORD`, `RESET_PASSWORD_ERROR`, `EXECUTE_ACTION_TOKEN`, `EXECUTE_ACTION_TOKEN_ERROR`, `UPDATE_PASSWORD` y `UPDATE_PASSWORD_ERROR`, y `eventsExpiration` es de 30 días

### Requirement: Configuración aplicada a un realm existente
Como `--import-realm` no reimporta un realm que ya existe, el proyecto SHALL versionar `infra/keycloak/configure-realm.sh`, que aplica al realm `ultrasist-portal` ya importado:
- el tema de login;
- el restablecimiento de contraseña;
- los eventos registrados (`enabledEventTypes`), incluidos los del restablecimiento;
- el servidor de correo de las variables `KEYCLOAK_SMTP_*`.

**Funcionamiento**
- SHALL usar `kcadm.sh` de la imagen de Keycloak, con una cuenta administradora tomada del entorno: `KCADM_USER` y `KCADM_PASSWORD` si existen; si no, las de *bootstrap*.
- SHALL guardar la configuración de `kcadm` en un archivo temporal que borra al terminar.
- Los valores del tema, del restablecimiento y de los eventos SHALL coincidir con los del realm versionado.
- SHALL ser idempotente.

**Restricciones**
- MUST NOT contener secretos.
- MUST NOT modificar clientes, roles, flujos de autenticación ni la política de contraseñas.

#### Scenario: Realm importado antes del tema
- **WHEN** el realm existe sin `loginTheme` y se ejecuta `docker compose exec -T keycloak bash /opt/keycloak/scripts/configure-realm.sh`
- **THEN** el realm queda con `loginTheme: "ultrasist"`, `resetPasswordAllowed: true`, los eventos del realm versionado y el `smtpServer` de las variables, y conserva sus usuarios, clientes, flujos y política

#### Scenario: Ejecución repetida
- **WHEN** el script se ejecuta dos veces seguidas
- **THEN** la segunda ejecución termina sin error y el realm queda igual

#### Scenario: Keycloak no disponible
- **WHEN** el script se ejecuta con Keycloak detenido o sin el realm
- **THEN** termina con un código distinto de cero y un mensaje que indica la causa, sin mostrar contraseñas

#### Scenario: Script y realm coherentes
- **WHEN** se comparan el script y el realm versionado
- **THEN** el tema de login, `resetPasswordAllowed` y `enabledEventTypes` tienen el mismo valor en ambos

### Requirement: Servidor de correo de pruebas
`compose.yaml` SHALL incluir un servicio `mailpit`:
- imagen `axllent/mailpit` con versión exacta;
- interfaz web publicada sólo en `127.0.0.1`, en `MAILPIT_PORT` (58025 por defecto);
- puerto SMTP sin publicar en el host;
- healthcheck.

En desarrollo, Keycloak SHALL enviar sus correos a Mailpit. Ningún correo de Keycloak de desarrollo SHALL salir al SMTP real configurado para el portal en `.env`.

#### Scenario: Correo de restablecimiento capturado
- **WHEN** en el entorno local se solicita el restablecimiento de una cuenta existente
- **THEN** el correo con el enlace aparece en la API de Mailpit (`/api/v1/messages`) y no se envía a ningún servidor externo

#### Scenario: Versión fijada y exposición local de Mailpit
- **WHEN** se inspecciona `docker compose config`
- **THEN** la imagen de `mailpit` tiene una etiqueta `v<mayor>.<menor>.<parche>`, su interfaz web se publica con `host_ip: 127.0.0.1` y su puerto SMTP no se publica

