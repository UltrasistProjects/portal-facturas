# Auditoría Técnica — Portal Interno de Facturas (PoC Ultrasist)

**Fecha:** 2026-09-22  ·  **Alcance:** `PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress/`

**Stack:** Python 3.12 · FastAPI 0.116.1 · SQLAlchemy 2.0.43 (ORM) · Jinja2 server-rendered · SQLite embebida · Alembic 1.16.5 · pwdlib/Argon2

**Método:** lectura estática del 100% del código de `app/`, `tests/`, `scripts/`, `alembic/`; extracción del esquema real vía `sqlite_master` y `PRAGMA` sobre `data/invoice_portal.db`; inspección de datos y logs. **No se ejecutó la aplicación** (no hay `.venv` en el paquete entregado) ni escáner de dependencias.

---

## 1. Resumen ejecutivo

El proyecto está **notablemente bien estructurado para una PoC**: la separación en capas es real y la dirección de dependencias se respeta casi sin excepciones, el acceso a datos es 100% ORM parametrizado (sin SQL concatenado en ninguna parte), CSRF está presente en todos los formularios mutables, las contraseñas usan Argon2 y el parser CFDI está endurecido contra XXE. El README documenta sus propias limitaciones con honestidad poco común.

Los problemas críticos no están en el diseño sino en **la configuración de seguridad y en la capa de persistencia**:

1. **`SECRET_KEY` con valor por defecto público** (`change-me-use-a-long-random-value`), hardcodeado en el código *y* en `.env` *y* en `.env.example`. Firma las cookies de sesión → cualquiera que conozca el valor forja una sesión de ADMIN. **Crítica.**
2. **`DEBUG=true`** entregado en `.env` y pasado a `FastAPI(debug=...)`; en Starlette el flag `debug` **tiene precedencia sobre el handler de excepciones**, anulando la protección contra fugas de stack trace que el README afirma tener. **Crítica.**
3. **`PRAGMA foreign_keys` nunca se activa** (verificado: `PRAGMA foreign_keys = 0` en la BD, cero ocurrencias en el código). Las 13 llaves foráneas declaradas son **decorativas**; SQLite no las enforza. **Alta.**
4. **Los montos se almacenan como punto flotante.** `Numeric(16,2)` en SQLite se persiste como `REAL` (confirmado: `typeof(confidence) = 'real'`). Aritmética de dinero en binario flotante en un sistema fiscal. **Alta.**
5. **La "migración" Alembic es `Base.metadata.create_all()`** — no hay historial de esquema, no hay forma de evolucionar la BD, y `downgrade()` es un `drop_all()` que destruye todo. **Alta.**

**Veredicto:** arquitectura sólida, base de datos y hardening inmaduros. No apto para recibir documentos fiscales reales sin remediar los 5 puntos anteriores.

---

## 2. Calificación por área

| Área | Calificación | Justificación en una línea |
|---|:---:|---|
| **Calidad del código** | **3.5 / 5** | Capas bien separadas y reglas como funciones puras, pero hay lógica de negocio en routers, filtrado en memoria, código muerto y una densidad de líneas que daña la legibilidad. |
| **Calidad de la base de datos** | **2.5 / 5** | Modelo en 3FN con PKs e índices razonables, pero integridad referencial no enforzada, dinero en flotante, cero `CHECK`, sin WAL y sin migraciones reales. |
| **Seguridad del sistema** | **2.5 / 5** | Excelentes fundamentos (ORM parametrizado, CSRF, Argon2, XXE-safe, RBAC con scoping por proveedor) anulados por `SECRET_KEY` por defecto y `DEBUG=true` en el paquete entregado. |

Desglose de apoyo:

| Sub-área | Cal. | Nota |
|---|:---:|---|
| Separación de capas | 4 / 5 | Dirección de dependencias correcta; fugas menores hacia routers. |
| Pruebas | 2 / 5 | 14 pruebas reales pero cero cobertura de upload, revisión y permisos de documentos; sin herramienta de cobertura. |
| Manejo de errores y logging | 2.5 / 5 | Excepciones estrechas y bien tipadas, pero logging casi inexistente y errores de máquina de estados terminan en HTTP 500. |
| Configuración / operación | 2 / 5 | Sin lock file, sin separación por ambiente, rutas relativas al CWD, sin respaldos. |

---

## 3. Hallazgos por área

Cada hallazgo indica si está **[CONFIRMADO]** (verificado sobre código, esquema o datos) o **[SOSPECHA]** (requiere validación en ejecución).

---

### 3.A — Seguridad

---

#### SEC-01 · `SECRET_KEY` por defecto y público firma las sesiones — **Crítica** · [CONFIRMADO]

**Descripción.** La clave que firma las cookies de sesión tiene el mismo valor placeholder en tres lugares: como default del modelo de configuración, en `.env.example` y en el `.env` que viene dentro del paquete entregado. No hay validación que impida arrancar con ella.

**Evidencia.**

```
app/core/config.py:12    secret_key: str = "change-me-use-a-long-random-value"
.env:4                   SECRET_KEY=change-me-use-a-long-random-value
.env.example:4           SECRET_KEY=change-me-use-a-long-random-value
app/main.py:26           app.add_middleware(SessionMiddleware, secret_key=settings.secret_key, ...)
```

La sesión sólo contiene `{"user_id": N, "csrf_token": "..."}` (ver `app/core/security.py:38-44`), y `get_current_user` confía en ese `user_id` sin más verificación.

**Impacto.** Un atacante con acceso de red al puerto construye una cookie `itsdangerous` firmada con la clave conocida, poniendo `user_id: 1` (el ADMIN sembrado). Obtiene: alta de usuarios, alta de contratos con montos autorizados arbitrarios, lectura del expediente completo de todos los proveedores y del Audit Log. Es una **escalada a administrador sin credenciales**. Borrar `.env` no ayuda: el default está en el código.

**Recomendación.**

1. Eliminar el valor por defecto de `config.py:12` y hacerlo obligatorio: `secret_key: str` sin default, de modo que la app **no arranque** sin una clave provista.
2. Añadir un `field_validator` que rechace el valor `change-me-*` y longitudes < 32 bytes.
3. Generar la clave con `secrets.token_urlsafe(64)`; en producción, desde Azure Key Vault o variable de entorno del host, nunca de un archivo en el repositorio.
4. Rotar la clave invalida todas las sesiones — documentarlo como procedimiento.

---

#### SEC-02 · `DEBUG=true` anula el handler de errores y expone stack traces — **Crítica** · [SOSPECHA — alta confianza]

**Descripción.** `.env` entrega `DEBUG=true`, que llega a `FastAPI(debug=settings.debug)`. El proyecto registra un handler global de `Exception` que devuelve una página genérica (`app/main.py:48-52`), y el README afirma en la línea 134 *"Errores sin stack trace en UI"*. Pero en Starlette, `ServerErrorMiddleware` evalúa `if self.debug:` **antes** de `else: self.handler(...)` — con `debug=True` el handler personalizado nunca se ejecuta y se devuelve la página de traceback interactiva, que incluye código fuente y variables locales de cada frame.

**Evidencia.**

```
.env:3                   DEBUG=true
app/core/config.py:11    debug: bool = True
app/main.py:25           app = FastAPI(title=settings.app_name, debug=settings.debug, lifespan=lifespan)
app/main.py:48-52        @app.exception_handler(Exception)  <- anulado mientras debug=True
README.md:134            "- Errores sin stack trace en UI; detalle técnico en logs/app.log."
```

**Por qué es explotable y no teórico:** existe un camino de disparo alcanzable por usuario autenticado. `transition_invoice` lanza `ValueError` ante una transición no permitida (`app/services/invoice_service.py:10-11`) y **ningún router lo captura**:

```
app/routers/invoices.py:157   transition_invoice(db, invoice, InvoiceStatus.UNDER_REVIEW, user.id)   # /submit
app/routers/invoices.py:187   transition_invoice(db, invoice, target, user.id)                       # /clickbalance
```

Un `POST /invoices/{id}/submit` sobre una factura en `DRAFT` (p. ej. la factura 1 del seed) produce `ValueError` → excepción no manejada → traceback completo.

**Impacto.** Divulgación de rutas absolutas del host, versiones de librerías, fragmentos de código fuente y valores de variables locales (que en este punto del stack incluyen el objeto `Invoice` y el `User` autenticado). Facilita el encadenamiento con SEC-01.

**Validación pendiente.** Reproducir con `curl -X POST .../invoices/1/submit` con sesión válida y CSRF. Se marca como sospecha por no haberse ejecutado, pero la precedencia de `debug` en `ServerErrorMiddleware` es comportamiento documentado de Starlette.

**Recomendación.**

1. `DEBUG=false` por defecto en `config.py` y en `.env.example`; que `true` requiera acción explícita del desarrollador.
2. Desacoplar: no pasar `debug` a `FastAPI(...)`. Si se quiere traceback en desarrollo, hacerlo condicional a `app_env == "development"` y nunca acoplado al flag que usa el middleware.
3. Independientemente de lo anterior, **capturar `ValueError` en los routers** y traducirlo a `HTTPException(409, ...)`. Un error de máquina de estados es un error de negocio, no un fallo del servidor.

