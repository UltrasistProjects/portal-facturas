## Context

**Proyecto.** PoC del Portal Interno de Facturas:
- ubicación: `PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress-V1/PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress/` (en adelante, **raíz de la PoC**);
- stack: Python 3.12, FastAPI 0.116, SQLAlchemy 2.0 ORM, Jinja2 server-rendered, SQLite, Alembic 1.16, pwdlib/Argon2;
- tamaño: unas 1,800 líneas en `app/`, `tests/`, `scripts/` y `alembic/`.

**Punto de partida.** La auditoría del 2026-09-22 (33 hallazgos) propone un plan de 30 acciones en tres fases. La arquitectura en capas, el ORM parametrizado, el CSRF, Argon2, el parser endurecido contra XXE, la ausencia de IDOR y el versionado documental están bien resueltos. Este diseño los preserva y actúa sólo sobre la configuración, la persistencia, el hardening y la calidad.

**Hechos verificados en este repositorio** (complementan la auditoría):
- El checkout versionado de la PoC **no** contiene `.env`, BD ni logs. En cambio, el ZIP `PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress-V1.zip`, versionado y publicado en `origin` (GitHub), sí contiene `.env`, `data/invoice_portal.db`, `logs/`, `.pytest_cache/`, `Microsoft/` y `storage/`. SEC-09 sigue vivo en el repositorio.
- Las plantillas no tienen `<script>` en línea, atributos `style=` ni manejadores `on*=`. Bootstrap usa 23 imágenes `data:image/svg+xml`, por lo que una CSP estricta es viable si permite `img-src data:`.
- `scripts/init_db.py` usa `create_all`, que evita Alembic y deja la BD sin `alembic_version`.
- La ERS del MVP (RF-06) fija la política de contraseñas en al menos 8 caracteres, con letra, número y carácter especial.
- El desarrollo original se hace en Windows (`run_local.ps1`/`.bat`); el equipo actual usa Linux. Los scripts nuevos deben ser multiplataforma.

**Restricciones.**
- La PoC es la base del MVP (sprint al 2026-09-30).
- El destino de BD de producción (PostgreSQL/Azure SQL) no está decidido.
- No se incorpora infraestructura nueva (Redis, colas, antivirus).

## Goals / Non-Goals

**Goals:**
- Cerrar los 2 hallazgos críticos y los 5 altos. Atender todos los medios y bajos que dependen del código o del repositorio.
- Dejar el esquema bajo migraciones explícitas y verificables, con datos monetarios exactos y restricciones en la BD.
- Que cada fase termine con la suite verde y en un commit propio, para poder revisarla o revertirla de forma independiente.
- No romper los flujos funcionales existentes ni los escenarios demo del seed.

**Non-Goals:**
- Cifrado en reposo de la BD y de `storage/` (SEC-10): es responsabilidad de infraestructura (BitLocker/LUKS o TDE). Sólo se documenta.
- Migrar a PostgreSQL/Azure SQL. El diseño debe ser agnóstico (ver D2), pero la migración no se hace aquí.
- Escaneo antimalware de adjuntos, endpoint de cambio de contraseña, primer login obligatorio y estado `CANCELLED`: son funcionalidad del MVP según la ERS.
- Reescribir el historial de Git para purgar el ZIP (decisión del dueño del repositorio; ver Open Questions).
- Sustituir `SessionMiddleware`, Jinja2 o la estructura de capas.

## Decisions

### D1. Un solo cambio, ejecutado por fases con commits aislados
El cambio agrupa las 30 acciones en el orden 0 → 1 → 2, con dos ajustes respecto de la auditoría:

1. **El aislamiento de pruebas (COD-07b) y el formateo con `ruff` (COD-08) van primero.** Sin aislamiento, correr las pruebas destruye la BD de trabajo. El formateo mecánico en un commit aislado deja limpios los diffs funcionales posteriores y facilita editar líneas con múltiples sentencias.
2. **La regeneración de `0001_initial` (BD-03) se adelanta al inicio de la Fase 1.** La Fase 1 ya introduce cambios de esquema (índices, `login_attempts`), y la revisión inicial tiene que ser el snapshot del esquema **previo** a cualquier cambio de modelo.

