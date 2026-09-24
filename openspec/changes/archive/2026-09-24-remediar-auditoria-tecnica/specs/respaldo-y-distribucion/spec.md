## ADDED Requirements

### Requirement: Respaldo consistente de base de datos y almacenamiento
El proyecto SHALL incluir un script de respaldo que:
- copie la base de datos con la API de respaldo en línea de SQLite (consistente aun con la aplicación en ejecución y con WAL activo);
- archive el contenido de `storage/`;
- escriba un manifiesto con la revisión Alembic, la fecha UTC y el SHA-256 de cada artefacto, todo en `backups/<AAAAMMDD-HHMMSS>/`;
- conserve sólo los `BACKUP_RETENTION` respaldos más recientes (14 por defecto).

#### Scenario: Respaldo con la aplicación en ejecución
- **WHEN** se ejecuta el respaldo mientras la aplicación atiende peticiones
- **THEN** se genera un directorio de respaldo cuya base de datos pasa `PRAGMA integrity_check` y contiene todas las transacciones confirmadas antes del inicio del respaldo

#### Scenario: Retención
- **WHEN** existen 14 respaldos y se genera uno nuevo con `BACKUP_RETENTION=14`
- **THEN** se elimina el respaldo más antiguo y quedan 14

### Requirement: Restauración verificable
El proyecto SHALL incluir un script de restauración que verifique los SHA-256 del manifiesto antes de reemplazar la base de datos y `storage/`, que exija confirmación explícita (`--yes`) y que respalde el estado actual antes de sobrescribirlo. El README SHALL documentar el procedimiento, incluida la necesidad de detener la aplicación.

#### Scenario: Manifiesto alterado
- **WHEN** el archivo de base de datos de un respaldo no coincide con el SHA-256 del manifiesto
- **THEN** la restauración aborta sin modificar nada

#### Scenario: Restauración completa
- **WHEN** se restaura un respaldo válido con `--yes`
- **THEN** la base de datos y `storage/` quedan iguales al respaldo y los documentos se pueden descargar

### Requirement: Reinicio de demo seguro
`reset_demo.py` SHALL detectar datos no-demo (usuarios cuyo correo no termina en `@poc.local` o facturas sin evento `DEMO_SEEDED`). En ese caso SHALL pedir confirmación interactiva, o abortar si se ejecuta sin terminal y sin `--yes`. Antes de borrar SHALL generar un respaldo y SHALL eliminar también los archivos `-wal` y `-shm`. Los scripts de arranque local MUST NOT ejecutar `reset_demo.py`: SHALL aplicar las migraciones y sembrar datos sólo si la base está vacía.

#### Scenario: Arranque local con datos existentes
- **WHEN** un desarrollador ejecuta `run_local` con una base que ya contiene facturas creadas en la sesión anterior
- **THEN** la base conserva esas facturas

#### Scenario: Reset con datos no-demo sin terminal
- **WHEN** se ejecuta `reset_demo.py` sin `--yes`, sin terminal interactiva y la base contiene un usuario `ana@ultrasist.com.mx`
- **THEN** el script aborta sin borrar nada

#### Scenario: Reset confirmado
- **WHEN** se ejecuta `reset_demo.py --yes`
- **THEN** se genera un respaldo, se eliminan la base y sus archivos `-wal`/`-shm` y el contenido de `storage/` (salvo `.gitkeep`), y se reconstruye la demo

### Requirement: Empaquetado limpio para distribución
El proyecto SHALL incluir un script de empaquetado que genere un ZIP sólo con archivos versionados. Si el directorio no está bajo Git, SHALL aplicar una lista de exclusión explícita equivalente. El paquete MUST NOT contener `.env`, `data/*.db*`, `logs/*` (salvo `.gitkeep`), `storage/**` (salvo `.gitkeep`), `backups/`, `.venv/`, `.pytest_cache/`, `__pycache__/` ni `Microsoft/`. Tras generar el paquete, el script SHALL verificar su contenido y fallar si detecta alguno de esos archivos. `.gitignore` SHALL incluir `Microsoft/`, `backups/` y `data/*.db-*`.

#### Scenario: Paquete generado
- **WHEN** se ejecuta el script de empaquetado en un checkout con `.env`, base de datos, logs y documentos en `storage/`
- **THEN** el ZIP resultante no contiene ninguno de esos archivos

#### Scenario: Verificación posterior
- **WHEN** la lista de exclusión falla y el ZIP contiene `.env`
- **THEN** el script termina con error y elimina el ZIP generado

### Requirement: Dependencias auditadas y reproducibles
El proyecto SHALL mantener un `requirements.lock` universal (válido en Linux, macOS y Windows) con versiones exactas y hashes de todas las dependencias, incluidas las transitivas, y fijar `starlette` explícitamente. Las dependencias de sólo prueba (`httpx`, `pytest*`, `ruff`, `pip-audit`, `uv`) SHALL estar únicamente en `requirements-dev.txt`. `scripts/check.py` SHALL ejecutar `pip-audit` sobre el lock y fallar ante vulnerabilidades conocidas que no estén explícitamente excluidas y justificadas.

#### Scenario: Instalación reproducible
- **WHEN** se instala con `pip install --require-hashes -r requirements.lock` en dos fechas distintas
- **THEN** se obtienen exactamente las mismas versiones

#### Scenario: Vulnerabilidad conocida
- **WHEN** una dependencia bloqueada tiene un aviso de seguridad publicado
- **THEN** el paso `pip-audit` de `scripts/check.py` falla e identifica el paquete y el aviso
