# Invoice Portal PoC

Portal local de facturación y prevalidación de proveedores para ULTRASIST. Recibe expedientes, extrae CFDI 4.0, aplica reglas determinísticas, presenta una matriz de evidencia y soporta revisión administrativa con trazabilidad completa.

> **Datos exclusivamente DEMO.** Los RFC, XML, contratos, nombres y documentos incluidos son sintéticos, no tienen validez fiscal o legal y no representan personas reales.

## Principio de arquitectura

La solución separa cuatro responsabilidades:

1. **Reglas Python:** XML, RFC, documentos, fechas, montos, duplicados, contrato y transiciones.
2. **Extracción documental:** parser CFDI con `lxml` y PDF con PyMuPDF.
3. **AI semántica:** interfaz `DocumentAnalyzer`; por defecto usa un mock local reproducible.
4. **Human in the loop:** sólo un usuario `PMO` o `Administrador` puede registrar la decisión final.

La AI recomienda o aporta evidencia; el Rule Engine determina la prevalidación técnica y el usuario administrativo toma la decisión final. Un LLM nunca cambia una factura a `ACCEPTED`.

## Requisitos

- Python 3.12 recomendado (validado con 3.12.4).
- Windows PowerShell/CMD o Linux/macOS con shell POSIX.
- **Docker con Compose v2** para PostgreSQL y Keycloak: Docker Desktop en Windows y macOS; Docker Engine o Podman (con `podman compose` o el alias `docker`) en Linux. Sólo PostgreSQL y Keycloak corren en contenedores; la aplicación corre en el host.
- Puertos `55432` (PostgreSQL) y `58080` (Keycloak) libres en `127.0.0.1` (configurables con `POSTGRES_PORT` y `KEYCLOAK_PORT` en `.env`; el 5432 y el 5433 suelen estar ocupados por otras instancias).
- No requiere Node.js, Azure ni conexión a servicios externos para operar.

## Instalación en Windows PowerShell

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install --require-hashes -r requirements.lock
python scripts/create_env.py
docker compose up -d --wait db keycloak
python scripts/init_db.py
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

También puede ejecutar `scripts\create_venv.ps1` y después `run_local.ps1`. `run_local` crea o completa `.env`, levanta PostgreSQL y Keycloak (`docker compose up -d --wait db keycloak`), aplica las migraciones y siembra la demo sólo si la base está vacía. **Conserva los datos entre arranques.** El primer arranque de Keycloak tarda alrededor de un minuto (descarga la imagen e importa el realm).

En CMD use `.venv\Scripts\activate` y `run_local.bat`.

## Instalación en Linux/macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install --require-hashes -r requirements.lock
python scripts/create_env.py
docker compose up -d --wait db keycloak
python scripts/init_db.py
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

O bien `./run_local.sh`, que hace lo mismo. Abra <http://127.0.0.1:8000>: el portal lo lleva a la página de inicio de sesión de Keycloak. El health check está en <http://127.0.0.1:8000/health>.

## Cuentas demo

Existen sólo en el Keycloak local; el seed las crea (o las vuelve a enlazar) al sembrar la demo:

| Rol | Usuario |
|---|---|
| Administrador | `admin@poc.local` |
| PMO | `pmo@poc.local` |
| Proveedor moral | `proveedor1@poc.local` |
| Proveedor físico | `proveedor2@poc.local` |
| Proveedor internacional | `proveedor3@poc.local` |

- **Contraseña:** el valor de `DEMO_PASSWORD` en su `.env`. `scripts/create_env.py` la genera; ninguna contraseña demo está en el repositorio.
- La fuente única de estas cuentas es `app/core/demo.py`.
- En `test` o `production`, el seed genera contraseñas temporales aleatorias, las imprime una sola vez en consola y Keycloak pide cambiarlas en el primer acceso.
- Con `APP_ENV=production`, la aplicación **no arranca** mientras exista alguna cuenta `@poc.local` activa.

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

## Keycloak: inicio de sesión y cuentas

El portal no recibe ni guarda contraseñas (RN-HU03-01). La autenticación la hace **Keycloak**, el proveedor de identidad (IdP), con OIDC Authorization Code + PKCE (S256).

**Keycloak local.**

- Servicio `keycloak` de `compose.yaml` (`quay.io/keycloak/keycloak:26.7.4`, modo `start-dev`), sólo en `127.0.0.1:${KEYCLOAK_PORT}` (58080 por defecto). Consola: <http://127.0.0.1:58080/admin>, con `KC_BOOTSTRAP_ADMIN_USERNAME` y `KC_BOOTSTRAP_ADMIN_PASSWORD` del `.env`.
- Al arrancar importa el realm versionado `infra/keycloak/realm-ultrasist-portal.json` (roles `Administrador`, `Proveedor` y `PMO`; clientes `portal-facturas-web` y `portal-facturas-admin`; política de contraseñas; detección de fuerza bruta; eventos; sesión SSO de 60 min de inactividad y 8 h de máximo). El realm no contiene secretos: los de los clientes llegan como variables de entorno desde el `.env`, y sin ellas el contenedor no arranca.
- Los datos viven en el volumen `portal-facturas_keycloak-data`. El realm sólo se importa si no existe: para aplicar cambios del JSON, `docker compose rm -sf keycloak`, `docker volume rm portal-facturas_keycloak-data` y vuelva a levantarlo (se pierden las cuentas; `python scripts/reset_demo.py` o `python scripts/link_keycloak_users.py` las recrean).

**Inicio y cierre de sesión.**

- `/login` redirige a Keycloak con `state`, `nonce` y `code_challenge`. El callback (`/auth/callback`) valida la firma del ID token con el JWKS del realm, `iss`, `aud`, `exp` (60 s de tolerancia) y `nonce`.
- El usuario del portal se localiza **sólo por el `sub`** de su cuenta de Keycloak (`users.keycloak_sub`), nunca por correo. El token debe traer exactamente uno de los roles del portal, igual al del usuario local; si no, 403 y `LOGIN_DENIED` en la auditoría. Cambiar el rol de alguien exige cambiarlo en el portal y en Keycloak.
- La sesión sigue siendo del servidor (`user_sessions`); el ID token se guarda allí sólo para el cierre de sesión. Los access y refresh tokens se descartan.
- "Cerrar sesión" revoca la sesión local y termina la de Keycloak (`end_session_endpoint`).

**Primer acceso y contraseñas.** Ver "Primer acceso y cambio de contraseña".

**Keycloak no disponible.** Nadie puede iniciar sesión nueva (503 "El servicio de autenticación no está disponible.") ni autorizar proveedores, dar de alta usuarios o reenviar credenciales (503). Las sesiones ya abiertas siguen funcionando hasta expirar. `/health` no consulta Keycloak.

