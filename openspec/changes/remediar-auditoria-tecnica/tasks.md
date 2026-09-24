> Todas las rutas son relativas a la raíz de la PoC (`PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress-V1/PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress/`), salvo que se indique "raíz del repo". Cada grupo termina con la suite verde y `ruff` limpio. Los grupos marcados "Checkpoint" cierran una fase con un commit propio.

## 1. Línea base y aislamiento de pruebas (COD-07b, COD-08)

- [x] 1.1 Crear `.venv` con Python 3.12, instalar `requirements-dev.txt`, ejecutar la suite actual en el checkout limpio y registrar el resultado de referencia (14 pruebas).
- [x] 1.2 Crear `pyproject.toml` con la configuración de `ruff` (`line-length=120`, reglas `E,F,W,I`), `pytest` y `coverage` (fuente `app`), aún sin umbral.
- [x] 1.3 Ajustar `scripts/seed_db.py`:
  - `main(passwords=None)` acepta contraseñas explícitas;
  - escribe documentos en `settings.storage_path`, no en `ROOT/storage`;
  - genera `_seed_N.xml` y el PDF demo en un directorio temporal, sin reescribir `data/demo_documents/factura_demo.pdf`.
- [x] 1.4 Reescribir `tests/conftest.py`. Antes de importar `app`:
  - fijar `SECRET_KEY` aleatoria, `APP_ENV=test`, y `DATABASE_URL` y `STORAGE_PATH` bajo `tmp_path_factory`;
  - ejecutar `alembic upgrade head` y el seed con contraseñas explícitas;
  - eliminar la invocación de `reset_demo.py`.
- [x] 1.5 Sustituir en `tests/test_permissions.py` y `tests/test_demo_workflow.py` las dependencias de ids y folios del seed (`/invoices/2`, `FAC-2026-00002`, `/suppliers/1`) por búsquedas por `invoice_number` y `email`.
- [x] 1.6 Añadir una prueba guardián: la BD y el almacenamiento de la sesión de pruebas están bajo el directorio temporal, y `data/invoice_portal.db` y `storage/` del proyecto conservan su SHA-256 tras la suite.
- [x] 1.7 Commit aislado de pruebas: "test: aislar BD y almacenamiento de la suite".
- [x] 1.8 Ejecutar `ruff format` y `ruff check --fix` (E701/E702/F401/I), corregir a mano lo restante sin cambios funcionales y verificar la suite. Hacer un commit aislado: "style: ruff format (sin cambios funcionales)".

## 2. Fase 0 — Configuración segura y errores (SEC-01, SEC-02, COD-10)

- [x] 2.1 Reescribir `app/core/config.py`:
  - `BASE_DIR`, y `.env` anclado a `BASE_DIR`;
  - `secret_key` obligatoria, con validador (≥ 32 caracteres, rechaza el prefijo `change-me`);
  - `app_env` ∈ {`development`, `test`, `production`};
  - `debug=False` por defecto;
  - `session_https_only` derivado de `app_env`;
  - `business_timezone`, `log_dir` y `backup_retention`;
  - resolución de `storage_path`, `log_dir` y la ruta `sqlite:///` relativa contra `BASE_DIR`.
- [x] 2.2 Actualizar `.env.example`: `SECRET_KEY=` vacío con instrucciones de generación, `DEBUG=false`, y las variables nuevas (`BUSINESS_TIMEZONE`, `LOG_DIR`, `BACKUP_RETENTION`).
- [x] 2.3 Crear `scripts/create_env.py`, que copia `.env.example` y genera `SECRET_KEY` con `secrets.token_urlsafe(64)` sólo si `.env` no existe. Invocarlo desde `run_local.sh`, `run_local.ps1` y `run_local.bat`.
- [x] 2.4 En `app/main.py`: eliminar `debug=` de `FastAPI(...)`; montar `StaticFiles` y `Jinja2Templates` con rutas absolutas; enviar los logs a `settings.log_dir`.
- [x] 2.5 Crear `app/core/errors.py` con `BusinessRuleError`, `InvalidTransitionError` (hereda también de `ValueError`) y `DuplicateInvoiceError`. `transition_invoice` lanza `InvalidTransitionError`. Registrar un handler global que responda 409 en HTML o JSON según `Accept`.
- [x] 2.6 Pruebas:
  - `SECRET_KEY` ausente, placeholder o corta impide construir `Settings`;
  - `.env` existente no se sobrescribe;
  - excepción no manejada con `DEBUG=true` → 500 genérico sin traceback, con la traza en el log;
  - `POST /invoices/{id}/submit` en `DRAFT` → 409 y el estado no cambia;
  - `clickbalance` desde `UNDER_REVIEW` → 409;
  - con `Accept: application/json` → JSON 409;
  - rutas resueltas iguales desde otro directorio de trabajo.

