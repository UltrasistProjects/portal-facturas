# configuracion-entorno Specification

## Purpose
Configuración segura por entorno (`SECRET_KEY`, `DEBUG`, `APP_ENV`, conexión con Keycloak), rutas ancladas a la raíz del proyecto y verificaciones de arranque que impiden operar con valores inseguros.
## Requirements
### Requirement: SECRET_KEY obligatoria y robusta
El sistema SHALL negarse a arrancar si `SECRET_KEY` no está definida, si tiene menos de 32 caracteres o si comienza con el prefijo de placeholder `change-me`. La configuración MUST NOT contener ningún valor por defecto para `SECRET_KEY` ni en el código ni en `.env.example`.

`scripts/create_env.py` SHALL generar valores aleatorios para:
- `SECRET_KEY` y `POSTGRES_PASSWORD`;
- `KEYCLOAK_CLIENT_SECRET` y `KEYCLOAK_ADMIN_CLIENT_SECRET`;
- `KC_BOOTSTRAP_ADMIN_PASSWORD`;
- `DEMO_PASSWORD`, que cumple la política de contraseñas.

Además SHALL:
- escribir `DATABASE_URL` con las credenciales de PostgreSQL y `POSTGRES_PORT`;
- escribir `KEYCLOAK_SERVER_URL` y `KEYCLOAK_REALM` del entorno local;
- ante un `.env` existente, añadir sólo las claves ausentes sin cambiar los valores presentes, salvo un `DATABASE_URL` de SQLite, que reemplaza avisándolo.

#### Scenario: Arranque sin SECRET_KEY
- **WHEN** la aplicación se inicia sin `SECRET_KEY` en el entorno ni en `.env`
- **THEN** el arranque falla con un error de configuración que indica que `SECRET_KEY` es obligatoria y cómo generarla (`secrets.token_urlsafe(64)`)

#### Scenario: Placeholder rechazado
- **WHEN** `SECRET_KEY=change-me-use-a-long-random-value`
- **THEN** el arranque falla con un error que identifica el valor como placeholder inseguro

#### Scenario: Clave demasiado corta
- **WHEN** `SECRET_KEY` tiene 31 caracteres
- **THEN** el arranque falla indicando la longitud mínima de 32

#### Scenario: Generación del .env local
- **WHEN** un script de arranque local (`run_local.*`) se ejecuta y no existe `.env`
- **THEN** se crea `.env` a partir de `.env.example` con `SECRET_KEY`, `POSTGRES_PASSWORD`, los dos secretos de Keycloak, `KC_BOOTSTRAP_ADMIN_PASSWORD` y `DEMO_PASSWORD` aleatorios, y con `DATABASE_URL` y `KEYCLOAK_SERVER_URL` coherentes con ellos

#### Scenario: .env existente se completa sin sobrescribir
- **WHEN** existe un `.env` con `SECRET_KEY` propia, sin `POSTGRES_PASSWORD` ni claves de Keycloak y con `DATABASE_URL` de SQLite, y se ejecuta `scripts/create_env.py`
- **THEN** `SECRET_KEY` y las demás claves conservan su valor; se añaden `POSTGRES_PASSWORD`, las claves de PostgreSQL y de Keycloak ausentes; y `DATABASE_URL` se reemplaza por la de PostgreSQL con un aviso en consola

#### Scenario: .env ya completo
- **WHEN** existe un `.env` que ya contiene todas las claves y se ejecuta `scripts/create_env.py`
- **THEN** el archivo permanece sin cambios

### Requirement: Modo debug desacoplado del manejo de errores
El sistema MUST NOT pasar `debug=True` a `FastAPI(...)` bajo ninguna configuración. `DEBUG` SHALL valer `false` por defecto y su único efecto SHALL ser elevar el nivel de log a `DEBUG`.

#### Scenario: Excepción no manejada con DEBUG activo
- **WHEN** `DEBUG=true` y una petición provoca una excepción no manejada
- **THEN** la respuesta es la página de error genérica con HTTP 500, sin traceback, código fuente ni variables locales, y la traza completa queda registrada en el log

#### Scenario: Valor por defecto
- **WHEN** la variable `DEBUG` no está definida
- **THEN** el sistema opera con `debug = false`

