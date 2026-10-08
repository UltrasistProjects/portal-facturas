## Why

La HU-04 (RF-04) pide que el Administrador defina los archivos mínimos que el proveedor debe subir con cada factura, distintos para el proveedor Nacional y el Internacional. El registro de la factura nacional (HU-12) y el de la internacional (HU-15) dependen de esa configuración.

Hoy el PoC exige a todos los proveedores los mismos cuatro archivos, fijos en código (DOC-001 a DOC-004: XML, PDF, orden de compra y Vo.Bo.). Esto tiene dos problemas:
- un proveedor internacional no puede cumplir, porque no emite CFDI y DOC-001 (`CRITICAL`) lo bloquea siempre;
- cambiar un requisito exige un despliegue, por ejemplo para definir los soportes del Invoice extranjero cuando se analicen los ejemplos acordados en la minuta del 21-sep-2026.

HU-01 dejó registrado el origen del proveedor (`suppliers.origin`) justamente para esta HU. La historia completa, sus reglas derivadas (RD-01 a RD-10) y sus preguntas abiertas están en `docs/stories/new/HU-04 Definicion de archivos requeridos por tipo de proveedor.md`.

## What Changes

- **Catálogo persistente de tipos de documento de factura** (`invoice_document_types`). Cada tipo tiene:
  - una clave inmutable, que es el valor de `documents.document_type`;
  - un nombre en español, una descripción y los formatos admitidos (PDF, PNG, JPEG, XML, TXT);
  - un nivel de exigencia por origen: Obligatorio, Opcional o No aplica.

  Incluye los 9 tipos actuales y el nuevo tipo `FOREIGN_INVOICE` ("Invoice (PDF)").
- **Pantalla Administración › Archivos mínimos** (`/admin/required-documents`), exclusiva del rol `ADMIN`:
  - una matriz de niveles por origen que se guarda en una sola transacción;
  - protección contra ediciones concurrentes mediante la huella `config_version`;
  - auditoría de cada cambio.
- **Niveles fijos**, protegidos en la pantalla, en el servidor (409) y en la base de datos (`CHECK`):
  - XML y PDF del CFDI son Obligatorios para el Nacional y No aplican al Internacional;
  - el Invoice es Obligatorio para el Internacional y No aplica al Nacional.
- **Tipos de documento soporte definidos por el Administrador:** alta, edición de nombre, descripción y formatos, desactivación y reactivación. Su clave es `SOPORTE_<id>` y nunca se borran. Los tipos del sistema no se editan ni se desactivan.
- **Carga documental según el origen del proveedor:**
  - el selector ofrece sólo los tipos que aplican, con su nombre y sus formatos;
  - el servidor rechaza con 400, antes de escribir el archivo, un tipo que no aplica o un formato que el tipo no admite;
  - el checklist separa obligatorios y opcionales e indica cuántos obligatorios faltan.
- **Reglas documentales según la configuración:**
  - DOC-001 a DOC-004 conservan su código y su severidad, y resultan `NOT_APPLICABLE` cuando su tipo no es obligatorio para el origen;
  - nueva DOC-008 (Invoice, `CRITICAL`);
  - nueva DOC-009 (`ERROR`), con un resultado por cada otro tipo obligatorio;
  - los mensajes usan el nombre del tipo, por ejemplo "Falta Vo.Bo. del líder de proyecto".
- **Nombres en español** de los tipos también en el detalle de la factura. Los documentos de tipos que dejaron de aplicar siguen listados y descargables.
- **Migración** `0003_invoice_document_types`: crea la tabla y siembra los 10 tipos del sistema. Los valores iniciales conservan el comportamiento actual para los proveedores nacionales. Los resultados de las 10 facturas demo no cambian.

**Fuera de alcance** (detalle en la sección 3 de la HU):
- expediente del proveedor (Anexo A) y reglas SUP-003/SUP-004;
- expediente del proveedor internacional, que pasa a HU-16 (P-02);
- reglas XML, SUP y de contrato para facturas internacionales (HU-16);
- estatus "Cargada" y "Enviada" (HU-12, HU-13, HU-15 y HU-16);
- duplicados del Invoice (HU-15) y acuse de cancelación (HU-14);
- exigencias condicionales o por contrato, proyecto o tipo de persona;
- tamaño máximo por tipo de documento;
- otros catálogos administrables (HU-07).

## Capabilities

### New Capabilities
- `archivos-minimos-factura`: catálogo de tipos de documento de factura y configuración de los archivos mínimos por origen del proveedor. Cubre:
  - acceso exclusivo del Administrador;
  - matriz de niveles y niveles fijos;
  - tipos soporte del Administrador;
  - carga documental y checklist según el origen;
  - protección contra ediciones concurrentes;
  - auditoría.

### Modified Capabilities
- `motor-validacion`: nuevo requisito de reglas documentales según los archivos mínimos configurados (DOC-001 a DOC-004 condicionadas al origen, nuevas DOC-008 y DOC-009, y evaluación con la configuración vigente sólo en facturas editables).
- `integridad-datos`:
  - la restricción de enumeraciones incluye el nivel de exigencia de archivo;
  - nuevo requisito de integridad del catálogo de tipos de documento: unicidad de clave y de nombre sin distinguir mayúsculas, formatos válidos, tipos del sistema siempre activos y niveles fijos.

## Impact

- **Código:**
  - `app/core/constants.py`: `DocumentType.FOREIGN_INVOICE`, `DocumentRequirement` con etiquetas en español, formatos y sus extensiones, y niveles fijos;
  - `app/models/__init__.py`: modelo `InvoiceDocumentType`;
  - `app/schemas/__init__.py`: `DocumentTypeCreate` y `DocumentTypeUpdate`;
  - nuevo `app/services/document_requirements_service.py`;
  - `app/rules/base.py` y `app/rules/document_rules.py`;
  - `app/services/validation_engine.py`;
  - `app/routers/admin.py`: rutas `/admin/required-documents*`;
  - `app/routers/invoices.py`: página y carga documental;
  - plantillas: nueva `admin/required_documents.html`; cambios en `invoices/documents.html`, `invoices/detail.html` y `base.html`.
- **Esquema:** nueva revisión Alembic `0003_invoice_document_types`, posterior a `0002_supplier_bulk_import`.
- **Rutas nuevas:**
  - `GET /admin/required-documents` y `POST /admin/required-documents`;
  - `POST /admin/required-documents/types`;
  - `POST /admin/required-documents/types/{type_id}`;
  - `POST /admin/required-documents/types/{type_id}/status`.
- **Pruebas:** nuevo `tests/test_archivos_minimos.py`; ajustes en `tests/test_migraciones.py`, `tests/test_integridad.py`, `tests/test_archivos.py` y `tests/test_permissions.py`.
- **Documentación:** `README.md` (reglas DOC, configuración de archivos mínimos y limitación de las facturas internacionales hasta HU-16).
- **Sin cambios:**
  - dependencias;
  - datos demo (`scripts/seed_db.py`);
  - extensiones globales y tamaño máximo de archivo (`almacenamiento-documentos`);
  - estados editables y bloqueo del envío (`flujo-facturas`);
  - la vista `/admin/rules`.
- **Comportamiento visible para el proveedor nacional:** los tipos se muestran con su nombre en español y cada tipo acepta sólo sus formatos. Por ejemplo, ya no se puede cargar un PDF como XML del CFDI.