**Migrar usuarios existentes.** Tras `alembic upgrade head` (revisión `0015_keycloak_identity`), `python scripts/link_keycloak_users.py --dry-run` informa qué haría y `python scripts/link_keycloak_users.py` enlaza o crea en Keycloak a cada usuario sin cuenta, con una contraseña temporal. Vacía su `password_hash`, audita `USER_LINKED_TO_IDP` y entrega la temporal: a los proveedores autorizados por el correo de credenciales y a los demás en consola, una sola vez. Es idempotente; un conflicto (el correo tiene otro rol del portal en Keycloak) se informa y el usuario queda sin enlazar. Haga un respaldo antes: tras enlazar, el downgrade de `0015` exige restaurarlo.

**Despliegue en QA y producción.**

- Instancia de Keycloak **dedicada**, por HTTPS (`KEYCLOAK_SERVER_URL` con `https://` es obligatoria en `production`), con el realm importado y las URIs de redirección (`/auth/callback`) y de cierre (`/`) del dominio real del portal.
- Secretos de los clientes: generados en el servidor de Keycloak y copiados sólo a las variables de entorno del portal.
- La lista `infra/keycloak/common_passwords.txt` debe instalarse en `data/password-blacklists/` del servidor (la exige la política `passwordBlacklist`).
- *Rate limiting* por IP en el proxy inverso frente a Keycloak: Keycloak bloquea por cuenta, no por IP.
- Correo de Keycloak (para funciones futuras como la recuperación de contraseña): el mismo servidor y remitente SMTP del portal (`smtpServer` del realm); la contraseña SMTP se configura en Keycloak, nunca en el JSON versionado.

**Lista de contraseñas comunes.** Se mantiene a mano en `infra/keycloak/common_words.txt`. `python scripts/build_password_blacklist.py` genera `common_passwords.txt` con esas entradas y sus variantes decoradas (`password1!`, `portal2026!`): como la política exige dígito y carácter especial, sin variantes la lista no bloquearía ninguna contraseña. Una prueba verifica que el archivo generado esté al día.

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
docker compose up -d --wait db   # las pruebas necesitan PostgreSQL (no Keycloak)
pytest                      # pruebas con umbral de cobertura (pyproject.toml) y coverage.xml para SonarQube
python scripts/check.py     # ruff, formato, alembic check, pytest y pip-audit (--skip-audit sin conexión)
```

- Cada sesión de `pytest` crea una base temporal `portal_test_<aleatorio>` en el servidor y un `storage/` temporal, y los elimina al terminar, también si la sesión falla. No modifica la base de trabajo ni `storage/` del proyecto: al terminar compara el número de filas de cada tabla y la huella de `storage/`.
- Si el servidor no responde, la sesión se cancela indicando ejecutar `docker compose up -d --wait db`.
- Otro servidor: defina `TEST_DATABASE_URL` (`postgresql+psycopg://...`); se usa en lugar de `DATABASE_URL`. Si no tiene acceso al contenedor `db`, defina también `PG_CLIENT=local` para que las pruebas de respaldo usen `pg_dump`/`pg_restore` del host, que deben ser de la misma versión mayor que el servidor o más nuevos. El CI compartido necesitará una de estas dos opciones.
- `scripts/check.py` ejecuta `alembic check` sobre otra base temporal, que elimina al terminar aunque el paso falle.
- La cobertura mínima de `app/` es del 93 % (`--cov-fail-under`).
- Ninguna prueba necesita Keycloak ni red: `tests/idp.py` simula su API de administración y su OIDC (discovery, JWKS firmado por sesión y token endpoint con PKCE) sobre un `httpx.MockTransport`. Los scripts que corren en un subproceso (`init_db`, `reset_demo`) lo usan mediante un servidor local en `127.0.0.1`.

Cubre:

- inicio de sesión OIDC (state, nonce, firma, `iss`, `aud`, `exp`, PKCE), enlace por `sub`, roles, cierre de sesión y cambio de contraseña en Keycloak;
- aprovisionamiento en Keycloak (éxito, fallo parcial, cuenta existente, conflicto, Keycloak caído), migración de usuarios, y realm y política de contraseñas versionados;
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
- Resultado de la auditoría del 2026-09-24: se corrigieron avisos en `starlette` (0.47.3 → 1.3.1, que obliga a subir `fastapi` a 0.133.1), `lxml` (6.1.3), `python-dotenv` (1.2.3), `python-multipart` (0.0.32) y `pytest` (9.0.3). Después se añadió el driver `psycopg[binary]` 3.3.6 (con libpq incluida en wheels para Windows, Linux y macOS). El 2026-09-30 se añadió `Authlib` 1.7.2 (cliente OIDC; trae `cryptography` y `joserfc`) y `httpx` pasó a ser dependencia de producción. Se fijó la 1.7.2 porque la 1.8.0 cambia su cliente HTTP a `httpx2`. El lock no tiene avisos conocidos.

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
compose.yaml     PostgreSQL y Keycloak locales (servicios db y keycloak)
infra/keycloak/  realm versionado sin secretos y lista de contraseñas comunes
data/            documentos sintéticos versionados
scripts/         .env, BD, seed, reset, respaldo/restauración, utilidades de PostgreSQL (pgtools), empaquetado y check
storage/         uploads segregados por proveedor/factura
tests/           pruebas críticas automatizadas
```

## Flujo funcional

Login → alta de factura → carga/reemplazo documental → "Verificar" (opcional) → "Enviar a validación" (parser XML/PDF, reglas, score y evidencia) → decisión del PMO: autorizar, rechazar u observaciones, con su correo (Recepción de Facturas o el proveedor). En cualquier momento, el proveedor puede cancelar la factura con su acuse; Recepción de Facturas recibe el aviso.

El proveedor registra, carga, verifica y envía sus facturas, y sólo ve las suyas. `PMO` revisa y decide. `Administrador` añade administración de usuarios, proveedores, contratos, reglas visibles y Audit Log. `PMO` y `Administrador` consultan las facturas y descargan sus documentos, pero no las registran, cargan, verifican ni envían (403).

### Estatus de la factura

Modelo del ERS (§3.6), fijado por EP-01 para el proveedor y el PMO:

| Estatus | Clave | Cuándo | ¿El proveedor puede editar? |
| --- | --- | --- | --- |
| Borrador | `DRAFT` | Registrada; faltan archivos obligatorios | Sí |
| Cargada | `UPLOADED` | Archivos obligatorios completos | Sí |
| Enviada | `UNDER_REVIEW` | El envío superó las validaciones | No |
| Autorizada | `ACCEPTED` | Decisión del PMO | No |
| Rechazada | `REJECTED` | Decisión del PMO; no admite otra decisión | No |
| Observaciones | `REQUIRES_CORRECTION` | El PMO pidió correcciones | Sí: corrige y reenvía |
| Cancelada | `CANCELLED` | El proveedor la canceló con su acuse; es final | No |

- **Registro (HU-12):** el formulario usa el proveedor del usuario y sólo ofrece sus contratos activos; los de otros proveedores nunca llegan al navegador. Un proveedor que no está "Autorizado" no puede registrar (409). La factura nace en "Borrador" y cada carga o reemplazo de documento la pasa a "Cargada" o de vuelta a "Borrador" según los [archivos mínimos](#archivos-mínimos-por-tipo-de-proveedor); con los obligatorios completos, la carga documental avisa "Factura cargada. Ya puede enviarla a validación". "Observaciones" no se recalcula.
- **Verificar:** ejecuta el motor y guarda sus resultados sin cambiar el estatus. El detalle lista las "Reglas que impiden el envío".
- **Envío (HU-13):** "Enviar a validación", desde "Cargada" u "Observaciones", ejecuta el motor con la configuración vigente en ese momento. Sin ningún `FAIL`, la factura pasa a "Enviada" con `submitted_at` y la auditoría `INVOICE_SUBMITTED`. Con algún `FAIL` (crítico o error), responde 409, conserva el estatus y muestra cada regla que lo impide con el valor esperado y el detectado. Las advertencias no bloquean. Desde "Borrador" responde 409 ("Faltan archivos obligatorios") sin ejecutar el motor.
- **Duplicados (RN-HU13-01):** el UUID del CFDI (folio fiscal) no se repite en ninguna otra factura, de ningún proveedor ni estatus, incluidas las rechazadas (FIN-004 y `uq_invoices_uuid`). El mensaje no revela datos de la otra factura.
- **Concurrencia:** la carga, la verificación y el envío bloquean la fila de la factura, así que se ejecutan uno después del otro.
- **Migración `0010_invoice_status_model`:** retira `VALIDATING`, `VALIDATION_FAILED` y `PREVALIDATED`. Las facturas previas al envío pasan a "Cargada" o "Borrador" según sus obligatorios, salvo las que el PMO devolvió y aún no se reenvían, que quedan en "Observaciones". Cada cambio queda en el Audit Log como `STATUS_MIGRATED`.

### Cancelación de la factura

El proveedor cancela su factura desde cualquier estatus excepto "Cancelada" (HU-14, RF-09), también si ya está "Autorizada" o "Rechazada": en México el receptor del CFDI tiene 72 horas para aceptar la cancelación ante el SAT.

- **Sección "Cancelar factura"** al final del detalle, sólo para el proveedor. Pide el "Acuse de cancelación" (PDF o XML) y la casilla "Confirmo que la factura se canceló y adjunto su acuse". Sin confirmación, sin acuse o con otro formato responde 400 antes de escribir el archivo, y la factura no cambia. El acuse XML del SAT no se procesa como CFDI; al proveedor internacional le basta un PDF que documente la cancelación.
- **Registro:** bloquea la fila, guarda el acuse como documento `CANCELLATION_ACK` y pasa la factura a "Cancelada" con `cancelled_at`, `cancelled_by` y `cancellation_deadline` (`cancelled_at` + 72 horas naturales). Audita `STATUS_CHANGED` e `INVOICE_CANCELLED` con el estatus anterior, el acuse y la fecha límite. Una segunda cancelación responde 409 "La factura ya está cancelada".
- **Factura cancelada:** no admite documentos, verificación, envío ni decisión (409) y sale de la bandeja del PMO. El detalle muestra a todos los roles "Cancelada el … Recepción de Facturas debe aceptar la cancelación antes del …" (hora de negocio) y el acuse entre los documentos.
- **Correo:** después de confirmar, el aviso "Cancelada" va al buzón "Recepción de Facturas" con número, proveedor, monto, folio y fecha límite. El proveedor ve "Se notificó a Recepción de Facturas" o "No se pudo notificar…", sin direcciones. Si falló, el PMO ve "Reenviar notificación" en el detalle, como con los correos de la decisión.
- **Fuera de alcance:** registrar en el portal la aceptación de la cancelación (ocurre ante el SAT), el motivo SAT, la consulta del estatus del CFDI y revertir una cancelación.
- **Migración `0012_invoice_cancellation`:** agrega las columnas con el `CHECK ck_invoices_cancellation`, el estatus `CANCELLED` y el tipo del sistema "Acuse de cancelación". Se detiene si un tipo soporte ya usa ese nombre; el downgrade se niega si hay facturas canceladas.

### Seguimiento del proveedor

El proveedor da seguimiento a sus facturas (HU-17, RF-16):

- **Tablero:** total de facturas con su monto acumulado e indicadores Enviadas, Observaciones, Autorizadas, Rechazadas y Canceladas. Cada indicador abre el listado filtrado por su estatus. El PMO y el Administrador ven los mismos indicadores sobre todas las facturas.
- **Listado:** sólo sus facturas, con búsqueda, filtro por los siete estatus y 25 por página. Una factura de otro proveedor responde 404.
- **Causa de la decisión:** en "Rechazada" el detalle destaca "Motivo del rechazo" y en "Observaciones", "Observaciones del PMO", con el texto de la última decisión: el mismo del correo. En "Observaciones" añade "Corrija lo indicado y vuelva a enviar la factura" con el enlace a la carga documental. En los demás estatus no hay aviso de observaciones: las de rondas anteriores quedan en el seguimiento.
- **Seguimiento:** sus envíos, las decisiones del PMO (atribuidas a "PMO", sin el nombre del revisor ni los comentarios internos) y la cancelación con su fecha límite, en orden cronológico.

## Listados

Todos los listados de registros se paginan en la base de datos (`LIMIT/OFFSET`) y muestran "Página N de M · T registros":

| Listado | Por página | Orden | Búsqueda |
| --- | --- | --- | --- |
| Facturas (`/invoices`) | 25 | más recientes (bandeja del PMO: la que más ha esperado) | folio, número, proyecto, proveedor |
| Proveedores (`/suppliers`) | 25 | razón social | razón social, RFC, ID fiscal, correo (con el filtro de estatus) |
| Usuarios (`/admin/users`) | 25 | nombre | nombre, correo |
| Contratos (`/contracts`) | 25 | más recientes | proyecto, proveedor |
| Claves de catálogo (`/admin/catalogs/…`) | 25 | clave | clave, descripción |
| Bitácora de envíos (`/admin/notifications`) | 25 | más recientes | — |
| Audit Log (`/admin/audit`) | 50 | más recientes | — |

- La búsqueda no distingue mayúsculas y trata `%` y `_` como caracteres literales.
- **Altas:** crear un usuario, un contrato o una clave regresa al listado buscando el registro creado, con el aviso "Usuario creado", "Contrato creado" o "Clave agregada". El alta de un proveedor lleva a su expediente.
- **Acciones:** habilitar un usuario, registrar una enmienda o editar una clave regresa a la misma búsqueda y página.
- **Transacciones:** cada alta o acción se confirma en una sola transacción de PostgreSQL con su auditoría: o queda todo o no queda nada. Los correos salen después de confirmar y un envío fallido se reenvía desde la pantalla.
- No se paginan los formularios de configuración (archivos mínimos, reglas, plantillas, índice de catálogos) ni los resultados de un archivo (vista previa de la carga masiva).

## Reglas implementadas

- `DOC-001..009`: archivos mínimos según el origen del proveedor (XML y PDF del CFDI, orden de compra, Vo.Bo., Invoice y otros tipos obligatorios; ver [Archivos mínimos por tipo de proveedor](#archivos-mínimos-por-tipo-de-proveedor)), contrato/anexo disponible, complemento y procesabilidad.
- `XML-001..010`: parseabilidad, RFC del receptor, método y forma de pago, UsoCFDI, UUID, moneda, esenciales, razón social y código postal del receptor, con los valores de [Reglas de validación](#reglas-de-validación).
- `SUP-001..004`: proveedor activo, contrato vigente, expediente mínimo y vigencia aproximada (`SUP-003` y `SUP-004` no aplican al proveedor internacional).
- `CON-001..004`: contrato, proyecto, periodo y heurística mes/tecnología.
- `DAT-001`: recepción del día 1 al 20; advertencia no fatal.
- `FIN-001..006`: límite autorizado, consistencia, moneda, UUID/número duplicados y diferencia absoluta/porcentual. `FIN-007`: Invoice duplicado por nombre de archivo (sólo internacional).
- `INT-001..004`: datos del proveedor y de ULTRASIST en el texto del Invoice (sólo internacional; advertencias). Ver [Facturas de proveedores internacionales](#facturas-de-proveedores-internacionales).
- `SEM-001`: comparación semántica mediante adaptador; el mock reconoce Power Platform/Power Automate con confianza 0.93.

`SEM-002..004` quedan reservadas como extensión. Los parámetros del motor (datos del receptor, método y forma de pago, usos de CFDI e interruptores) tienen una sola fuente, la tabla `validation_settings`, que el Administrador edita en `/admin/rules` y el motor lee en cada prevalidación. Las monedas aceptadas son las activas del catálogo de monedas. Sólo los pesos del score siguen en `BUSINESS_RULES` (`app/core/constants.py`).

### Cálculo del score

Cada regla evaluada aporta al denominador según severidad: `CRITICAL=35`, `ERROR=18`, `WARNING=6`, `INFO=0`. Un `FAIL` o `WARNING` descuenta su peso. `NOT_APPLICABLE` y `NOT_EVALUATED` no alteran el denominador. Una falla `CRITICAL` genera bloqueo; una evidencia AI de baja confianza permanece diferenciada y nunca equivale a aprobación administrativa.

## Reglas de validación

El Administrador define en **Administración › Reglas de validación** (`/admin/rules`) los datos de ULTRASIST y los parámetros del CFDI contra los que se comparan las facturas (HU-06). La migración `0007_validation_rules_catalogs` siembra los valores que antes estaban fijos en el código, y la siguiente verificación o envío usa lo que se guarde.

| Regla | Compara | Severidad | Valor inicial |
| --- | --- | --- | --- |
| XML-002 | `Receptor.Rfc` con el RFC | `CRITICAL` | `ULT940623AG0` |
| XML-009 | `Receptor.Nombre` con la razón social, sin distinguir mayúsculas, acentos ni espacios repetidos | `ERROR` | `ULTRASIST` |
| XML-010 | `Receptor.DomicilioFiscalReceptor` con el código postal | `ERROR` | `03930` |
| XML-003 | `MetodoPago` con el método esperado | `ERROR` | `PPD` |
| XML-004 | `FormaPago` con la forma esperada | `ERROR` | `99` |
| XML-005 | `UsoCFDI` con los usos permitidos | `ERROR` | `G03`, `I04` |
| XML-007 | `Moneda` con las monedas activas del catálogo | `ERROR` | `MXN`, `USD`, `EUR` |

- **Interruptores:** cada comparación, salvo XML-007, se puede desactivar. Una comparación desactivada resulta `NOT_APPLICABLE` ("Comparación desactivada en Reglas de Validación") y no altera el score.
- **Datos de referencia:** la dirección (el CFDI 4.0 del receptor sólo trae el código postal; la usará la validación de invoices internacionales, HU-16) y el régimen fiscal se guardan sin comparación.
- **Validación:** RFC de persona moral con fecha válida, razón social obligatoria, código postal de 5 dígitos, y régimen, método, forma y usos elegidos de las claves activas de los catálogos. Todos los errores se muestran juntos (HTTP 400).
- **Concurrencia y auditoría:** el formulario lleva la versión; si otro Administrador guardó antes, responde 409. Cada cambio queda en el Audit Log (`VALIDATION_SETTINGS_UPDATED`, sólo los campos que cambiaron) y en el log técnico (`validation_settings.updated`, sin valores).
- **Pesos del score:** se muestran en solo lectura; se cambian en `BUSINESS_RULES`.

## Catálogos

**Administración › Catálogos** (`/admin/catalogs`) administra las claves del SAT que usa la validación (HU-07): monedas, usos de CFDI (24), formas de pago (22), métodos de pago (2) y regímenes fiscales (19), según los catálogos de CFDI 4.0. La migración siembra también las monedas `MXN`, `USD` y `EUR`.

- **Alta y edición:** la clave se guarda en mayúsculas con el formato de su catálogo (p. ej. dos dígitos para una forma de pago) y no se repite; la descripción tiene hasta 150 caracteres. Las claves nunca se borran ni se renombran.
- **Desactivación:** una clave inactiva deja de ofrecerse en Reglas de validación y, en monedas, deja de aceptarse en XML-007. Las claves marcadas "En uso" (las que usan las Reglas de validación) y la última moneda activa no se pueden desactivar.
- **Carga desde Excel:** "Descargar plantilla" entrega las claves vigentes en la hoja "Catalogo" (Clave, Descripción, Activo). Al cargarla modificada:
  - se agregan las claves nuevas y se actualizan la descripción y el estado de las existentes; las que no vienen en el archivo no cambian;
  - si una fila tiene errores no se aplica nada y se listan los errores por fila;
  - se aplican las mismas protecciones de archivo que en la carga de proveedores (sólo `.xlsx`, 5 MB, sin fórmulas ni entidades XML, hasta 1000 filas);
  - en los catálogos numéricos, una clave que Excel convirtió en número (`3`) se completa con ceros (`03`).
- **Auditoría:** `CATALOG_ENTRY_CREATED`, `CATALOG_ENTRY_UPDATED`, `CATALOG_ENTRY_STATUS_CHANGED` y `CATALOG_IMPORTED`. En el log técnico, `catalog.import` con los contadores de la carga.

## Archivos mínimos por tipo de proveedor

El Administrador define en **Administración › Archivos mínimos** (`/admin/required-documents`) qué archivos debe cargar el proveedor con cada factura, por separado para el proveedor **Nacional** y el **Internacional** (`suppliers.origin`):

| Nivel | En la carga documental | En la verificación y el envío |
| --- | --- | --- |
| Obligatorio | Se ofrece; el checklist indica cuántos faltan y la factura sigue en "Borrador" | Si falta, su regla DOC resulta `FAIL` y el envío no procede |
| Opcional | Se ofrece | No se exige |
| No aplica | No se ofrece; el servidor rechaza la carga | No se exige |

- **Catálogo** (`invoice_document_types`): 11 tipos del sistema, con nombre en español, descripción y formatos admitidos (PDF, PNG, JPEG, XML, TXT), más los tipos soporte que cree el Administrador. La carga documental rechaza con HTTP 400, antes de escribir el archivo, un tipo que no aplica a la factura o una extensión que el tipo no admite.
- **Valores iniciales:** Nacional exige XML y PDF del CFDI, orden de compra y Vo.Bo., y conserva el comportamiento anterior. Internacional exige Invoice (PDF), orden de compra y Vo.Bo. Contrato, anexo y documentación adicional son opcionales para ambos; los complementos de pago sólo aplican al Nacional.
- **Niveles fijos:** XML y PDF del CFDI son obligatorios para el Nacional y no aplican al Internacional; el Invoice, al revés. El "Acuse de cancelación" no aplica a ninguno: sólo se carga al [cancelar la factura](#cancelación-de-la-factura). La pantalla los muestra con candado, el servidor rechaza cambiarlos (409) y la base de datos los garantiza con un `CHECK`.
- **Tipos soporte:** el Administrador los da de alta (nombre, descripción, formatos y un nivel por origen, "No aplica" por defecto), los edita y los desactiva o reactiva. Su clave es `SOPORTE_<id>`. Nunca se borran, y los documentos ya cargados siguen visibles y descargables en el detalle de la factura. Los tipos del sistema no se editan ni se desactivan.
- **Reglas:** DOC-001 (XML del CFDI, `CRITICAL`), DOC-002 (PDF del CFDI), DOC-003 (orden de compra) y DOC-004 (Vo.Bo.) resultan `PASS`/`FAIL` cuando su tipo es obligatorio para el origen y `NOT_APPLICABLE` en otro caso. DOC-008 evalúa el Invoice (`CRITICAL`) y DOC-009 genera un resultado por cada otro tipo obligatorio, con su clave en la fuente.
- **Vigencia:** la configuración se lee en cada verificación y envío. Una factura que ya salió de los estados editables conserva sus resultados; una editable se evalúa con la configuración vigente al verificarse o enviarse. Si la configuración cambia, el estatus "Borrador"/"Cargada" se recalcula en la siguiente carga o en el envío.
- **Concurrencia y auditoría:** el formulario lleva la huella `config_version`; si otro Administrador guardó antes, el guardado responde 409 sin cambios. Cada cambio queda en el Audit Log (`INVOICE_DOCUMENT_REQUIREMENTS_UPDATED`, `INVOICE_DOCUMENT_TYPE_CREATED`, `INVOICE_DOCUMENT_TYPE_UPDATED` e `INVOICE_DOCUMENT_TYPE_STATUS_CHANGED`) con los valores anterior y nuevo.

**Probar con un proveedor internacional.** La demo incluye uno: `proveedor3@poc.local` (ver [Facturas de proveedores internacionales](#facturas-de-proveedores-internacionales)). En su carga documental se ofrecen el Invoice y los soportes configurados, no el XML ni el PDF del CFDI.

## Facturas de proveedores internacionales

El proveedor extranjero (`suppliers.origin = INTERNATIONAL`) no emite CFDI: factura con un Invoice en PDF (HU-15, HU-16).

- **Datos del Invoice:** al registrar la factura captura la fecha, el subtotal, los impuestos, el total y la moneda (catálogo de monedas activas). El total debe ser igual al subtotal más impuestos (tolerancia 0.02, como `FIN-002`). Se guardan en las mismas columnas que el XML llena para el nacional. Mientras la factura es editable ("Borrador", "Cargada" u "Observaciones") los corrige desde la carga documental; cada cambio se audita como `INVOICE_AMOUNTS_UPDATED`.
- **Duplicados por nombre de archivo:** al cargar un Invoice cuyo nombre (sin distinguir mayúsculas ni espacios de los extremos) ya tiene otra factura no cancelada del mismo proveedor, la carga responde 409 con el folio de esa factura y no escribe el archivo. Un bloqueo consultivo por proveedor serializa estas cargas y `FIN-007` (`CRITICAL`) lo verifica de nuevo al enviar.
- **Validación:** `XML-001..010`, `FIN-004`, `SUP-003` y `SUP-004` resultan "No aplica a proveedores internacionales"; `SEM-001` no se evalúa. Las demás reglas se aplican con los importes capturados: por ejemplo, `FIN-001` bloquea un subtotal mayor al monto autorizado del contrato.
- **Reglas del Invoice (`INT`):** buscan en el texto del PDF, sin acentos, mayúsculas, espacios ni signos: `INT-001` el identificador fiscal del proveedor, `INT-002` la razón social de ULTRASIST, `INT-003` su código postal y `INT-004` su dirección (si está configurada). `INT-002` e `INT-003` respetan los interruptores de [Reglas de validación](#reglas-de-validación). Son advertencias: no bloquean el envío. Un PDF sin texto legible (escaneado) las deja "No evaluadas".
- **Pendiente con negocio:** se calibrarán con las tres muestras de invoices extranjeros acordadas en la minuta. El expediente del proveedor internacional (equivalente al Anexo A) está por definir.
- **Demo:** `proveedor3@poc.local` es "Global Data Services Inc. (DEMO)" (US, identificador `98-7654321`), con el contrato "Analitica Global 2026" por 20,000.00 USD y la factura `INV-2026-0042` en "Cargada", lista para enviar.

## Bandeja y revisión del PMO

El PMO (rol `PMO`) y el Administrador (rol `Administrador`) revisan las facturas enviadas (HU-18, HU-19):

- **Bandeja:** **Facturas** abre en "Enviada", con las que más han esperado primero (orden por fecha de envío, también en las páginas siguientes). "Todos los estados" u otro estatus vuelven al orden por fecha de creación. El filtro de origen separa facturas nacionales e internacionales. Cada fila muestra proveedor, folio y número, origen, proyecto, fecha de envío, monto, score con el número de advertencias y estatus. El proveedor conserva su listado de siempre.
- **Ver documentos:** el ícono del ojo abre el documento en una pestaña del portal. Las páginas de un PDF se muestran como imágenes renderizadas en el servidor (hasta 20 páginas); las imágenes se muestran tal cual y el XML o el texto, escapados (hasta 200,000 caracteres). El navegador nunca abre el PDF ni el XML como documento, así que no depende de su visor ni se relaja la CSP. La autorización es la de la descarga, que sigue siendo un adjunto.
- **Detalle:** para el PMO y el Administrador, un bloque "Proveedor" (origen, identificador fiscal, correo y estatus) y el "Historial" con los envíos del proveedor, las revisiones (decisión, observaciones y revisor) y la cancelación, en orden cronológico. El proveedor ve el mismo historial como "Seguimiento" (ver [Seguimiento del proveedor](#seguimiento-del-proveedor)).
- **Decisión (HU-20):** en el panel "Decisión" del detalle de una factura "Enviada" (el botón "Decidir" del encabezado lleva ahí), con tres botones:
  - **Autorizar** pide confirmación y envía a Recepción de Facturas el correo "Autorizada" (RN-HU20-02: número, proveedor y monto total con moneda);
  - **Observaciones** y **Rechazar** exigen las observaciones (hasta 2,000 caracteres; RN-HU20-01) y envían al correo del proveedor el correo respectivo con la causa (RN-HU20-03). Con Observaciones el proveedor corrige y reenvía; Rechazada y Autorizada no admiten otra decisión (sólo la cancelación del proveedor).
- **Una decisión por envío:** la factura se bloquea al decidir; una segunda decisión responde 409 "La factura ya fue revisada" sin revisión ni correo.
- **Correo de la decisión:** sale después de confirmarla; el detalle muestra "Correo enviado a …" o el error. Si el último envío falló, "Reenviar notificación" lo intenta de nuevo (auditoría `INVOICE_NOTIFICATION_RESENT`).
- **ClickBalance:** los pasos manuales del PoC se retiraron; la migración `0011_retire_clickbalance` pasó sus facturas a "Autorizada" con auditoría `STATUS_MIGRATED`.

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
- **Vista previa:** compone el borrador con los datos de ejemplo de la tabla, sin JavaScript y sin guardar ni auditar. Muestra el correo tal como se envía, su versión HTML en un `iframe` aislado (`sandbox`, `srcdoc`), y debajo, plegada, la versión de texto plano.
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
- **Transporte** vigente en solo lectura, sin usuario ni contraseña, y la **bitácora de envíos** completa, paginada de 25 en 25, con su resultado.

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

- Resuelve los destinatarios con la configuración vigente, compone el correo con la plantilla de HU-05 y lo envía como `multipart/alternative` UTF-8: el texto plano y una versión HTML con el logo de ULTRASIST incrustado (`cid:`) en una tarjeta centrada con estilos en línea (`app/services/mail_layout.py`, `app/email_templates/layout.html`). La versión HTML se deriva del texto: cada valor se escapa, las direcciones `http(s)` se vuelven enlaces y un párrafo de líneas `Etiqueta: valor` se muestra como bloque de datos. Las plantillas de HU-05 siguen siendo de texto plano.
- Registra el intento en `email_deliveries` (evento, destinatarios, resultado, error técnico, entidad y usuario, **sin asunto ni cuerpo**) y confirma ese registro.
- Un error del servidor de correo **no** se propaga: el envío queda `FAILED` en la bitácora y en el log (`notification.failed`). No hay cola ni reintentos automáticos.
- Lanza `NotificationDataError` si falta el correo del proveedor o una variable de la plantilla.

### Conectar el servidor SMTP

El `.env` trae un bloque comentado para el servidor de ULTRASIST. Para conectarlo:

1. Pida a TI el servidor, el puerto y el tipo de conexión, la cuenta que envía (o si el servidor acepta relay por IP sin usuario) y la dirección de remitente autorizada.
2. En `.env`, descomente y complete `MAIL_BACKEND=smtp`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_SECURITY`, `SMTP_USERNAME`, `SMTP_PASSWORD` y `MAIL_FROM`. La contraseña sólo vive en `.env`: nunca se muestra en la pantalla ni se escribe en el log.
3. Reinicie uvicorn: la configuración se lee al arrancar y `--reload` no vigila `.env`. Si falta `SMTP_HOST` o `MAIL_FROM`, la aplicación no arranca y lo indica.
4. En **Administración › Notificaciones**, confirme en "Transporte" el servidor y el cifrado, y envíe un correo de prueba a su buzón. El resultado y, si falla, el error técnico aparecen en la pantalla y en la "Bitácora de envíos".