## 3. Fase 0 — Credenciales demo y dependencias (SEC-03, SEC-11)

- [x] 3.1 Crear `app/core/demo.py` con `DEMO_ACCOUNTS` (`Admin#Demo2026`, `Pmo#Demo2026`, `Proveedor#Demo2026`). El seed los usa sólo en `development`; en otro entorno genera contraseñas aleatorias conformes a la política y las imprime una sola vez.
- [x] 3.2 El router de login pasa las cuentas demo a la plantilla sólo si `app_env == "development"`. `auth/login.html` renderiza el bloque de acceso rápido de forma condicional, sin contraseñas codificadas en la plantilla.
- [x] 3.3 Verificaciones de arranque en el `lifespan` para `production`: abortar si hay usuarios `@poc.local` activos o si `SESSION_HTTPS_ONLY=false`, listando las causas.
- [x] 3.4 Actualizar la tabla de credenciales del README e indicar que sólo aplica en desarrollo.
- [x] 3.5 Pruebas:
  - login en `development` muestra `data-demo`; en `production` no contiene `data-demo` ni contraseñas (usar `monkeypatch`);
  - el seed en `test` sin contraseñas explícitas genera contraseñas aleatorias;
  - el arranque en `production` aborta con un usuario demo activo o sin cookie `Secure`.
- [x] 3.6 Dependencias:
  - fijar `starlette==<versión resuelta>` en `requirements.txt`;
  - mover `httpx` a `requirements-dev.txt`;
  - añadir `tzdata` a producción, y `ruff`, `pytest-cov`, `pip-audit` y `uv` a dev;
  - generar `requirements.lock` con `uv pip compile --universal --generate-hashes` (lock multiplataforma; `pip-compile` sólo resuelve la plataforma actual y rompería `--require-hashes` en Windows).
- [x] 3.7 Ejecutar `pip-audit -r requirements.lock` y registrar el resultado. Actualizar sólo los paquetes señalados, regenerar el lock y volver a correr la suite. Documentar las excepciones justificadas, si las hay.
- [x] 3.8 Checkpoint Fase 0: suite verde, `ruff` limpio, commit "fix(seguridad): fase 0 de la auditoría".

## 4. Línea base de migraciones (BD-03, adelantado a la Fase 1)

- [x] 4.1 **Antes de modificar cualquier modelo**, generar con `alembic revision --autogenerate` contra una BD vacía el snapshot del esquema actual. Reemplazar el cuerpo de `alembic/versions/0001_initial.py` (mismo `revision`) por `op.create_table`/`op.create_index` explícitos, sin importar `app.models`, y con `downgrade()` que lance `NotImplementedError("Restaure un respaldo")`.
- [x] 4.2 En `alembic/env.py`: `render_as_batch=True`; `PRAGMA foreign_keys=OFF` a nivel de conexión antes de abrir la transacción; `PRAGMA foreign_key_check` al terminar, fallando si hay violaciones.
- [x] 4.3 Reescribir `scripts/init_db.py`: `alembic upgrade head` y seed sólo si la BD está vacía, sustituyendo `create_all`.
- [x] 4.4 Pruebas:
  - `upgrade head` sobre una BD vacía seguido de `alembic check` no reporta diferencias;
  - `downgrade base` lanza `NotImplementedError` sin tocar tablas;
  - ninguna revisión contiene `create_all`, `drop_all` ni `app.models`.

