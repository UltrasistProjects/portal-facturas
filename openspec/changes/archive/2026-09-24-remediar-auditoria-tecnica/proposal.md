## Why

La Auditoría Técnica del 2026-09-22 (`docs/AUDITORIA_TECNICA_PortalFacturas_2026-09-22.docx`) concluye que el Portal Interno de Facturas tiene una arquitectura sólida pero **no es apto para recibir documentos fiscales reales**. Reporta 2 hallazgos críticos (sesiones forjables con `SECRET_KEY` pública y trazas expuestas por `DEBUG=true`), 5 altos (FKs no enforzadas, dinero en flotante, migraciones inexistentes, UUID fiscal sin unicidad, credenciales demo públicas) y 26 medios/bajos. El MVP del Portal de Proveedores (ERS v1.3, sprint al 2026-09-30) se construirá sobre esta base. Por eso conviene corregirla ahora, antes de que el modelo de datos y los flujos crezcan encima de estos defectos.

## What Changes

**Fase 0: bloqueantes de seguridad (SEC-01, SEC-02, SEC-03, SEC-11)**
- **BREAKING** `SECRET_KEY` pasa a ser obligatoria: sin valor por defecto, con un mínimo de 32 bytes, y se rechaza el placeholder `change-me-*`. Los scripts de arranque generan una clave local la primera vez.
- `DEBUG` deja de pasarse a `FastAPI(debug=)` y su valor por defecto es `false`. Los errores de negocio (transición de estado inválida) responden HTTP 409 en lugar de 500.
- Las credenciales demo del login sólo se renderizan con `APP_ENV=development`. Fuera de ese entorno, el arranque aborta si existen usuarios `@poc.local` activos.
- Auditoría de dependencias con `pip-audit` y lock file con hashes. `starlette` queda fijado explícitamente.

**Fase 1: quick wins (SEC-04..08, BD-01, BD-06, BD-07, COD-03, COD-04, COD-06, COD-07b, COD-08)**
- PRAGMAs de SQLite en cada conexión: `foreign_keys=ON`, `journal_mode=WAL`, `busy_timeout`, `synchronous=NORMAL`.
- Middleware de cabeceras de seguridad (CSP, `X-Frame-Options`, `nosniff`, `Referrer-Policy`, y HSTS bajo TLS).
- Verificación de archivos subidos por *magic bytes*, con MIME derivado por el servidor. Las descargas se sirven siempre como `application/octet-stream`.
- Limitación de intentos de login por correo y por IP, con bloqueo temporal exponencial.
- **BREAKING** Política de contraseñas en el servidor (ERS RF-06) y `EmailStr` en altas. El alta de facturas usa el esquema `InvoiceCreate`.
- El folio interno se deriva del `id` asignado, sin carrera. Se añaden los índices faltantes en FKs y en el ordenamiento del listado.
- **BREAKING** `/admin/rules` muestra las reglas que el motor realmente aplica (incluidos los pesos del score) y se elimina `business_rules.json`.
- Las pruebas usan una BD temporal aislada y dejan de destruir la BD de trabajo. Se añaden `ruff`, `ruff format` y `pytest-cov` con umbral, ejecutables con `scripts/check.py`; el CI sigue siendo el pipeline compartido del equipo.

**Fase 2: cambios estructurales (BD-02..05, BD-08..12, COD-01, COD-02, COD-05, COD-07, COD-09, COD-10, SEC-07, SEC-09)**
- **BREAKING** (esquema) Los montos y la confianza se almacenan como enteros escalados exactos (centavos / diezmilésimas). La aplicación sigue operando con `Decimal`.
- Migraciones Alembic explícitas: `0001` pasa a ser un snapshot real, se añaden revisiones incrementales y ningún `downgrade` hace `drop_all`.
- **BREAKING** `UNIQUE` en `invoices.uuid` y en `(supplier_id, invoice_number)`, más restricciones `CHECK` en estados, montos, vigencias y score. Los estados de proveedor y contrato pasan a ser enums tipados.
- Campos de trazabilidad en `contracts` y versionado del monto autorizado mediante enmiendas auditadas.
- La regla DAT-001 y el año del folio se evalúan en la zona horaria de negocio `America/Mexico_City`.
- `documents.path` guarda rutas relativas a la raíz de almacenamiento. Se prohíbe el borrado físico de facturas y se elimina el `delete-orphan`.
- Las reglas de negocio salen de los routers hacia `invoice_service`. Filtro, búsqueda, paginación y KPIs pasan a SQL.
- Los servicios dejan de hacer commit; el límite transaccional queda en el router.
- Log estructurado JSON con `request_id` y `user_id`, y eventos de subida, validación y revisión.
- Las rutas se anclan al paquete, no al CWD, y `APP_ENV` gobierna los valores por defecto.
- Sesiones revocables del lado del servidor, con expiración por inactividad y máxima.
- Respaldos consistentes (BD + `storage/`) con retención y restauración. `reset_demo` pide confirmación ante datos no-demo y **deja de ejecutarse en cada arranque**.
- Un script de empaquetado excluye `.env`, BD, logs y `storage/`. Se retira del árbol el ZIP que hoy contiene esos archivos.
- Pruebas de `file_service`, de la autorización de descarga y del bloqueo por severidad crítica.

