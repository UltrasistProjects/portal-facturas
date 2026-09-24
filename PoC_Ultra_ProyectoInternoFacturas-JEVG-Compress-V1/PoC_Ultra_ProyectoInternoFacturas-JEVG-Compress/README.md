# Invoice Portal PoCC

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
- No requiere Node.js, Docker, Azure ni conexión a servicios externos para operar.

## Instalación en Windows PowerShell

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install --require-hashes -r requirements.lock
python scripts/create_env.py
python scripts/init_db.py
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

También puede ejecutar `scripts\create_venv.ps1` y después `run_local.ps1`. `run_local` crea `.env` si no existe, aplica las migraciones y siembra la demo sólo si la base está vacía. **Conserva los datos entre arranques.**

En CMD use `.venv\Scripts\activate` y `run_local.bat`.

## Instalación en Linux/macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install --require-hashes -r requirements.lock
python scripts/create_env.py
python scripts/init_db.py
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Abra <http://127.0.0.1:8000>. El health check está en <http://127.0.0.1:8000/health>.

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

- SQLite: `data/invoice_portal.db` (ignorada por Git). Opera en modo WAL, así que junto a ella aparecen `invoice_portal.db-wal` y `invoice_portal.db-shm`.
- Aplicar migraciones y sembrar sólo si la base está vacía: `python scripts/init_db.py`.
- Aplicar migraciones: `alembic upgrade head`.
- Cargar seed sobre una base vacía: `python scripts/seed_db.py`.
- Reconstruir base y archivos demo: `python scripts/reset_demo.py`.

**Migraciones.**

- Cada revisión de `alembic/versions/` describe su cambio de forma explícita. `0001_initial` es el snapshot del esquema original y ningún `downgrade` borra todo: los que perderían datos lanzan `NotImplementedError` (restaure un respaldo).
- **Regla:** todo cambio en `app/models` requiere una revisión nueva. Nunca edite una revisión publicada. `alembic check` (incluido en `scripts/check.py`) falla si modelos y migraciones difieren.
- `0004_integridad_datos` convierte montos a centavos y rutas de documentos a relativas. Antes de tocar nada verifica precondiciones: huérfanos, UUID o números de factura duplicados, valores fuera de catálogo, montos con más de 2 decimales y rutas no convertibles. Si alguna falla, aborta sin cambios y lista las filas.
  - Una BD sembrada con la versión anterior del seed **tiene UUID duplicados** entre escenarios demo y no migrará.
  - Si es sólo demo, recréela con `python scripts/reset_demo.py`, que respalda antes de borrar.

`reset_demo.py` borra datos, así que actúa con cuidado:

- no se ejecuta con `APP_ENV=production`;
- valida que la BD y `storage/` estén dentro del workspace;
- si detecta datos que no son demo (usuarios fuera de `@poc.local` o facturas no sembradas), pide escribir `REINICIAR`; sin terminal interactiva exige `--yes`;
- antes de borrar genera un respaldo en `backups/`;
- elimina la BD con sus archivos `-wal`/`-shm` y el contenido de `storage/`, aplica las migraciones y vuelve a sembrar.

## Respaldo y restauración

Los documentos fiscales deben conservarse 5 años. Respalde la BD **y** `storage/`; uno sin el otro no sirve.

- **Respaldo:** `python scripts/backup.py`. Puede ejecutarse con la aplicación en marcha, porque usa la API de respaldo en línea de SQLite (consistente también con WAL).
  - Crea `backups/<AAAAMMDD-HHMMSS>/` con la BD, `storage.zip` y `manifest.json` (revisión Alembic, fecha UTC y SHA-256 de cada artefacto).
  - Conserva los `BACKUP_RETENTION` respaldos más recientes (14 por defecto) en `BACKUP_DIR` (`./backups`).
- **Restauración:**
  1. Detenga la aplicación.
  2. Ejecute `python scripts/restore_backup.py backups/<AAAAMMDD-HHMMSS> --yes`.
  3. El script verifica los SHA-256 del manifiesto y aborta si no coinciden. Luego respalda el estado actual y reemplaza la BD y `storage/`.
  4. Arranque la aplicación.