*Alternativa descartada:* tres cambios OpenSpec separados. Aportan poco aquí: las fases comparten archivos (`models`, `routers/invoices.py`) y el orden importa. Los grupos de `tasks.md` mantienen la granularidad.

### D2. Dinero exacto mediante enteros escalados y un `TypeDecorator`
`app/core/types.py` define `ScaledDecimal(scale)`, un `TypeDecorator` con `impl=Integer`:
- al escribir, convierte `Decimal` → `int(value * 10**scale)`;
- al leer, convierte `int` → `Decimal(value).scaleb(-scale)`;
- rechaza con `ValueError` todo valor que no sea exacto en la escala (`value != value.quantize(...)`), sin redondear en silencio.

Se aplica como `Money = ScaledDecimal(2)` a subtotal, tax, total, authorized_amount y a los montos de enmienda, y como `ScaledDecimal(4)` a `confidence`. Las **columnas físicas** se renombran (`subtotal_cents`, `tax_cents`, `total_cents`, `authorized_amount_cents`, `confidence_bp`) para que el SQL directo no sea ambiguo. Los **atributos ORM conservan su nombre** (`mapped_column("subtotal_cents", Money)`), así que reglas, servicios y plantillas siguen usando `Decimal` sin cambios.

Los importes de cabecera del CFDI admiten hasta 6 decimales en el XSD. El motor los cuantiza explícitamente a 2 (`ROUND_HALF_UP`) antes de asignarlos a la factura y conserva el valor original en `metadata_json` del documento XML. FIN-002 sigue operando sobre los valores del XML.

*Alternativas:*
- `String(20)` decimal: exacto, pero no ordenable ni agregable en SQL.
- Decidir PostgreSQL ahora: fuera de alcance.
- `Numeric` con `asdecimal`: sigue siendo REAL en SQLite.

El `TypeDecorator` aísla la decisión. Si se adopta PostgreSQL, una migración convierte `*_cents` a `NUMERIC(16,2)` y el decorador se sustituye por `Numeric` sin tocar el dominio.

### D3. Fechas-hora UTC explícitas y zona horaria de negocio
- `UTCDateTime` (`TypeDecorator` sobre `DateTime`) normaliza a UTC al escribir y devuelve `tzinfo=UTC` al leer. Sustituye a `DateTime(timezone=True)` en todos los modelos.
- `app/core/timeutils.py` expone `business_tz()`, `to_business(dt)` y `business_now()`, basados en `BUSINESS_TIMEZONE` (por defecto `America/Mexico_City`).
- DAT-001 usa `to_business(invoice.created_at).day`, y el año del folio usa `to_business(created_at).year`.
- Se añade `tzdata` a las dependencias, porque Windows no trae base de datos IANA.

### D4. PRAGMAs de SQLite en un único listener reutilizable
`app/core/database.py` expone `install_sqlite_pragmas(engine)`, un listener `connect` que ejecuta `foreign_keys=ON`, `journal_mode=WAL`, `busy_timeout=5000` y `synchronous=NORMAL`. Lo usan el engine de la app, `alembic/env.py` y, por extensión, las pruebas y los scripts, que importan el mismo engine.

**Durante las migraciones** `env.py` desactiva `foreign_keys` a nivel de conexión antes de abrir la transacción. Esto sigue el procedimiento oficial de SQLite para reconstruir tablas en modo batch. Al terminar, ejecuta `PRAGMA foreign_key_check` y falla si hay violaciones. `env.py` activa `render_as_batch=True`.

