# Invoice Portal PoC

Portal local de facturación y prevalidación de proveedores para ULTRASIST. Recibe expedientes, extrae CFDI 4.0, aplica reglas determinísticas, presenta una matriz de evidencia y soporta revisión administrativa con trazabilidad completa.

> **Datos exclusivamente DEMO.** Los RFC, XML, contratos, nombres y documentos incluidos son sintéticos, no tienen validez fiscal o legal y no representan personas reales.

## Principio de arquitectura

La solución separa cuatro responsabilidades:

1. **Reglas Python:** XML, RFC, documentos, fechas, montos, duplicados, contrato y transiciones.
2. **Extracción documental:** parser CFDI con `lxml` y PDF con PyMuPDF.
3. **AI semántica:** interfaz `DocumentAnalyzer`; por defecto usa un mock local reproducible.
4. **Human in the loop:** sólo un usuario `INTERNAL` o `ADMIN` puede registrar la decisión final.

La AI recomienda o aporta evidencia; el Rule Engine determina la prevalidación técnica y el usuario administrativo toma la decisión final. Un LLM nunca cambia una factura a `ACCEPTED`.

## Requisitos

- Python 3.12 recomendado (validado con 3.12.4).
- Windows PowerShell/CMD o Linux/macOS con shell POSIX.
- **Docker con Compose v2** para la base de datos: Docker Desktop en Windows y macOS; Docker Engine o Podman (con `podman compose` o el alias `docker`) en Linux. Sólo PostgreSQL corre en un contenedor; la aplicación corre en el host.
- Puerto `55432` libre en `127.0.0.1` (configurable con `POSTGRES_PORT` en `.env`; el 5432 y el 5433 suelen estar ocupados por otras instancias).
- No requiere Node.js, Azure ni conexión a servicios externos para operar.

## Instalación en Windows PowerShell

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install --require-hashes -r requirements.lock
python scripts/create_env.py
docker compose up -d --wait db
python scripts/init_db.py
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

También puede ejecutar `scripts\create_venv.ps1` y después `run_local.ps1`. `run_local` crea o completa `.env`, levanta PostgreSQL (`docker compose up -d --wait db`), aplica las migraciones y siembra la demo sólo si la base está vacía. **Conserva los datos entre arranques.**

En CMD use `.venv\Scripts\activate` y `run_local.bat`.

## Instalación en Linux/macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install --require-hashes -r requirements.lock
python scripts/create_env.py
docker compose up -d --wait db
python scripts/init_db.py
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

O bien `./run_local.sh`, que hace lo mismo. Abra <http://127.0.0.1:8000>. El health check está en <http://127.0.0.1:8000/health>.

## Credenciales demo

Sólo aplican con `APP_ENV=development`:

| Rol | Usuario | Contraseña |
|---|---|---|
| ADMIN | `admin@poc.local` | `Admin#Demo2026` |
| INTERNAL / PMO | `pmo@poc.local` | `Pmo#Demo2026` |
| Proveedor moral | `proveedor1@poc.local` | `Proveedor#Demo2026` |
| Proveedor físico | `proveedor2@poc.local` | `Proveedor#Demo2026` |

- La fuente única de estas cuentas es `app/core/demo.py`.
- El bloque de acceso rápido del login sólo aparece en `development`.
- En `test` o `production`, el seed genera contraseñas aleatorias y las imprime una sola vez en consola.
- Con `APP_ENV=production`, la aplicación **no arranca** mientras exista alguna cuenta `@poc.local` activa.

No reutilice estas contraseñas fuera de la PoC.

## Base de datos, migraciones y demo

- **PostgreSQL 18** en Docker, definido en `compose.yaml` (servicio `db`, imagen `postgres:18.<menor>-alpine` fijada). Es el único motor soportado.
  - Sólo escucha en `127.0.0.1:${POSTGRES_PORT}` (55432 por defecto).
  - Toma `POSTGRES_USER`, `POSTGRES_DB` y `POSTGRES_PASSWORD` del mismo `.env` que la aplicación; sin `POSTGRES_PASSWORD`, `docker compose up` se niega a arrancar.
  - Los datos viven en el volumen `portal-facturas_pgdata`: sobreviven a `docker compose down` y sólo se borran con `docker compose down -v`.
  - `docker compose up -d --wait db` arranca el servicio y espera a que el healthcheck (`pg_isready`) lo declare `healthy`.
- `DATABASE_URL` es obligatoria y debe usar `postgresql+psycopg://` (driver psycopg 3). `python scripts/create_env.py` la genera junto con `POSTGRES_PASSWORD`; en un `.env` existente sólo añade las claves ausentes y reemplaza, avisando, una URL de SQLite.
- Tipos nativos: montos en `NUMERIC(16,2)` y confianza en `NUMERIC(5,4)` (un valor con más decimales se rechaza antes de enviarse: PostgreSQL lo redondearía en silencio), fechas-hora en `TIMESTAMPTZ` normalizadas a UTC y JSON en `JSONB`. Cada conexión trabaja en UTC.
- Aplicar migraciones y sembrar sólo si la base está vacía: `python scripts/init_db.py` (falla con un mensaje claro si PostgreSQL no responde).
- Aplicar migraciones: `alembic upgrade head`.
- Cargar seed sobre una base vacía: `python scripts/seed_db.py`.
- Reconstruir base y archivos demo: `python scripts/reset_demo.py`.