## 5. Fase 1 — PRAGMAs de SQLite e índices (BD-01, BD-06, BD-07)

- [x] 5.1 Ejecutar `PRAGMA foreign_key_check` sobre una BD sembrada y confirmar que no hay huérfanos. Implementar `install_sqlite_pragmas(engine)` en `app/core/database.py` (`foreign_keys=ON`, `journal_mode=WAL`, `busy_timeout=5000`, `synchronous=NORMAL`) y aplicarlo al engine de la app.
- [x] 5.2 En los modelos: `index=True` en `invoices.uploaded_by`, `invoices.reviewed_by`, `invoices.contract_id`, `documents.uploaded_by`, `documents.replaced_document_id`, `reviews.reviewer_id` y `users.supplier_id`. Añadir `Index("ix_invoices_supplier_created", supplier_id, created_at)` e índice en `invoices.created_at`, y quitar el índice simple de `invoices.supplier_id`.
- [x] 5.3 Crear la revisión `0002_indices` y verificar con `alembic check`.
- [x] 5.4 `scripts/reset_demo.py` elimina también `invoice_portal.db-wal` y `invoice_portal.db-shm`.
- [x] 5.5 Pruebas:
  - en una conexión nueva, `PRAGMA foreign_keys = 1`, `journal_mode = wal` y `busy_timeout = 5000`;
  - insertar una factura con `supplier_id` inexistente → `IntegrityError`;
  - una lectura concurrente durante una transacción de escritura abierta no falla;
  - `EXPLAIN QUERY PLAN` del listado por proveedor usa `ix_invoices_supplier_created` sin `TEMP B-TREE`.

## 6. Fase 1 — Cabeceras de seguridad y correlación de peticiones (SEC-05, COD-05 parcial)

- [x] 6.1 Crear `app/core/middleware.py` con `SecurityHeadersMiddleware`, un middleware ASGI puro: CSP como constante única, `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy: same-origin`, y HSTS sólo si `scope["scheme"] == "https"`.
- [x] 6.2 Añadir `RequestContextMiddleware`, también ASGI puro:
  - valida un `X-Request-ID` entrante (8 a 64 caracteres `[A-Za-z0-9-]`) o genera uno nuevo;
  - lo guarda en `scope["state"]` y en un `ContextVar`;
  - lo devuelve en la cabecera de respuesta.
- [x] 6.3 El handler de 500 añade explícitamente las cabeceras de seguridad (helper compartido) y pasa `request_id` a `error.html`, que lo muestra.
- [x] 6.4 Pruebas:
  - cabeceras en `/login`, `/static/css/app.css` y un 404;
  - sin HSTS por HTTP y con HSTS usando `base_url="https://testserver"`;
  - `X-Request-ID` válido reutilizado e inválido reemplazado;
  - la página 500 incluye cabeceras y `request_id`;
  - no hay `CORSMiddleware` registrado.
- [x] 6.5 Verificación manual con `run_local`: recorrer login, tablero, listado, detalle, documentos, revisión y las tres vistas de administración con la consola del navegador abierta, y confirmar que no hay violaciones de CSP.

## 7. Fase 1 — Login, contraseñas y validación de altas (SEC-04, SEC-08, COD-03a)

- [x] 7.1 Crear el modelo `LoginAttempt` (`email`, `ip`, `result`, `attempted_at`, con índices `(email, attempted_at)` e `(ip, attempted_at)`) y la revisión `0003_login_attempts`.
- [x] 7.2 Crear `app/services/login_throttle.py` con reloj inyectable:
  - `check_allowed(email, ip)`: `n` = fallos consecutivos desde el último éxito en 24 h; bloqueo de `min(60, 2^(n-5))` min desde el último fallo; límite por IP de 20 fallos en 15 min;
  - `record(result)`: los intentos rechazados por bloqueo se registran como `THROTTLED` y no cuentan como fallos;
  - purga de filas de más de 24 h;
  - `LOGIN_LOCKED` en auditoría y log `WARNING`.