---

#### SEC-03 · Credenciales demo publicadas en el HTML servido a usuarios anónimos — **Alta** · [CONFIRMADO]

**Descripción.** La página de login incluye botones con las contraseñas en texto plano en un atributo `data-*`, servidos a cualquier visitante sin autenticar. Las mismas credenciales están en el README y en el seed.

**Evidencia.**

```
app/templates/auth/login.html:11
  <button type="button" data-demo="admin@poc.local|Admin123!">Administrador</button>
  <button type="button" data-demo="pmo@poc.local|Pmo123!">PMO</button>
  <button type="button" data-demo="proveedor1@poc.local|Proveedor123!">Proveedor</button>

app/static/js/app.js:1-5      lee data-demo y rellena el formulario
README.md:56-61               tabla de credenciales
scripts/seed_db.py:65-68      hash_password("Admin123!") / ("Pmo123!") / ("Proveedor123!")
```

Confirmado en la BD: los 4 usuarios sembrados están activos con esos hashes Argon2 (`users` id 1-4, `is_active=1`).

**Impacto.** Si la instancia se expone más allá de `127.0.0.1` — y `run_local.ps1` se limita a localhost, pero nada impide otro binding — el acceso ADMIN es trivial. Además, estas cuentas sobreviven a cualquier despliegue que reutilice el seed.

**Recomendación.**

1. Condicionar el bloque de credenciales rápidas a `settings.app_env == "development"` en la plantilla.
2. Que `seed_db.py` genere contraseñas aleatorias y las imprima una sola vez en consola, o las tome de variables de entorno.
3. Añadir al arranque una verificación que aborte si `app_env != "development"` y existe algún usuario `@poc.local`.

---

#### SEC-04 · Sin límite de intentos ni bloqueo de cuenta en el login — **Media** · [CONFIRMADO]

**Descripción.** `POST /login` no tiene rate limiting, throttling, bloqueo tras N fallos ni CAPTCHA. El intento fallido se audita pero no se cuenta.

**Evidencia.** `app/routers/auth.py:23-36` — el flujo es `verificar → auditar LOGIN_FAILED → devolver 400`. No hay middleware de rate limiting en la aplicación (`grep add_middleware` devuelve únicamente `SessionMiddleware`). En `audit_logs` hay registros `LOGIN_FAILED` pero nada los consulta.

**Impacto.** Fuerza bruta sobre cuentas conocidas. Argon2 encarece cada intento (mitigación parcial y, a la vez, vector de agotamiento de CPU: cada intento fallido cuesta ~65 MB y varios ms de CPU, por lo que el propio login es un blanco de DoS).

**Recomendación.** `slowapi` o middleware propio con ventana deslizante por IP **y** por email; bloqueo temporal exponencial tras 5 fallos; alerta cuando `LOGIN_FAILED` para un mismo email supere un umbral — la tabla de auditoría ya tiene los datos, sólo falta consultarla.

---

#### SEC-05 · Sin cabeceras de seguridad HTTP — **Media** · [CONFIRMADO]

**Descripción.** No se emite `Content-Security-Policy`, `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy` ni `Strict-Transport-Security`.

**Evidencia.** El único middleware registrado es `SessionMiddleware` (`app/main.py:26`). `grep -rn "CORSMiddleware\|TrustedHost\|X-Frame\|Content-Security"` sobre `app/` no devuelve nada.

**Impacto.** Clickjacking sobre las acciones de aprobación/rechazo de factura (un iframe invisible sobre `/invoices/{id}/review` es el escenario de riesgo real aquí); MIME sniffing sobre documentos descargados; ausencia de CSP como segunda línea de defensa ante un futuro XSS.

**Nota a favor:** la ausencia de `CORSMiddleware` es **correcta** — es una app server-rendered de mismo origen; añadir CORS permisivo sería un retroceso.

**Recomendación.** Un middleware pequeño que añada: `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin`, y `Content-Security-Policy: default-src 'self'` (viable sin fricción: todos los assets son locales bajo `app/static/vendor/`, no hay CDN). `HSTS` sólo cuando se sirva por TLS.

---

#### SEC-06 · Validación de archivos subidos basada en metadatos controlados por el cliente — **Media** · [CONFIRMADO]

**Descripción.** El filtro de subida confía en la extensión del nombre de archivo y en el `Content-Type` que envía el navegador. `application/octet-stream` está en la lista blanca, lo que hace que el chequeo MIME sea efectivamente opcional. Sólo el XML recibe una verificación de contenido (y es mínima: que empiece con `<`).

**Evidencia.**

```
app/services/file_service.py:14-15
  ALLOWED_EXTENSIONS = {".xml", ".pdf", ".txt", ".png", ".jpg", ".jpeg"}
  ALLOWED_MIMES = {..., "application/octet-stream"}      <- comodín efectivo
app/services/file_service.py:41   extension = Path(original).suffix.lower()      <- del nombre
app/services/file_service.py:44   mime = (upload.content_type or ...)            <- del cliente
app/services/file_service.py:52   if extension == ".xml" and not content.lstrip().startswith(b"<")
```

No hay verificación de magic bytes para PDF/PNG/JPG, ni escaneo antimalware.

**Impacto.** Se puede almacenar contenido arbitrario bajo una extensión permitida (p. ej. un ejecutable como `contrato.pdf`). El riesgo de XSS almacenado está **mitigado**: `FileResponse` con parámetro `filename=` emite `Content-Disposition: attachment` (`app/routers/invoices.py:136`), por lo que el navegador descarga en vez de renderizar. El riesgo residual es distribución de malware entre usuarios internos que abran los adjuntos, y el `media_type=doc.mime_type` propaga al descargador un MIME que el proveedor eligió.

**Aspectos correctos que conviene destacar:** nombre de almacenamiento por `uuid4().hex` (no se reutiliza el nombre del cliente), verificación explícita de path traversal (`app/services/file_service.py:55-57`), `entity_id` forzado a `int`, límite de tamaño con lectura acotada (`read(max+1)` — evita agotar memoria), SHA-256 registrado, y `safe_download_name()` saneando el nombre de descarga. Es un diseño de almacenamiento mejor que el promedio.

**Recomendación.**

1. Quitar `application/octet-stream` de `ALLOWED_MIMES`.
2. Verificar magic bytes: `%PDF-` para PDF, `\x89PNG`, `\xff\xd8\xff` para JPEG; rechazar si no coincide con la extensión.
3. Servir siempre con `media_type="application/octet-stream"` en la descarga en lugar del MIME almacenado.
4. Para producción: escaneo antimalware antes de marcar `processing_status="PROCESSED"` (ya está en la lista de "próximos pasos" del README).

---

#### SEC-07 · Sin invalidación de sesión del lado del servidor — **Media** · [CONFIRMADO]

**Descripción.** La sesión vive enteramente en una cookie firmada (no cifrada). `logout` sólo limpia la cookie del cliente; no existe registro de sesiones activas. Una cookie capturada sigue siendo válida durante sus 8 horas completas aunque el usuario cierre sesión.

**Evidencia.**

```
app/main.py:26-27    max_age=8 * 60 * 60, same_site="lax", https_only=settings.session_https_only
.env:9               SESSION_HTTPS_ONLY=false
app/routers/auth.py:46   request.session.clear()   <- sólo lado cliente
```

**Impacto.** Ventana de reutilización de cookie robada de hasta 8 horas sin posibilidad de revocar. Con `SESSION_HTTPS_ONLY=false`, la cookie viaja en claro si se sirve por HTTP.

**Mitigación existente:** `get_current_user` recarga el usuario desde BD y comprueba `is_active` en cada petición (`app/core/security.py:41-43`), por lo que deshabilitar la cuenta **sí** corta el acceso de inmediato. Esa es la palanca de revocación disponible hoy.

**Recomendación.** Para producción: sesiones del lado del servidor (tabla `sessions` o Redis) con un `session_id` opaco en la cookie; `SESSION_HTTPS_ONLY=true`; reducir `max_age` a 1-2 h con renovación por actividad.

---

#### SEC-08 · Sin política de contraseñas en el servidor — **Media** · [CONFIRMADO]

**Descripción.** El alta de usuarios acepta cualquier cadena como contraseña. La única restricción es `minlength="8"` en el atributo HTML, trivialmente evitable con una petición directa.

**Evidencia.**

```
app/routers/admin.py:23-26
  async def create_user(..., password: str = Form(...), ...):
      created = User(..., password_hash=hash_password(password), ...)
app/templates/admin/users.html   <input type="password" name="password" minlength="8" ...>
```

Existe además una clase `InvoiceCreate` en `app/schemas/__init__.py` con validación Pydantic **que nunca se usa** (ver COD-03), y `email-validator==2.2.0` está en `requirements.txt` pero `EmailStr` no se importa en ninguna parte de `app/`.

**Impacto.** Cuentas con contraseña de un carácter. Ningún endpoint de cambio de contraseña existe, así que una contraseña débil es permanente.

**Recomendación.** Validar en el servidor con Pydantic (la infraestructura ya está instalada y sin usar): longitud mínima 12, y contraste contra una lista de contraseñas comunes. Usar `EmailStr` en `create_user` y `create_supplier`.

---

