# migraciones-esquema Specification

## Purpose
Historial de esquema explícito con Alembic, downgrades no destructivos y regla de una revisión por cambio de modelo.

## Requirements
### Requirement: Revisión inicial explícita
La revisión `0001_initial` SHALL describir el esquema de forma explícita con operaciones `op.create_table` / `op.create_index`, y MUST NOT importar los modelos ORM ni invocar `Base.metadata.create_all`. Su contenido SHALL corresponder al esquema previo a este cambio, para que las bases existentes marcadas en `0001_initial` sigan siendo coherentes.

#### Scenario: Contenido de 0001
- **WHEN** se inspecciona `alembic/versions/0001_initial.py`
- **THEN** contiene una llamada `op.create_table` por cada una de las 8 tablas de dominio y ninguna referencia a `create_all`, `drop_all` ni `app.models`

#### Scenario: Esquema resultante coincide con los modelos
- **WHEN** se ejecuta `alembic upgrade head` sobre una base vacía y luego `alembic check`
- **THEN** `alembic check` no reporta diferencias entre la base de datos y los modelos

### Requirement: Downgrades no destructivos
Ninguna revisión MUST invocar `drop_all`. El `downgrade` de `0001_initial` SHALL lanzar `NotImplementedError` con un mensaje que remita a restaurar un respaldo. Las revisiones posteriores SHALL implementar un downgrade explícito o lanzar `NotImplementedError` cuando revertir implique pérdida de datos.

#### Scenario: Downgrade de la revisión inicial
- **WHEN** se ejecuta `alembic downgrade base` sobre una base con datos
- **THEN** la operación falla con `NotImplementedError` antes de modificar cualquier tabla

### Requirement: Una revisión por cambio de modelo
Todo cambio en los modelos ORM SHALL acompañarse de una revisión Alembic nueva. Las revisiones ya publicadas MUST NOT editarse. `scripts/check.py` SHALL ejecutar `alembic check` y fallar si los modelos difieren del esquema producido por las migraciones.

#### Scenario: Modelo modificado sin migración
- **WHEN** se añade una columna a un modelo sin crear una revisión
- **THEN** `alembic check` falla en `scripts/check.py`

### Requirement: Migración de datos segura y verificada
La revisión que introduce los cambios de este remedio SHALL verificar precondiciones antes de modificar datos: ausencia de filas huérfanas (`PRAGMA foreign_key_check`), ausencia de `uuid` duplicados, ausencia de `(supplier_id, invoice_number)` duplicados y ausencia de valores fuera de las enumeraciones. Si alguna falla, SHALL abortar con un informe de las filas afectadas y sin modificar la base. Las revisiones SHALL usar operaciones batch compatibles con SQLite.

#### Scenario: Duplicados preexistentes
- **WHEN** la base contiene dos facturas con el mismo `uuid` y se ejecuta `alembic upgrade head`
- **THEN** la migración aborta listando los `id` afectados y la base permanece en la revisión anterior sin cambios

#### Scenario: Actualización de una base existente
- **WHEN** una base poblada por el seed anterior (revisión `0001_initial`) se actualiza a `head`
- **THEN** los montos, la confianza y las rutas de documentos se convierten sin pérdida, y el número de filas de cada tabla se conserva