### D5. Estrategia de migraciones
1. **`0001_initial`** se regenera con `alembic revision --autogenerate` contra una BD vacía **antes de cualquier cambio de modelo** y se limpia a mano: sin imports de `app.models`, y `downgrade()` lanza `NotImplementedError("Restaure un respaldo")`. Las BD existentes ya marcadas en `0001_initial` quedan coherentes.
2. **Una revisión por grupo de cambio de modelo**, para que cada grupo de tareas termine con `alembic check` limpio:
   - `0002_indices` (Fase 1): índices de BD-07.
   - `0003_login_attempts` (Fase 1): tabla `login_attempts`.
   - `0004_integridad_datos` (Fase 2): se ejecuta en este orden:
     - precondiciones (huérfanos, duplicados de `uuid` y de `(supplier_id, invoice_number)`, valores fuera de enumeración, rutas sin segmento `storage`); si alguna falla, aborta con un informe;
     - conversión de dinero a centavos con `CAST(ROUND(x * 100) AS INTEGER)` y de confianza a diezmilésimas;
     - rutas relativas;
     - FKs con `ON DELETE RESTRICT`;
     - `CHECK`s, enums con `create_constraint=True` y `UNIQUE`.
     
     El downgrade lanza `NotImplementedError`.
   - `0005_trazabilidad_contratos` (Fase 2): campos de auditoría y tabla `contract_amendments`.
   - `0006_user_sessions` (Fase 2): tabla `user_sessions`.

Regla de proceso: una revisión nueva por cada cambio de modelo, sin editar revisiones publicadas. `alembic check` corre en `scripts/check.py`.

*Alternativa:* dejar que `reset_demo` recree todo, ya que los datos son demo. Se descarta porque la BD de trabajo de los desarrolladores y cualquier piloto necesitan migración sin pérdida (spec `migraciones-esquema`).

### D6. Sesiones revocables sobre `SessionMiddleware`
Se conserva `SessionMiddleware` (cookie firmada) como transporte, que ahora sólo lleva `sid` y `csrf_token`.
- **Tabla `user_sessions`:** `id`, `user_id`, `sid_hash` (SHA-256, único), `created_at`, `last_seen_at`, `revoked_at`, `ip` y `user_agent` truncado.
- **`get_current_user`:** busca por `sha256(sid)` y comprueba revocación, inactividad (60 min) y edad absoluta (8 h).
- **`last_seen_at`:** se actualiza como máximo una vez por minuto, para no convertir cada GET en escritura.
- **Login:** limpia la sesión y crea un `sid` nuevo (antifijación).
- **Logout y desactivación de usuario:** marcan `revoked_at`.
- **Limpieza:** el login purga de forma oportunista las sesiones vencidas hace más de 7 días.
- **Cookie:** `max_age` = 8 h, como tope del lado del cliente.

Como defensa en profundidad frente a SEC-01, una cookie forjada con la clave necesita además un `sid` válido.

*Alternativas:* Redis (infraestructura nueva) y timestamps de `itsdangerous` (expiran pero no se pueden revocar).

### D7. Limitación de login respaldada en BD
La tabla `login_attempts` (`email`, `ip`, `result` ∈ {`SUCCESS`, `FAILURE`, `THROTTLED`}, `attempted_at`) tiene índices `(email, attempted_at)` e `(ip, attempted_at)`. El servicio `login_throttle` decide **antes** de `verify_password`, así los intentos bloqueados no consumen Argon2, lo que también mitiga el DoS por CPU. Los intentos se registran igual para correos inexistentes, así que no hay enumeración. El bloqueo emite `LOGIN_LOCKED` en `audit_logs` y un log `WARNING`. Las filas de más de 24 h se purgan de forma oportunista.

*Alternativas:*
- `slowapi`: estado en memoria por proceso; no sobrevive reinicios ni se comparte entre workers.
- Consultar `audit_logs`: el correo vive en JSON, no indexable, y mezcla propósitos.

### D8. Middlewares ASGI puros para cabeceras y `request_id`
`SecurityHeadersMiddleware` y `RequestContextMiddleware` son ASGI puros (no `BaseHTTPMiddleware`), así que cubren `StaticFiles` y `FileResponse`.
- `RequestContextMiddleware` guarda `request_id` en `scope["state"]` y en un `ContextVar` que lee el formateador de logs.
- En Starlette, el handler de `Exception` lo ejecuta `ServerErrorMiddleware`, que es **externo** a los middlewares de usuario. Por eso el handler de 500 añade explícitamente las cabeceras de seguridad (helper compartido) y lee `request.state.request_id`.
- La CSP se define como constante única. HSTS se emite sólo si `scope["scheme"] == "https"`. Detrás de un proxy, uvicorn debe correr con `--proxy-headers --forwarded-allow-ips`, y esto se documenta.