#### SEC-09 · El paquete distribuido incluye `.env`, la BD poblada y los logs — **Media** · [CONFIRMADO]

**Descripción.** `.gitignore` excluye correctamente `.env`, `data/*.db`, `storage/*` y `logs/*`, pero el ZIP entregado los contiene igualmente.

**Evidencia.** Presentes en el paquete: `.env` (con `SECRET_KEY`), `data/invoice_portal.db` (204 800 bytes, 4 usuarios con hashes Argon2, 10 facturas, 59 registros de auditoría, 51 documentos), `logs/app.log`, `logs/uvicorn_dev.log`, `.pytest_cache/`, `Microsoft/Windows/PowerShell/ModuleAnalysisCache`, y 51 archivos reales bajo `storage/`. El directorio no es un repositorio Git, así que `.gitignore` no ejerce ningún efecto sobre la distribución.

**Impacto.** Con datos sintéticos el daño hoy es nulo. El problema es el **proceso**: el mismo mecanismo de empaquetado, aplicado tras una demo con documentos reales de proveedor, distribuiría RFC, datos bancarios y facturas.

**Recomendación.** Script de empaquetado que respete `.gitignore` (`git archive` si se versiona, o una lista de exclusión explícita). Añadir `Microsoft/` y `.pytest_cache/` a `.gitignore`.

**A favor:** los logs están limpios — `grep -i "password|rfc|secret"` sobre `logs/*.log` devuelve **0 coincidencias**. No hay fuga de datos sensibles al log.

---

#### SEC-10 · Sin cifrado en reposo del archivo SQLite — **Baja** (en el contexto actual) · [CONFIRMADO]

**Evidencia.** `data/invoice_portal.db` es SQLite estándar sin cifrado. ACL en la máquina auditada: `SYSTEM:(F)`, `Administrators:(F)`, `jobhd:(F)` — sin acceso para `BUILTIN\Users`, lo cual es **adecuado** para una ejecución local mono-usuario.

**Impacto.** Hoy contiene únicamente datos demo. Para operación real, el archivo contendría RFC, razones sociales, montos y `bank_information` (campo ya presente en el modelo, `app/models/__init__.py:45`) en texto plano, junto con todos los archivos de `storage/`.

**Recomendación.** Con datos reales: cifrado de volumen (BitLocker/LUKS) como mínimo, o la migración a Azure SQL/PostgreSQL con TDE que ya está prevista en el README.

---

#### SEC-11 · Dependencias: **no evaluable** con los medios disponibles · [NO EVALUADO]

No se pudo ejecutar `pip-audit` ni `safety` (sin entorno virtual en el paquete y sin acceso a la base de datos de vulnerabilidades). **No afirmo que las dependencias sean seguras ni que sean vulnerables.**

Lo que sí es verificable estáticamente:

- **Sin lock file.** No existe `requirements.lock`, `poetry.lock` ni hashes. Las versiones directas están fijadas con `==`, pero las transitivas flotan.
- **`starlette` no está fijado** y es la dependencia con mayor superficie de seguridad del proyecto (sesiones, middleware, manejo de errores, `StaticFiles`). Su versión la resuelve el rango de FastAPI, por lo que dos instalaciones en fechas distintas pueden diferir.
- Las versiones directas corresponden a lanzamientos de mediados de 2025 — al corte de esta auditoría (2026-09) llevan **más de un año sin actualizar**.

**Recomendación.** `pip-audit` en CI; `pip freeze > requirements.lock` con hashes; fijar `starlette==` explícitamente; revisión trimestral de versiones. **Ejecutar `pip-audit` es el primer quick win de este reporte** — es barato y cierra la única área que no pude evaluar.

---

### 3.B — Base de datos

---

#### BD-01 · Las llaves foráneas no se enforzan — **Alta** · [CONFIRMADO]

**Descripción.** El esquema declara 13 llaves foráneas, pero SQLite las ignora salvo que cada conexión ejecute `PRAGMA foreign_keys = ON`. No existe ningún `event.listens_for(engine, "connect")` que lo haga.

**Evidencia.**

```
PRAGMA foreign_keys  ->  0        (verificado sobre data/invoice_portal.db)
grep -rn "foreign_keys" *.py  ->  una sola coincidencia, y es el parámetro
                                  foreign_keys=[invoice_id] de una relationship ORM,
                                  no el PRAGMA (app/models/__init__.py:122)
app/core/database.py:19-22        create_engine(...) sin listener de conexión
```

FKs declaradas y no enforzadas: `users.supplier_id`, `contracts.supplier_id`, `invoices.supplier_id`, `invoices.uploaded_by`, `invoices.contract_id`, `invoices.reviewed_by`, `documents.invoice_id`, `documents.supplier_id`, `documents.uploaded_by`, `documents.replaced_document_id`, `validation_results.invoice_id`, `reviews.invoice_id`, `reviews.reviewer_id`, `audit_logs.user_id`.

**Impacto.** La integridad referencial depende íntegramente de que el código ORM no se equivoque. Se pueden insertar facturas con `supplier_id` inexistente, documentos huérfanos o revisiones apuntando a un usuario eliminado — sin error. Cualquier script, migración o intervención manual por `sqlite3` rompe la consistencia silenciosamente. El `cascade="all, delete-orphan"` declarado en `Invoice.documents/validations/reviews` es **exclusivamente ORM**: un `DELETE` en SQL deja huérfanos.

**Recomendación.**

```python
from sqlalchemy import event

@event.listens_for(engine, "connect")
def _sqlite_pragmas(dbapi_conn, _):
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA foreign_keys=ON")
    cur.close()
```

Antes de activarlo, verificar que no haya ya filas huérfanas (`PRAGMA foreign_key_check`). Añadir el mismo listener en `alembic/env.py` y en `conftest.py`.

---

#### BD-02 · Los montos se almacenan como punto flotante — **Alta** · [CONFIRMADO]

**Descripción.** Todas las columnas monetarias usan `Numeric(16,2)`. SQLite no tiene tipo decimal nativo; SQLAlchemy convierte el `Decimal` a `float` al escribir y aplica un formateo `%.2f` al leer. El almacenamiento físico es IEEE-754 binario.

**Evidencia.** Verificación directa sobre la BD:

```sql
SELECT DISTINCT confidence, typeof(confidence) FROM validation_results;
-- (0.93, 'real')                     <- Numeric(5,4) persistido como REAL

SELECT DISTINCT total, typeof(total) FROM invoices;
-- (0,'integer'), (116000,'integer'), (136880,'integer')
```

Los valores de `invoices` aparecen como `integer` sólo porque la afinidad `NUMERIC` de SQLite colapsa `116000.0` a entero; en cuanto un monto tenga centavos se almacenará como `REAL`, exactamente igual que `confidence`. Columnas afectadas: `invoices.subtotal`, `invoices.tax`, `invoices.total`, `contracts.authorized_amount`, `validation_results.confidence`.

El problema se propaga al código: `app/routers/invoices.py:81` hace `Decimal(invoice.contract.authorized_amount)` y `app/rules/financial_rules.py:7-10` construye `Decimal` a partir de valores que provienen de la BD.

**Impacto.** La regla **FIN-001 es el control financiero central** del portal (*el subtotal no debe exceder el monto autorizado*) y **FIN-002** compara `|subtotal + tax − total| ≤ 0.02`. Ambas operan sobre valores que atravesaron representación binaria. En el límite exacto (subtotal idéntico al autorizado) el resultado de la comparación depende del redondeo — una factura en el límite puede aprobarse o bloquearse de forma no determinista. Cualquier `SUM()` hecho en SQL acumularía error.

**Matiz honesto:** el procesador de resultados de SQLAlchemy reformatea a 2 decimales al leer, así que los valores con centavos sobreviven el viaje de ida y vuelta. El riesgo no es corrupción visible de datos, sino **aritmética y comparaciones en flotante en el motor de decisión financiera**, más agregaciones SQL futuras.

**Recomendación.** Dos opciones, en orden de preferencia:

1. **Enteros en centavos:** `subtotal_cents: Mapped[int]`, conversión a `Decimal` en una sola capa de frontera. Exacto, ordenable e indexable. Requiere migración de datos.
2. **Texto decimal:** `String(20)` con `Decimal` en la capa de aplicación. Exacto pero no ordenable ni agregable en SQL.

Si el plan es migrar a PostgreSQL/Azure SQL (como indica el README), `NUMERIC` allí es decimal real y el problema desaparece — pero entonces conviene decidirlo **ahora**, porque el formato de almacenamiento condiciona la migración.

---

#### BD-03 · La migración Alembic no es una migración — **Alta** · [CONFIRMADO]

**Descripción.** La única revisión existente llama a `create_all()` sobre los metadatos actuales del ORM, y su `downgrade()` es `drop_all()`.

**Evidencia.**

```python
# alembic/versions/0001_initial.py:10-14
def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())

def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
```

Confirmado en la BD: `alembic_version` contiene una fila; `PRAGMA user_version = 0`.

**Impacto.** Tres consecuencias:

1. **No hay historial de esquema.** La revisión "0001" produce lo que los modelos digan *hoy*, no lo que decían cuando se escribió. Dos entornos en `head` pueden tener esquemas distintos.
2. **No se puede evolucionar la BD.** Añadir una columna exige una revisión nueva escrita a mano; no existe ninguna base desde la cual `--autogenerate` pueda diferenciar correctamente.
3. **`downgrade` destruye todos los datos.** Un `alembic downgrade -1` mal ejecutado sobre datos fiscales es pérdida total sin respaldo (ver BD-08).

**Recomendación.**

1. Regenerar `0001_initial` con `alembic revision --autogenerate` contra una BD vacía, de modo que contenga `op.create_table(...)` explícito.
2. Prohibir `drop_all()` en `downgrade`: escribir los `op.drop_table` explícitos o dejarlo como `raise NotImplementedError`.
3. Regla de proceso: **toda modificación de modelo genera una revisión nueva**; nunca editar `0001`.

---

#### BD-04 · Sin `UNIQUE` en el UUID fiscal de la factura — **Alta** · [CONFIRMADO]

**Descripción.** `invoices.uuid` (el UUID del Timbre Fiscal Digital del CFDI, identificador fiscalmente único por definición) tiene índice pero **no restricción de unicidad**. La duplicidad se detecta sólo en tiempo de validación, como una regla evaluable.

**Evidencia.**

```sql
CREATE INDEX ix_invoices_uuid ON invoices (uuid);        -- NO es UNIQUE
```

```
app/models/__init__.py:78   uuid: Mapped[str | None] = mapped_column(String(50), index=True)
app/services/validation_engine.py:63   duplicate_uuid = bool(... select(Invoice.id).where(Invoice.uuid == ...))
app/rules/financial_rules.py:16        FIN-004, severidad CRITICAL
```

Tampoco existe `UNIQUE (supplier_id, invoice_number)`, controlado igualmente sólo por la regla FIN-005 (severidad ERROR).

**Impacto.** El mismo CFDI puede existir varias veces en la BD. FIN-004 impide la *aceptación* (un `FAIL` de severidad `CRITICAL` bloquea, `app/routers/invoices.py:176-177`), pero sólo si la validación se ejecutó. Además, la comprobación de duplicado y la escritura del `uuid` ocurren en la misma transacción sin bloqueo: dos validaciones concurrentes del mismo CFDI pueden pasar ambas (TOCTOU). El riesgo final es **doble pago**.

**Recomendación.** `UNIQUE` parcial en `invoices.uuid` (permitiendo `NULL` para borradores sin XML) y `UNIQUE (supplier_id, invoice_number)`. Mantener FIN-004/FIN-005 como retroalimentación amable al usuario, pero que la base de datos sea la autoridad. Limpiar duplicados preexistentes antes de aplicar.

---

#### BD-05 · Cero restricciones `CHECK`; los estados no están acotados en la BD — **Media** · [CONFIRMADO]

**Descripción.** El esquema no contiene ni una sola cláusula `CHECK`. Los enums de SQLAlchemy se materializan como `VARCHAR` sin restricción (`Enum.create_constraint` es `False` por defecto desde SQLAlchemy 1.4).

**Evidencia.** Del DDL real:

```sql
status VARCHAR(24) NOT NULL,              -- invoices: 11 estados válidos, 0 CHECK
role VARCHAR(8) NOT NULL,                 -- users: 3 roles válidos, 0 CHECK
supplier_type VARCHAR(14) NOT NULL,       -- 0 CHECK
status VARCHAR(30) NOT NULL,              -- suppliers y contracts: texto libre
severity VARCHAR(20) NOT NULL,            -- validation_results: 0 CHECK
```

Además, `suppliers.status` y `contracts.status` ni siquiera tienen enum en el código — son cadenas literales `"ACTIVE"` dispersas (`app/models/__init__.py:42`, `:65`, `app/routers/invoices.py:49`, `app/rules/supplier_rules.py:6`). Tampoco hay `CHECK (total >= 0)` ni `CHECK (end_date >= start_date)`.

**Impacto.** Un estado inválido escrito por script o por SQL directo hace que el ORM falle al leer la fila (`LookupError` al desempaquetar el enum), rompiendo la página sin diagnóstico claro. Montos negativos y contratos con vigencia invertida son insertables.

**Recomendación.** `SAEnum(..., create_constraint=True, native_enum=False)` para los enums; `CheckConstraint` para `total >= 0`, `subtotal >= 0`, `tax >= 0`, `authorized_amount > 0`, `end_date >= start_date`, `validation_score BETWEEN 0 AND 100`. Convertir `suppliers.status` y `contracts.status` en enums tipados.

---

#### BD-06 · Journal en modo `delete`, sin WAL ni `busy_timeout` — **Media** · [CONFIRMADO]

**Descripción.** La BD opera en el modo de journal por defecto. El engine se crea con `check_same_thread=False` (habilitando acceso multihilo) pero sin ninguna configuración de concurrencia.

**Evidencia.**

```
PRAGMA journal_mode  ->  delete        (verificado)

app/core/database.py:19-22
  engine = create_engine(settings.database_url,
      connect_args={"check_same_thread": False} if ... else {})
  <- sin timeout, sin listener de PRAGMA, sin pool_pre_ping
```

**Impacto.** En modo `delete`, un escritor bloquea a todos los lectores. FastAPI ejecuta los endpoints síncronos (todos los de este proyecto) en un threadpool, por lo que varias peticiones concurrentes comparten el mismo archivo. Una validación de factura —que es la operación larga: parseo XML, ~31 reglas, `DELETE` + ~31 `INSERT` en `validation_results`, todo en una transacción (`app/services/validation_engine.py:75-86`)— bloqueará la BD para el resto. Sin `busy_timeout`, el resultado es `database is locked` inmediato en vez de una espera.

**No verificado:** no se realizó prueba de carga. La severidad se deduce de la configuración, no de una medición.

**Recomendación.** En el mismo listener de BD-01: `PRAGMA journal_mode=WAL`, `PRAGMA busy_timeout=5000`, `PRAGMA synchronous=NORMAL`. WAL permite lectores concurrentes con un escritor y es la configuración correcta para este perfil de uso (muchas lecturas, pocas escrituras). Tener en cuenta que WAL añade los archivos `-wal` y `-shm`, que deben incluirse en los respaldos.

---

#### BD-07 · Llaves foráneas sin índice y ausencia de índice en la columna de ordenamiento — **Media** · [CONFIRMADO]

**Descripción.** Seis columnas FK carecen de índice, y la columna por la que se ordena el listado principal tampoco lo tiene.

**Evidencia.** Comparando las FKs del DDL con los índices existentes:

| Columna sin índice | Tabla | Uso |
|---|---|---|
| `uploaded_by` | `invoices` | FK → users |
| `reviewed_by` | `invoices` | FK → users |
| `contract_id` | `invoices` | FK → contracts; se recorre en cada detalle |
| `created_at` | `invoices` | **`ORDER BY` del listado principal** (`app/repositories/invoice_repository.py:7`) |
| `uploaded_by` | `documents` | FK → users |
| `replaced_document_id` | `documents` | FK → documents (cadena de versiones) |
| `reviewer_id` | `reviews` | FK → users |
| `supplier_id` | `users` | FK → suppliers |

**Impacto.** Irrelevante con 10 facturas; con decenas de miles, el listado principal hace un scan completo más un sort en cada carga de página.

**Índices existentes que sí son correctos:** `invoices(supplier_id)`, `invoices(status)`, `invoices(internal_folio)` UNIQUE, `invoices(invoice_number)`, `documents(invoice_id)`, `documents(supplier_id)`, `documents(document_type)`, `validation_results(invoice_id)`, `audit_logs(timestamp)`, `users(email)` UNIQUE, `suppliers(rfc)` UNIQUE. Ninguno redundante. La elección de índices es, en conjunto, razonada.

**Recomendación.** Índice compuesto `(supplier_id, created_at DESC)` — cubre el filtro por proveedor y el orden en una sola estructura. Índices simples en las FKs restantes.

---

#### BD-08 · Sin estrategia de respaldo — **Media** · [CONFIRMADO por ausencia]

**Descripción.** No existe script de respaldo, tarea programada, documentación de recuperación ni política de retención. `grep -ri "backup\|respaldo"` sobre el proyecto no devuelve nada operativo.

**Impacto.** Los documentos fiscales tienen obligación legal de conservación (5 años en México). El único mecanismo de "reset" del proyecto, `reset_demo.py`, **borra la BD y el contenido de `storage/`** (`scripts/reset_demo.py:24-30`) y es invocado automáticamente por `run_local.ps1` en cada arranque. Un desarrollador que use el script de arranque documentado pierde el trabajo de la sesión anterior.

**A favor:** `reset_demo.py` está bien defendido — valida que las rutas estén dentro del workspace, exige `sqlite:///`, y preserva los `.gitkeep`. El README advierte explícitamente del comportamiento destructivo (línea 36). El riesgo es de proceso, no de implementación descuidada.

**Recomendación.** Copia de seguridad con la API online de SQLite (`sqlite3 .backup`, consistente sin detener la app) más `storage/`, con retención. Confirmación interactiva en `reset_demo.py` si detecta datos no-demo. Documentar el procedimiento de restauración.

---

#### BD-09 · `contracts` no tiene ningún campo de trazabilidad — **Media** · [CONFIRMADO]