- Programe `backup.py` (Programador de tareas de Windows o cron) y copie `backups/` fuera del equipo. Un respaldo en el mismo disco no protege contra la pérdida del disco.

## Pruebas

```powershell
pip install -r requirements-dev.txt
pytest                      # pruebas con umbral de cobertura (pyproject.toml) y coverage.xml para SonarQube
python scripts/check.py     # ruff, formato, alembic check, pytest y pip-audit (--skip-audit sin conexión)
```

La suite crea una BD SQLite y un `storage/` temporales por sesión. No lee ni modifica `data/invoice_portal.db` ni `storage/` del proyecto. La cobertura mínima de `app/` es del 93 % (`--cov-fail-under`).

Cubre:

- login, CSRF, limitación de intentos y política de contraseñas;
- sesiones revocables, RBAC y aislamiento entre proveedores;
- carga y descarga de documentos (firmas de contenido, tamaño, path traversal);
- parser CFDI y reglas XML/FIN/DAT, incluido el límite del día 20 en hora local;
- dinero exacto, restricciones de la BD y migraciones desde el esquema original con datos heredados;
- cabeceras de seguridad, errores sin traza y log JSON sin datos sensibles;
- respaldo, restauración, reinicio de demo y empaquetado.

## Dependencias

- `requirements.txt` declara las dependencias directas fijadas, y `requirements.lock` las congela todas (incluidas las transitivas) con hashes. El lock es universal: sirve en Windows, Linux y macOS.
- Regenerar el lock tras cambiar `requirements.txt`:

  ```bash
  uv pip compile --universal --generate-hashes --python-version 3.12 requirements.txt -o requirements.lock
  ```

- Auditar vulnerabilidades conocidas: `pip-audit -r requirements.lock` (y `pip-audit -r requirements-dev.txt` para las herramientas).
- Resultado de la auditoría del 2026-09-24: se corrigieron avisos en `starlette` (0.47.3 → 1.3.1, que obliga a subir `fastapi` a 0.133.1), `lxml` (6.1.3), `python-dotenv` (1.2.3), `python-multipart` (0.0.32) y `pytest` (9.0.3). El lock no tiene avisos conocidos.

## Estructura

```text
app/
  core/          configuración, seguridad, DB, enums y logging
  models/        entidades SQLAlchemy
  repositories/ consultas con alcance por usuario
  routers/       auth, dashboard, facturas, proveedores, contratos y admin
  rules/         reglas DOC/XML/SUP/CON/FIN/DAT/SEM
  services/      storage, XML, PDF, conciliación, score, auditoría y workflow
    ai/          interfaz, mock y adaptadores Azure
  templates/     interfaz Jinja server-rendered
  static/        CSS y JavaScript Vanilla
alembic/         migraciones explícitas (una revisión por cambio de modelo)
data/            SQLite generada y documentos sintéticos versionados
scripts/         .env, BD, seed, reset, respaldo/restauración, empaquetado y check
storage/         uploads segregados por proveedor/factura
tests/           pruebas críticas automatizadas
```

## Flujo funcional

Login → alta de factura → carga/reemplazo documental → parser XML/PDF → reglas → score y evidencia → envío a revisión → aceptación/rechazo/corrección → marcado manual para ClickBalance.

El proveedor sólo observa sus facturas. `INTERNAL` revisa y decide. `ADMIN` añade administración de usuarios, proveedores, contratos, reglas visibles y Audit Log.

## Reglas implementadas

- `DOC-001..007`: XML, PDF, OC, Vo.Bo., contrato/anexo, complemento y procesabilidad.
- `XML-001..008`: parseabilidad, receptor, PPD, FormaPago 99, UsoCFDI, UUID, moneda y esenciales.
- `SUP-001..004`: proveedor activo, contrato vigente, expediente mínimo y vigencia aproximada.
- `CON-001..004`: contrato, proyecto, periodo y heurística mes/tecnología.
- `DAT-001`: recepción del día 1 al 20; advertencia no fatal.
- `FIN-001..006`: límite autorizado, consistencia, moneda, UUID/número duplicados y diferencia absoluta/porcentual.
- `SEM-001`: comparación semántica mediante adaptador; el mock reconoce Power Platform/Power Automate con confianza 0.93.