- [x] 7.3 Integrar en `POST /login`: consultar el bloqueo **antes** de `verify_password` y responder 429 con un mensaje genérico idéntico para correos existentes e inexistentes.
- [x] 7.4 Crear `app/core/passwords.py` con `validate_password()` (8 a 128 caracteres, letra, dígito, especial, lista común) y `app/core/common_passwords.txt`, con fuente y licencia anotadas en la cabecera del archivo.
- [x] 7.5 Añadir `UserCreate` y `SupplierCreate` (con `EmailStr` y validación de contraseña) en `app/schemas/`. Usarlos en `admin.create_user` y `suppliers.create_supplier`, con re-render HTTP 400 y el motivo.
- [x] 7.6 Conectar `InvoiceCreate` a `POST /invoices/new`, con re-render HTTP 400 en `invoices/new.html` mostrando el error.
- [x] 7.7 Pruebas:
  - bloqueo tras 5 fallos, incluso con la contraseña correcta;
  - 7 fallos → bloqueo de 4 min;
  - correo inexistente → misma respuesta;
  - límite de 20 por IP;
  - un éxito reinicia `n`;
  - `THROTTLED` no incrementa `n`;
  - evento `LOGIN_LOCKED`;
  - cada caso de política de contraseña (corta, sin especial, común, 129 caracteres, válida);
  - las contraseñas de `DEMO_ACCOUNTS` y las aleatorias del seed pasan `validate_password()`;
  - correo inválido en alta de usuario y de proveedor;
  - `service_period = "13/2026"` → 400.

## 8. Fase 1 — Archivos subidos y descarga (SEC-06)

- [x] 8.1 En `app/services/file_service.py`:
  - tabla extensión → (firma o validador, MIME canónico): PDF, PNG, JPEG, XML con BOM opcional, y TXT UTF-8 sin NUL;
  - ignorar el `Content-Type` del cliente y almacenar el MIME canónico;
  - eliminar `application/octet-stream`.
- [x] 8.2 La descarga responde siempre con `media_type="application/octet-stream"` y `Content-Disposition: attachment`.
- [x] 8.3 Pruebas unitarias de `file_service`:
  - `MZ` como `.pdf` → rechazado, sin archivo escrito;
  - PDF válido con `application/octet-stream` → aceptado con `application/pdf`;
  - JPEG como `.png`, TXT con NUL y `.html` → rechazados;
  - XML con BOM → aceptado;
  - vacío y tamaño `+1` byte → rechazados;
  - verificación de path traversal.
- [x] 8.4 Pruebas de endpoint:
  - `POST /invoices/{id}/documents` válido y rechazado;
  - carga en `UNDER_REVIEW` → 409;
  - descarga con `application/octet-stream`;
  - un PROVIDER que descarga un documento de otro proveedor → 404;
  - un documento de otra factura → 404.

## 9. Fase 1 — Folio, reglas visibles y código muerto (COD-06, COD-04, COD-03b-d)

- [x] 9.1 Crear `app/core/timeutils.py` con `business_tz()`, `to_business()` y `business_now()` basados en `BUSINESS_TIMEZONE`.
- [x] 9.2 Folio en `create_invoice`: insertar con el marcador `TMP-<24 hex>`, hacer `flush()` y asignar `FAC-{to_business(created_at).year}-{id:05d}` en la misma transacción.
- [x] 9.3 `/admin/rules` renderiza `BUSINESS_RULES`, incluidos los pesos del score por severidad. Eliminar `app/rules/business_rules.json` y actualizar el texto de `admin/rules.html`.
- [x] 9.4 Eliminar los reexports `app/models/{audit,contract,document,invoice,review,supplier,user,validation}.py` y confirmar que nada los importa. Limpiar los imports sin usar señalados por `ruff`.
- [x] 9.5 Pruebas:
  - formato del folio;
  - factura creada el 31 de diciembre a las 20:00 en la zona de negocio → `FAC-2026-`;
  - dos altas concurrentes (dos sesiones o hilos) → folios distintos, sin error;
  - `/admin/rules` muestra los pesos, y un `monkeypatch` de `BUSINESS_RULES["payment_form"]` se refleja en la vista y en XML-004.
- [x] 9.6 Checkpoint Fase 1: suite verde, `ruff` limpio, `alembic check` limpio, commit "fix: fase 1 de la auditoría".