**Descripción.** La tabla `contracts` carece de `created_at`, `updated_at`, `created_by` y `updated_by`. Es la única tabla del modelo sin marca temporal alguna.

**Evidencia.**

```sql
CREATE TABLE contracts (
  id, supplier_id, project_name, project_leader, authorized_technology,
  authorized_amount NUMERIC(16,2) NOT NULL, currency, start_date, end_date,
  status, notes, PRIMARY KEY (id), FOREIGN KEY(supplier_id) ...
);   -- ningún campo de auditoría
```

Comparar con `suppliers`, que sí tiene `created_at` + `updated_at` (`app/models/__init__.py:47-48`).

**Impacto grave por el contenido.** `authorized_amount` es el **techo financiero** contra el que la regla FIN-001 aprueba o rechaza cada factura. Si alguien modifica ese monto, no queda registro de cuándo, quién ni cuál era el valor anterior. Tampoco se audita la modificación: sólo existe `CONTRACT_CREATED` (`app/routers/contracts.py:29`), sin endpoint de edición y, por tanto, sin auditoría de cambio. El control financiero principal del sistema es mutable sin rastro.

Carencias menores del mismo tipo: `invoices` tiene `created_at` pero no `updated_at`; `reviews` y `validation_results` sólo tienen `created_at` (correcto, son inmutables por naturaleza).

**Recomendación.** Añadir `created_at`/`updated_at`/`created_by`/`updated_by` a `contracts`. Mejor aún: versionar el contrato (una fila nueva por modificación de monto, con `effective_from`), de modo que una factura validada en el pasado siga siendo auditable contra el monto vigente entonces. Auditar cualquier cambio de `authorized_amount` con `old_value`/`new_value` — la tabla `audit_logs` ya soporta ambos campos.

---

#### BD-10 · Fechas: la zona horaria se pierde, y una regla de negocio depende de ello — **Media** · [CONFIRMADO]

**Descripción.** Las columnas usan `DateTime(timezone=True)`, pero SQLite no almacena offset: guarda una cadena naive. Al leer, se obtiene un `datetime` sin zona horaria, interpretado implícitamente como UTC.

**Evidencia.** Datos reales de la BD:

```
created_at   = '2026-09-22 00:47:47.782703'   typeof = 'text'   <- sin offset
invoice_date = '2026-08-15'                   typeof = 'text'   <- ISO 8601, correcto
```

La regla DAT-001 usa ese valor directamente:

```python
# app/rules/date_rules.py:5
received_day = invoice.created_at.day if invoice.created_at else 1
# -> PASS si received_day <= 20
```

**Impacto.** El corte de recepción "del día 1 al 20" es un plazo de negocio **en horario local de México (UTC−6)**, pero se evalúa sobre el día UTC. Una factura cargada el **20 de agosto a las 19:00 CST** tiene `created_at` en UTC del **21 de agosto** → la regla devuelve `WARNING` ("puede programarse para el siguiente ciclo") sobre una factura que llegó en plazo. La ventana de error es de 6 horas todos los días del mes, y afecta a la decisión más sensible al calendario del portal.

Nota adicional: el folio interno usa `datetime.now().year` (hora local del servidor, `app/routers/invoices.py:65`) mientras el resto del sistema usa UTC — dos relojes distintos en el mismo registro.

**A favor:** las fechas puras (`invoice_date`, `start_date`, `end_date`, `document_date`) se almacenan en ISO 8601 (`YYYY-MM-DD`) de forma consistente, que es lo correcto.

**Recomendación.** Definir explícitamente la zona horaria de negocio (`America/Mexico_City`) en configuración y convertir antes de aplicar reglas de calendario: `invoice.created_at.astimezone(ZoneInfo("America/Mexico_City")).day`. Unificar el año del folio con el mismo criterio. Añadir un caso de prueba para el límite: 20 de agosto 23:00 CST debe ser `PASS`.

---

#### BD-11 · Rutas absolutas del host almacenadas en la base de datos — **Baja** · [CONFIRMADO]

**Evidencia.** Las 51 filas de `documents` contienen rutas como:

```
C:\Users\jobhd\Desktop\Ultrasist-ProyectoInternoFacturas\...\storage\suppliers\1\demo_962e8155a8.txt
```

Origen: `app/routers/invoices.py:118` y `scripts/seed_db.py:41`, ambos `str(stored.path)` / `str(destination.resolve())`. La descarga hace `Path(doc.path)` directo (`app/routers/invoices.py:134`).

**Impacto.** La BD no es portable: restaurarla en otra máquina, otro usuario o un contenedor deja el 100% de los documentos inaccesibles. Filtra la estructura del sistema de archivos y el nombre de usuario del host a cualquier copia de la BD. Bloquea la migración futura a Azure Blob.

**Recomendación.** Almacenar la ruta **relativa a `storage_path`** (`invoices/10/ab12cd.pdf`) y resolverla al servir: `settings.storage_path / doc.path`, validando que el resultado siga bajo la raíz. Migración de datos simple (recortar el prefijo). Esto además prepara la abstracción de almacenamiento que el README ya anticipa.

---

#### BD-12 · `cascade="all, delete-orphan"` sobre documentos fiscales — **Baja** · [CONFIRMADO]

**Evidencia.** `app/models/__init__.py:97-99`:

```python
documents:   Mapped[list[Document]]          = relationship(..., cascade="all, delete-orphan")
validations: Mapped[list[ValidationResult]]  = relationship(..., cascade="all, delete-orphan")
reviews:     Mapped[list[Review]]            = relationship(..., cascade="all, delete-orphan")
```

**Impacto.** Hoy es latente: **no existe ningún endpoint que borre facturas** — lo cual es acertado para documentos fiscales. Pero si alguna vez se añade, un `db.delete(invoice)` eliminaría en cascada los documentos, los resultados de validación y el historial de revisiones, dejando además los archivos huérfanos en disco. Sería destrucción de evidencia fiscal.

**A favor — y vale la pena subrayarlo:** el versionado documental está bien resuelto. Reemplazar un documento marca el anterior `is_current=False` y guarda `replaced_document_id`, conservando la cadena completa (`app/routers/invoices.py:115-120`). El archivo antiguo permanece en disco. Eso es borrado lógico correcto.

**Recomendación.** Cambiar a `passive_deletes=True` sin `delete-orphan`, o mejor: añadir `is_deleted`/`deleted_at` a `invoices` y prohibir el borrado físico por política. Si se implementa cancelación, que sea un estado (`CANCELLED`), no un `DELETE`.

---

### 3.C — Calidad de código

---

#### COD-01 · Lógica de negocio en la capa de presentación — **Media** · [CONFIRMADO]

**Descripción.** La arquitectura en capas es real y se respeta en general (ver Fortalezas), pero hay fugas concretas de reglas de negocio hacia los routers.

**Evidencia.**

```python
# app/routers/invoices.py:82-83  -- cálculo del resumen de validación en el router
summary = {"pass": sum(v.status == "PASS" for v in validations),
           "warnings": sum(v.status == "WARNING" for v in validations),
           "errors": sum(v.status == "FAIL" for v in validations),
           "blockers": sum(v.status == "FAIL" and v.severity == "CRITICAL" for v in validations)}
```

Esta lógica **ya existe** en `calculate_score()` (`app/services/validation_score_service.py:9-11`) con idéntica semántica — está duplicada.

```python
# app/routers/invoices.py:176-177  -- regla de bloqueo por severidad crítica, en el router
blockers = any(v.status == "FAIL" and v.severity == "CRITICAL" for v in invoice.validations)
if decision == "ACCEPTED" and blockers: raise HTTPException(409, ...)

# app/routers/invoices.py:186  -- regla de transición ClickBalance, en el router
target = READY_FOR_CLICKBALANCE if invoice.status == ACCEPTED else UPLOADED_TO_CLICKBALANCE

# app/routers/invoices.py:91, 101, 143  -- reglas de mutabilidad por estado, repetidas
#   tres veces el mismo conjunto {DRAFT, REQUIRES_CORRECTION, VALIDATION_FAILED}
```

**Impacto.** "No se puede aceptar una factura con bloqueos críticos" es la regla de control más importante del flujo de aprobación y vive en un handler HTTP, fuera de la capa de reglas y fuera del alcance de las pruebas unitarias. El conjunto de estados mutables repetido en tres sitios divergirá.

**Recomendación.** Mover a `invoice_service`: `can_accept(invoice) -> bool`, `is_editable(invoice) -> bool`, `next_clickbalance_status(invoice)`. Reutilizar `calculate_score()` en el detalle en lugar de recalcular. Los routers deben quedar como traducción HTTP ↔ servicio.

---

#### COD-02 · Filtrado y búsqueda en memoria, con N+1 — **Media** · [CONFIRMADO]

**Evidencia.**

```python
# app/repositories/invoice_repository.py:6-10  -- sin LIMIT, sin joinedload
def visible_invoices(db, user):
    stmt = select(Invoice).order_by(Invoice.created_at.desc())
    if user.role.value == "PROVIDER": stmt = stmt.where(Invoice.supplier_id == user.supplier_id)
    return list(db.scalars(stmt))

# app/routers/invoices.py:36-40  -- búsqueda y filtro en Python
rows = visible_invoices(db, user)
if q:      rows = [i for i in rows if q.lower() in f"{i.internal_folio} {i.invoice_number} {i.project_name} {i.supplier.business_name}".lower()]
if status: rows = [i for i in rows if i.status.value == status]
```

