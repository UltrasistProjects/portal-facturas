## Why

El portal sigue sobre SQLite: un único archivo, un solo escritor a la vez y sin tipo decimal nativo. La remediación de la auditoría dejó el código preparado para cambiar de motor (montos detrás de un tipo propio, restricciones en los modelos), pero el destino de la base de datos quedó como pregunta abierta. Se decide ahora: **PostgreSQL local, ejecutado con Docker Compose**. Es el paso previo al MVP (sprint al 2026-09-30) y elimina las limitaciones de concurrencia y de tipos de SQLite antes de que crezca el modelo de datos.

## What Changes

- **Infraestructura local:** un `compose.yaml` en la raíz de la PoC levanta PostgreSQL 18 con las siguientes características:
  - volumen persistente y healthcheck;
  - puerto publicado sólo en `127.0.0.1` (por defecto 55432, configurable con `POSTGRES_PORT`; en este equipo el 5432 y el 5433 ya están ocupados);
  - credenciales tomadas de `.env`.
- **BREAKING** PostgreSQL pasa a ser el **único** motor soportado. `DATABASE_URL` debe ser `postgresql+psycopg://…`, y una URL de SQLite impide arrancar con un mensaje que indica cómo migrar el `.env`.
- **BREAKING** (esquema) Tipos nativos de PostgreSQL:
  - montos en `NUMERIC(16,2)` y confianza en `NUMERIC(5,4)`, con columnas sin sufijo `_cents`/`_bp`;
  - fechas-hora en `TIMESTAMPTZ`;
  - JSON en `JSONB`.
  
  Se conservan todas las garantías de la remediación: sin redondeo silencioso, UNIQUE fiscales, CHECKs, FKs `ON DELETE RESTRICT`, UTC y prohibición de borrado físico.
- **BREAKING** Migraciones: la cadena `0001`–`0006`, escrita para SQLite (PRAGMAs, `group_concat`, batch), se retira. Una nueva revisión base `0001_postgresql_baseline` describe el esquema completo de forma explícita, y la regla de una revisión por cambio de modelo continúa desde ella.
- **BREAKING** Sin traslado automático de datos: las BD SQLite existentes sólo contienen datos demo sintéticos. La demo se reconstruye en PostgreSQL con el seed.
- **Respaldo y restauración:** `pg_dump -Fc` / `pg_restore`, ejecutados dentro del contenedor (el `pg_dump` 16 del host no puede respaldar un servidor 18). Se mantienen el manifiesto SHA-256, `storage.zip`, la retención y las confirmaciones.
- **Scripts:**
  - `create_env.py` genera también `POSTGRES_PASSWORD` y `DATABASE_URL`, y completa un `.env` existente sin tocar sus demás valores;
  - `run_local.*` levantan el contenedor antes de migrar;
  - `reset_demo.py` recrea el esquema en lugar de borrar un archivo y sólo actúa sobre servidores locales.
- **Pruebas:** cada sesión de `pytest` crea una base temporal `portal_test_<aleatorio>` en el servidor dockerizado y la elimina al terminar. Las pruebas específicas de SQLite (PRAGMAs, WAL, migración de datos heredados) se sustituyen por equivalentes de PostgreSQL. `scripts/check.py` usa el mismo mecanismo.
- **Dependencias:** se añade `psycopg[binary]` (v3) al lock universal y se audita con `pip-audit`.

**Fuera de alcance:**
- contenerizar la aplicación (sólo la base de datos va en Docker);
- Azure SQL o PostgreSQL gestionado;
- herramienta de traslado de datos SQLite → PostgreSQL;
- búsqueda sin acentos (`unaccent`);
- réplicas, PITR y tuning de PostgreSQL.

## Capabilities

### New Capabilities
- `infraestructura-local`: servicio PostgreSQL dockerizado con Docker Compose: versión fijada, sólo en localhost, credenciales desde `.env`, volumen persistente y healthcheck.

### Modified Capabilities
- `integridad-datos`:
  - la integridad referencial la enforza el motor, sin PRAGMAs;
  - desaparece la configuración de concurrencia de SQLite (queda la conexión a PostgreSQL con zona UTC y `pool_pre_ping`);
  - montos en `NUMERIC` sin redondeo silencioso;
  - plan de consulta verificado con `EXPLAIN` de PostgreSQL;
  - fechas en `TIMESTAMPTZ`.
- `migraciones-esquema`:
  - la revisión inicial pasa a ser la base explícita de PostgreSQL;
  - se retira la migración de datos 0004 y sus precondiciones de SQLite.
- `respaldo-y-distribucion`:
  - respaldo y restauración con `pg_dump`/`pg_restore` desde el contenedor;
  - reinicio de demo que recrea el esquema, sólo en servidores locales y sin archivos `-wal`/`-shm`.
- `configuracion-entorno`:
  - `DATABASE_URL` de PostgreSQL obligatoria;
  - `.env` con credenciales de PostgreSQL generadas;
  - rutas ancladas sin BD SQLite.
- `calidad-y-pruebas`:
  - pruebas sobre una base PostgreSQL temporal por sesión;
  - cobertura de migraciones sobre la base de PostgreSQL.
- `almacenamiento-documentos`: se retira el escenario de migración de rutas absolutas heredadas (propio de la cadena SQLite).
- `trazabilidad-contratos`: se retira el escenario de contratos preexistentes sin campos de auditoría (propio de la cadena SQLite).

## Impact

- **Código:**
  - `app/core/config.py`, `app/core/database.py`, `app/core/types.py`, `app/models/__init__.py` (tipos y nombres de columnas);
  - `app/services/invoice_service.py` (`violates()` por nombre de restricción);
  - `alembic/` (env y nueva base; se eliminan `0001`–`0006`);
  - `scripts/` (`create_env`, `init_db`, `reset_demo`, `backup`, `restore_backup`, `check` y un módulo nuevo de utilidades de PostgreSQL);
  - `run_local.*`, `tests/`, `README.md` y `.env.example`.
- **Archivos nuevos:** `compose.yaml`.
- **Dependencias:** `psycopg[binary]`; `requirements.lock` regenerado.
- **Requisitos de entorno:** Docker con Compose v2 para desarrollo y pruebas. `pytest` y `scripts/check.py` necesitan el contenedor en marcha o un `TEST_DATABASE_URL` alcanzable.
- **CI:** el pipeline compartido (`calidad.yml`, runner self-hosted) necesitará un PostgreSQL alcanzable para `pytest` (ver Open Questions en `design.md`).
- **Datos:** `data/invoice_portal.db` deja de usarse y puede borrarse; la demo se recrea con `init_db.py`.