`SEM-002..004` quedan reservadas como extensión. Los parámetros de negocio (receptor, método/forma de pago, usos CFDI y pesos del score) tienen una sola fuente, `BUSINESS_RULES` en `app/core/constants.py`, que usan tanto el motor como la vista `/admin/rules`.

### Cálculo del score

Cada regla evaluada aporta al denominador según severidad: `CRITICAL=35`, `ERROR=18`, `WARNING=6`, `INFO=0`. Un `FAIL` o `WARNING` descuenta su peso. `NOT_APPLICABLE` y `NOT_EVALUATED` no alteran el denominador. Una falla `CRITICAL` genera bloqueo; una evidencia AI de baja confianza permanece diferenciada y nunca equivale a aprobación administrativa.

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

Para producción use `APP_ENV=production`: la aplicación no arranca sin `SESSION_HTTPS_ONLY=true` ni con cuentas demo activas. Añada además políticas de retención, escaneo antimalware y gestión de secretos.

**Detrás de un proxy inverso**, arranque uvicorn con `--proxy-headers --forwarded-allow-ips=<IP del proxy>`. Sin eso, todas las peticiones parecen venir del proxy: el límite de login por IP se vuelve global y HSTS no se emite.

**Cifrado en reposo (requisito de infraestructura).** La BD SQLite y `storage/` guardan en claro RFC, razones sociales, montos, datos bancarios y documentos. Con datos reales, cifre el volumen (BitLocker o LUKS) o migre a un motor con TDE (Azure SQL o PostgreSQL gestionado). Restrinja también el acceso a `backups/`.

### Variables de entorno

| Variable | Por defecto | Descripción |
|---|---|---|
| `SECRET_KEY` | *(obligatoria)* | Firma de la cookie de sesión; mínimo 32 caracteres. |
| `APP_ENV` | `development` | `development`, `test` o `production`. Gobierna los valores por defecto y las verificaciones de arranque. |
| `DEBUG` | `false` | Sólo eleva el nivel de log. |
| `SESSION_HTTPS_ONLY` | según `APP_ENV` | Cookie `Secure`; `true` fuera de `development`. |
| `DATABASE_URL`, `STORAGE_PATH`, `LOG_DIR`, `BACKUP_DIR` | `./data/...`, `./storage`, `./logs`, `./backups` | Las rutas relativas se resuelven contra la raíz del proyecto, no contra el directorio de trabajo. |
| `BUSINESS_TIMEZONE` | `America/Mexico_City` | Zona de las reglas de calendario (corte del día 20) y del año del folio. |
| `BACKUP_RETENTION` | `14` | Respaldos que conserva `scripts/backup.py`. |
| `MAX_UPLOAD_MB` | `20` | Tamaño máximo por archivo. |

## Empaquetado para distribución

`python scripts/package_release.py` genera `dist/<proyecto>-<fecha>.zip`:

- Con Git, incluye sólo los archivos versionados; sin Git, recorre el árbol aplicando una lista de exclusión.
- Nunca incluye `.env`, la BD (ni sus `-wal`/`-shm`), `logs/`, `storage/`, `backups/`, `.venv/` ni cachés.
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
- Sin pagos, banca, correo, firma, SharePoint, Blob, Azure SQL, SSO, despliegue Azure, Kubernetes o colas.
- Los adaptadores Azure son contratos preparados, no llamadas productivas.
- El catálogo de reglas se muestra en modo lectura; su edición persistente es un siguiente paso.
- La verificación documental del Anexo A es presencia/vigencia referencial, no validación legal.
- Bootstrap 5.3.3 y Bootstrap Icons están incluidos bajo `app/static/vendor/`; la interfaz tampoco requiere Internet.

## Próximos pasos para producción

PostgreSQL/Azure SQL (los montos en centavos se convierten a `NUMERIC` con una migración), Azure Blob con malware scanning, secretos administrados, Entra ID/External ID, cifrado y retención documental, workers para OCR, agregación centralizada del log JSON, pruebas E2E, accesibilidad formal y un workflow de excepciones con doble aprobación.
