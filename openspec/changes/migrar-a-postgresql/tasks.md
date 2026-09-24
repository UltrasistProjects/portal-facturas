> Todas las rutas son relativas a la raíz de la PoC (`PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress-V1/PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress/`). Cada grupo termina con `ruff` limpio. A partir del grupo 5, también con la suite verde sobre PostgreSQL. Trabajar en una rama `feature/migrar-a-postgresql` creada desde `dev`.

## 1. Dependencias e infraestructura local

- [x] 1.1 Añadir `psycopg[binary]==<vigente>` a `requirements.txt`, regenerar `requirements.lock` con `uv pip compile --universal --generate-hashes --python-version 3.12`, instalarlo en `.venv` y ejecutar `pip-audit` sobre el lock y sobre dev (sin avisos).
- [x] 1.2 Crear `compose.yaml` según D2:
  - `name: portal-facturas`;
  - servicio `db` con `postgres:18.<menor>-alpine` fijada;
  - `POSTGRES_PASSWORD` obligatoria;
  - puerto `127.0.0.1:${POSTGRES_PORT:-55432}:5432`;
  - volumen `pgdata:/var/lib/postgresql`, healthcheck `pg_isready` y `restart: unless-stopped`.
- [x] 1.3 Actualizar `.env.example`: `POSTGRES_USER=portal`, `POSTGRES_DB=portal`, `POSTGRES_PORT=55432`, `POSTGRES_PASSWORD=` y `DATABASE_URL=` (ambas generadas), con comentarios. Eliminar la URL de SQLite.
- [x] 1.4 Extender `scripts/create_env.py` (D11):
  - generar `SECRET_KEY` y `POSTGRES_PASSWORD`;
  - armar `DATABASE_URL` desde `POSTGRES_USER`, `POSTGRES_DB` y `POSTGRES_PORT`;
  - ante un `.env` existente, añadir sólo las claves ausentes y reemplazar con aviso un `DATABASE_URL` de SQLite.
- [x] 1.5 Verificar a mano:
  - `docker compose config` (imagen fijada, `host_ip: 127.0.0.1`);
  - `docker compose up -d --wait db` → `healthy`;
  - persistencia tras `down`/`up` sin `-v`;
  - sin `POSTGRES_PASSWORD`, `up` falla con el mensaje.

## 2. Configuración, conexión y tipos

- [x] 2.1 `app/core/config.py`:
  - `database_url` obligatoria, con validador que exige `postgresql+psycopg://` y da un mensaje específico para `sqlite:///`;
  - eliminar `anchored_sqlite_url` y `sqlite_path`.
- [x] 2.2 `app/core/database.py`:
  - engine con `pool_pre_ping=True` y `connect_args={"options": "-c timezone=UTC"}`;
  - eliminar `install_sqlite_pragmas`, `check_same_thread` y la creación de `data/`;
  - `Base.metadata` con `naming_convention` para `fk` y `pk` (D4).
- [x] 2.3 `app/core/types.py`:
  - `ExactNumeric(precision, scale)` sobre `Numeric(asdecimal=True)`, que rechaza en el *bind* los valores con más decimales que la escala;
  - `Money()` = `ExactNumeric(16, 2)`;
  - `UTCDateTime` sobre `DateTime(timezone=True)`, normalizando a UTC al escribir y al leer;
  - eliminar `ScaledDecimal` si queda sin uso.
- [x] 2.4 `app/models/__init__.py`:
  - columnas físicas sin sufijo (`subtotal`, `tax`, `total`, `authorized_amount`, `previous_amount`, `new_amount`, `confidence` con `ExactNumeric(5, 4)`);
  - `CheckConstraint` con los nombres de columna nuevos (`authorized_amount > 0`, `new_amount > 0`, `confidence BETWEEN 0 AND 1`, montos ≥ 0);
  - `JSONB` en `metadata_json`, `evidence_json`, `old_value` y `new_value`.