| Caso | Configuración |
| --- | --- |
| Puerto 587 con STARTTLS y usuario (lo más común; Microsoft 365: `smtp.office365.com`) | `SMTP_PORT=587`, `SMTP_SECURITY=starttls`, usuario y contraseña |
| Puerto 465 con TLS directo | `SMTP_PORT=465`, `SMTP_SECURITY=ssl` |
| Relay interno por IP, sin usuario | `SMTP_USERNAME` vacío; el transporte no inicia sesión |
| Relay en el puerto 25 sin cifrar | `SMTP_SECURITY=none`: sólo en desarrollo, porque en `production` el arranque lo rechaza |

Errores frecuentes al enviar la prueba:
- `SMTPAuthenticationError`: usuario o contraseña incorrectos, o, en Microsoft 365, SMTP AUTH deshabilitado para ese buzón.
- `SSLCertVerificationError`: el certificado del servidor lo firmó una autoridad interna de ULTRASIST. Agregue su certificado raíz al almacén del sistema, o defina `SSL_CERT_FILE` con un archivo `.pem` que la incluya. La verificación del certificado no se desactiva.
- `SMTPRecipientsRefused` o `SMTPSenderRefused`: el servidor no permite enviar con ese `MAIL_FROM` o a ese destinatario.
- `ConnectionRefusedError` o `TimeoutError`: servidor o puerto incorrectos, o un firewall de por medio.