### Requirement: APP_ENV gobierna los valores por defecto
`APP_ENV` SHALL aceptar únicamente `development`, `test` o `production`; cualquier otro valor MUST impedir el arranque. `SESSION_HTTPS_ONLY` SHALL valer `true` por defecto cuando `APP_ENV` sea distinto de `development`.

#### Scenario: Valor de entorno desconocido
- **WHEN** `APP_ENV=prod`
- **THEN** el arranque falla indicando los valores permitidos

#### Scenario: Cookie segura por defecto en producción
- **WHEN** `APP_ENV=production` y `SESSION_HTTPS_ONLY` no está definida
- **THEN** la cookie de sesión se emite con el atributo `Secure`

### Requirement: Verificaciones de seguridad al arranque fuera de desarrollo
Cuando `APP_ENV` sea `production`, el sistema SHALL abortar el arranque si detecta alguna condición insegura:
- usuarios activos con correo `@poc.local`;
- `SESSION_HTTPS_ONLY=false`;
- `MAIL_BACKEND=file`, porque los correos no se enviarían y quedarían escritos en disco;
- `SMTP_SECURITY=none`, porque las credenciales y los correos viajarían sin cifrar.

#### Scenario: Usuario demo activo en producción
- **WHEN** `APP_ENV=production` y existe un usuario activo `admin@poc.local`
- **THEN** el arranque falla con un mensaje que lista las cuentas demo activas a deshabilitar

#### Scenario: Cookie sin Secure en producción
- **WHEN** `APP_ENV=production` y `SESSION_HTTPS_ONLY=false`
- **THEN** el arranque falla indicando que en producción la cookie debe ser `Secure`

#### Scenario: Transporte de archivo en producción
- **WHEN** `APP_ENV=production` y `MAIL_BACKEND=file`
- **THEN** el arranque falla indicando que en producción los correos deben enviarse por SMTP

#### Scenario: SMTP sin cifrar en producción
- **WHEN** `APP_ENV=production`, `MAIL_BACKEND=smtp` y `SMTP_SECURITY=none`
- **THEN** el arranque falla indicando que en producción la conexión SMTP debe cifrarse

#### Scenario: Desarrollo no aplica verificaciones de producción
- **WHEN** `APP_ENV=development` y existen usuarios `@poc.local`
- **THEN** la aplicación arranca normalmente

### Requirement: Rutas ancladas al directorio del proyecto
Todas las rutas de la aplicación (`.env`, `storage/`, `logs/`, `backups/`, `app/static`, `app/templates`) SHALL resolverse contra la raíz del proyecto y MUST NOT depender del directorio de trabajo actual. Las rutas relativas provistas por configuración SHALL interpretarse relativas a la raíz del proyecto.

#### Scenario: Arranque desde otro directorio
- **WHEN** la aplicación se inicia con el directorio de trabajo fuera de la raíz del proyecto
- **THEN** usa el mismo `.env`, almacenamiento, logs y recursos estáticos que al iniciarse desde la raíz, y no crea archivos en el directorio de trabajo

#### Scenario: Ruta relativa en configuración
- **WHEN** `STORAGE_PATH=./storage` y el directorio de trabajo es distinto de la raíz
- **THEN** el almacenamiento resuelto es `<raíz del proyecto>/storage`

### Requirement: Base de datos PostgreSQL obligatoria
`DATABASE_URL` SHALL ser obligatoria y SHALL usar el esquema `postgresql+psycopg://`. Una URL ausente o de otro motor (en particular `sqlite:///`) MUST impedir el arranque, con un mensaje que remita a `scripts/create_env.py`.

#### Scenario: URL de SQLite heredada
- **WHEN** `.env` contiene `DATABASE_URL=sqlite:///./data/invoice_portal.db`
- **THEN** el arranque falla indicando que SQLite ya no es compatible y que `python scripts/create_env.py` actualiza el `.env`

#### Scenario: URL ausente
- **WHEN** `DATABASE_URL` no está definida
- **THEN** el arranque falla indicando que es obligatoria

