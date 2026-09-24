## Context

La remediación de la auditoría (archivada en `openspec/changes/archive/2026-09-24-remediar-auditoria-tecnica/`) dejó el portal sobre SQLite con garantías fuertes: montos exactos, `UNIQUE` fiscales, `CHECK`, FKs `RESTRICT`, UTC, sesiones revocables y respaldos verificables. También dejó abierta la pregunta del motor definitivo. La decisión es **PostgreSQL local, dockerizado con Docker Compose**; sólo la base de datos va en un contenedor, la aplicación sigue corriendo en el host.

**Acoplamiento actual con SQLite:**
- **Aplicación:**
  - `app/core/database.py`: PRAGMAs, `check_same_thread`, creación del directorio `data/`;
  - `app/core/config.py`: `sqlite_path` y anclaje de la URL `sqlite:///`;
  - `app/core/types.py`: montos como enteros escalados;
  - `app/services/invoice_service.violates()`, que lee el mensaje de error de SQLite.
- **Migraciones:** `alembic/env.py` (FKs desactivadas y `foreign_key_check`) y la revisión `0004` (`PRAGMA foreign_key_check`, `group_concat` y batch con nombres de FK inventados). Esta cadena no puede ejecutarse sobre PostgreSQL.
- **Scripts:**
  - `backup.py` y `restore_backup.py`, con la API de respaldo de `sqlite3`;
  - `reset_demo.py`, que borra el archivo y sus `-wal`/`-shm`;
  - `check.py`, que corre `alembic check` sobre un SQLite temporal.
- **Pruebas:**
  - `test_sqlite.py`, `test_migraciones.py` (datos heredados), `test_respaldos.py`;
  - SQL crudo con `typeof()` y columnas `*_cents` en `test_integridad.py`;
  - `conftest.py`, que crea un SQLite temporal.

**Hechos verificados en este equipo:**
- Docker Desktop 29.6 y Compose v5.3 están disponibles.
- El puerto 5432 lo ocupa un PostgreSQL 16 del sistema y el 5433 un contenedor `cacao-db`.
- El `pg_dump` del host es la versión 16 y se niega a respaldar un servidor más nuevo.
- También corre un contenedor SonarQube.

**Restricciones:**
- Todos los datos existentes son demo sintéticos.
- El sprint del MVP cierra el 2026-09-30.
- El CI es el pipeline compartido del equipo (`calidad.yml`) y no se duplica en el repositorio.

## Goals / Non-Goals

**Goals:**
- PostgreSQL 18 dockerizado como único motor, con arranque local de un comando (`run_local`) y datos persistentes.
- Conservar todas las garantías de integridad de la remediación, usando tipos nativos de PostgreSQL.
- Historial de migraciones limpio y explícito para PostgreSQL.
- Respaldos, restauración, reinicio de demo, pruebas y `scripts/check.py` funcionando sobre PostgreSQL.

**Non-Goals:**
- Contenerizar la aplicación.
- Azure SQL, PostgreSQL gestionado, réplicas, PITR y tuning.
- Soporte simultáneo de SQLite y PostgreSQL.
- Herramienta de traslado de datos SQLite → PostgreSQL.
- Búsqueda sin acentos (`unaccent`).

## Decisions

### D1. PostgreSQL como único motor; SQLite se retira
`DATABASE_URL` SHALL ser `postgresql+psycopg://`. Una URL de SQLite falla al arrancar con un mensaje que remite a `create_env.py`.

*Alternativa descartada:* soportar ambos motores. Duplicaría migraciones (dialectos distintos), pruebas y scripts de operación, a cambio de conservar datos que son sólo demo.

