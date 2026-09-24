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
python scripts/reset_demo.py
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

También puede ejecutar `scripts\create_venv.ps1` y después `run_local.ps1`. El script `run_local` reconstruye intencionalmente la demo antes de iniciar; para conservar cambios, arranque directamente con Uvicorn.

En CMD use `.venv\Scripts\activate` y `run_local.bat`.

## Instalación en Linux/macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install --require-hashes -r requirements.lock
python scripts/create_env.py
python scripts/reset_demo.py
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

- SQLite: `data/invoice_portal.db` (ignorada por Git).
- Crear tablas directamente: `python scripts/init_db.py`.
- Aplicar migraciones: `alembic upgrade head`.
- Cargar seed sobre una base vacía: `python scripts/seed_db.py`.
- Reconstruir base y archivos demo: `python scripts/reset_demo.py`.

`reset_demo.py` valida que las rutas estén dentro del workspace, elimina sólo la SQLite configurada y el contenido generado de `storage/invoices`, `storage/suppliers` y `storage/temp`, aplica Alembic y vuelve a crear el seed.

## Pruebas

```powershell
pip install -r requirements-dev.txt
pytest
```

La suite crea una BD SQLite y un `storage/` temporales por sesión. No lee ni modifica `data/invoice_portal.db` ni `storage/` del proyecto.

La suite cubre login válido/inválido, CSRF, RBAC, aislamiento entre proveedores, parser CFDI, XML corrupto, RFC receptor, Método/Forma de pago extraídos, regla de fecha, montos con `Decimal`, UUID duplicado, score y transiciones inválidas.

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
alembic/         migración inicial
data/            SQLite generada y documentos sintéticos versionados
scripts/         inicialización, seed, reset y creación de .venv
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

- Passwords Argon2 mediante `pwdlib`.
- Sesión firmada, cookie HttpOnly de Starlette, SameSite Lax y HTTPS configurable.
- CSRF por token de sesión y operaciones mutables sólo por POST.
- UUID interno para uploads, nombre original sólo como metadata, SHA-256, extensión/MIME/tamaño y path traversal validados.
- PDFs validados con PyMuPDF; un PDF sin texto se marca para OCR y no inventa contenido.
- Autorización por rol y por pertenencia del objeto/documento.
- Errores sin stack trace en UI; detalle técnico en `logs/app.log`.
- Versiones sustituidas quedan en DB con `is_current=false` y referencia al documento anterior.

`SECRET_KEY` es obligatoria (mínimo 32 caracteres; se rechaza el valor de ejemplo `change-me...`). `scripts/create_env.py` la genera al crear `.env`. `DEBUG` sólo sube el nivel de log; nunca muestra trazas al usuario.

Para producción use `APP_ENV=production`: la aplicación no arranca sin `SESSION_HTTPS_ONLY=true` ni con cuentas demo activas. Añada además políticas de retención, escaneo antimalware y gestión de secretos.

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

Los XML bajo `data/demo_documents/` son estructuralmente útiles para el parser, pero **no están timbrados ni son fiscalmente válidos**. El seed genera además un PDF sintético con PyMuPDF.

## Limitaciones y fuera de alcance

- Sin validación SAT online, timbrado ni generación CFDI.
- Sin integración real ClickBalance o SAP Ariba; ClickBalance es un estado manual.
- Sin pagos, banca, correo, firma, SharePoint, Blob, Azure SQL, SSO, despliegue Azure, Kubernetes o colas.
- Los adaptadores Azure son contratos preparados, no llamadas productivas.
- El catálogo de reglas se muestra en modo lectura; su edición persistente es un siguiente paso.
- La verificación documental del Anexo A es presencia/vigencia referencial, no validación legal.
- Bootstrap 5.3.3 y Bootstrap Icons están incluidos bajo `app/static/vendor/`; la interfaz tampoco requiere Internet.

## Próximos pasos para producción

PostgreSQL/Azure SQL, Azure Blob con malware scanning, secretos administrados, Entra ID/External ID, CSP y assets locales, rate limiting, cifrado/retención documental, workers para OCR, migraciones explícitas por cambio, observabilidad, pruebas E2E, accesibilidad formal y un workflow de excepciones con doble aprobación.