> **`data/invoice_portal.db` ya no se usa.** Era la base SQLite de versiones anteriores y sólo contenía datos demo. No hay traslado automático: la demo se reconstruye en PostgreSQL con `init_db.py`. Puede conservar o borrar el archivo.

**Migraciones.**

- Cada revisión de `alembic/versions/` describe su cambio de forma explícita. La base es `0001_postgresql_baseline`: crea las 11 tablas con sus llaves foráneas `RESTRICT`, `UNIQUE`, `CHECK` e índices, sin importar los modelos. La cadena anterior, escrita para SQLite, queda sólo en el historial de Git.
- Ningún `downgrade` borra todo: los que perderían datos (incluido el de la revisión base) lanzan `NotImplementedError` (restaure un respaldo).
- **Regla:** todo cambio en `app/models` requiere una revisión nueva a partir de `0001_postgresql_baseline`. Nunca edite una revisión publicada. `alembic check` (incluido en `scripts/check.py`) falla si modelos y migraciones difieren.

`reset_demo.py` borra datos, así que actúa con cuidado:

- no se ejecuta con `APP_ENV=production` ni si `DATABASE_URL` apunta a un servidor que no sea local (`localhost`, `127.0.0.1` o `::1`);
- valida que `storage/` esté dentro del workspace;
- si detecta datos que no son demo (usuarios fuera de `@poc.local` o facturas no sembradas), pide escribir `REINICIAR`; sin terminal interactiva exige `--yes`;
- antes de borrar genera un respaldo en `backups/`;
- recrea el esquema (`DROP SCHEMA public CASCADE; CREATE SCHEMA public`), vacía `storage/`, aplica las migraciones y vuelve a sembrar. Detenga la aplicación antes: si mantiene bloqueos, el script falla a los 10 s en lugar de esperar.

## Respaldo y restauración

Los documentos fiscales deben conservarse 5 años. Respalde la BD **y** `storage/`; uno sin el otro no sirve.

- **Respaldo:** `python scripts/backup.py`. Puede ejecutarse con la aplicación en marcha: `pg_dump` toma una instantánea transaccional consistente.
  - `pg_dump -Fc` corre **dentro del contenedor** `db`, con la misma versión que el servidor. El `pg_dump` del host puede ser más antiguo y negarse a respaldar un servidor 18.
  - Crea `backups/<AAAAMMDD-HHMMSS>/` con `<base>.dump`, `storage.zip` y `manifest.json` (revisión Alembic, versión del servidor, fecha UTC y SHA-256 de cada artefacto). Antes de darlo por bueno comprueba el volcado con `pg_restore --list`.
  - Conserva los `BACKUP_RETENTION` respaldos más recientes (14 por defecto) en `BACKUP_DIR` (`./backups`).
- **Restauración:**
  1. Detenga la aplicación: `pg_restore --clean` necesita bloquear las tablas.
  2. Ejecute `python scripts/restore_backup.py backups/<AAAAMMDD-HHMMSS> --yes`.
  3. El script verifica los SHA-256 del manifiesto y el contenido de `storage.zip`, y aborta sin tocar nada si algo no cuadra. Luego respalda el estado actual (sin poda) y ejecuta `pg_restore --clean --if-exists --single-transaction --no-owner` en el contenedor: si falla, la BD queda como estaba. Por último reemplaza `storage/`.
  4. Arranque la aplicación.
- Programe `backup.py` (Programador de tareas de Windows o cron) y copie `backups/` fuera del equipo. Un respaldo en el mismo disco no protege contra la pérdida del disco.

## Pruebas

```powershell
pip install -r requirements-dev.txt
docker compose up -d --wait db   # las pruebas necesitan PostgreSQL
pytest                      # pruebas con umbral de cobertura (pyproject.toml) y coverage.xml para SonarQube
python scripts/check.py     # ruff, formato, alembic check, pytest y pip-audit (--skip-audit sin conexión)
```

- Cada sesión de `pytest` crea una base temporal `portal_test_<aleatorio>` en el servidor y un `storage/` temporal, y los elimina al terminar, también si la sesión falla. No modifica la base de trabajo ni `storage/` del proyecto: al terminar compara el número de filas de cada tabla y la huella de `storage/`.
- Si el servidor no responde, la sesión se cancela indicando ejecutar `docker compose up -d --wait db`.
- Otro servidor: defina `TEST_DATABASE_URL` (`postgresql+psycopg://...`); se usa en lugar de `DATABASE_URL`. Si no tiene acceso al contenedor `db`, defina también `PG_CLIENT=local` para que las pruebas de respaldo usen `pg_dump`/`pg_restore` del host, que deben ser de la misma versión mayor que el servidor o más nuevos. El CI compartido necesitará una de estas dos opciones.
- `scripts/check.py` ejecuta `alembic check` sobre otra base temporal, que elimina al terminar aunque el paso falle.
- La cobertura mínima de `app/` es del 93 % (`--cov-fail-under`).