### D2. Servicio `db` en `compose.yaml`
```yaml
name: portal-facturas
services:
  db:
    image: postgres:18.<menor>-alpine      # menor vigente fijada al implementar
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-portal}
      POSTGRES_DB: ${POSTGRES_DB:-portal}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?Defina POSTGRES_PASSWORD en .env (python scripts/create_env.py)}
    ports: ["127.0.0.1:${POSTGRES_PORT:-55432}:5432"]
    volumes: ["pgdata:/var/lib/postgresql"]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $${POSTGRES_USER} -d $${POSTGRES_DB}"]
      interval: 5s
      retries: 10
    restart: unless-stopped
volumes:
  pgdata:
```
- **Nombre de proyecto fijo:** da nombres estables al volumen y al contenedor y los separa de `cacao-db` y SonarQube.
- **Puerto 55432:** propio del proyecto y configurable; sólo en `127.0.0.1`.
- **Volumen en `/var/lib/postgresql`:** desde la versión 18, la imagen oficial ubica `PGDATA` en `/var/lib/postgresql/18/docker` y recomienda montar ese directorio padre.
- **Credenciales:** Compose lee `.env` desde la raíz de la PoC, el mismo archivo que usa la aplicación.

### D3. Driver y engine
- **Driver:** `psycopg[binary]` (v3), con wheels para Windows, Linux y macOS, compatible con el lock universal.
- **Engine:** `create_engine(url, pool_pre_ping=True, connect_args={"options": "-c timezone=UTC"})`.
- **Limpieza:** se eliminan `install_sqlite_pragmas`, `check_same_thread`, la creación de `data/`, `Settings.sqlite_path` y el anclaje de rutas `sqlite:///`.

### D4. Tipos nativos con las mismas garantías

| Tipo | Implementación |
|---|---|
| Montos | `ExactNumeric(16, 2)`: `TypeDecorator` sobre `Numeric(16, 2, asdecimal=True)`. Reutiliza la validación de escala de `ScaledDecimal` y rechaza en el *bind* un valor con más decimales, porque PostgreSQL redondearía `10.005` a `10.01` en silencio. |
| Nombres de columna | Las físicas vuelven a `subtotal`, `tax`, `total`, `authorized_amount`, `previous_amount`, `new_amount` y `confidence`. Los atributos ORM no cambian. |
| Confianza | `ExactNumeric(5, 4)`, con `CHECK (confidence BETWEEN 0 AND 1)`. |
| Fechas | `UTCDateTime` pasa a `DateTime(timezone=True)` (`TIMESTAMPTZ`). Al escribir: naive → UTC, aware → `astimezone(UTC)`. Al leer: `astimezone(UTC)`. |
| JSON | `postgresql.JSONB` en `metadata_json`, `evidence_json`, `old_value` y `new_value`. |
| Enumeraciones | Siguen siendo `VARCHAR` + `CHECK` (`native_enum=False`). Añadir un valor no exige `ALTER TYPE`, y el comportamiento es idéntico al actual. |
| Nombres de restricciones | `Base.metadata` recibe una `naming_convention` para `fk` (`fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s`) y `pk` (`pk_%(table_name)s`). Así los nombres son deterministas en cualquier servidor y útiles para migraciones futuras. `UNIQUE` y `CHECK` ya tienen nombre explícito. |

*Alternativa:* conservar enteros en centavos (`BIGINT`). También es exacto, pero en PostgreSQL `NUMERIC` es decimal real: el SQL directo, los reportes y las herramientas de BI leen montos en pesos sin escalar. Ya lo anticipaba la D2 del diseño anterior.

### D5. Nueva base de migraciones para PostgreSQL
- **Base nueva:** `0001_postgresql_baseline` se genera con autogenerate contra una base PostgreSQL vacía y se limpia a mano: tipos `sa.*` y `postgresql.JSONB`, sin imports de `app`. Su `downgrade` lanza `NotImplementedError`.
- **Cadena retirada:** `0001_initial` a `0006_user_sessions` se eliminan de `alembic/versions/` y se conservan en el historial de Git.
- **`env.py`:** pierde la rama de SQLite (PRAGMAs, `foreign_key_check`, `render_as_batch`). Conserva `config.attributes["database_url"]`.
- **Regla vigente:** una revisión por cambio de modelo desde la nueva base, más `alembic check` en `check.py`.

*Alternativa descartada:* volver portable la cadena existente. Habría que editar revisiones publicadas (la `0004` usa `PRAGMA`, `group_concat` y nombres de FK que en PostgreSQL no existen) sólo para ejecutar conversiones de datos que en PostgreSQL no tienen sentido: las columnas nacen ya con su tipo final.