`i.supplier.business_name` dispara un `SELECT` por factura (N+1). El dashboard tiene el mismo patrón: carga todas las facturas para contar por estado (`app/routers/dashboard.py:17-22`) — importa `func` de SQLAlchemy y no lo usa. `admin/audit` limita a 500 sin paginación (`app/routers/admin.py:41`).

**Impacto.** Con 10 facturas es irrelevante. Con 10 000, cada carga del listado trae toda la tabla a memoria y ejecuta 10 000 consultas adicionales. Es el principal obstáculo de escalabilidad del código, y no depende de SQLite.

**Recomendación.** Llevar filtro, búsqueda (`ILIKE`/`LIKE`) y paginación a la consulta SQL dentro del repositorio; `joinedload(Invoice.supplier)` para eliminar el N+1; `func.count()` agrupado por estado para los KPIs del dashboard. La capa de repositorio ya existe y es el lugar correcto — sólo está infrautilizada (18 líneas para toda la aplicación).

---

#### COD-03 · Código muerto e infraestructura de validación sin usar — **Media** · [CONFIRMADO]

**Evidencia.**

**(a) `InvoiceCreate` nunca se usa.** `app/schemas/__init__.py:5-15` define validación Pydantic completa — incluido `service_period` con patrón `^(0[1-9]|1[0-2])/\d{4}$`. `grep -rn "InvoiceCreate"` fuera de `app/schemas/` → **cero resultados**. El endpoint real recibe `service_period: str = Form(...)` sin validar (`app/routers/invoices.py:56`), y `contract_rules` tiene que defenderse con un `try/except (ValueError, TypeError)` (`app/rules/contract_rules.py:15-19`) de un dato que debió validarse en la frontera. La validación correcta **ya está escrita** y no se conecta.

**(b) Los 8 archivos de `app/models/*.py` son reexportaciones de una línea.** `invoice.py`, `user.py`, `supplier.py`, etc. contienen únicamente `from app.models import X`. Sugieren una estructura por entidad que no existe: todo está en `__init__.py` (170 líneas).

**(c) Dependencias declaradas y no usadas.** `email-validator==2.2.0` y `httpx==0.28.1` están en `requirements.txt` (producción); `grep` sobre `app/` no encuentra ninguna. `httpx` sólo lo consume `TestClient` — pertenece a `requirements-dev.txt`.

**(d) Import sin usar.** `from sqlalchemy import func, select` en `app/routers/dashboard.py:3` — `func` nunca se utiliza.

**Recomendación.** Conectar `InvoiceCreate` al endpoint de alta (cierra también parte de SEC-08 al habilitar el mismo patrón para usuarios y proveedores). Eliminar los reexports o repartir realmente los modelos. Mover `httpx` a dev y eliminar `email-validator` o empezar a usar `EmailStr`. Añadir `ruff` al CI — detectaría (b), (c) y (d) automáticamente.

---

#### COD-04 · Doble fuente de verdad para las reglas de negocio — **Media** · [CONFIRMADO]

**Descripción.** Los parámetros de negocio (RFC receptor, método de pago, usos de CFDI permitidos) existen en dos archivos independientes. El motor de validación lee uno; la pantalla de administración muestra el otro.

**Evidencia.**

```python
# app/core/constants.py:86-90  -- lo que el motor USA
BUSINESS_RULES = {"receiver": {..., "rfc": "ULT940623AG0", ...},
                  "payment_method": "PPD", "payment_form": "99",
                  "allowed_cfdi_uses": ["G03", "I04"], "score_weights": {...}}
```

```json
// app/rules/business_rules.json  -- lo que el ADMIN VE
{"receiver": {"rfc": "ULT940623AG0"}, "payment_method": "PPD",
 "payment_form": "99", "allowed_cfdi_uses": ["G03", "I04"],
 "note": "Referencia editable para futura persistencia administrativa; ..."}
```

Consumidores: el motor usa `BUSINESS_RULES` (`app/rules/xml_rules.py:1`, `app/services/validation_score_service.py:1`); la vista `/admin/rules` lee el JSON (`app/routers/admin.py:47`). Nada los sincroniza.

**Impacto.** Si alguien edita el JSON —cosa que su propia nota ("Referencia editable") invita a hacer— la pantalla de administración mostrará reglas que el sistema no aplica. El administrador tomaría decisiones sobre información falsa. Nótese además que el JSON **no incluye `score_weights`**, así que la ponderación real del score no es visible en ninguna parte de la interfaz.

**Atenuante:** la duplicación está documentada, tanto en el `note` del JSON como en el README (línea 120). Es una decisión consciente, no un descuido — pero sigue siendo una trampa.

**Recomendación.** Una sola fuente. Lo más directo: `/admin/rules` renderiza `BUSINESS_RULES` (incluyendo `score_weights`) y el JSON se elimina. Si el objetivo final es edición persistente por el administrador, invertir la dirección: el JSON (o una tabla) es la fuente, se carga validado con Pydantic al arranque, y `constants.py` sólo aporta los valores por defecto.

---

#### COD-05 · Logging insuficiente para diagnóstico — **Media** · [CONFIRMADO]

**Descripción.** La aplicación emite tres mensajes de log en total: arranque, parada y error no manejado.

**Evidencia.** Todas las llamadas a logger en `app/`:

```
app/main.py:20   logger.info("Starting %s in %s", ...)
app/main.py:22   logger.info("Stopping %s", ...)
app/main.py:50   logger.exception("Unhandled application error")
```

Confirmado en `logs/app.log`: 101 líneas, exclusivamente arranques/paradas y trazas HTTP de `httpx` durante las pruebas. Formato de texto plano sin estructura (`app/core/logging_config.py:8`), sin `request_id`, `user_id` ni correlación.

No se registra: subida de documento, ejecución de validación (ni su duración), decisión de revisión, fallo de parseo de XML. `app/services/pdf_service.py:17-18` captura `Exception` y **no lo registra** antes de relanzar un mensaje genérico — el motivo real por el que un PDF falló se pierde para siempre.

**Impacto.** Un proveedor reporta "mi factura no se valida" y no hay forma de reconstruir qué ocurrió. El Audit Log de la BD cubre el *qué* de negocio, pero no el *por qué* técnico.

**A favor:** `RotatingFileHandler` con rotación configurada (2 MB × 3) y, sobre todo, **cero fugas de datos sensibles** — verificado con `grep -ci "password|rfc|secret"` sobre ambos logs → 0. La disciplina de no loguear datos personales está bien mantenida.

**Recomendación.** Log estructurado JSON con `request_id` (middleware) y `user_id`. Registrar al menos: inicio/fin de validación con duración y score, subidas con tipo y tamaño, decisiones de revisión, y todo fallo de parseo con el detalle técnico. Loguear en `pdf_service` antes de relanzar.

---

#### COD-06 · Carrera en la generación del folio interno — **Media** · [CONFIRMADO]

**Evidencia.**

```python
# app/routers/invoices.py:64-65
count = db.scalar(select(Invoice.id).order_by(Invoice.id.desc()).limit(1)) or 0
invoice = Invoice(internal_folio=f"FAC-{datetime.now().year}-{count + 1:05d}", ...)
```

**Impacto.** Leer-máximo-y-sumar-uno sin bloqueo ni unicidad transaccional. Dos altas concurrentes calculan el mismo `count` y generan el mismo folio; el índice `UNIQUE ix_invoices_internal_folio` lo rechaza con `IntegrityError` **no capturado** → HTTP 500 (y, con `DEBUG=true`, traceback — ver SEC-02). El usuario pierde el formulario. Secundario: el año proviene del reloj local mientras el resto del sistema usa UTC (ver BD-10), y el contador nunca se reinicia por año.

**Recomendación.** Derivar el folio del `id` autoincremental ya asignado, después del `flush()`: `invoice.internal_folio = f"FAC-{year}-{invoice.id:05d}"`. Alternativa si se requiere numeración por año: una tabla `folio_counters(year, last_number)` actualizada con `UPDATE ... RETURNING` en la misma transacción. En ambos casos, capturar `IntegrityError` y reintentar.

---

#### COD-07 · Cobertura de pruebas parcial en las áreas de mayor riesgo — **Media** · [CONFIRMADO]

**Descripción.** Hay 14 pruebas, bien escritas y con casos límite genuinos. Pero los módulos con mayor superficie de riesgo no están cubiertos, y **no hay herramienta de cobertura configurada**, por lo que no puedo dar un porcentaje medido.

**Evidencia.** `requirements-dev.txt` contiene sólo `pytest` y `pytest-asyncio` — no hay `pytest-cov`. Inventario por módulo:

| Módulo | Estado | Nota |
|---|---|---|
| `services/xml_service.py` | Cubierto | CFDI válido, RFC incorrecto, XML corrupto |
| `services/reconciliation_service.py` | Cubierto | Dentro y excedido, con `Decimal` exacto |
| `services/validation_score_service.py` | Cubierto | Score y bloqueo crítico |
| `services/invoice_service.py` | Cubierto | Transición inválida rechazada |
| `rules/date_rules.py` | Parcial | Sólo el caso `WARNING`; falta el límite (día 20) y el efecto de zona horaria (BD-10) |
| `rules/financial_rules.py` | Parcial | FIN-001 y FIN-004; faltan FIN-002/003/005/006 |
| `routers/auth.py` | Cubierto | Login válido, inválido y rechazo CSRF |
| `repositories/` (RBAC) | Smoke | Aislamiento de proveedor verificado en listado y detalle |
| **`services/file_service.py`** | **Sin cobertura** | **Ninguna prueba de subida: extensión, MIME, tamaño, path traversal** |
| **`services/pdf_service.py`** | **Sin cobertura** | Nunca se ejecuta en pruebas |
| **`POST /invoices/{id}/documents`** | Sin cobertura | El flujo principal del portal |
| **`POST /invoices/{id}/review`** | Sin cobertura | **Incluida la regla de bloqueo por severidad crítica (COD-01)** |
| `GET .../documents/{id}/download` | Sin cobertura | El control de autorización sobre documentos no se prueba |
| `routers/admin.py`, `contracts.py`, `suppliers.py` (POST) | Sin cobertura | Sólo smoke de renderizado en GET |
| `rules/document_rules, xml_rules, supplier_rules, contract_rules` | Sin cobertura directa | Sólo indirecta vía el seed |

**(b) Efecto secundario destructivo.** El fixture de sesión ejecuta `reset_demo.py`, que **borra la base de datos de trabajo** del desarrollador:

```python
# tests/conftest.py:12-14
@pytest.fixture(scope="session", autouse=True)
def demo_database():
    subprocess.run([sys.executable, str(ROOT / "scripts" / "reset_demo.py")], cwd=ROOT, check=True)
```

Ejecutar `pytest` destruye `data/invoice_portal.db` y el contenido de `storage/`. Las pruebas deberían usar una BD temporal aislada.

**(c) Acoplamiento a IDs del seed.** `tests/test_permissions.py:13-14` depende de `"FAC-2026-00002"` y de que `/invoices/2` sea del otro proveedor. Cualquier cambio de orden en el seed rompe la prueba sin que la lógica haya cambiado.

**Recomendación.** Por prioridad: (1) pruebas de `file_service` — es el módulo de mayor riesgo de seguridad y tiene cero cobertura; (2) prueba de que un PROVIDER recibe 404 al descargar un documento de otro proveedor; (3) prueba de que FIN-001 `CRITICAL` impide la aceptación; (4) BD temporal por sesión de prueba (`tmp_path` + `DATABASE_URL` sobrescrito); (5) añadir `pytest-cov` y fijar un umbral en CI.

---

#### COD-08 · Densidad de línea que perjudica la mantenibilidad — **Baja** · [CONFIRMADO]

**Descripción.** Un estilo recurrente de múltiples sentencias por línea separadas con `;`, concentrado en los routers.

**Evidencia.**

```python
# app/routers/invoices.py:156
await validate_csrf(request); invoice = _invoice_or_404(db, invoice_id, user)

# app/routers/invoices.py:179  -- cinco operaciones en una línea
db.add(Review(...)); audit(db, decision, "Invoice", invoice.id, user.id, new={"comments": comments}); db.commit()

# app/routers/suppliers.py:62  -- alta de documento, auditoría y commit en una línea
db.add(document); db.flush(); audit(db, "SUPPLIER_DOCUMENT_REPLACED" if previous else ..., ...); db.commit()

# app/routers/suppliers.py:54-55
try: stored = await LocalFileStorage().save_supplier_file(supplier.id, upload)
except ValueError as exc: raise HTTPException(400, str(exc)) from exc
```

**Impacto.** Los diffs de Git pierden granularidad (un cambio en el `audit` toca la misma línea que el `commit`), la depuración por línea es imprecisa y las trazas de excepción no identifican qué sentencia falló. No afecta al comportamiento.

**Recomendación.** `ruff format` (o `black`) con longitud de línea de 120 y `ruff check --select E701,E702` para prohibir múltiples sentencias por línea. Es un cambio mecánico de bajo riesgo; conviene hacerlo en un commit aislado para no contaminar diffs funcionales.

---

#### COD-09 · Transacciones gestionadas desde la capa de servicio — **Baja** · [CONFIRMADO]

**Evidencia.** `run_validation()` ejecuta `db.commit()` en su interior (`app/services/validation_engine.py:86`), mientras el resto de los servicios (`transition_invoice`, `audit`) delega el commit al router. Dos convenciones conviviendo. `scripts/seed_db.py:109` incluso hace `db.commit(); run_validation(...)` — commit antes de llamar a algo que vuelve a commitear.

**Impacto.** El router de validación no puede componer `run_validation` con otra operación en la misma transacción. Si algo falla después del commit interno, queda un estado parcialmente persistido. Menor hoy porque nadie compone esa llamada.

**Recomendación.** Convención única: **los servicios no hacen commit**; el límite transaccional pertenece al router (o a un context manager de unidad de trabajo). Quitar el `commit()` de `run_validation` y añadirlo en `app/routers/invoices.py:145`.

---

#### COD-10 · Configuración: sin separación por ambiente y rutas relativas al CWD — **Baja** · [CONFIRMADO]

**Evidencia.**

- Un único `.env`; no hay `.env.production` ni perfiles. `app_env` existe en la configuración pero **no altera ningún comportamiento** — `grep -rn "app_env"` sólo lo encuentra en su definición y en un mensaje de log.
- Rutas dependientes del directorio de trabajo: `StaticFiles(directory="app/static")` (`app/main.py:28`), `Path("logs")` (`app/core/logging_config.py:7`), `sqlalchemy.url = sqlite:///./data/...` en `alembic.ini:4`. Arrancar desde otro directorio rompe la aplicación silenciosamente (crearía una BD vacía nueva).
- `settings` se instancia a nivel de módulo (`app/core/config.py:47`), dificultando la sobrescritura en pruebas.

**Recomendación.** Anclar las rutas al paquete (`Path(__file__).resolve().parents[1]`), como ya hacen correctamente `app/routers/common.py:7` y los scripts. Hacer que `app_env` gobierne de verdad los valores por defecto de `debug` y `session_https_only`. Inyectar `Settings` vía `Depends(get_settings)` donde se necesite sobrescribir.

---

## 4. Fortalezas

Lo que está bien resuelto y **debe conservarse** en cualquier refactorización:

1. **La arquitectura en capas es real, no nominal.** `routers → services → repositories → models`, con `rules/` como capa de dominio puro. La dirección de dependencias se respeta: ningún modelo importa un servicio, ninguna regla importa un router. Para una PoC, esto es inusualmente disciplinado y es el activo principal del proyecto.

2. **Cero SQL concatenado.** Acceso a datos 100% por SQLAlchemy ORM con parámetros vinculados. `grep` de `text(`, `execute(f`, `%s` y `.format(` sobre `app/` no arroja ni un solo uso en contexto SQL. **La inyección SQL no es una superficie de ataque en este sistema.**

3. **Parser CFDI endurecido contra XXE.** `etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False)` (`app/services/xml_service.py:36`) neutraliza XXE, billion-laughs y SSRF vía entidades externas — las tres defensas correctas en el mismo sitio. El uso de `local-name()` en XPath en lugar de prefijos de namespace es además técnicamente acertado para CFDI.

4. **Las reglas de negocio son funciones puras y testeables.** `document_rules`, `xml_rules`, `financial_rules`, etc. reciben datos y devuelven `ValidationOutcome`; sin BD, sin I/O, sin estado. Diseño de motor de reglas de calidad. El campo `evidence_json` por resultado hace la validación auditable y explicable — exactamente lo que un proceso fiscal necesita.

5. **Máquina de estados explícita y centralizada.** `ALLOWED_TRANSITIONS` (`app/core/constants.py:73-83`) declara el grafo completo en un solo lugar, y `transition_invoice` es el único punto de mutación de estado — que además audita cada cambio con valor anterior y nuevo.

6. **CSRF completo y correctamente implementado.** Token por sesión, comparación con `secrets.compare_digest` (tiempo constante), presente en los 10 formularios mutables verificados, y rotado al iniciar sesión. Se probó que su ausencia devuelve 403.

7. **Autenticación bien construida.** Argon2id vía `pwdlib` con parámetros recomendados; `request.session.clear()` **antes** de fijar `user_id` (previene fijación de sesión, `app/routers/auth.py:31`); mensaje de error idéntico para usuario inexistente, contraseña incorrecta y cuenta deshabilitada (sin enumeración de usuarios); `is_active` revalidado en cada petición.

8. **Control de acceso por pertenencia de objeto, sin IDOR detectado.** `get_visible_invoice` filtra por `supplier_id` para el rol PROVIDER, y la descarga verifica **además** que el documento pertenezca a esa factura (`app/routers/invoices.py:132`). Se revisaron todas las rutas parametrizadas por ID (`/invoices/{id}`, `/invoices/{id}/documents/{id}/download`, `/suppliers/{id}`, `/suppliers/{id}/documents`, `/admin/users/{id}/toggle`) — **todas verifican autorización; no se encontró IDOR**. El alta de factura incluso valida que el contrato pertenezca al proveedor indicado (`app/routers/invoices.py:59-63`).