- [x] 2.5 `app/services/invoice_service.violates(exc, constraint_name)` compara `exc.orig.diag.constraint_name`. Actualizar los llamadores en `routers/invoices.py` a `uq_invoices_supplier_number` y `uq_invoices_uuid`.

## 3. Migraciones

- [x] 3.1 Eliminar `alembic/versions/0001_initial.py` a `0006_user_sessions.py` (quedan en el historial de Git).
- [x] 3.2 `alembic/env.py`: eliminar la rama de SQLite (FKs desactivadas, `foreign_key_check`, `render_as_batch`) y conservar `config.attributes["database_url"]`.
- [x] 3.3 Generar `alembic/versions/0001_postgresql_baseline.py` con autogenerate contra una base PostgreSQL vacía y limpiarlo:
  - operaciones explícitas de las 11 tablas con sus FKs, `UNIQUE`, `CHECK` e índices;
  - tipos `sa.*` y `postgresql.JSONB`, sin imports de `app`;
  - `downgrade` que lanza `NotImplementedError("… Restaure un respaldo.")`.
- [x] 3.4 Verificar sobre una base vacía: `upgrade head` y luego `alembic check` sin diferencias.

## 4. Utilidades de PostgreSQL (`scripts/pgtools.py`)

- [x] 4.1 Conexión y bases temporales:
  - `server_url()`: `TEST_DATABASE_URL`, o `DATABASE_URL` del entorno o de `.env`;
  - `check_server()`, con un mensaje claro si no responde;
  - `create_database(name)` y `drop_database(name)` en `AUTOCOMMIT`, con `WITH (FORCE)`;
  - `temporary_database(prefix)` como context manager.
- [x] 4.2 Herramientas cliente: `dump(database, destination)`, `restore(database, source)`, `list_dump(path)` y `server_version()`. Por defecto (`PG_CLIENT=docker`) ejecutan `docker compose -f <PoC>/compose.yaml exec -T db …`; con `PG_CLIENT=local` usan los binarios del host sobre la URL.

## 5. Pruebas sobre PostgreSQL

- [x] 5.1 `tests/conftest.py` (D8), antes de importar `app`:
  - verificar el servidor (si no responde, `pytest.exit` con el mensaje de `docker compose up -d --wait db`);
  - crear `portal_test_<hex>` y exportar su `DATABASE_URL`;
  - migraciones y seed con contraseñas explícitas;
  - al final, `engine.dispose()` y `drop_database()`.
  
  Guardián: conteo de filas de la base de trabajo (si es alcanzable) y huella de `storage/`, antes y después.
- [x] 5.2 Sustituir `tests/test_sqlite.py` por `tests/test_postgres.py`:
  - FK inexistente → `IntegrityError`;
  - todas las FKs con `confdeltype = 'r'`;
  - `SHOW TimeZone` = `UTC`;
  - lectura inmediata durante una escritura sin confirmar;
  - `EXPLAIN` del listado por proveedor con `enable_seqscan = off` → `ix_invoices_supplier_created`, sin nodo `Sort`.
- [x] 5.3 `tests/test_migraciones.py`:
  - sobre una base temporal adicional, `upgrade head` y `alembic check`;
  - downgrade rechazado sin tocar tablas;
  - la revisión base no contiene `create_all`, `drop_all`, `app.models`, `PRAGMA` ni `sqlite`, y tiene 11 `op.create_table`;
  - eliminar las pruebas de datos heredados de SQLite.
- [x] 5.4 `tests/test_integridad.py`:
  - columnas sin sufijo y `pg_typeof`/`information_schema` (`numeric`, `timestamp with time zone`, `jsonb`);
  - rechazo de `10.005` sin que se guarde `10.01`;
  - mensajes de PostgreSQL en `UNIQUE`, `CHECK` y FK, incluido `CHECK` de `confidence > 1` y de `new_amount <= 0`.