### D9. Excepciones de dominio en lugar de `ValueError` genérico
`app/core/errors.py` define:
- `BusinessRuleError(Exception)` con `status_code = 409`;
- `InvalidTransitionError(BusinessRuleError, ValueError)` (la herencia de `ValueError` mantiene compatible la prueba existente);
- `DuplicateInvoiceError(BusinessRuleError)`.

Un handler global traduce `BusinessRuleError` a 409 (HTML o JSON según `Accept`) reutilizando el render de `HTTPException`.

`IntegrityError` **no** se captura globalmente, porque ocultaría bugs. Se traduce sólo en los puntos donde se sabe qué restricción puede violarse: el alta de factura (`uq_invoices_supplier_number`) y la validación (`uq_invoices_uuid`), con rollback previo.

### D10. Verificación de archivos por firma y MIME derivado por el servidor
Una tabla `extensión → (firma o validador, MIME canónico)` en `file_service`. El `Content-Type` del cliente se ignora para decidir (ver escenario "PDF válido declarado como octet-stream"). Así se cumple la intención de la auditoría sin rechazar navegadores que envían `application/octet-stream`. La descarga fuerza `application/octet-stream`.

*Alternativa:* `python-magic`/libmagic, descartada por su dependencia nativa, problemática en Windows, y porque es excesiva para 5 formatos.

### D11. Rutas relativas en `documents.path`
`LocalFileStorage` expone:
- `relative_path(abs) -> str`: POSIX y relativa a la raíz;
- `resolve(rel) -> Path`: resuelve y verifica `root in path.parents`; si no, `FileNotFoundError` → 404.

`StoredFile` incorpora `relative_path`. La migración normaliza `\` a `/`, toma lo que sigue al **último** segmento `storage/` y aborta si una ruta no lo contiene. El seed usa la misma API.

### D12. Folio derivado del `id`
La factura se inserta con un marcador único temporal (`TMP-<24 hex>`, cabe en `String(30)`), se hace `flush()` para obtener el `id` y se asigna `FAC-{año negocio}-{id:05d}` en la misma transacción.

*Alternativa:* tabla `folio_counters` por año con `UPDATE … RETURNING`, más compleja. Sólo hace falta si Negocio exige que la numeración se reinicie por año (ver Open Questions).

### D13. Reglas de flujo en `invoice_service`
El servicio concentra:
- `EDITABLE_STATUSES`, `is_editable()`, `PREVALIDATABLE_STATUSES`;
- `ensure_can_accept()`, que lanza `BusinessRuleError`;
- `next_clickbalance_status()`;
- `review_invoice()`, que orquesta la transición, la revisión y la auditoría;
- `validation_summary()`, que delega en `calculate_score`.

Los routers quedan como traducción HTTP ↔ servicio. Ningún servicio hace `commit`: el router confirma, y `get_db` revierte al cerrar si hubo excepción. `run_validation` pierde su `commit` y el seed se ajusta.

### D14. Consultas en el repositorio
- **`invoice_repository.search_invoices(db, user, q, status, page, per_page=25) -> Page`:** `join(Supplier)` con `contains_eager` para la búsqueda por razón social, sin N+1. `ilike` con escape de `%`, `_` y `\`. Una consulta `count()` separada para la paginación.
- **`status_counts()` y `total_amount()`:** `GROUP BY` y `SUM` sobre centavos, que es exacto por D2.
- **`/admin/audit`:** paginación `LIMIT/OFFSET`, 50 por página.

La prueba de N+1 cuenta las sentencias con un listener `before_cursor_execute`.

### D15. Log JSON con biblioteca estándar
`JsonFormatter` propio en `logging_config.py`:
- campos base más los atributos `extra` no estándar;
- `request_id` y `user_id` desde `ContextVar`;
- rotación de 2 MB × 3.

Los eventos usan nombres estables (`document.uploaded`, `validation.started`, `validation.completed`, `review.decided`, `xml.parse_failed`, `pdf.analysis_failed`, `login.locked`). Sus campos excluyen explícitamente RFC, nombres de archivo y cualquier secreto. Los logs de uvicorn conservan su formato propio.

*Alternativas:* `structlog` o `python-json-logger`. No hacen falta para un formateador de unas 30 líneas.

### D16. Configuración anclada y validada
- `BASE_DIR = Path(__file__).resolve().parents[2]`.
- `model_config.env_file = BASE_DIR / ".env"`.
- Validadores de `Settings`:
  - resuelven `storage_path`, `log_dir` y la ruta relativa de `sqlite:///` contra `BASE_DIR`;
  - validan `app_env` ∈ {`development`, `test`, `production`};
  - rechazan `secret_key` ausente, de menos de 32 caracteres o con prefijo `change-me`;
  - derivan el valor por defecto de `session_https_only` de `app_env`.