**Fuera de alcance:** cifrado en reposo (SEC-10, responsabilidad de infraestructura; se documenta), migración a PostgreSQL/Azure SQL, escaneo antimalware, endpoint de cambio de contraseña y estado `CANCELLED` (ambos son funcionalidad del MVP según la ERS), y reescritura del historial de Git.

## Capabilities

### New Capabilities
- `configuracion-entorno`: configuración segura por entorno (`SECRET_KEY`, `DEBUG`, `APP_ENV`), rutas ancladas al paquete y verificaciones de arranque que impiden operar con valores inseguros.
- `autenticacion-sesiones`: login con limitación de intentos y bloqueo, política de contraseñas, validación de correo, sesiones revocables del lado del servidor y credenciales demo restringidas a desarrollo.
- `proteccion-http`: cabeceras de seguridad y manejo de errores sin fuga de trazas, con errores de negocio traducidos a códigos HTTP 4xx.
- `almacenamiento-documentos`: validación de archivos subidos por contenido, descarga segura y rutas de almacenamiento relativas y portables.
- `integridad-datos`: integridad referencial enforzada, dinero exacto, unicidad fiscal, restricciones `CHECK`, índices, concurrencia SQLite y prohibición de borrado físico de evidencia fiscal.
- `migraciones-esquema`: historial de esquema explícito con Alembic, downgrades no destructivos y regla de una revisión por cambio de modelo.
- `trazabilidad-contratos`: campos de auditoría en contratos y versionado auditado del monto autorizado.
- `flujo-facturas`: alta validada, folio sin carrera, listado filtrado y paginado en SQL, KPIs agregados y reglas de estado centralizadas en el servicio.
- `motor-validacion`: fuente única de reglas de negocio visible para el administrador, reglas de calendario en zona horaria de negocio y detección de duplicados coherente con la unicidad de la BD.
- `observabilidad`: log estructurado con correlación por petición y registro de eventos técnicos del flujo.
- `respaldo-y-distribucion`: respaldo y restauración, reinicio de demo seguro, empaquetado limpio y dependencias auditadas con lock file.
- `calidad-y-pruebas`: pruebas aisladas de la BD de trabajo, cobertura de módulos de riesgo con umbral, lint y formato automatizados.

### Modified Capabilities
_Ninguna._ `openspec/specs/` está vacío; todas las capacidades se especifican por primera vez.

## Impact

- **Código:** prácticamente todo `app/` (`core/`, `models/`, `routers/`, `services/`, `repositories/`, `rules/date_rules.py`, `templates/auth/login.html`, `templates/admin/rules.html`), `alembic/` (env y revisiones nuevas), `scripts/` (seed, reset, nuevos backup/restore/package/create_env), `run_local.*`, `tests/`.
- **Esquema de BD:** columnas monetarias renombradas a `*_cents` y `confidence` → `confidence_bp`; nuevas tablas `user_sessions`, `login_attempts` y `contract_amendments`; nuevas columnas de auditoría en `contracts`; índices y restricciones `UNIQUE`/`CHECK`. Requiere migración de datos, que aborta si encuentra huérfanos o duplicados en lugar de corregirlos en silencio.
- **Dependencias:** se añaden `tzdata` (zonas horarias en Windows) y, en dev, `ruff`, `pytest-cov`, `pip-audit` y `uv` (para el lock universal). `httpx` se mueve a dev. Se fija `starlette`. Se genera `requirements.lock`.
- **Operación:** `.env` requiere `SECRET_KEY`. Los arranques locales ya no borran la BD. Aparecen los archivos `-wal`/`-shm` junto a la BD. Nuevo directorio `backups/` (ignorado por Git). Las sesiones activas se invalidan al desplegar.
- **Repositorio:** se retira `PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress-V1.zip` (contiene `.env`, BD, logs y `storage/`) y `Microsoft/…/ModuleAnalysisCache`. No se añaden workflows: se conserva `.github/workflows/calidad.yml`.
- **Usuarios demo:** las contraseñas demo cambian para cumplir la política (RF-06) y no figurar en la lista de contraseñas comunes. Se actualiza el README.
