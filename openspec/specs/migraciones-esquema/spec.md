# migraciones-esquema Specification

## Purpose
Historial de esquema explícito con Alembic, downgrades no destructivos y regla de una revisión por cambio de modelo.

## Requirements
### Requirement: Revisión inicial explícita
La revisión `0001_postgresql_baseline` SHALL describir de forma explícita el esquema completo para PostgreSQL:
- tablas, columnas con sus tipos nativos (`NUMERIC`, `TIMESTAMPTZ`, `JSONB`), llaves foráneas `RESTRICT`, restricciones `UNIQUE` y `CHECK`, e índices;
- sin importar los modelos ORM ni invocar `Base.metadata.create_all`.

La cadena anterior (`0001_initial` a `0006_user_sessions`), escrita para SQLite, SHALL retirarse de `alembic/versions/`; sólo se conserva en el historial de Git.

#### Scenario: Contenido de la revisión base
- **WHEN** se inspecciona `alembic/versions/0001_postgresql_baseline.py`
- **THEN** contiene un `op.create_table` por cada una de las 11 tablas de dominio y ninguna referencia a `create_all`, `drop_all`, `app.models`, `PRAGMA` ni `sqlite`

#### Scenario: Esquema resultante coincide con los modelos
- **WHEN** se ejecuta `alembic upgrade head` sobre una base PostgreSQL vacía y luego `alembic check`
- **THEN** `alembic check` no reporta diferencias entre la base de datos y los modelos

### Requirement: Downgrades no destructivos
Ninguna revisión MUST invocar `drop_all`. El `downgrade` de `0001_postgresql_baseline` SHALL lanzar `NotImplementedError` con un mensaje que remita a restaurar un respaldo. Las revisiones posteriores SHALL implementar un downgrade explícito o lanzar `NotImplementedError` cuando revertir implique pérdida de datos.

#### Scenario: Downgrade de la revisión inicial
- **WHEN** se ejecuta `alembic downgrade base` sobre una base con datos
- **THEN** la operación falla con `NotImplementedError` antes de modificar cualquier tabla

### Requirement: Una revisión por cambio de modelo
Todo cambio en los modelos ORM SHALL acompañarse de una revisión Alembic nueva. Las revisiones ya publicadas MUST NOT editarse. `scripts/check.py` SHALL ejecutar `alembic check` y fallar si los modelos difieren del esquema producido por las migraciones.

#### Scenario: Modelo modificado sin migración
- **WHEN** se añade una columna a un modelo sin crear una revisión
- **THEN** `alembic check` falla en `scripts/check.py`