## 10. Fase 2 — Respaldo, restauración y reinicio seguro (BD-08)

- [x] 10.1 Crear `scripts/backup.py`:
  - copia la BD con `sqlite3.Connection.backup()` y archiva `storage/` en ZIP;
  - escribe `manifest.json` (revisión Alembic, fecha UTC, SHA-256) en `backups/<AAAAMMDD-HHMMSS>/`;
  - aplica la retención `BACKUP_RETENTION`.
- [x] 10.2 Crear `scripts/restore_backup.py`: verifica los SHA-256, exige `--yes`, respalda el estado actual y restaura la BD y `storage/`.
- [x] 10.3 Modificar `scripts/reset_demo.py`:
  - detectar datos no-demo (usuarios fuera de `@poc.local`, facturas sin `DEMO_SEEDED`);
  - pedir confirmación si hay terminal; sin terminal y sin `--yes`, abortar;
  - respaldar antes de borrar.
- [x] 10.4 `run_local.{sh,ps1,bat}` ejecutan `create_env` → `init_db` → uvicorn, sin `reset_demo`. Actualizar `ejecucion.txt` y la sección de arranque del README.
- [x] 10.5 Añadir `backups/` a `.gitignore`. Documentar en el README el procedimiento de respaldo y restauración, incluida la necesidad de detener la aplicación y la conservación fiscal de 5 años.
- [x] 10.6 Pruebas:
  - respaldo con una conexión de escritura abierta → `integrity_check` = `ok` y contiene las filas confirmadas;
  - retención de 14;
  - restauración con un manifiesto alterado → aborta sin cambios;
  - restauración válida → documentos descargables;
  - `reset_demo` sin terminal, sin `--yes` y con un usuario no-demo → aborta;
  - `reset_demo --yes` → respalda, elimina `-wal`/`-shm` y reconstruye.

## 11. Fase 2 — Integridad de datos y dinero exacto (BD-02, BD-04, BD-05, BD-10 UTC, BD-11, BD-12)

- [x] 11.1 Crear `app/core/types.py`:
  - `ScaledDecimal(scale)`: entero; rechaza valores no exactos en la escala;
  - `Money = ScaledDecimal(2)`;
  - `UTCDateTime`: normaliza a UTC al escribir y devuelve `tzinfo=UTC` al leer.
  
  Incluir pruebas unitarias.
- [x] 11.2 Añadir `SupplierStatus` y `ContractStatus` (`ACTIVE`, `INACTIVE`) en `app/core/constants.py` y reemplazar los literales `"ACTIVE"` en modelos, routers y `supplier_rules`.
- [x] 11.3 Actualizar los modelos:
  - columnas físicas `subtotal_cents`, `tax_cents`, `total_cents`, `authorized_amount_cents` y `confidence_bp` (`ScaledDecimal(4)`), conservando los nombres de atributo;
  - `UTCDateTime` en todas las fechas-hora;
  - `SAEnum(..., native_enum=False, create_constraint=True)` en rol, tipo de proveedor, estados de factura, proveedor y contrato, estado y severidad de regla, decisión de revisión y `processing_status`;
  - `CheckConstraint` en montos ≥ 0, `authorized_amount_cents > 0`, `end_date >= start_date`, `validation_score` 0..100 y `confidence_bp` 0..10000;
  - `UniqueConstraint("uuid")` y `UniqueConstraint("supplier_id", "invoice_number")` con nombres `uq_invoices_uuid` y `uq_invoices_supplier_number`;
  - `ondelete="RESTRICT"` en las FKs.
- [x] 11.4 En las relaciones de `Invoice`, quitar `delete-orphan` (`cascade="save-update, merge"`) y registrar un evento `before_delete` sobre `Invoice` que lance `BusinessRuleError("Borrado fisico de facturas prohibido")`.
- [x] 11.5 Rutas relativas:
  - `LocalFileStorage.relative_path()` y `resolve()`, con verificación de raíz → 404;
  - `StoredFile.relative_path`;
  - usar la ruta relativa al persistir (routers de facturas y proveedores, seed), al descargar y en `validation_engine` (`parse_cfdi(storage.resolve(...))`).