- `debug` sólo ajusta el nivel de log.
- `StaticFiles` y `Jinja2Templates` usan rutas absolutas.
- Se mantiene el singleton `settings` más `get_settings()`. Las pruebas definen las variables de entorno antes de importar la app y usan `monkeypatch` para alternar `app_env`. Se descarta inyectar `Depends(get_settings)` en todos los endpoints, porque no aporta nada con este patrón de prueba.
- Las verificaciones de producción (usuarios `@poc.local` activos, `SESSION_HTTPS_ONLY=false`) corren en el `lifespan` y abortan el arranque.

### D17. Credenciales demo y contraseñas
- `app/core/demo.py` define `DEMO_ACCOUNTS`, la única fuente para el seed y para el bloque de acceso rápido. Ese bloque se renderiza sólo si `app_env == "development"`.
- Contraseñas demo nuevas, conformes a RF-06 y ausentes de la lista común: `Admin#Demo2026`, `Pmo#Demo2026` y `Proveedor#Demo2026`.
- Fuera de `development`, el seed genera contraseñas con `secrets.token_urlsafe` más los caracteres requeridos y las imprime una vez.
- `app/core/passwords.py`: `validate_password()` aplica RF-06, límite superior de 128 y la lista `common_passwords.txt` (unas 1,000 entradas de una lista pública, comparación sin distinguir mayúsculas).
- Longitud mínima de 8 según la ERS; la auditoría sugería 12 (ver Open Questions).
- `EmailStr` en las altas.
- Los formularios de alta se validan con modelos Pydantic (`UserCreate`, `SupplierCreate` e `InvoiceCreate`, ya existente). Los errores se re-renderizan con HTTP 400.

### D18. Trazabilidad de contratos
- `contracts` recibe `created_at`, `created_by`, `updated_at` y `updated_by`.
- Tabla `contract_amendments`:

  | Columna | Detalle |
  |---|---|
  | `id` | |
  | `contract_id` | FK |
  | `previous_amount_cents` | |
  | `new_amount_cents` | `CHECK > 0` |
  | `reason` | not null |
  | `created_by` | FK |
  | `created_at` | |

- Endpoint ADMIN `POST /contracts/{id}/amendments`: crea la enmienda, actualiza `authorized_amount`, `updated_*` y audita `CONTRACT_AMOUNT_CHANGED` con old/new, todo en una transacción.
- FIN-001 añade a su evidencia `authorized_amount` y `amendment_id`, que es la última enmienda o `null`.

### D19. Operación: scripts multiplataforma en Python
Los scripts de soporte se escriben en Python, así sirven igual en Windows y Linux:

| Script | Función |
|---|---|
| `create_env.py` | Copia `.env.example` y genera `SECRET_KEY` sólo si `.env` no existe. |
| `init_db.py` | `alembic upgrade head` y seed sólo si la BD está vacía; deja de usar `create_all`. |
| `backup.py` | `sqlite3.Connection.backup()`, ZIP de `storage/`, `manifest.json` con SHA-256 y retención. |
| `restore_backup.py` | Verifica hashes, exige `--yes` y respalda el estado actual antes de restaurar. |
| `package_release.py` | Usa `git ls-files` si hay Git y, si no, una lista de exclusión. Verifica el ZIP después de generarlo. |