Los tres modos (STARTTLS con usuario, TLS directo y certificado no confiable) se verificaron contra un servidor SMTP real con autenticación y un certificado propio.

## Usuarios

**Administración › Usuarios** (`/admin/users`) da de alta usuarios en el portal y su cuenta en Keycloak, con una contraseña temporal que la respuesta del alta muestra **una sola vez** (`Cache-Control: no-store`); Keycloak pide cambiarla en el primer acceso. El formulario no pide contraseña.

- **Keycloak:** si ya existe una cuenta con ese correo, se enlaza cuando no pertenece a otro usuario del portal y no tiene otro rol del portal (si no, 409). Sin Keycloak, el alta responde 503 y no crea nada.
- **Habilitar y deshabilitar:** deshabilitar cierra el acceso al portal siempre y después deshabilita la cuenta de Keycloak y cierra sus sesiones; si Keycloak no responde, el usuario queda deshabilitado en el portal, se audita `IDP_SYNC_FAILED` y la página avisa que hay que deshabilitarlo también en la consola de Keycloak. Habilitar empieza por Keycloak: si no responde, nada cambia (503).

- **Rol y proveedor:** un usuario `Proveedor` siempre está vinculado a un proveedor existente: sin él, el alta responde 400 "Seleccione el proveedor del usuario". Los `PMO` y `Administrador` no tienen proveedor (se ignora si se envía). La base de datos lo garantiza con `CHECK ck_users_provider_supplier`.
- **Vía recomendada para proveedores:** registrar al proveedor en `/suppliers` y autorizarlo: el portal crea su usuario con el proveedor ya vinculado y le envía las credenciales.
- **Usuarios previos sin proveedor:** la migración `0013_provider_user_supplier` deshabilita a los usuarios Proveedor que se crearon sin proveedor (auditoría `USER_DEACTIVATED_WITHOUT_SUPPLIER`, sesiones revocadas) y no pueden volver a habilitarse (409): se da de alta uno nuevo con su proveedor. Si el correo ya está ocupado por el usuario deshabilitado, use otro correo.
- **Nombres de los roles:** los roles son `Administrador`, `Proveedor` y `PMO`, y así se guardan en `users.role`. La migración `0014_business_role_names` renombró los valores previos (`ADMIN`, `PROVIDER`, `INTERNAL`); los registros de auditoría anteriores conservan el nombre que tenía el rol al registrarse.