- [x] 5.5 `tests/test_configuracion.py`:
  - URL de SQLite rechazada con el mensaje específico;
  - URL ausente rechazada;
  - `create_env` genera `POSTGRES_PASSWORD` y `DATABASE_URL`;
  - `create_env` completa un `.env` existente sin cambiar sus valores y reemplaza la URL de SQLite;
  - un `.env` completo no cambia;
  - reemplazar la prueba de anclaje de URL de SQLite por la de rutas.
- [x] 5.6 `tests/test_aislamiento.py`: la base de la sesión empieza con `portal_test_` y no es la de trabajo; el almacenamiento está bajo el directorio temporal.
- [x] 5.7 Revisar el resto de la suite en busca de SQL crudo o mensajes propios de SQLite y corregirlos. Suite verde.

## 6. Operación: respaldo, restauración, reinicio y arranque

- [x] 6.1 `scripts/backup.py` (D9):
  - `pg_dump -Fc` mediante `pgtools`, verificado con `list_dump`;
  - `storage.zip`;
  - `manifest.json` con revisión, versión del servidor, fecha UTC y SHA-256;
  - retención.
- [x] 6.2 `scripts/restore_backup.py`:
  - verificación de SHA-256 y `--yes`;
  - respaldo de seguridad sin poda;
  - `pg_restore --clean --if-exists --single-transaction --no-owner`;
  - reemplazo de `storage/` con la protección contra zip slip.
- [x] 6.3 `scripts/reset_demo.py` (D10):
  - se niega en `production` y con host no local;
  - detecta datos no-demo con SQL y exige confirmación o `--yes`;
  - respalda, ejecuta `DROP SCHEMA public CASCADE; CREATE SCHEMA public`, vacía `storage/` dentro del workspace, migra y siembra;
  - eliminar el manejo de `-wal`/`-shm`.
- [x] 6.4 `scripts/init_db.py`: mensaje claro si PostgreSQL no responde. `run_local.{sh,ps1,bat}`: `create_env` → `docker compose up -d --wait db` → `init_db` → uvicorn. Actualizar `ejecucion.txt`.
- [x] 6.5 `scripts/check.py`: `alembic check` sobre una base temporal de `pgtools` que se elimina al terminar, aunque el paso falle.
- [x] 6.6 Pruebas en `tests/test_respaldos.py`:
  - respaldo con una escritura sin confirmar (el volcado no la incluye y `pg_restore --list` lo lee);
  - retención de 14;
  - manifiesto alterado → aborta sin cambios;
  - restauración completa en una base temporal → datos y `storage/` iguales y documentos descargables;
  - zip slip rechazado;
  - `reset_demo` en subproceso con una base temporal: sin terminal ni `--yes` aborta; con `--yes` respalda y reconstruye; host no local y `production` se rechazan.

## 7. Documentación y verificación final

- [x] 7.1 Actualizar el README:
  - requisito de Docker (Desktop o Podman) y puerto 55432 configurable;
  - instalación y arranque con `docker compose`;
  - variables `POSTGRES_*`, `DATABASE_URL` y `TEST_DATABASE_URL`/`PG_CLIENT`;
  - migraciones desde `0001_postgresql_baseline`;
  - respaldo y restauración con `pg_dump`/`pg_restore`;
  - pruebas que requieren el contenedor;
  - nota sobre `data/invoice_portal.db` obsoleto;
  - eliminar las menciones a SQLite, WAL y centavos.
- [x] 7.2 Medir la cobertura y ajustar `--cov-fail-under` al valor medido redondeado hacia abajo (mínimo 80).
- [x] 7.3 Verificación final:
  - `openspec validate migrar-a-postgresql --strict`;
  - `python scripts/check.py` completo;
  - no quedan bases `portal_test_*` en el servidor;
  - `grep -ri sqlite app scripts alembic` sin usos funcionales;
  - prueba de humo en Chromium con `run_local` (tres roles: alta, carga, prevalidación, descarga, revisión, enmienda) sin violaciones de CSP;
  - respaldo y restauración reales sobre la base de trabajo.
- [x] 7.4 Commits por grupo en `feature/migrar-a-postgresql` y resumen para el PR, que incluye la Open Question de CI de `design.md`.
