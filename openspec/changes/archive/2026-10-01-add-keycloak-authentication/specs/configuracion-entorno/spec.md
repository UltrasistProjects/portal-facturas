## ADDED Requirements

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

## MODIFIED Requirements

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