- [x] 11.6 En `run_validation`, cuantizar a 2 decimales (`ROUND_HALF_UP`) los importes de cabecera del XML antes de asignarlos a la factura y conservar los valores originales en `metadata_json` del documento XML.
- [x] 11.7 Crear la revisión `0004_integridad_datos`, con operaciones batch y `downgrade` que lanza `NotImplementedError`:
  - precondiciones con informe y aborto sin cambios: `foreign_key_check`, duplicados de `uuid` y de `(supplier_id, invoice_number)`, valores fuera de enumeración, y rutas sin segmento `storage`;
  - conversión `CAST(ROUND(x*100) AS INTEGER)` para montos y `×10000` para confianza;
  - conversión de rutas absolutas (Windows y POSIX) a relativas;
  - FKs `RESTRICT`, `CHECK`s, enums y `UNIQUE`s.
- [x] 11.8 Añadir `ContractCreate` para validar el alta de contrato (fechas coherentes, monto > 0) con re-render 400 antes de llegar al `CHECK` de la BD.
- [x] 11.9 Prueba de migración: construir una BD en `0001` con datos del esquema anterior (montos `REAL`, rutas absolutas Windows) y ejecutar `upgrade head`. Verificar que se conservan los conteos por tabla, que los centavos y `confidence_bp` son correctos y que las rutas quedan relativas. Con `uuid` duplicados, verificar que aborta y la revisión no cambia.
- [x] 11.10 Pruebas de integridad:
  - `typeof(subtotal_cents) = 'integer'` y round-trip exacto de `100000.10`;
  - `10.005` rechazado;
  - `SUM` de 0.10 + 0.20 + 0.30 = 0.60 exacto;
  - FIN-001 en el límite exacto con centavos → `PASS`;
  - `UNIQUE` sobre `uuid`, múltiples `NULL` y número por proveedor (mismo número en otro proveedor, permitido);
  - `CHECK`s por SQL directo (estado inválido, total negativo, vigencia invertida, score 101);
  - `db.delete(invoice)` → error sin borrar;
  - quitar un documento de la colección no lo borra;
  - `DELETE` SQL de una factura con documentos → error;
  - `created_at` con `tzinfo` UTC;
  - ruta manipulada `../../.env` → 404.
- [x] 11.11 `alembic check` limpio y commit del grupo.

## 12. Fase 2 — Flujo de facturas y motor de validación (COD-01, COD-02, COD-09, BD-04, BD-10 DAT-001)

- [x] 12.1 En `app/services/invoice_service.py`: `EDITABLE_STATUSES`, `PREVALIDATABLE_STATUSES`, `is_editable()`, `ensure_can_accept()`, `next_clickbalance_status()`, `review_invoice()` y `validation_summary()` (delega en `calculate_score`). Reescribir `routers/invoices.py` para usarlos, sin reglas propias.
- [x] 12.2 Quitar `db.commit()` de `run_validation` y de cualquier otro servicio. El router de validación y el seed confirman la transacción; `get_db` revierte ante excepción.
- [x] 12.3 UUID duplicado en `run_validation`:
  - comprobar antes de asignar; si es duplicado, FIN-004 `FAIL`, UUID detectado en `metadata_json` e `invoices.uuid` sin asignar;
  - en el router, capturar `IntegrityError` de `uq_invoices_uuid` → rollback → `DuplicateInvoiceError` (409).