## Autorización y acceso de proveedores

Un proveedor nace **"Registrado"** (carga masiva o formulario individual), sin usuario ni acceso al portal, y no puede facturar: SUP-001 exige el estatus operativo, que ahora se muestra como **"Autorizado"** (HU-02).

En ambos casos, el **Origen** decide la identidad fiscal: el **Nacional** se registra con RFC y país MX; el **Internacional**, con identificador fiscal extranjero y país distinto de MX, sin RFC. El formulario individual ("+ Agregar proveedor") rechaza combinaciones incongruentes (400) y un RFC o un par (país, identificador) ya registrados (409). El origen no se edita después.

Con JavaScript (`supplier_form.js`), el alta muestra sólo los campos que aplican: RFC para el Nacional; identificador fiscal extranjero y país para el Internacional; fecha de constitución sólo para persona moral. Un campo que deja de aplicar se oculta, se limpia y se deshabilita: no se valida ni se envía. Al volver a aplicar, recupera su obligatoriedad. Sin JavaScript se ven todos y el servidor valida la combinación. En la edición, el origen y el tipo de persona no cambian, y el servidor pinta sólo los campos que aplican.

- **Autorización masiva:** en **Proveedores**, el Administrador filtra por "Registrado", marca las casillas (o "seleccionar todos") y pulsa "Autorizar seleccionados". Un modal pide confirmación, porque se enviarán las credenciales. Se autorizan hasta 100 proveedores por operación, en una transacción con las filas bloqueadas y un punto de guardado por proveedor:
  - los que no están "Registrado" se omiten;
  - si el correo de un proveedor lo usa otro usuario, ese proveedor no se autoriza;
  - si ya tenía su propio usuario `Proveedor`, se autoriza sin credenciales nuevas;
  - si Keycloak rechaza o no responde al crear la cuenta de un proveedor, sólo ese proveedor sigue "Registrado" (auditoría `SUPPLIER_PROVISIONING_FAILED`) y los demás se procesan.
