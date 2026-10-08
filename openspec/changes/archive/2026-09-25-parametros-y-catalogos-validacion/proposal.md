## Why

La minuta del 21-sep-2026 asigna al Administrador "Configurar parámetros y reglas de validación" y "Administrar y cargar catálogos". La ERS lo concreta en dos HU:

- **HU-06 (RF-11):** configurar las Reglas de Validación, es decir, los datos de ULTRASIST (RFC, Razón Social, Dirección y Código Postal) contra los que se comparan las facturas. RF-11 pide dar de alta, modificar y dar de baja los campos y valores de referencia. También exige que la validación nacional (HU-13) consuma esa configuración.
- **HU-07 (RF-12):** administrar y cargar los catálogos que usa el portal, además del de proveedores.

Hoy esos valores están fijos en código (`BUSINESS_RULES`). `/admin/rules` sólo los muestra, así que cambiar un parámetro exige un despliegue. El motor sólo compara el RFC del receptor, aunque la minuta pide comparar también la razón social y el código postal. Las claves permitidas de moneda, uso de CFDI, forma y método de pago y régimen fiscal también están en el código.

## What Changes

- **Reglas de Validación editables** (HU-06) en **Administración › Reglas de validación** (`/admin/rules`), exclusiva del rol `ADMIN`:
  - datos de ULTRASIST: RFC, Razón Social, Dirección y Código Postal, y el régimen fiscal como dato de referencia;
  - parámetros del CFDI: método de pago esperado, forma de pago esperada y usos de CFDI permitidos, elegidos de los catálogos;
  - un interruptor por comparación: RFC, Razón Social, Código Postal, método de pago, forma de pago y uso de CFDI;
  - validación con los errores juntos (400), control de edición concurrente por versión (409), auditoría `VALIDATION_SETTINGS_UPDATED` y evento `validation_settings.updated`;
  - los pesos del score siguen en código y se muestran en solo lectura.
- **Motor de validación con la configuración vigente**, leída en cada prevalidación:
  - XML-002 (RFC), XML-003 (método), XML-004 (forma) y XML-005 (uso de CFDI) usan los valores configurados;
  - nuevas **XML-009** (Razón Social del receptor, `ERROR`) y **XML-010** (Código Postal del receptor, `ERROR`);
  - una comparación desactivada resulta `NOT_APPLICABLE`;
  - XML-007 acepta las monedas activas del catálogo.
- **Catálogos de referencia** (HU-07) en **Administración › Catálogos** (`/admin/catalogs`):
  - cinco catálogos del SAT: monedas, usos de CFDI, formas de pago, métodos de pago y regímenes fiscales, sembrados por la migración;
  - alta, edición de la descripción, desactivación y reactivación de claves, que nunca se borran;
  - una clave en uso por las Reglas de Validación no se puede desactivar, y siempre debe quedar al menos una moneda activa;
  - **carga desde Excel**: plantilla descargable con el contenido vigente y carga que agrega claves nuevas y actualiza las existentes, todo o nada, con las protecciones de archivo de HU-01;
  - auditoría y eventos de log.
- **Migración** `0007_validation_rules_catalogs`: tablas `validation_settings` (una sola fila) y `catalog_entries`, sembradas con los valores actuales de `BUSINESS_RULES` y los catálogos.

**Fuera de alcance:**
- validación de invoices internacionales con la Dirección (HU-16);
- flujo de envío a PMO y bloqueo por reglas (HU-13);
- editar los pesos del score o crear reglas nuevas desde la interfaz;
- catálogo de países (lista ISO fija de HU-01), expediente del proveedor (Anexo A) y tipos de documento (HU-04);
- usar los catálogos en otros formularios, como la moneda del contrato.

## Supuestos

Decisiones tomadas ante ambigüedades de las HU, consistentes con el código existente y confirmadas en el plan de módulos:

- **S1.** "Dar de alta y baja los campos" (RF-11) se interpreta como activar o desactivar cada comparación. Los campos son los de la minuta y los parámetros que ya existían; no se crean reglas arbitrarias.
- **S2.** Se agregan XML-009 (Razón Social) y XML-010 (Código Postal), activas por omisión. Sin ellas, configurar esos datos no tendría efecto. Los XML de la demo cumplen ambas.
- **S3.** La Dirección se guarda y se muestra, pero no se compara: el CFDI 4.0 del receptor sólo trae el código postal. La usará la validación de invoices internacionales (HU-16).
- **S4.** El régimen fiscal se conserva como dato de referencia sin comparación, como hoy.
- **S5.** "Catálogos que utiliza el portal" son las cinco listas de claves que hoy usa la validación del CFDI. Países, Anexo A y tipos de documento quedan fuera: los dos últimos ya tienen su propia administración o dependen de otra HU.
- **S6.** La razón social se compara sin distinguir mayúsculas, acentos ni espacios repetidos.
- **S7.** La carga de un catálogo desde Excel actualiza la descripción y el estado de las claves existentes y agrega las nuevas. Nunca borra claves. Si una fila tiene errores no se aplica nada, a diferencia del registro parcial de HU-01, porque un catálogo de referencia a medias es peor que uno sin cambios.
- **S8.** Los pesos del score no son "datos de ULTRASIST": siguen en código (`BUSINESS_RULES`) y en solo lectura.

## Capabilities

### New Capabilities
- `reglas-validacion`: configuración de las Reglas de Validación. Cubre acceso, datos de ULTRASIST, parámetros del CFDI, interruptores por comparación, validación, edición concurrente y auditoría.
- `catalogos-referencia`: catálogos de monedas, usos de CFDI, formas y métodos de pago y regímenes fiscales. Cubre acceso, alta, edición, desactivación con protección de claves en uso, carga desde Excel y auditoría.

### Modified Capabilities
- `motor-validacion`: la fuente única de los parámetros pasa a ser la configuración de Reglas de Validación; nuevas reglas XML-009 y XML-010, interruptores y monedas del catálogo.
- `integridad-datos`:
  - la enumeración de catálogos se agrega a las restricciones;
  - nuevo requisito de integridad de las Reglas de Validación y de los catálogos.
- `observabilidad`: eventos `validation_settings.updated` y `catalog.import`.

## Impact

- **Código:**
  - `app/core/constants.py`: enumeración `CatalogType` y sus etiquetas; `BUSINESS_RULES` conserva sólo los pesos del score;
  - `app/models/__init__.py`: `ValidationSettings` y `CatalogEntry`;
  - nuevos `app/services/validation_settings_service.py`, `app/services/catalog_service.py` y `app/services/catalog_template.py`;
  - `app/rules/xml_rules.py` y `app/services/validation_engine.py`;
  - `app/routers/admin.py`: `/admin/rules` (GET y POST) y `/admin/catalogs*`;
  - plantillas `admin/rules.html` (reescrita), `admin/catalogs.html` y `admin/catalog.html`; opciones de menú en `base.html`.
- **Esquema:** nueva revisión Alembic `0007_validation_rules_catalogs`.
- **Rutas nuevas:**
  - `POST /admin/rules`;
  - `GET /admin/catalogs` y `GET /admin/catalogs/{catalogo}`;
  - `POST /admin/catalogs/{catalogo}`, `POST /admin/catalogs/{catalogo}/{id}` y `POST /admin/catalogs/{catalogo}/{id}/status`;
  - `GET /admin/catalogs/{catalogo}/template` y `POST /admin/catalogs/{catalogo}/import`.
- **Dependencias:** ninguna nueva (`openpyxl` y `defusedxml` ya están).
- **Pruebas:** nuevos `tests/test_reglas_validacion.py` y `tests/test_catalogos.py`; ajustes en `tests/test_folio_y_reglas.py`, `tests/test_integridad.py`, `tests/test_migraciones.py` y `tests/test_observabilidad.py`.
- **Documentación:** `README.md`.
- **Comportamiento visible:** una factura cuyo XML trae una razón social o un código postal del receptor distintos a los de ULTRASIST ahora recibe un `ERROR` y queda en "Requiere corrección".
