## Why

El catálogo de proveedores es el requisito base del MVP (RF-01): sin él no se puede autorizar a los proveedores (HU-02), enviarles credenciales (HU-03) ni recibir sus facturas. Hoy el único medio de alta es un formulario individual, inviable para poblar el catálogo inicial. La HU-01 pide cargarlo de forma masiva mediante un formato de Excel predefinido, y la regla RN-HU01-01 exige mapear los datos requeridos del catálogo. La historia completa y sus decisiones están en `docs/stories/new/HU-01 Carga masiva de proveedores.md`.

## What Changes

- **Plantilla de Excel predefinida:** el sistema la genera (`plantilla_carga_proveedores_v1.xlsx`). Tiene una hoja `Proveedores` con 10 columnas (Origen, Tipo de persona, Razón social, RFC, Identificador fiscal extranjero, País, Correo electrónico, Teléfono, Convenio de confidencialidad y Notas), listas desplegables y una hoja `Instrucciones`.
- **Carga masiva** en `/suppliers/import`, exclusiva del rol `ADMIN`:
  - **validación del archivo:** sólo `.xlsx`, hasta 5 MB y 50 MB descomprimidos, sin entidades XML, con la plantilla vigente y de 1 a 1000 filas;
  - **mapeo y normalización** de cada columna al catálogo;
  - **validación por fila**, con reglas distintas para proveedores Nacional e Internacional (RFC con patrón SAT; identificador fiscal y país ISO);
  - **duplicados:** los repetidos dentro del archivo son un error, los que ya existen en el catálogo se omiten sin modificarse y un correo ya en uso es un error.
- **Confirmación ante filas con errores:** en modo `strict` no se registra nada. Si hay filas registrables, una ventana emergente ofrece "No, corregir primero (Recomendado)", preseleccionada, o "Agrega las filas válidas y omite el resto". Esta segunda opción reenvía el mismo archivo en modo `partial`, verificado por su SHA-256.
- **Registro atómico** de las filas que se registran; una carga concurrente responde 409.
- **Estatus inicial `REGISTERED` ("Registrado"):** no se crean usuarios ni se envían correos. El paso a "Autorizado" es de HU-02.
- **Resumen** del resultado, **auditoría** (`SUPPLIER_BULK_IMPORTED` y `SUPPLIER_CREATED` con el origen de la carga) y evento de log `supplier.bulk_import` sin datos sensibles.
- **Modelo:** `suppliers` gana `origin` (`NATIONAL`/`INTERNATIONAL`), `foreign_tax_id` y `country`, y `rfc` pasa a admitir `NULL`. Se agregan la unicidad `(country, foreign_tax_id)`, un `CHECK` de coherencia por origen y el estatus `REGISTERED`. Los proveedores existentes quedan como `NATIONAL`/`MX`.
- **Dependencias:** `openpyxl` y `defusedxml`.

**Fuera de alcance:**
- autorización de proveedores (HU-02) y envío de credenciales (HU-03);
- actualizar proveedores existentes mediante la carga;
- alinear el alta individual con el nuevo estatus (HU-02);
- otros catálogos o contratos (HU-07);
- expediente de proveedores internacionales (HU-04);
- datos bancarios, domicilio y código postal del proveedor.

## Capabilities

### New Capabilities
- `catalogo-proveedores`: carga masiva del catálogo de proveedores desde una plantilla de Excel predefinida. Cubre plantilla, acceso, validación del archivo y de las filas, mapeo, duplicados, confirmación del registro parcial, registro atómico, estatus inicial, resumen y auditoría.

### Modified Capabilities
- `integridad-datos`:
  - la enumeración de `suppliers.status` incluye `REGISTERED`;
  - se añade la enumeración `suppliers.origin`;
  - nuevo requisito de identidad fiscal única de proveedores: `rfc` único con `NULL` permitidos, `(country, foreign_tax_id)` único y `CHECK` de coherencia por origen.
- `observabilidad`: el registro de eventos técnicos incluye `supplier.bulk_import`.

## Impact

- **Código:**
  - `app/core/constants.py` (estatus, origen y etiquetas);
  - `app/models/__init__.py` (`Supplier`);
  - `app/schemas/__init__.py` (validadores de proveedor);
  - nuevos `app/services/supplier_import_service.py` y `app/services/supplier_template.py`;
  - `app/routers/suppliers.py` (tres rutas nuevas);
  - `app/templates/suppliers/` (nueva `import.html`; estatus en `list.html` y `detail.html`);
  - nuevo `app/static/js/supplier_import.js`.
- **Esquema:** nueva revisión Alembic `0002_supplier_bulk_import`.
- **Dependencias:** `openpyxl` y `defusedxml` en `requirements.txt`; `requirements.lock` regenerado y auditado con `pip-audit`.
- **Datos demo:** `scripts/seed_db.py` crea sus proveedores como `NATIONAL`.
- **Pruebas:** nuevo `tests/test_carga_masiva_proveedores.py`; ajustes en `tests/test_integridad.py` y `tests/test_migraciones.py`.
- **Documentación:** `README.md`.
- **Sin cambios de comportamiento** en el alta individual, la validación de facturas (SUP-001 sigue exigiendo `ACTIVE`) ni el resto de los flujos.