### D6. Detección de restricciones por nombre
`violates(exc, "uq_invoices_uuid")` compara `exc.orig.diag.constraint_name`, que psycopg expone, en lugar de buscar texto en el mensaje de error. Los llamadores pasan a usar `uq_invoices_uuid` y `uq_invoices_supplier_number`.

### D7. Utilidades de PostgreSQL compartidas (`scripts/pgtools.py`)
Un solo módulo para scripts y pruebas:
- **Bases temporales:** `server_url()` toma `TEST_DATABASE_URL` o, si no existe, el `DATABASE_URL` del entorno o de `.env`. `create_database(name)` y `drop_database(name)` usan `AUTOCOMMIT` y `DROP DATABASE … WITH (FORCE)`.
- **Herramientas cliente:** `dump(db, destino)`, `restore(db, origen)`, `list_dump(archivo)` y `server_version()`.
- **Modo de ejecución:** con `PG_CLIENT=docker` (por defecto), `pg_dump`/`pg_restore` corren con `docker compose -f <PoC>/compose.yaml exec -T db …`: la misma versión que el servidor, autenticación local por socket y sin clientes en el host. Con `PG_CLIENT=local` usan los binarios del host sobre la URL; sirve para un CI con servicio PostgreSQL.

### D8. Pruebas sobre una base temporal por sesión
- **Arranque de la sesión:** antes de importar `app`, `conftest.py`:
  1. obtiene la URL del servidor (D7) y verifica la conexión; si falla, ejecuta `pytest.exit` con el mensaje "levante `docker compose up -d --wait db` o defina `TEST_DATABASE_URL`";
  2. crea `portal_test_<hex>` y exporta su `DATABASE_URL`;
  3. al final de la sesión, `engine.dispose()` y `drop_database()`.
- **Guardián:** la base de la sesión empieza con `portal_test_` y no es la de trabajo. Si la base de trabajo es alcanzable, se toma el conteo de filas por tabla antes y después. `storage/` del proyecto se compara igual que hoy.
- **Pruebas que se sustituyen:**
  - `test_sqlite.py` → `test_postgres.py`: FK inexistente, `confdeltype = 'r'`, `SHOW TimeZone`, lectura bajo escritura y `EXPLAIN` con `enable_seqscan = off`;
  - `test_migraciones.py`: base temporal adicional → `upgrade head`, `alembic check` y downgrade rechazado. Las pruebas de datos heredados se eliminan;
  - `test_respaldos.py`: `pg_dump`/`pg_restore` con bases temporales. `reset_demo` se prueba en subproceso contra otra base temporal;
  - SQL crudo y mensajes de error con los textos de PostgreSQL (`violates unique constraint "uq_invoices_uuid"`, `violates check constraint`, `violates foreign key constraint`) y `pg_typeof()`.

### D9. Respaldo y restauración
- **Contenido de `backups/<stamp>/`:** `<db>.dump` (`pg_dump -Fc`, instantánea transaccional consistente con la app en marcha), `storage.zip` y `manifest.json` (revisión Alembic, versión del servidor, fecha UTC, SHA-256).
- **Verificación:** `pg_restore --list`.
- **Restauración:** verifica hashes, exige `--yes`, genera un respaldo de seguridad sin poda y ejecuta `pg_restore --clean --if-exists --single-transaction --no-owner`. Si algo falla no queda nada a medias. Después reemplaza `storage/` con la protección contra zip slip existente.
- **Requisito:** la aplicación debe estar detenida, porque `--clean` necesita bloquear las tablas. Se documenta.

### D10. `reset_demo.py`, `init_db.py` y `run_local`
- **`reset_demo`:**
  - se niega con `APP_ENV=production` o con un host no local (`localhost`, `127.0.0.1`, `::1`);
  - detecta datos no-demo con las mismas consultas y exige confirmación o `--yes`;
  - respalda, ejecuta `DROP SCHEMA public CASCADE; CREATE SCHEMA public` y vacía `storage/` dentro del workspace;
  - aplica las migraciones y siembra.
- **`init_db`:** si la base no responde, falla con el mensaje de D8.
- **`run_local.{sh,ps1,bat}`:** `create_env` → `docker compose up -d --wait db` → `init_db` → uvicorn.