- `run_local.{sh,ps1,bat}` ejecutan `create_env` → `init_db` → uvicorn y ya no llaman a `reset_demo`.
- `reset_demo.py` se modifica: detecta datos no-demo, exige confirmación o `--yes`, respalda antes de borrar y elimina `-wal`/`-shm`.

### D20. Calidad y CI
- **`pyproject.toml`** en la raíz de la PoC:
  - ruff: `line-length=120`, reglas `E, F, W, I`;
  - pytest: `addopts` con `--cov=app --cov-fail-under=<umbral>`;
  - coverage: `source`, excluyendo sólo `if TYPE_CHECKING`.
- **`requirements.lock`** generado con `uv pip compile --universal --generate-hashes --python-version 3.12`. Se prefiere a `pip-compile` porque este sólo resuelve la plataforma actual: omitiría dependencias exclusivas de Windows (`colorama`) y `pip install --require-hashes` fallaría ahí.
- **Resultado de `pip-audit` (2026-09-24):** hubo avisos en `starlette` 0.47.3 (el arreglo exige 1.3.1, lo que obliga a subir `fastapi` a 0.133.1, la mínima compatible), `lxml` 6.0.1, `python-dotenv` 1.1.1, `python-multipart` 0.0.20 y, en dev, `pytest` 8.4.2 (con `pytest-asyncio` 1.3.0 por compatibilidad). Se subió cada paquete a la versión corregida, la suite pasa sin cambios y el lock queda sin avisos conocidos.
- **`tests/conftest.py`**, antes de importar `app`: fija `SECRET_KEY` aleatoria, `APP_ENV=test`, `DATABASE_URL` y `STORAGE_PATH` bajo `tmp_path_factory`, y ejecuta `alembic upgrade head` y el seed sobre esa BD. Las pruebas localizan los datos por `invoice_number` o `email`, nunca por `id`.
- **Ajustes al seed para permitir el aislamiento:**
  - `seed_db.main(passwords=None)` acepta contraseñas explícitas, que las pruebas usan porque en `APP_ENV=test` serían aleatorias;
  - escribe en `settings.storage_path` y no en `ROOT/storage`;
  - genera sus archivos intermedios (`_seed_N.xml`, PDF demo) en un directorio temporal, sin reescribir `data/demo_documents/factura_demo.pdf`, que está versionado.
- **Reloj inyectable:** `login_throttle` y `session_service` reciben un reloj (`now: Callable[[], datetime]`) para probar ventanas y expiraciones sin esperar.
- **CI:** se conserva el pipeline compartido del equipo (`.github/workflows/calidad.yml`, SonarQube), que indica no duplicar lógica en el repositorio; no se crea un workflow propio (decisión del equipo, 2026-09-24). `pytest` genera el `coverage.xml` que consume. Las verificaciones completas (`ruff check`, `ruff format --check`, `alembic check` sobre una BD temporal, `pytest` con umbral y `pip-audit -r requirements.lock`) se ejecutan con `python scripts/check.py`.

### D21. Retiro del ZIP y del caché de PowerShell
`git rm` de `PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress-V1.zip` y de `Microsoft/Windows/PowerShell/ModuleAnalysisCache`. Se añaden `Microsoft/`, `backups/` y `data/*.db-*` a `.gitignore`. Los paquetes se generan bajo demanda con `package_release.py` y no se versionan. Los datos del ZIP son sintéticos y su `SECRET_KEY` es el placeholder que este cambio invalida, así que el impacto residual del historial es bajo.

## Risks / Trade-offs