9. **Almacenamiento de archivos bien diseñado.** Nombre generado con `uuid4` (el nombre del cliente sólo como metadato), verificación explícita de path traversal, `entity_id` forzado a entero, lectura acotada que evita agotar memoria, SHA-256 de cada archivo, segregación por proveedor/factura, y `Content-Disposition: attachment` en la descarga.

10. **Versionado documental con borrado lógico.** Reemplazar un documento conserva el anterior (`is_current=False` + `replaced_document_id`), manteniendo la cadena completa. Es el comportamiento correcto para documentos fiscales y ya está implementado.

11. **Auditoría de negocio funcional.** La tabla `audit_logs` con `old_value`/`new_value` en JSON está poblada y en uso (59 registros verificados, cubriendo login, cambios de estado, validaciones, subidas y decisiones). `admin/audit` la expone a ADMIN.

12. **Jinja2 con autoescape y sin `|safe`.** `grep` de `|safe`, `autoescape`, `innerHTML` y `eval(` sobre plantillas y JS → **cero resultados**. El JavaScript (19 líneas) usa exclusivamente `.value` y `.textContent`. **No se encontró ningún vector de XSS.**

13. **Adaptador de IA correctamente abstraído.** `DocumentAnalyzer` ABC con implementación mock determinista por defecto y adaptadores Azure que fallan de forma controlada si no están configurados. Ningún router, regla ni modelo importa un SDK de Azure. La separación "la IA aporta evidencia, las reglas deciden, el humano aprueba" está implementada de verdad: `SEM-001` sólo puede producir `PASS` o `WARNING`, nunca un bloqueo — la IA no puede aprobar ni rechazar una factura.

14. **README honesto.** Documenta limitaciones, alcance excluido y próximos pasos de producción, y advierte que los datos son sintéticos. La sección "Limitaciones y fuera de alcance" describe con precisión lo que el sistema no hace. La única discrepancia encontrada entre documentación y comportamiento es la de la línea 134 (SEC-02).

---

## 5. Plan de remediación priorizado

### Fase 0 — Bloqueantes antes de cualquier exposición fuera de `localhost`

| # | Acción | Hallazgo | Esfuerzo |
|:--:|---|---|:--:|
| 1 | `SECRET_KEY` sin default, obligatoria, con validador que rechace el placeholder | SEC-01 | 30 min |
| 2 | `DEBUG=false` por defecto y desacoplar de `FastAPI(debug=)` | SEC-02 | 30 min |
| 3 | Capturar `ValueError` de `transition_invoice` → HTTP 409 | SEC-02, COD-05 | 1 h |
| 4 | Ocultar el bloque de credenciales demo fuera de `development` | SEC-03 | 30 min |
| 5 | Ejecutar `pip-audit` y actuar sobre el resultado | SEC-11 | 1 h |

**Total: menos de una jornada.** Los cinco puntos son cambios localizados y de bajo riesgo. El #5 es el único que puede revelar trabajo adicional.

---

### Fase 1 — Quick wins (1–2 días, bajo riesgo, alto retorno)

| # | Acción | Hallazgo |
|:--:|---|---|
| 6 | Listener de conexión SQLite: `foreign_keys=ON`, `journal_mode=WAL`, `busy_timeout=5000` — **verificar antes con `PRAGMA foreign_key_check`** | BD-01, BD-06 |
| 7 | Middleware de cabeceras de seguridad (`X-Frame-Options`, `nosniff`, `Referrer-Policy`, CSP — viable: todos los assets son locales) | SEC-05 |
| 8 | Quitar `application/octet-stream` de `ALLOWED_MIMES` + verificación de magic bytes | SEC-06 |
| 9 | Rate limiting en `/login` con bloqueo temporal | SEC-04 |
| 10 | Conectar `InvoiceCreate` al endpoint de alta; validación de contraseña y `EmailStr` en el servidor | SEC-08, COD-03 |
| 11 | Folio derivado del `id` tras el `flush()`; capturar `IntegrityError` | COD-06 |
| 12 | Índice compuesto `(supplier_id, created_at DESC)` + índices en las FKs faltantes | BD-07 |
| 13 | Unificar la fuente de reglas de negocio: `/admin/rules` lee `BUSINESS_RULES` (incl. `score_weights`) | COD-04 |
| 14 | BD temporal en `conftest.py` — dejar de destruir la BD de trabajo | COD-07(b) |
| 15 | `ruff` + `ruff format` en CI; eliminar código muerto y mover `httpx` a dev | COD-03, COD-08 |

---

### Fase 2 — Cambios estructurales (requieren migración de datos y pruebas de regresión)

| # | Acción | Hallazgo | Nota |
|:--:|---|---|---|
| 16 | **Migrar montos a enteros en centavos** (o decidir la migración a PostgreSQL ahora) | BD-02 | Toca modelos, reglas financieras, plantillas y datos. **Decidirlo antes que el resto de Fase 2** — condiciona todo lo demás. |
| 17 | **Regenerar `0001_initial` con `--autogenerate`**; prohibir `drop_all` en `downgrade` | BD-03 | Prerrequisito de los puntos 18-20 |
| 18 | `UNIQUE` en `invoices.uuid` (parcial) y `(supplier_id, invoice_number)` | BD-04 | Limpiar duplicados antes |
| 19 | `CHECK` en estados, montos y vigencias; enums tipados para `suppliers.status` y `contracts.status` | BD-05 | |
| 20 | Auditoría en `contracts` (`created_at/by`, `updated_at/by`) + versionado de `authorized_amount` | BD-09 | El control financiero principal |
| 21 | Rutas relativas en `documents.path` | BD-11 | Prepara la migración a Blob |
| 22 | Zona horaria de negocio explícita para reglas de calendario (DAT-001) | BD-10 | **Corrige un error de negocio activo hoy** |
| 23 | Mover reglas de negocio de routers a `invoice_service`; reutilizar `calculate_score` | COD-01 | |
| 24 | Filtro, búsqueda y paginación en SQL; `joinedload`; KPIs con `func.count()` | COD-02 | |
| 25 | Pruebas de `file_service`, autorización de descarga y bloqueo por severidad crítica; `pytest-cov` con umbral | COD-07 | |
| 26 | Log estructurado JSON con `request_id` y `user_id` | COD-05 | |
| 27 | Respaldos con `sqlite3 .backup` + `storage/`, con retención y procedimiento de restauración documentado | BD-08 | |
| 28 | Sesiones del lado del servidor; `SESSION_HTTPS_ONLY=true` | SEC-07 | Junto con el despliegue TLS |
| 29 | Lock file con hashes; fijar `starlette==`; `pip-audit` recurrente en CI | SEC-11 | |
| 30 | Script de empaquetado que excluya `.env`, `data/*.db`, `logs/`, `storage/` | SEC-09 | |

---

### Orden recomendado

**Fase 0 completa** antes de cualquier demostración fuera de la máquina de desarrollo. **Fase 1** en el siguiente sprint: son 15 cambios acotados que elevan sustancialmente la postura de seguridad y de rendimiento sin tocar el modelo de datos. **Fase 2** sólo tras decidir el destino de la base de datos: si se confirma la migración a PostgreSQL/Azure SQL que el README contempla, los puntos 16, 18 y 19 se resuelven de forma distinta (y más barata) y conviene no hacerlos dos veces.

---

## Anexo — Alcance de la verificación

**Verificado con ejecución:** esquema real vía `sqlite_master`; `PRAGMA journal_mode`, `foreign_keys`, `user_version`, `page_size`, `encoding`, `auto_vacuum`; `typeof()` sobre columnas monetarias y de fecha; conteo de filas de las 9 tablas; contenido de `users`, `audit_logs`, `documents`; búsquedas de patrones sobre todo el árbol de código.

**Verificado por lectura estática:** los 44 archivos `.py` de `app/`, `tests/`, `scripts/` y `alembic/` en su totalidad; las 14 plantillas Jinja; `app.js`; `requirements*.txt`; `.env`; `.env.example`; `.gitignore`; `alembic.ini`; los scripts de arranque; `README.md`.

**No evaluado, y por qué:**

- **Ejecución de la aplicación** — no hay entorno virtual en el paquete entregado. SEC-02 se marcó como sospecha por este motivo.
- **Escaneo de vulnerabilidades de dependencias** — sin entorno ni acceso a base de datos de CVE. Ver SEC-11.
- **Comportamiento bajo concurrencia** — BD-06 se deduce de la configuración, sin prueba de carga.
- **Respaldos y cifrado en reposo** — no existe configuración alguna que auditar; se reportan como ausencias (BD-08, SEC-10), no como implementaciones deficientes.
- **Documentos `.docx`/`.pdf` de requerimientos** en la raíz del workspace — fuera del alcance técnico solicitado; no se contrastó la implementación contra los requerimientos funcionales.

---

**Nota sobre el método:** esta auditoría fue de sólo lectura. No se modificó ningún archivo del proyecto auditado y las consultas a la base de datos fueron exclusivamente `SELECT` y `PRAGMA`.
