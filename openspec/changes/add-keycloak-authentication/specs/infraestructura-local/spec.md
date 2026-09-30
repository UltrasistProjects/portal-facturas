## ADDED Requirements

### Requirement: Servicio Keycloak con Docker Compose
`compose.yaml` SHALL incluir un servicio `keycloak` con estas características:
- imagen oficial `quay.io/keycloak/keycloak` con una versión exacta fija, nunca `latest` ni sólo la mayor;
- arranque con `start-dev --import-realm`;
- el realm versionado montado en el directorio de importación, y `app/core/common_passwords.txt` montado en `/opt/keycloak/data/password-blacklists/`;
- los datos persistidos en un volumen con nombre;
- el puerto publicado sólo en `127.0.0.1`, en `KEYCLOAK_PORT` (58080 por defecto);
- las credenciales del administrador inicial (`KC_BOOTSTRAP_ADMIN_USERNAME` y `KC_BOOTSTRAP_ADMIN_PASSWORD`) y los secretos de los clientes tomados del `.env`; el servicio SHALL negarse a arrancar si falta alguno;
- un healthcheck.

Los scripts `run_local.*` SHALL levantar `db` y `keycloak` y esperar a que ambos estén sanos.

#### Scenario: Arranque del servicio
- **WHEN** se ejecuta `docker compose up -d --wait keycloak` con un `.env` generado por `scripts/create_env.py`
- **THEN** el comando termina con el servicio sano y el realm `ultrasist-portal` importado

#### Scenario: Versión fijada y exposición local
- **WHEN** se inspecciona `docker compose config`
- **THEN** la imagen del servicio `keycloak` tiene una etiqueta `26.<menor>.<parche>` y su puerto publicado tiene `host_ip: 127.0.0.1`

#### Scenario: Secreto ausente
- **WHEN** `KEYCLOAK_CLIENT_SECRET` no está definida en `.env`
- **THEN** `docker compose up keycloak` falla con un mensaje que indica definirla

#### Scenario: Persistencia entre reinicios
- **WHEN** el seed crea las cuentas demo, se ejecuta `docker compose down` (sin `-v`) y luego `docker compose up -d --wait keycloak`
- **THEN** las cuentas demo siguen existiendo en Keycloak

### Requirement: Realm versionado sin secretos
El proyecto SHALL versionar el realm de desarrollo en `infra/keycloak/realm-ultrasist-portal.json` con:
- los realm roles `Administrador`, `Proveedor` y `PMO`;
- el cliente `portal-facturas-web`: confidencial, sólo Standard Flow, PKCE `S256` obligatorio, redirect URIs de `/auth/callback` y post-logout redirect URIs del portal local, y un *mapper* que incluye los realm roles en el ID token;
- el cliente `portal-facturas-admin`: sólo cuenta de servicio, con los roles de `realm-management` `manage-users`, `view-users` y `query-users` y ningún otro;
- la política de contraseñas, la detección de fuerza bruta, los eventos de inicio de sesión y de cambio de contraseña, y los tiempos de sesión SSO.

Los secretos de los clientes SHALL escribirse como marcadores de variables de entorno (`${KEYCLOAK_CLIENT_SECRET}` y `${KEYCLOAK_ADMIN_CLIENT_SECRET}`). El archivo MUST NOT contener secretos, contraseñas ni usuarios.

#### Scenario: Realm sin secretos
- **WHEN** se inspecciona el realm versionado
- **THEN** el `secret` de cada cliente es un marcador `${…}`, no hay arreglo `users` y ningún valor coincide con un secreto del `.env`

#### Scenario: Cuenta de servicio mínima
- **WHEN** se inspecciona el realm versionado
- **THEN** la cuenta de servicio de `portal-facturas-admin` sólo tiene `manage-users`, `view-users` y `query-users` de `realm-management`

#### Scenario: PKCE obligatorio
- **WHEN** se inspecciona el cliente `portal-facturas-web`
- **THEN** tiene `publicClient: false`, `standardFlowEnabled: true`, `implicitFlowEnabled: false`, `directAccessGrantsEnabled: false` y el atributo `pkce.code.challenge.method` igual a `S256`
