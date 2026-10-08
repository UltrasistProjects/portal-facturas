> Todas las rutas son relativas a la raíz de la PoC (`PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress-V1/PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress/`). Cada grupo termina con `ruff` limpio. A partir del grupo 2, también con la suite verde sobre PostgreSQL (`docker compose up -d --wait db`).

## 1. Dependencias

- [x] 1.1 Añadir `openpyxl` y `defusedxml` (versiones vigentes fijadas) a `requirements.txt`, regenerar `requirements.lock` con `uv pip compile --universal --generate-hashes --python-version 3.12 requirements.txt -o requirements.lock`, instalarlo en `.venv` y ejecutar `pip-audit` sobre el lock (sin avisos).

## 2. Modelo y migración

- [x] 2.1 `app/core/constants.py`: `SupplierStatus.REGISTERED`, enumeración `SupplierOrigin` (`NATIONAL`, `INTERNATIONAL`) y `SUPPLIER_STATUS_LABELS` (`Registrado`, `Activo`, `Inactivo`).
- [x] 2.2 `app/models/__init__.py` (D4):
  - `Supplier` con `origin` (por defecto `NATIONAL`), `foreign_tax_id` y `country` (por defecto `"MX"`);
  - `rfc` que admite `NULL`;
  - `UniqueConstraint` `uq_suppliers_country_foreign_tax_id` y `CheckConstraint` `ck_suppliers_origin_identity`;
  - propiedad `tax_identifier`.
- [x] 2.3 Revisión `alembic/versions/0002_supplier_bulk_import.py` (D9): upgrade con relleno `NATIONAL`/`MX`, `CHECK` de estatus y origen, unicidad compuesta y coherencia. Downgrade explícito, o `NotImplementedError` si existen proveedores `INTERNATIONAL` o `REGISTERED`.
- [x] 2.4 Plantillas: `tax_identifier` en lugar de `rfc` en `suppliers/list.html`, `suppliers/detail.html`, `invoices/detail.html`, `invoices/new.html` y `components/invoice_table.html`. Etiqueta de estatus (`SUPPLIER_STATUS_LABELS`, publicada como global en `app/routers/common.py`) en el listado y el detalle de proveedores.
- [x] 2.5 Pruebas en `tests/test_integridad.py` (spec `integridad-datos`):
  - `CHECK` de `suppliers.status = 'PENDIENTE'` y de un origen inválido;
  - varios internacionales sin RFC;
  - `(country, foreign_tax_id)` repetido rechazado y aceptado en países distintos;
  - nacional sin RFC rechazado;
  - internacional con `country = 'MX'` rechazado.
- [x] 2.6 Pruebas en `tests/test_migraciones.py`:
  - proveedores previos a `0002` quedan `NATIONAL`/`MX` con su RFC y su estatus;
  - el downgrade de `0002` sin datos nuevos funciona;
  - con un proveedor `INTERNATIONAL` lanza `NotImplementedError`;
  - ajustar la prueba del downgrade de la revisión base y las de `tests/test_respaldos.py` para que lean la revisión cabeza (`head_revision()` en `conftest.py`) en lugar de fijarla.

## 3. Plantilla de Excel

- [x] 3.1 `app/core/countries.py` con los códigos ISO 3166-1 alfa-2 y su nombre en español.
- [x] 3.2 `app/services/supplier_template.py` (D13):
  - `HEADERS`, `TEMPLATE_VERSION` y `TEMPLATE_FILENAME`;
  - `build_template()` con la hoja `Proveedores` (encabezados, listas desplegables en Origen, Tipo de persona y Convenio, y formato de texto en RFC, Identificador fiscal extranjero y Teléfono);
  - hoja `Instrucciones` (versión, descripción de columnas, un ejemplo por origen y la lista de países).

## 4. Servicio de importación