- **Credenciales (HU-03):** por cada proveedor autorizado sin usuario se crea un usuario `Proveedor` del portal, sin contraseña, y su cuenta en Keycloak (o se enlaza la existente con su correo, si no pertenece a otro usuario ni tiene otro rol del portal): rol `Proveedor`, contraseña temporal aleatoria de 20 caracteres y la acción requerida `UPDATE_PASSWORD`. La contraseña sólo existe en memoria, en Keycloak y en el correo "Credenciales de acceso", que se envía después de confirmar con el usuario, la contraseña y la dirección `/login` del servidor.
- **Resumen:** tras autorizar, el listado muestra a cada proveedor con "Credenciales enviadas", "Envío fallido" (con el error), "Ya tenía usuario", "Omitido", "No autorizado" (correo en uso) o "No autorizado: el servicio de identidad no pudo crear su cuenta". Los proveedores cuyo último envío falló llevan la marca "Credenciales no enviadas".
- **Expediente:** la sección "Acceso al portal" muestra el usuario, el último acceso, el estado de la contraseña leído de Keycloak ("Temporal, pendiente de cambio", "Cambiada por el proveedor" o "No disponible" si Keycloak no responde) y el último envío de credenciales. **"Reenviar credenciales"** fija en Keycloak una contraseña temporal nueva (la anterior deja de funcionar), sólo mientras la cuenta conserve `UPDATE_PASSWORD`, aunque ya haya entrado con la temporal.
- **Auditoría:** `SUPPLIER_STATUS_CHANGED`, `USER_CREATED` (origen `SUPPLIER_AUTHORIZATION`, cuenta de Keycloak `created` o `linked`), `SUPPLIER_PROVISIONING_FAILED`, `SUPPLIER_BULK_AUTHORIZED` y `SUPPLIER_CREDENTIALS_RESENT`, sin contraseñas ni tokens. En el log técnico queda `supplier.bulk_authorize` sólo con contadores.
- **Proveedor de identidad (RN-HU03-01):** las credenciales viven sólo en Keycloak; el portal no guarda contraseñas ni hashes.
- **Primer acceso:** el proveedor debe cambiar la contraseña temporal antes de usar el portal; ver la sección siguiente.

## Primer acceso y cambio de contraseña

Los aplica Keycloak (RF-06); el portal no muestra formularios de contraseña.

- **Primer acceso:** toda contraseña que asigna otra persona (autorización, reenvío, alta en **Administración › Usuarios** y migración de usuarios) se registra en Keycloak como temporal, con la acción requerida `UPDATE_PASSWORD`: Keycloak exige la nueva antes de volver al portal. Las cuentas demo de `development` no la tienen.
- **Política del realm:** 8 a 128 caracteres, con letra, número y carácter especial; distinta del usuario, del correo y de la actual; fuera de la lista de contraseñas comunes (con sus variantes decoradas).
- **Fuerza bruta:** Keycloak bloquea la cuenta tras 5 fallos consecutivos, con espera creciente hasta 60 minutos; el contador se reinicia a las 24 h. Los fallos y cambios quedan en los eventos del realm (30 días).
- **Cambio voluntario:** "Cambiar contraseña" (menú lateral) lleva a Keycloak con `kc_action=UPDATE_PASSWORD`; al volver, el portal abre una sesión nueva, muestra "Contraseña actualizada" y audita `PASSWORD_CHANGED` (`forced: false`).
- No hay recuperación de contraseña ni caducidad de la temporal (fuera del MVP). Las columnas `users.password_hash` y `users.must_change_password` quedan obsoletas y se eliminarán cuando todos los usuarios estén enlazados.

## Archivos y seguridad de PoC