Cubre:

- login, CSRF, limitación de intentos y política de contraseñas;
- sesiones revocables, RBAC y aislamiento entre proveedores;
- carga y descarga de documentos (firmas de contenido, tamaño, path traversal);
- parser CFDI y reglas XML/FIN/DAT, incluido el límite del día 20 en hora local;
- dinero exacto (`NUMERIC` sin redondeo silencioso), restricciones de la BD, plan de consulta con `EXPLAIN` y migraciones sobre una base PostgreSQL vacía;
- cabeceras de seguridad, errores sin traza y log JSON sin datos sensibles;
- respaldo, restauración, reinicio de demo y empaquetado.

## Dependencias

- `requirements.txt` declara las dependencias directas fijadas, y `requirements.lock` las congela todas (incluidas las transitivas) con hashes. El lock es universal: sirve en Windows, Linux y macOS.
- Regenerar el lock tras cambiar `requirements.txt`:

  ```bash
  uv pip compile --universal --generate-hashes --python-version 3.12 requirements.txt -o requirements.lock
  ```

- Auditar vulnerabilidades conocidas: `pip-audit -r requirements.lock` (y `pip-audit -r requirements-dev.txt` para las herramientas).
- Resultado de la auditoría del 2026-09-24: se corrigieron avisos en `starlette` (0.47.3 → 1.3.1, que obliga a subir `fastapi` a 0.133.1), `lxml` (6.1.3), `python-dotenv` (1.2.3), `python-multipart` (0.0.32) y `pytest` (9.0.3). Después se añadió el driver `psycopg[binary]` 3.3.6 (con libpq incluida en wheels para Windows, Linux y macOS). El lock no tiene avisos conocidos.

## Estructura

```text
app/
  core/          configuración, seguridad, DB, enums y logging
  models/        entidades SQLAlchemy
  repositories/ consultas con alcance por usuario
  routers/       auth, dashboard, facturas, proveedores, contratos y admin
  rules/         reglas DOC/XML/SUP/CON/FIN/DAT/SEM
  services/      storage, XML, PDF, conciliación, score, auditoría, workflow y notificaciones por correo
    ai/          interfaz, mock y adaptadores Azure
  templates/     interfaz Jinja server-rendered
  static/        CSS y JavaScript Vanilla
alembic/         migraciones explícitas (una revisión por cambio de modelo)
compose.yaml     PostgreSQL local (servicio db)
data/            documentos sintéticos versionados
scripts/         .env, BD, seed, reset, respaldo/restauración, utilidades de PostgreSQL (pgtools), empaquetado y check
storage/         uploads segregados por proveedor/factura
tests/           pruebas críticas automatizadas
```

## Flujo funcional

Login → alta de factura → carga/reemplazo documental → parser XML/PDF → reglas → score y evidencia → envío a revisión → aceptación/rechazo/corrección → marcado manual para ClickBalance.

El proveedor sólo observa sus facturas. `INTERNAL` revisa y decide. `ADMIN` añade administración de usuarios, proveedores, contratos, reglas visibles y Audit Log.

## Reglas implementadas