- [x] 4.1 Lectura del archivo (D1, D8): extensión `.xlsx`, 5 MB, ZIP válido con `xl/workbook.xml`, 50 MB descomprimidos, sin `<!DOCTYPE`/`<!ENTITY`, hoja y encabezados vigentes, filas vacías ignoradas y de 1 a 1000 filas con datos. Mensajes exactos de la spec y log técnico del fallo de lectura, sin nombre de archivo.
- [x] 4.2 Normalización y validación por fila (D2): espacios; mayúsculas y minúsculas; listas sin acentos; enteros a texto; celdas con fórmula o fecha; reglas de Nacional (RFC con patrón, fecha, longitud por tipo de persona y RFC genérico) y de Internacional (identificador y país ISO); teléfono, notas y convenio.
- [x] 4.3 Duplicados:
  - dentro del archivo, en todas sus apariciones: RFC, (país, identificador) y correo;
  - contra el catálogo, con consultas en lote: existentes omitidos y correo en uso por un proveedor o usuario.
- [x] 4.4 Orquestación (D3, D12):
  - modos `strict` y `partial` con `expected_sha256`;
  - registro atómico en `REGISTERED`, sin usuarios;
  - `IntegrityError` → rollback y 409;
  - errores limitados a 200, más `hidden_errors`;
  - `summary` con singular y plural correctos.
- [x] 4.5 Auditoría (`SUPPLIER_BULK_IMPORTED` con `mode`, `sha256`, `size_bytes`, `rows`, `created`, `skipped` e `invalid`; `SUPPLIER_CREATED` con `source` e `import_sha256`) y evento de log `supplier.bulk_import` (`mode`, `result`, `rows`, `registered`, `skipped`, `invalid`, `size_bytes` y `duration_ms`; `created` es un atributo reservado de `LogRecord`), sin datos del archivo.

## 5. Rutas e interfaz

- [x] 5.1 `app/routers/suppliers.py` (D6): `GET /suppliers/import`, `GET /suppliers/import/template` y `POST /suppliers/import`, declaradas antes de `/{supplier_id}`, sólo para `ADMIN` y con CSRF en el POST.
- [x] 5.2 `app/templates/suppliers/import.html`:
  - instrucciones, botón de descarga de la plantilla y formulario (`accept=".xlsx"`);
  - zonas de resumen y de errores;
  - modal de confirmación con el texto y los dos botones de la spec;
  - aviso `<noscript>`.
  
  Añadir el bloque `scripts` en `base.html` y el enlace "Carga masiva" en `suppliers/list.html` (sólo `ADMIN`).
- [x] 5.3 `app/static/js/supplier_import.js` (D11): envío con `fetch`; modal con el foco en "No, corregir primero (Recomendado)"; cierre o Esc → lista de errores; "Agrega las filas válidas y omite el resto" → reenvío con `mode=partial` y `expected_sha256`; pintado con `textContent`.
- [x] 5.4 Estilos mínimos en `app/static/css/app.css` para el resumen, la tabla de errores y el estatus "Registrado".

## 6. Pruebas de la carga

- [x] 6.1 `tests/test_carga_masiva_proveedores.py` con utilidades que generan libros en memoria (filas, fórmulas, fechas, encabezados alterados, bomba de descompresión y entidades XML) y datos únicos por prueba.
- [x] 6.2 Escenarios de plantilla, acceso (INTERNAL, PROVIDER, CSRF) y validación del archivo.
- [x] 6.3 Escenarios de mapeo, normalización, validación por fila y duplicados.
- [x] 6.4 Escenarios de confirmación (`strict`, `partial`, SHA-256, sin filas registrables, más de 200 errores), registro atómico (archivo sin errores; conflicto de unicidad → 409), estatus inicial y resumen.
- [x] 6.5 Escenarios de auditoría, evento `supplier.bulk_import` y log sin datos del archivo.

## 7. Documentación y verificación

- [x] 7.1 `README.md`: sección "Carga masiva de proveedores" (flujo, plantilla, límites y confirmación).
- [x] 7.2 `python scripts/check.py` en verde: ruff, formato, `alembic check`, pytest con cobertura ≥ 93 % y `pip-audit`.
- [x] 7.3 Verificación manual en la aplicación: descargar la plantilla, abrirla en LibreOffice Calc, capturar filas válidas y con errores, comprobar el modal (foco, Esc, las dos opciones) y el resumen, y ver los proveedores en "Registrado". *(Automatizada con Chromium headless (Playwright) sobre una base temporal, 20/20 verificaciones, y con LibreOffice Calc headless: la plantilla conserva hojas, listas y formato, y un archivo guardado por Calc se importa. Microsoft Excel no está disponible en este equipo.)*
- [x] 7.4 `openspec validate carga-masiva-proveedores --strict` sin errores.