- [x] 12.4 En `create_invoice`, capturar `IntegrityError` de `uq_invoices_supplier_number` → rollback → 409 "Ya existe una factura con ese número para el proveedor".
- [x] 12.5 DAT-001 usa `to_business(invoice.created_at).day`.
- [x] 12.6 Repositorio:
  - `search_invoices(db, user, q, status, page, per_page=25) -> Page`, con `join(Supplier)`, `contains_eager`, `ilike` con escape de `%`, `_` y `\`, y `count()`;
  - `status_counts()` y `total_amount()` agregados en SQL;
  - paginación de `/admin/audit` a 50 por página.
  
  Actualizar `invoices/list.html`, `dashboard.html` y `admin/audit.html` con controles de paginación.
- [x] 12.7 Pruebas de flujo:
  - aceptar con bloqueo `CRITICAL` → 409 sin revisión registrada (servicio y HTTP);
  - resumen del detalle = `calculate_score`;
  - búsqueda por razón social;
  - `%` tratado como literal;
  - 30 facturas → la página 2 tiene 5;
  - número de consultas constante (listener `before_cursor_execute`);
  - alcance del PROVIDER;
  - KPIs del PROVIDER exactos;
  - fallo inyectado tras `run_validation` → sin estado persistido;
  - 600 entradas de auditoría → la última página es accesible.
- [x] 12.8 Pruebas del motor:
  - DAT-001 el 20 de agosto a las 23:00 CST → `PASS`;
  - el 21 de agosto a las 00:30 CST → `WARNING`;
  - con `BUSINESS_TIMEZONE=UTC` → `WARNING`;
  - UUID duplicado → FIN-004 `FAIL` y `invoices.uuid` `NULL`;
  - carrera simulada de UUID → 409 sin resultados persistidos;
  - revalidar la propia factura → `PASS`;
  - número de factura duplicado → 409;
  - pruebas unitarias de FIN-002, FIN-003, FIN-005 y FIN-006.

## 13. Fase 2 — Trazabilidad de contratos (BD-09)

- [ ] 13.1 Añadir `created_at`, `created_by`, `updated_at` y `updated_by` a `Contract`. Crear el modelo `ContractAmendment` (`previous_amount`/`new_amount` como `Money`, `reason` obligatorio, `created_by`, `created_at`, `CHECK new > 0`). Crear la revisión `0005_trazabilidad_contratos`: los contratos existentes reciben la marca temporal de la migración y `*_by = NULL`.
- [ ] 13.2 `create_contract` asigna los campos de auditoría.
- [ ] 13.3 Crear `POST /contracts/{id}/amendments` (sólo ADMIN, con CSRF): valida motivo y monto > 0; en una transacción crea la enmienda, actualiza el monto y `updated_*`, y audita `CONTRACT_AMOUNT_CHANGED` con old/new. Añadir a `contracts/list.html` el formulario de enmienda (ADMIN) y el historial (INTERNAL y ADMIN).
- [ ] 13.4 FIN-001 añade a `evidence` `authorized_amount` y `amendment_id` (la última enmienda, o `null`).
- [ ] 13.5 Pruebas:
  - campos de auditoría en el alta;
  - enmienda válida (enmienda, monto, auditoría con old/new);
  - INTERNAL o PROVIDER → 403;
  - sin motivo → 400;
  - monto 0 → 400;
  - historial visible para INTERNAL;
  - evidencia de FIN-001 tras una enmienda;
  - la evidencia histórica se conserva sin revalidar.

## 14. Fase 2 — Sesiones revocables (SEC-07)

- [ ] 14.1 Crear el modelo `UserSession` (`user_id`, `sid_hash` único, `created_at`, `last_seen_at`, `revoked_at`, `ip`, `user_agent` truncado) y la revisión `0006_user_sessions`.
- [ ] 14.2 Crear `app/services/session_service.py` con reloj inyectable: `create`, `resolve` (60 min de inactividad, 8 h absolutas, revocación), `touch` (a lo sumo 1 escritura por minuto), `revoke`, `revoke_all_for_user` y `purge` (vencidas hace más de 7 días).
- [ ] 14.3 Integración:
  - el login limpia la cookie y crea un `sid` nuevo;
  - el logout revoca;
  - `get_current_user` resuelve por `sid`;
  - `toggle_user` revoca las sesiones del usuario deshabilitado;
  - `SessionMiddleware` con `max_age` de 8 h y `https_only` desde `settings`.
- [ ] 14.4 Pruebas:
  - cookie reutilizada tras logout → redirige a `/login`;
  - inactividad de 61 min → expira;
  - actividad continua de más de 8 h → expira;
  - usuario deshabilitado → sesiones revocadas;
  - fijación: `sid` nuevo en el login y el anterior inválido;
  - cookie con `Secure` cuando `https_only`;
  - la BD sólo guarda el hash del `sid`.

## 15. Fase 2 — Observabilidad (COD-05)

- [ ] 15.1 En `app/core/logging_config.py`: `JsonFormatter` (`timestamp` UTC, `level`, `logger`, `message`, `request_id` y `user_id` desde `ContextVar`, más los campos `extra`) con rotación de 2 MB × 3 en `settings.log_dir`. `get_current_user` fija `user_id` en el contexto.
- [ ] 15.2 Emitir eventos, sin RFC, nombres de archivo ni secretos:
  - `document.uploaded`, `validation.started` y `validation.completed` (con `duration_ms`, `score`, `blockers` y `status`), `review.decided`;
  - `xml.parse_failed` y `pdf.analysis_failed`, registrando el detalle técnico **antes** de relanzar el mensaje genérico;
  - `login.locked`.
- [ ] 15.3 Pruebas:
  - las líneas del log son JSON con `request_id` y `user_id`;
  - la línea de arranque tiene `request_id = null`;
  - eventos de validación con `duration_ms`;
  - un PDF dañado genera `pdf.analysis_failed` y el mensaje genérico;
  - tras el flujo completo, el log no contiene `password`, `csrf`, contraseñas demo ni los RFC.

## 16. Fase 2 — Distribución limpia y repositorio (SEC-09)

- [ ] 16.1 Crear `scripts/package_release.py`: usa `git ls-files` si hay Git y, si no, una lista de exclusión explícita; verifica el ZIP después de generarlo; si detecta `.env`, `data/*.db*`, `logs/*`, `storage/**`, `backups/`, `.venv/`, cachés o `Microsoft/`, elimina el ZIP y falla.
- [ ] 16.2 Añadir `Microsoft/` y `data/*.db-*` a `.gitignore`.
- [ ] 16.3 `git rm` de `Microsoft/Windows/PowerShell/ModuleAnalysisCache` (PoC) y de `PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress-V1.zip` (raíz del repo). No reescribir el historial: queda como pregunta abierta para el dueño del repositorio.
- [ ] 16.4 Pruebas: sobre un árbol de prueba con `.env`, BD, logs y `storage/`, el paquete los excluye; al forzar la inclusión de `.env`, el script falla y borra el ZIP.

## 17. Cobertura, CI y documentación final (COD-07, SEC-11, SEC-10)

- [ ] 17.1 Medir la cobertura de `app/`. Si no llega a 80 %, añadir pruebas de las rutas "no configurado" de los adaptadores Azure y de las ramas pendientes. Fijar `--cov-fail-under` en `pyproject.toml` con el valor medido redondeado hacia abajo (≥ 80).
- [ ] 17.2 Crear `.github/workflows/poc-ci.yml` (raíz del repo): push y pull request, Python 3.12, `working-directory` en la raíz de la PoC, `SECRET_KEY` generada en el job, instalación desde `requirements.lock` y dev. Pasos: `ruff check`, `ruff format --check`, `alembic check`, `pytest` (con umbral) y `pip-audit -r requirements.lock`.
- [ ] 17.3 Actualizar el README:
  - variables de entorno nuevas, credenciales demo y arranque sin reset;
  - respaldo y restauración, y empaquetado;
  - política CSP (sin scripts ni estilos en línea) y `--proxy-headers` detrás de un proxy;
  - cifrado en reposo como requisito de infraestructura (SEC-10);
  - regla de una migración por cambio de modelo;
  - corregir la afirmación "Errores sin stack trace", que ahora es verdadera.
- [ ] 17.4 Verificación final:
  - `openspec validate remediar-auditoria-tecnica`, suite completa con umbral, `ruff`, `alembic check` y `pip-audit`;
  - prueba de humo con `run_local`: login con los tres roles, alta de factura, carga de documentos, prevalidación, revisión, enmienda de contrato y descarga, sin errores de CSP en la consola.
- [ ] 17.5 Checkpoint Fase 2: commit "fix: fase 2 de la auditoría" y resumen de trazabilidad hallazgo → tarea para el PR, incluidas las preguntas abiertas de `design.md`.
