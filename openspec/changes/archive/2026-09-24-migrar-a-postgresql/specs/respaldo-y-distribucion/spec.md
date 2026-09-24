## MODIFIED Requirements

### Requirement: Respaldo consistente de base de datos y almacenamiento
El proyecto SHALL incluir un script de respaldo que:
- ejecute `pg_dump` en formato custom (`-Fc`) dentro del contenedor `db`, cuya versión coincide con la del servidor; así obtiene una instantánea consistente aun con la aplicación en ejecución;
- archive el contenido de `storage/`;
- escriba un manifiesto con la revisión Alembic, la versión del servidor PostgreSQL, la fecha UTC y el SHA-256 de cada artefacto, todo en `backups/<AAAAMMDD-HHMMSS>/`;
- conserve sólo los `BACKUP_RETENTION` respaldos más recientes (14 por defecto).

#### Scenario: Respaldo con la aplicación en ejecución
- **WHEN** se ejecuta el respaldo mientras otra conexión mantiene una transacción de escritura sin confirmar
- **THEN** se genera un volcado que `pg_restore --list` lee sin errores, que contiene todas las transacciones confirmadas antes del inicio del respaldo y que no incluye la no confirmada

#### Scenario: Retención
- **WHEN** existen 14 respaldos y se genera uno nuevo con `BACKUP_RETENTION=14`
- **THEN** se elimina el respaldo más antiguo y quedan 14

### Requirement: Restauración verificable
El proyecto SHALL incluir un script de restauración que:
- verifique los SHA-256 del manifiesto antes de modificar nada;
- exija confirmación explícita (`--yes`);
- respalde el estado actual antes de sobrescribirlo;
- restaure con `pg_restore --clean --if-exists --single-transaction` dentro del contenedor `db` y reemplace `storage/`.

El README SHALL documentar el procedimiento, incluida la necesidad de detener la aplicación.

#### Scenario: Manifiesto alterado
- **WHEN** el volcado de un respaldo no coincide con el SHA-256 del manifiesto
- **THEN** la restauración aborta sin modificar nada

#### Scenario: Restauración completa
- **WHEN** se restaura un respaldo válido con `--yes`
- **THEN** la base de datos y `storage/` quedan iguales al respaldo y los documentos se pueden descargar

### Requirement: Reinicio de demo seguro
`reset_demo.py` SHALL:
- detectar datos no-demo (usuarios cuyo correo no termina en `@poc.local` o facturas sin evento `DEMO_SEEDED`) y, en ese caso, pedir confirmación interactiva o abortar si se ejecuta sin terminal y sin `--yes`;
- negarse a actuar con `APP_ENV=production` o si `DATABASE_URL` apunta a un servidor que no sea local (`localhost`, `127.0.0.1` o `::1`);
- generar un respaldo antes de borrar;
- recrear el esquema `public`, vaciar `storage/` (salvo `.gitkeep`), aplicar las migraciones y sembrar la demo.

Los scripts de arranque local MUST NOT ejecutar `reset_demo.py`: SHALL levantar el contenedor, aplicar las migraciones y sembrar datos sólo si la base está vacía.

#### Scenario: Arranque local con datos existentes
- **WHEN** un desarrollador ejecuta `run_local` con una base que ya contiene facturas creadas en la sesión anterior
- **THEN** la base conserva esas facturas

#### Scenario: Reset con datos no-demo sin terminal
- **WHEN** se ejecuta `reset_demo.py` sin `--yes`, sin terminal interactiva y la base contiene un usuario `ana@ultrasist.com.mx`
- **THEN** el script aborta sin borrar nada

#### Scenario: Reset confirmado
- **WHEN** se ejecuta `reset_demo.py --yes`
- **THEN** se genera un respaldo, se recrea el esquema, se vacía `storage/` (salvo `.gitkeep`) y se reconstruye la demo

#### Scenario: Servidor no local
- **WHEN** `DATABASE_URL` apunta a `db.ejemplo.com` y se ejecuta `reset_demo.py --yes`
- **THEN** el script aborta sin conectarse a borrar nada