- `DOC-001..009`: archivos mínimos según el origen del proveedor (XML y PDF del CFDI, orden de compra, Vo.Bo., Invoice y otros tipos obligatorios; ver [Archivos mínimos por tipo de proveedor](#archivos-mínimos-por-tipo-de-proveedor)), contrato/anexo disponible, complemento y procesabilidad.
- `XML-001..008`: parseabilidad, receptor, PPD, FormaPago 99, UsoCFDI, UUID, moneda y esenciales.
- `SUP-001..004`: proveedor activo, contrato vigente, expediente mínimo y vigencia aproximada.
- `CON-001..004`: contrato, proyecto, periodo y heurística mes/tecnología.
- `DAT-001`: recepción del día 1 al 20; advertencia no fatal.
- `FIN-001..006`: límite autorizado, consistencia, moneda, UUID/número duplicados y diferencia absoluta/porcentual.
- `SEM-001`: comparación semántica mediante adaptador; el mock reconoce Power Platform/Power Automate con confianza 0.93.

`SEM-002..004` quedan reservadas como extensión. Los parámetros de negocio (receptor, método/forma de pago, usos CFDI y pesos del score) tienen una sola fuente, `BUSINESS_RULES` en `app/core/constants.py`, que usan tanto el motor como la vista `/admin/rules`.

### Cálculo del score

Cada regla evaluada aporta al denominador según severidad: `CRITICAL=35`, `ERROR=18`, `WARNING=6`, `INFO=0`. Un `FAIL` o `WARNING` descuenta su peso. `NOT_APPLICABLE` y `NOT_EVALUATED` no alteran el denominador. Una falla `CRITICAL` genera bloqueo; una evidencia AI de baja confianza permanece diferenciada y nunca equivale a aprobación administrativa.

## Archivos mínimos por tipo de proveedor

El Administrador define en **Administración › Archivos mínimos** (`/admin/required-documents`) qué archivos debe cargar el proveedor con cada factura, por separado para el proveedor **Nacional** y el **Internacional** (`suppliers.origin`):

| Nivel | En la carga documental | En la prevalidación |
| --- | --- | --- |
| Obligatorio | Se ofrece; el checklist indica cuántos faltan | Si falta, su regla DOC resulta `FAIL` y la factura queda en "Requiere corrección" |
| Opcional | Se ofrece | No se exige |
| No aplica | No se ofrece; el servidor rechaza la carga | No se exige |

- **Catálogo** (`invoice_document_types`): 10 tipos del sistema, con nombre en español, descripción y formatos admitidos (PDF, PNG, JPEG, XML, TXT), más los tipos soporte que cree el Administrador. La carga documental rechaza con HTTP 400, antes de escribir el archivo, un tipo que no aplica a la factura o una extensión que el tipo no admite.
- **Valores iniciales:** Nacional exige XML y PDF del CFDI, orden de compra y Vo.Bo., y conserva el comportamiento anterior. Internacional exige Invoice (PDF), orden de compra y Vo.Bo. Contrato, anexo y documentación adicional son opcionales para ambos; los complementos de pago sólo aplican al Nacional.
- **Niveles fijos:** XML y PDF del CFDI son obligatorios para el Nacional y no aplican al Internacional; el Invoice, al revés. La pantalla los muestra con candado, el servidor rechaza cambiarlos (409) y la base de datos los garantiza con un `CHECK`.
- **Tipos soporte:** el Administrador los da de alta (nombre, descripción, formatos y un nivel por origen, "No aplica" por defecto), los edita y los desactiva o reactiva. Su clave es `SOPORTE_<id>`. Nunca se borran, y los documentos ya cargados siguen visibles y descargables en el detalle de la factura. Los tipos del sistema no se editan ni se desactivan.
- **Reglas:** DOC-001 (XML del CFDI, `CRITICAL`), DOC-002 (PDF del CFDI), DOC-003 (orden de compra) y DOC-004 (Vo.Bo.) resultan `PASS`/`FAIL` cuando su tipo es obligatorio para el origen y `NOT_APPLICABLE` en otro caso. DOC-008 evalúa el Invoice (`CRITICAL`) y DOC-009 genera un resultado por cada otro tipo obligatorio, con su clave en la fuente.
- **Vigencia:** la configuración se lee en cada prevalidación. Una factura que ya salió de los estados editables conserva sus resultados; una editable se evalúa con la configuración vigente al volver a prevalidarse.
- **Concurrencia y auditoría:** el formulario lleva la huella `config_version`; si otro Administrador guardó antes, el guardado responde 409 sin cambios. Cada cambio queda en el Audit Log (`INVOICE_DOCUMENT_REQUIREMENTS_UPDATED`, `INVOICE_DOCUMENT_TYPE_CREATED`, `INVOICE_DOCUMENT_TYPE_UPDATED` e `INVOICE_DOCUMENT_TYPE_STATUS_CHANGED`) con los valores anterior y nuevo.

**Probar con un proveedor internacional.** Los proveedores demo son nacionales; un internacional se prepara así:

1. Como `ADMIN`, registrar el proveedor con la carga masiva (`/suppliers/import`), origen Internacional. Queda en estatus "Registrado".
2. Autorizarlo desde **Proveedores** (filtro "Registrado", casilla y "Autorizar seleccionados"). Con el transporte `file`, sus credenciales quedan en un `.eml` de `outbox/`.
3. Crear su contrato en **Contratos**.
4. Iniciar sesión con el usuario y la contraseña temporal del correo, dar de alta una factura y abrir su carga documental: se ofrecen el Invoice y los soportes configurados, no el XML ni el PDF del CFDI.

## Plantillas de correo

El Administrador define en **Administración › Plantillas de correo** (`/admin/notification-templates`) el asunto y el cuerpo de los correos que se envían cuando una factura cambia de estatus. Hay exactamente una plantilla por evento, creada por la migración `0004_notification_templates` con un texto predeterminado que reproduce las reglas de negocio. Las plantillas no se crean, eliminan ni desactivan, y el destinatario lo fija la regla de negocio de cada evento:

| Evento | Lo dispara | Destinatario | Obligatorias en el cuerpo | Otras variables |
| --- | --- | --- | --- | --- |
| Autorizada (`INVOICE_AUTHORIZED`) | HU-20 (RN-HU20-02) | Recepción de Facturas | `numero_factura`, `proveedor`, `monto` | `folio_interno`, `estatus`, `fecha_estatus` |
| Rechazada (`INVOICE_REJECTED`) | HU-20 (RN-HU20-03) | Proveedor (correo del catálogo) | `numero_factura`, `observaciones` | `folio_interno`, `proveedor`, `monto`, `estatus`, `fecha_estatus` |
| Observaciones (`INVOICE_OBSERVATIONS`) | HU-20 (RN-HU20-03) | Proveedor (correo del catálogo) | `numero_factura`, `observaciones` | `folio_interno`, `proveedor`, `monto`, `estatus`, `fecha_estatus` |
| Cancelada (`INVOICE_CANCELLED`) | HU-14 | Recepción de Facturas | `numero_factura`, `proveedor`, `fecha_limite_cancelacion` | `folio_interno`, `monto`, `estatus`, `fecha_estatus` |
| Credenciales de acceso (`SUPPLIER_CREDENTIALS`) | HU-03, al autorizar al proveedor | Proveedor (correo del catálogo), sin copias | `usuario`, `contrasena_temporal`, `url_portal` | `proveedor` |

| Variable | Contenido | Ejemplo de la vista previa |
| --- | --- | --- |
| `numero_factura` | Número de la factura que capturó el proveedor | `A-1024` |
| `folio_interno` | Folio interno del portal | `FAC-2026-00042` |
| `proveedor` | Razón social del proveedor | `Servicios Digitales del Norte SA de CV` |
| `monto` | Total con separador de miles, dos decimales y moneda | `$116,000.00 MXN` |
| `estatus` | Nombre del evento | `Rechazada` |
| `fecha_estatus` | Fecha y hora del cambio de estatus (`dd/mm/aaaa HH:MM`, zona de negocio) | `25/09/2026 10:30` |
| `observaciones` | Causa que capturó el PMO | `El subtotal del XML no coincide con el de la orden de compra.` |
| `fecha_limite_cancelacion` | Fecha de la solicitud de cancelación + 72 horas | `28/09/2026 10:30` |
| `usuario` | Correo con el que el proveedor inicia sesión | `contacto@serviciosdelnorte.mx` |
| `contrasena_temporal` | Contraseña temporal generada al autorizar | `Ejemplo#Temporal2026` |
| `url_portal` | Dirección de inicio de sesión del portal | `https://proveedores.ultrasist.com.mx/login` |

- **Texto:** plano, sin HTML. Una variable se escribe `{{numero_factura}}` (se admiten espacios interiores) y sólo se reemplaza por su valor: no hay expresiones, filtros ni condiciones, y el texto nunca pasa por Jinja2. Una llave sencilla es texto normal. El asunto ocupa una línea de hasta 200 caracteres; el cuerpo, hasta 5000. Al guardar se recortan los espacios de los extremos y `CRLF` pasa a `LF`.
- **Validación:** al guardar y en la vista previa se reportan juntos, con HTTP 400 y el formato "Campo: mensaje", los campos vacíos o demasiado largos, las variables sin cerrar, las que no son de la plantilla y las obligatorias que faltan en el cuerpo.
- **Vista previa:** compone el borrador con los datos de ejemplo de la tabla, sin JavaScript y sin guardar ni auditar.
- **Texto predeterminado:** "Cargar texto predeterminado" lo pone en el formulario; la plantilla no cambia hasta pulsar Guardar.
- **Concurrencia y auditoría:** el formulario lleva la versión de la plantilla; si otro Administrador guardó antes, el guardado responde 409 sin cambios. Un guardado sin cambios no aumenta la versión. Cada cambio queda en el Audit Log (`NOTIFICATION_TEMPLATE_UPDATED`) con el asunto, el cuerpo y la versión anteriores y nuevos, y en el log técnico (`notification_template.updated`), sin el texto.
- **Composición para HU-20 y HU-14:** `app.services.notification_templates.compose(db, NotificationEvent.INVOICE_REJECTED, numero_factura=..., folio_interno=..., proveedor=..., monto=Decimal(...), moneda="MXN", fecha_estatus=..., observaciones=...)` devuelve `ComposedEmail(subject, body)` con la plantilla vigente.
  - Formatea montos y fechas, y deja el asunto en una sola línea de hasta 255 caracteres.
  - Lanza `NotificationDataError` si falta una variable del evento o si una obligatoria llega vacía.
  - Si la plantilla guardada no es válida (por ejemplo, modificada por SQL), usa el texto predeterminado y registra `notification.template_fallback`.
  - No envía el correo: para enviarlo use `notification_service.notify()` (sección siguiente).
- **Reinicio de la demo:** `reset_demo.py` recrea el esquema, así que las plantillas vuelven a su texto predeterminado.

## Correo y notificaciones

El Administrador define en **Administración › Notificaciones** (`/admin/notifications`) a qué direcciones llegan los avisos (HU-08). El destinatario principal de cada evento lo fija su regla de negocio; la pantalla configura:

- **Buzón "Recepción de Facturas":** de 1 a 10 correos. La migración `0005_notification_recipients` lo siembra con `recepcionfacturas@ultrasist.com.mx`. Recibe los avisos de facturas Autorizadas y Canceladas.
- **Copias por evento:** de 0 a 10 correos en `Cc` para Autorizada, Rechazada, Observaciones y Cancelada. Se omiten las que ya están en "Para".
- **Correo de prueba** a una dirección que indique el Administrador, con un texto fijo.
- **Transporte** vigente en solo lectura, sin usuario ni contraseña, y los **últimos 20 envíos** con su resultado.

Las listas se capturan una dirección por línea (también se aceptan comas o punto y coma). Al guardar se pasan a minúsculas y se quitan las repetidas; todos los errores se muestran juntos con HTTP 400. El formulario lleva una huella de la configuración: si otro Administrador guardó antes, responde 409 sin cambios. Cada cambio queda en el Audit Log (`NOTIFICATION_RECIPIENTS_UPDATED`, sólo las listas que cambiaron) y en el log técnico (`notification_recipients.updated`, sin direcciones).

**Transporte.** Se configura en `.env` (tabla de variables abajo):

- `MAIL_BACKEND=file`, el valor por omisión fuera de producción, **no envía**: escribe cada correo como `.eml` (permisos `0600`) en `MAIL_OUTBOX_DIR` (`./outbox`, excluido de git y de los respaldos). Ábralo con cualquier cliente de correo para revisarlo.
- `MAIL_BACKEND=smtp` envía con `smtplib` (STARTTLS o SSL con verificación del certificado) y exige `SMTP_HOST` y `MAIL_FROM`. Es el valor por omisión en producción, donde el arranque se aborta con `MAIL_BACKEND=file` o `SMTP_SECURITY=none`.

**Envío para HU-03, HU-14 y HU-20.** Después de confirmar la transacción de negocio:

```python
notification_service.notify(
    db,
    NotificationEvent.INVOICE_REJECTED,
    supplier_email=invoice.supplier.email,  # sólo en los eventos dirigidos al proveedor
    entity="Invoice",
    entity_id=invoice.id,
    user_id=user.id,
    **valores,  # los mismos de notification_templates.compose()
)
```

- Resuelve los destinatarios con la configuración vigente, compone el correo con la plantilla de HU-05 y lo envía en texto plano UTF-8.
- Registra el intento en `email_deliveries` (evento, destinatarios, resultado, error técnico, entidad y usuario, **sin asunto ni cuerpo**) y confirma ese registro.
- Un error del servidor de correo **no** se propaga: el envío queda `FAILED` en la bitácora y en el log (`notification.failed`). No hay cola ni reintentos automáticos.
- Lanza `NotificationDataError` si falta el correo del proveedor o una variable de la plantilla.

## Autorización y acceso de proveedores

Un proveedor nace **"Registrado"** (carga masiva o formulario individual), sin usuario ni acceso al portal, y no puede facturar: SUP-001 exige el estatus operativo, que ahora se muestra como **"Autorizado"** (HU-02).

- **Autorización masiva:** en **Proveedores**, el Administrador filtra por "Registrado", marca las casillas (o "seleccionar todos") y pulsa "Autorizar seleccionados". Un modal pide confirmación, porque se enviarán las credenciales. Se autorizan hasta 100 proveedores por operación, en una sola transacción con las filas bloqueadas:
  - los que no están "Registrado" se omiten;
  - si el correo de un proveedor lo usa otro usuario, ese proveedor no se autoriza;
  - si ya tenía su propio usuario `PROVIDER`, se autoriza sin credenciales nuevas.
- **Credenciales (HU-03):** por cada proveedor autorizado sin usuario se crea un usuario `PROVIDER` con su correo del catálogo y una contraseña temporal aleatoria de 20 caracteres. El portal guarda sólo su hash. Después de confirmar la autorización se envía el correo "Credenciales de acceso" con el usuario, la contraseña y la dirección `/login` del servidor.
- **Resumen:** tras autorizar, el listado muestra a cada proveedor con "Credenciales enviadas", "Envío fallido" (con el error), "Ya tenía usuario", "Omitido" o "No autorizado". Los proveedores cuyo último envío falló llevan la marca "Credenciales no enviadas".
- **Expediente:** la sección "Acceso al portal" muestra el usuario, el último acceso y el último envío de credenciales. **"Reenviar credenciales"** genera una contraseña nueva (la anterior deja de funcionar), sólo mientras el proveedor no haya iniciado sesión.
- **Auditoría:** `SUPPLIER_STATUS_CHANGED`, `USER_CREATED` (origen `SUPPLIER_AUTHORIZATION`), `SUPPLIER_BULK_AUTHORIZED` y `SUPPLIER_CREDENTIALS_RESENT`, sin contraseñas. En el log técnico queda `supplier.bulk_authorize` sólo con contadores.
- **ClickCloud (RN-HU03-01):** `app/services/secret_vault.py` es el punto de integración. Recibe la contraseña temporal antes de confirmar la transacción; si falla, la autorización se revierte. Hoy el adaptador activo (`NullSecretVault`) no guarda nada: falta la API de ClickCloud.
- **Pendiente de HU-10:** nada obliga todavía al proveedor a cambiar la contraseña temporal en su primer acceso, y la contraseña no expira.

## Archivos y seguridad de PoC

- **Contraseñas:** Argon2 mediante `pwdlib`. Política en el servidor (ERS RF-06): 8 a 128 caracteres, con letra, número y carácter especial, y sin contraseñas comunes.
- **Login:** limitado por correo (bloqueo de `min(60, 2^(n-5))` minutos tras 5 fallos consecutivos) y por IP (20 fallos en 15 minutos). Responde 429 sin evaluar la contraseña.
- **Sesiones:** revocables del lado del servidor (`user_sessions`). La cookie firmada sólo lleva un identificador opaco y el token CSRF. Expiran tras 60 minutos de inactividad u 8 horas de duración, y se revocan al cerrar sesión o al deshabilitar al usuario.
- **CSRF:** token de sesión en todas las operaciones mutables, que sólo aceptan POST.
- **Cabeceras:** CSP `default-src 'self'`, `X-Frame-Options: DENY`, `nosniff` y `Referrer-Policy`, más HSTS sobre HTTPS. **No agregue scripts ni estilos en línea:** la CSP los bloquea; use archivos bajo `app/static/`.
- **Cargas:**
  - UUID interno como nombre de almacenamiento y SHA-256;
  - verificación del contenido contra la extensión (firmas PDF, PNG y JPEG; XML; texto UTF-8);
  - MIME derivado por el servidor, límite de tamaño y control de path traversal;
  - descarga siempre como `application/octet-stream` y adjunto.
- **PDFs:** se validan con PyMuPDF; un PDF sin texto se marca para OCR y no inventa contenido.
- **Autorización:** por rol y por pertenencia del objeto o documento.
- **Errores:** sin traza en la interfaz (la página muestra una referencia `request_id`); el detalle técnico queda en `logs/app.log` como JSON. Los errores de negocio responden 409.
- **Evidencia fiscal:**
  - no se permite el borrado físico de facturas;
  - las versiones sustituidas quedan con `is_current=false` y referencia al documento anterior;
  - el monto autorizado de un contrato sólo cambia mediante enmiendas auditadas.

`SECRET_KEY` es obligatoria (mínimo 32 caracteres; se rechaza el valor de ejemplo `change-me...`). `scripts/create_env.py` la genera al crear `.env`. `DEBUG` sólo sube el nivel de log; nunca muestra trazas al usuario.

Para producción use `APP_ENV=production`: la aplicación no arranca sin `SESSION_HTTPS_ONLY=true`, con cuentas demo activas, con `MAIL_BACKEND=file` ni con `SMTP_SECURITY=none`. Añada además políticas de retención, escaneo antimalware y gestión de secretos.

**Detrás de un proxy inverso**, arranque uvicorn con `--proxy-headers --forwarded-allow-ips=<IP del proxy>`. Sin eso, todas las peticiones parecen venir del proxy: el límite de login por IP se vuelve global y HSTS no se emite.

**Cifrado en reposo (requisito de infraestructura).** El volumen de PostgreSQL (`pgdata`) y `storage/` guardan en claro RFC, razones sociales, montos, datos bancarios y documentos. Con datos reales, cifre el disco donde Docker guarda sus volúmenes (BitLocker o LUKS) o use un servicio gestionado con cifrado (Azure Database for PostgreSQL). Restrinja también el acceso a `backups/`.

### Variables de entorno

| Variable | Por defecto | Descripción |
|---|---|---|
| `SECRET_KEY` | *(obligatoria)* | Firma de la cookie de sesión; mínimo 32 caracteres. |
| `APP_ENV` | `development` | `development`, `test` o `production`. Gobierna los valores por defecto y las verificaciones de arranque. |
| `DEBUG` | `false` | Sólo eleva el nivel de log. |
| `SESSION_HTTPS_ONLY` | según `APP_ENV` | Cookie `Secure`; `true` fuera de `development`. |
| `DATABASE_URL` | *(obligatoria)* | `postgresql+psycopg://usuario:contraseña@127.0.0.1:55432/portal`. `create_env.py` la genera; una URL de SQLite impide arrancar. |
| `POSTGRES_USER`, `POSTGRES_DB`, `POSTGRES_PASSWORD` | `portal`, `portal`, *(generada)* | Credenciales del contenedor `db`; Compose las lee del mismo `.env`. |
| `POSTGRES_PORT` | `55432` | Puerto publicado sólo en `127.0.0.1`. Si lo cambia, actualice también el puerto de `DATABASE_URL`. |
| `TEST_DATABASE_URL` | *(sin definir)* | Servidor donde `pytest` y `scripts/check.py` crean sus bases temporales; sin definir, se usa el de `DATABASE_URL`. |
| `PG_CLIENT` | `docker` | `docker`: `pg_dump`/`pg_restore` dentro del contenedor `db`. `local`: los binarios del host contra la URL (p. ej. CI con un servicio PostgreSQL). |
| `STORAGE_PATH`, `LOG_DIR`, `BACKUP_DIR` | `./storage`, `./logs`, `./backups` | Las rutas relativas se resuelven contra la raíz del proyecto, no contra el directorio de trabajo. |
| `BUSINESS_TIMEZONE` | `America/Mexico_City` | Zona de las reglas de calendario (corte del día 20) y del año del folio. |
| `BACKUP_RETENTION` | `14` | Respaldos que conserva `scripts/backup.py`. |
| `MAX_UPLOAD_MB` | `20` | Tamaño máximo por archivo. |
| `MAIL_BACKEND` | según `APP_ENV` | `smtp` o `file`; `smtp` en `production` y `file` (no envía) en los demás. |
| `MAIL_FROM` | *(obligatoria con `smtp`)* | Remitente, p. ej. `Portal de Proveedores ULTRASIST <no-reply@ultrasist.com.mx>`. Con `file`: `…<no-reply@portal.local>`. |
| `MAIL_OUTBOX_DIR` | `./outbox` | Directorio de los `.eml` del transporte `file`. |
| `SMTP_HOST`, `SMTP_PORT` | *(obligatoria con `smtp`)*, `587` | Servidor SMTP. |
| `SMTP_SECURITY` | `starttls` | `starttls`, `ssl` o `none` (prohibido en `production`). |
| `SMTP_USERNAME`, `SMTP_PASSWORD` | *(vacías)* | Si hay usuario, el transporte inicia sesión. La contraseña nunca se muestra ni se registra. |
| `SMTP_TIMEOUT` | `10` | Segundos de espera del servidor SMTP (1 a 120). |

## Empaquetado para distribución

`python scripts/package_release.py` genera `dist/<proyecto>-<fecha>.zip`:

- Con Git, incluye sólo los archivos versionados; sin Git, recorre el árbol aplicando una lista de exclusión.
- Nunca incluye `.env`, bases SQLite heredadas en `data/`, `logs/`, `storage/`, `backups/`, `.venv/` ni cachés. La base PostgreSQL vive en el volumen de Docker, fuera del árbol.
- Al terminar verifica el ZIP: si contiene algo prohibido, lo elimina y falla.

No distribuya copias comprimidas a mano del directorio de trabajo.

## AI Mock Mode

La configuración predeterminada es:

```dotenv
AI_ENABLED=false
DOCUMENT_AI_PROVIDER=mock
```

`LocalMockAnalyzer` no usa red y devuelve resultados reproducibles para análisis, campos, comparación, confidence y evidencia. El portal funciona íntegramente sin Azure.

## Preparación Azure

Los adaptadores de `app/services/ai/` validan configuración y fallan de forma controlada:

- `AzureDocumentIntelligenceAnalyzer`: OCR/extracción de PDF, OC, contrato y anexos.
- `AzureContentUnderstandingAnalyzer`: extracción semiestructurada y clasificación.
- `AzureFoundryAnalyzer`: comparación semántica y explicación.

Complete las variables Azure en `.env`, implemente la llamada HTTP/SDK dentro del adaptador y seleccione el proveedor. Ningún router, regla financiera ni modelo importa SDKs Azure directamente. Las keys nunca deben incluirse en Git.

## Datos de demostración

El seed crea 4 usuarios, 2 proveedores, 2 contratos, expedientes Anexo A, 10 facturas y Audit Log. Incluye: borrador, correcta, prevalidada, en revisión, aceptada, rechazada, corrección, excedente, RFC incorrecto, semántico y estados manuales de ClickBalance.

Los XML bajo `data/demo_documents/` son estructuralmente útiles para el parser, pero **no están timbrados ni son fiscalmente válidos**. El seed asigna a cada factura demo un UUID fiscal distinto y usa el PDF sintético versionado `data/demo_documents/factura_demo.pdf` (si faltara, lo genera en un directorio temporal sin modificar el repositorio).

## Limitaciones y fuera de alcance

- Sin validación SAT online, timbrado ni generación CFDI.
- Sin integración real ClickBalance o SAP Ariba; ClickBalance es un estado manual.
- Sin pagos, banca, firma, SharePoint, Blob, Azure SQL, SSO, despliegue Azure, Kubernetes o colas.
- Los adaptadores Azure son contratos preparados, no llamadas productivas.
- El catálogo de reglas (`BUSINESS_RULES`) se muestra en modo lectura; su edición persistente es un siguiente paso. Los archivos mínimos por origen sí son configurables.
- Las facturas de proveedores internacionales sólo cumplen la parte documental: sin CFDI, las reglas XML y SUP-003 las dejan en "Requiere corrección" hasta que HU-16 defina sus validaciones y su expediente.
- El portal envía las credenciales de los proveedores autorizados (HU-03), pero todavía ningún cambio de estatus de factura dispara correos: eso llega con HU-20 y HU-14. El envío es síncrono, sin cola ni reintentos automáticos.
- La contraseña temporal no se resguarda aún en ClickCloud (falta su API) y su cambio en el primer acceso llega con HU-10.
- La verificación documental del Anexo A es presencia/vigencia referencial, no validación legal.
- Bootstrap 5.3.3 y Bootstrap Icons están incluidos bajo `app/static/vendor/`; la interfaz tampoco requiere Internet.

## Próximos pasos para producción

Contenerizar la aplicación (Dockerfile y servicio `app` en Compose), PostgreSQL gestionado en Azure, Azure Blob con malware scanning, secretos administrados, Entra ID/External ID, cifrado y retención documental, workers para OCR, agregación centralizada del log JSON, pruebas E2E, accesibilidad formal y un workflow de excepciones con doble aprobación.