- **Contraseñas e inicio de sesión:** en Keycloak (ver "Keycloak: inicio de sesión y cuentas"). El portal no recibe, guarda ni verifica contraseñas.
- **Sesiones:** revocables del lado del servidor (`user_sessions`). La cookie firmada sólo lleva un identificador opaco y el token CSRF (y, durante el viaje a Keycloak, `state`, `nonce` y `code_verifier`). Expiran tras 60 minutos de inactividad u 8 horas de duración, y se revocan al cerrar sesión o al deshabilitar al usuario; ambas acciones cierran también la sesión de Keycloak.
- **CSRF:** token de sesión en todas las operaciones mutables, que sólo aceptan POST.
- **Cabeceras:** CSP `default-src 'self'` (con `form-action` que admite sólo el origen de Keycloak, destino del cierre de sesión), `X-Frame-Options: DENY`, `nosniff` y `Referrer-Policy`, más HSTS sobre HTTPS. **No agregue scripts ni estilos en línea:** la CSP los bloquea; use archivos bajo `app/static/`. La única excepción es la vista previa del correo: su respuesta agrega `style-src 'self' 'unsafe-hashes'` con el hash de cada atributo `style` del correo (`content_security_policy_with_styles()`), sin `'unsafe-inline'`.
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

Para producción use `APP_ENV=production`: la aplicación no arranca sin `SESSION_HTTPS_ONLY=true`, con cuentas demo activas, con `MAIL_BACKEND=file`, con `SMTP_SECURITY=none` ni con `KEYCLOAK_SERVER_URL` sin `https://`. Añada además políticas de retención, escaneo antimalware y gestión de secretos.

**Detrás de un proxy inverso**, arranque uvicorn con `--proxy-headers --forwarded-allow-ips=<IP del proxy>`. Sin eso, todas las peticiones parecen venir del proxy: la auditoría registra su IP, HSTS no se emite y la URI de retorno a `/auth/callback` se arma con el host interno, que Keycloak rechaza.

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
| `KEYCLOAK_SERVER_URL` | *(obligatoria)* | URL base de Keycloak; `https://` obligatorio en `production`. `create_env.py` escribe la local (`http://127.0.0.1:58080`). |
| `KEYCLOAK_REALM` | *(obligatoria)* | `ultrasist-portal`. |
| `KEYCLOAK_CLIENT_ID`, `KEYCLOAK_CLIENT_SECRET` | `portal-facturas-web`, *(obligatoria)* | Cliente OIDC del portal. El secreto: mínimo 32 caracteres, sin valor de ejemplo; nunca se muestra ni se registra. |
| `KEYCLOAK_ADMIN_CLIENT_ID`, `KEYCLOAK_ADMIN_CLIENT_SECRET` | `portal-facturas-admin`, *(obligatoria)* | Cuenta de servicio del alta de usuarios (sólo `manage-users`, `view-users` y `query-users`). |
| `KEYCLOAK_TIMEOUT` | `10` | Segundos de espera de cada llamada a Keycloak (1 a 60). |
| `KEYCLOAK_PORT` | `58080` | Puerto local del servicio `keycloak`, sólo en `127.0.0.1`. |
| `KC_BOOTSTRAP_ADMIN_USERNAME`, `KC_BOOTSTRAP_ADMIN_PASSWORD` | `admin`, *(generada)* | Administrador inicial de la consola del Keycloak local. |
| `DEMO_PASSWORD` | *(generada)* | Contraseña de las cuentas demo en `development`. |

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

El seed crea 5 usuarios, 3 proveedores, 3 contratos, expedientes Anexo A, 12 facturas y Audit Log. Incluye: borrador sin documentos (`BORRADOR-001`), borrador sin Vo.Bo. (`D-SIN-VOBO`), cargadas listas para enviar (`A-CORRECTA`, `E-SEMANTICO`), cargada cuyo envío no procede porque excede el contrato (`B-EXCEDE`), enviada (`REVISION-001`), una segunda enviada por decidir (`ENVIADA-002`), autorizada, rechazada por RFC incorrecto, una devuelta con observaciones del PMO (`OBSERVACIONES-001`) y una cancelada con su acuse (`CANCELADA-001`; la siembra no envía su correo). Esas once son de `proveedor1@poc.local`; la duodécima, `INV-2026-0042`, es del proveedor internacional `proveedor3@poc.local` y está cargada, lista para enviar.

Los XML bajo `data/demo_documents/` son estructuralmente útiles para el parser, pero **no están timbrados ni son fiscalmente válidos**. El seed asigna a cada factura demo un UUID fiscal distinto y usa el PDF sintético versionado `data/demo_documents/factura_demo.pdf` (si faltara, lo genera en un directorio temporal sin modificar el repositorio).

## Limitaciones y fuera de alcance

- Sin validación SAT online, timbrado ni generación CFDI.
- Sin integración con ClickBalance ni SAP Ariba: el flujo del portal termina en "Autorizada".
- Sin pagos, banca, firma, SharePoint, Blob, Azure SQL, SSO con proveedores externos, despliegue Azure, Kubernetes o colas.
- Los adaptadores Azure son contratos preparados, no llamadas productivas.
- Las Reglas de validación y los catálogos son editables, pero los pesos del score siguen en el código y no se pueden crear reglas nuevas desde la interfaz. Los catálogos se usan en la validación del CFDI; la moneda del contrato sigue siendo texto libre de tres letras.
- Las reglas `INT` del Invoice internacional buscan texto literal y aún no se calibran con invoices reales; no hay extracción automática de datos del Invoice.
- Los correos (credenciales, decisión del PMO, cancelación) se envían de forma síncrona, sin cola ni reintentos automáticos; un envío fallido se reenvía a mano. No hay recordatorio antes de que venza el plazo de 72 horas de una cancelación.
- El monto acumulado del tablero suma los totales sin convertir moneda: con facturas en MXN y USD es sólo una referencia.
- La contraseña temporal no expira y no hay recuperación de contraseña.
- Keycloak limita los intentos por cuenta, no por IP (el portal limitaba ambos): el límite por IP debe ponerlo el proxy inverso. La lista de comunes de Keycloak compara contraseñas completas; sus variantes decoradas aproximan, sin igualar, la regla anterior (palabra común con dígitos y símbolos).
- El correo del proveedor en el catálogo no se sincroniza con su cuenta de Keycloak.
- La verificación documental del Anexo A es presencia/vigencia referencial, no validación legal.
- Bootstrap 5.3.3 y Bootstrap Icons están incluidos bajo `app/static/vendor/`; la interfaz tampoco requiere Internet.

## Próximos pasos para producción

Contenerizar la aplicación (Dockerfile y servicio `app` en Compose), PostgreSQL gestionado en Azure, Azure Blob con malware scanning, secretos administrados, federación de Keycloak con Entra ID/External ID, cifrado y retención documental, workers para OCR, agregación centralizada del log JSON, pruebas E2E, accesibilidad formal y un workflow de excepciones con doble aprobación.