### Requirement: Transporte de correo configurable por entorno
El transporte de correo SHALL configurarse con variables de entorno:
- `MAIL_BACKEND`: `smtp` o `file`; sin definir, `smtp` si `APP_ENV=production` y `file` en los demás entornos;
- `MAIL_FROM`: remitente de los correos; obligatorio con `smtp`, y con `file` toma por omisión "Portal de Proveedores ULTRASIST <no-reply@portal.local>";
- `MAIL_OUTBOX_DIR`: directorio donde el transporte `file` escribe cada correo como archivo `.eml`; por omisión `./outbox`, relativo a la raíz del proyecto;
- `SMTP_HOST`: obligatorio con `smtp`;
- `SMTP_PORT`: por omisión 587;
- `SMTP_SECURITY`: `starttls`, `ssl` o `none`; por omisión `starttls`;
- `SMTP_USERNAME` y `SMTP_PASSWORD`: opcionales; si hay usuario, el transporte inicia sesión;
- `SMTP_TIMEOUT`: segundos de espera, de 1 a 120; por omisión 10.

Un valor fuera de su dominio, o la falta de `SMTP_HOST` o `MAIL_FROM` con `smtp`, MUST impedir el arranque con un mensaje que nombre la variable. El transporte `file` MUST NOT enviar correos.

#### Scenario: Valores por omisión fuera de producción
- **WHEN** `APP_ENV=development` y no se define ninguna variable de correo
- **THEN** el transporte es `file`, el directorio de salida es `<raíz del proyecto>/outbox` y el remitente es "Portal de Proveedores ULTRASIST <no-reply@portal.local>"

#### Scenario: SMTP sin servidor
- **WHEN** `MAIL_BACKEND=smtp`, `MAIL_FROM` está definido y `SMTP_HOST` no
- **THEN** el arranque falla indicando que `SMTP_HOST` es obligatoria con `MAIL_BACKEND=smtp`

#### Scenario: SMTP sin remitente
- **WHEN** `MAIL_BACKEND=smtp`, `SMTP_HOST` está definido y `MAIL_FROM` no
- **THEN** el arranque falla indicando que `MAIL_FROM` es obligatoria con `MAIL_BACKEND=smtp`

#### Scenario: Cifrado desconocido
- **WHEN** `SMTP_SECURITY=tls`
- **THEN** el arranque falla indicando los valores permitidos

### Requirement: Configuración de Keycloak obligatoria
El sistema SHALL leer la conexión con Keycloak de estas variables:

| Variable | Por omisión | Regla |
|---|---|---|
| `KEYCLOAK_SERVER_URL` | ninguno | obligatoria |
| `KEYCLOAK_REALM` | ninguno | obligatoria |
| `KEYCLOAK_CLIENT_ID` | `portal-facturas-web` | — |
| `KEYCLOAK_CLIENT_SECRET` | ninguno | obligatoria |
| `KEYCLOAK_ADMIN_CLIENT_ID` | `portal-facturas-admin` | — |
| `KEYCLOAK_ADMIN_CLIENT_SECRET` | ninguno | obligatoria |
| `KEYCLOAK_TIMEOUT` | 10 | segundos, de 1 a 60 |

Los secretos MUST NOT tener valor por defecto en el código ni en `.env.example`. El sistema SHALL negarse a arrancar, con un mensaje que nombre la variable, si:
- falta una variable obligatoria;
- un secreto tiene menos de 32 caracteres o empieza con `change-me`;
- `APP_ENV=production` y `KEYCLOAK_SERVER_URL` no usa `https://`.

Los secretos MUST NOT mostrarse en pantallas, mensajes de error ni en el log.

#### Scenario: Arranque sin secreto del cliente
- **WHEN** la aplicación se inicia sin `KEYCLOAK_CLIENT_SECRET`
- **THEN** el arranque falla indicando que `KEYCLOAK_CLIENT_SECRET` es obligatoria

#### Scenario: Secreto de ejemplo
- **WHEN** `KEYCLOAK_ADMIN_CLIENT_SECRET=change-me-keycloak-admin-secret-value`
- **THEN** el arranque falla identificando el valor como placeholder inseguro

#### Scenario: Keycloak sin TLS en producción
- **WHEN** `APP_ENV=production` y `KEYCLOAK_SERVER_URL=http://keycloak:8080`
- **THEN** el arranque falla indicando que en producción Keycloak debe usarse por HTTPS

#### Scenario: .env.example sin secretos
- **WHEN** se inspecciona `.env.example`
- **THEN** `KEYCLOAK_CLIENT_SECRET`, `KEYCLOAK_ADMIN_CLIENT_SECRET`, `KC_BOOTSTRAP_ADMIN_PASSWORD` y `DEMO_PASSWORD` aparecen sin valor