### D11. `create_env.py` y configuración
- **Claves generadas:** `SECRET_KEY` y `POSTGRES_PASSWORD` (`secrets.token_urlsafe`, seguras dentro de una URL). `DATABASE_URL` se arma a partir de `POSTGRES_USER`, `POSTGRES_DB` y `POSTGRES_PORT`.
- **`.env` existente:** se añaden sólo las claves ausentes. Un `DATABASE_URL` de SQLite se reemplaza con aviso. Lo demás no se toca (spec `configuracion-entorno`).
- **`Settings`:** `database_url` obligatoria, con un validador que rechaza URLs que no sean `postgresql+psycopg://` y da un mensaje específico para SQLite.

### D12. Dependencias
- **Runtime:** `psycopg[binary]==<versión vigente>` en `requirements.txt`.
- **Lock:** se regenera con `uv pip compile --universal --generate-hashes`. `pip-audit` debe quedar sin avisos.

## Risks / Trade-offs

- **[Docker pasa a ser requisito para desarrollar y probar]** → `run_local` lo levanta solo. El README documenta Docker Desktop (Windows y macOS) y la compatibilidad con Podman. `TEST_DATABASE_URL` permite usar otro servidor.
- **[El pipeline compartido de CI necesitará PostgreSQL para `pytest`]** → `TEST_DATABASE_URL` y `PG_CLIENT=local` permiten un servicio PostgreSQL en el runner, o Docker en el runner self-hosted. Queda como Open Question: mientras no se resuelva, `pytest` fallará en `calidad.yml` con el mensaje de D8.
- **[Conflictos de puerto con otras instancias del equipo]** → puerto propio 55432 configurable; enlace sólo a `127.0.0.1`.
- **[Redondeo silencioso de `NUMERIC` en PostgreSQL]** → validación en el *bind* de `ExactNumeric`, cubierta por prueba.
- **[Diferencias de semántica]** → la suite completa corre sobre PostgreSQL. Casos concretos:
  - `ILIKE` también ignora mayúsculas fuera de ASCII (mejora);
  - `JSONB` no preserva el orden de las claves (sólo afecta la vista de auditoría);
  - `TIMESTAMPTZ` se normaliza por `UTCDateTime` y por la sesión en UTC.
- **[Se pierde el historial de migraciones SQLite en el árbol]** → queda en Git y en el change archivado. Nadie depende de él: no hay bases SQLite a migrar.
- **[Desfase de versión de `pg_dump`]** → las herramientas corren dentro del contenedor (`PG_CLIENT=docker`).
- **[Pruebas más lentas]** → la base se crea una vez por sesión; la creación de bases temporales en `check.py` y en `test_respaldos` se mide y se mantiene acotada.

## Migration Plan

1. Actualizar el código e instalar dependencias: `pip install --require-hashes -r requirements.lock` más dev.
2. `python scripts/create_env.py`: completa `.env` con `POSTGRES_*` y reemplaza el `DATABASE_URL` de SQLite.
3. `docker compose up -d --wait db`.
4. `python scripts/init_db.py`: aplica `0001_postgresql_baseline` y siembra la demo.
5. Arrancar la aplicación (`run_local` hace los pasos 2 a 5).
6. `data/invoice_portal.db` queda sin uso; puede conservarse o borrarse.

**Rollback:** volver a la versión anterior del código y restaurar en `.env` el `DATABASE_URL` de SQLite. El archivo SQLite no se toca, así que el rollback es inmediato. El volumen `pgdata` se elimina con `docker compose down -v` si se descarta PostgreSQL.

## Open Questions

1. **CI:** ¿el runner self-hosted de `calidad.yml` tiene Docker para levantar `db`, o se configura un servicio PostgreSQL con `TEST_DATABASE_URL` y `PG_CLIENT=local`? Lo decide el equipo dueño del pipeline compartido.
2. **Versión menor de `postgres:18`:** se fija la vigente al implementar; las actualizaciones posteriores se hacen por PR.
3. **Traslado de datos:** si algún ambiente llegara a tener datos reales en SQLite, haría falta una herramienta de traslado (fuera de alcance).
4. **Contenerizar la aplicación:** posible siguiente paso (Dockerfile y servicio `app` en Compose), fuera de este cambio.