- **[Cambio amplio en un solo change]** → Grupos de tareas por fase, cada uno cerrado con la suite verde y un commit propio. Las fases 0 y 1 son desplegables sin la 2.
- **[La migración 0003 reconstruye tablas en SQLite (batch)]** → Respaldo obligatorio antes de `upgrade` (ver Migration Plan), precondiciones que abortan sin tocar datos, `foreign_key_check` al final, y prueba automatizada de upgrade desde una BD sembrada con el esquema 0001.
- **[`UNIQUE(uuid)` impide re-registrar un CFDI de una factura `REJECTED`]** → El flujo de corrección reutiliza la misma factura (`REQUIRES_CORRECTION`). Confirmar con Facturación (Open Questions).
- **[`UNIQUE(supplier_id, invoice_number)` cambia un `ERROR` blando (FIN-005) por un rechazo en el alta]** → Mensaje claro en el formulario. FIN-005 se conserva como verificación informativa en validación.
- **[La CSP rompe cualquier script o estilo en línea futuro]** → Queda documentado en el README. La prueba de cabeceras y de las páginas principales detecta regresiones.
- **[Bloqueo de cuenta usable para negar el acceso a una víctima]** → Inherente al mecanismo. Se limita a 60 minutos, los intentos durante el bloqueo no lo extienden y existe límite por IP. Desactivar la cuenta sigue siendo la palanca del ADMIN.
- **[IP real detrás de un proxy]** → Sin `--proxy-headers`, todas las peticiones comparten la IP del proxy y el límite por IP se vuelve global. Queda documentado para el despliegue.
- **[Escrituras en `user_sessions` en cada petición]** → Actualización limitada a una por minuto; WAL mantiene las lecturas concurrentes.
- **[Umbral de cobertura ≥ 80 % inalcanzable por los adaptadores Azure]** → Se prueban sus rutas de "no configurado". Si aun así no se alcanza, se documenta la diferencia y se fija el umbral medido; nunca se excluyen módulos.
- **[`pip-audit` puede exigir actualizar dependencias con cambios de comportamiento]** → Se actualiza sólo lo señalado, con la suite completa como red. Las excepciones se justifican en el archivo de configuración de `pip-audit`.
- **[`tzdata` ausente en Windows]** → Se declara en `requirements.txt` y en el lock.

## Migration Plan

**Despliegue sobre una instalación existente:**
1. `python scripts/backup.py`. Si el script aún no existe en la versión instalada, copiar con la aplicación detenida `data/invoice_portal.db*` y `storage/`.
2. Detener la aplicación.
3. Actualizar el código e instalar dependencias: `pip install --require-hashes -r requirements.lock`.
4. Definir `SECRET_KEY` en `.env`, o dejar que `scripts/create_env.py` la genere en entornos locales. Revisar `APP_ENV` y `SESSION_HTTPS_ONLY`.
5. `alembic upgrade head`. Si una precondición aborta, corregir los datos reportados y repetir; la base sigue en la revisión anterior.
6. Arrancar la aplicación. Todas las sesiones previas quedan inválidas, así que los usuarios vuelven a iniciar sesión.
7. En `production`, confirmar que el arranque no reporta cuentas `@poc.local` activas.

**Rollback:** detener la aplicación, restaurar el respaldo del paso 1 con `scripts/restore_backup.py --yes` o por copia manual, y desplegar la versión anterior del código. Los downgrades con pérdida de datos lanzan `NotImplementedError` por diseño.

## Open Questions

1. **Historial de Git:** ¿se purga el ZIP del historial (`git filter-repo` y *force push* a `origin`)? Requiere la aprobación del dueño del repositorio y coordinarse con los clones existentes. Este cambio sólo lo retira del árbol.
2. **Reutilización de UUID:** ¿puede un CFDI de una factura `REJECTED` volver a registrarse en una factura nueva? El diseño actual lo impide, en línea con la ERS RN-HU13-01.
3. **Longitud mínima de contraseña:** 8 (ERS RF-06, adoptado) o 12 (recomendación de la auditoría). Cambiarlo es una constante.
4. **Numeración del folio:** ¿debe reiniciarse cada año? Si es así, se sustituye D12 por `folio_counters`.
5. **BD de producción:** cuando se decida PostgreSQL/Azure SQL, planear la migración de `*_cents` a `NUMERIC` (D2).
6. **Estados de proveedor:** la ERS introduce "Autorizado" (HU-02). Este cambio sólo tipa `ACTIVE`/`INACTIVE`; el MVP ampliará la enumeración con su propia migración.
