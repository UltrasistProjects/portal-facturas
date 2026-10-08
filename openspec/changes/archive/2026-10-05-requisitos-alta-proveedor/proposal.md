## Why

Negocio pidió (2026-10-02, HU-21) parametrizar en la configuración los documentos mínimos para dar de alta a un proveedor, marcados como obligatorios u opcionales, y que el sistema los exija antes de activarlo. Los Lineamientos de facturación (1.i) ya lo establecen: el Asociado se da de alta "con el cumplimiento al 100% de los requisitos detallados en el 'Anexo A'".

Hoy el PoC no cumple esa condición:
- el expediente del proveedor está fijo en código (`SUPPLIER_REQUIREMENTS`) y no incluye "Poderes"; cambiar un requisito exige un despliegue;
- la autorización (HU-02) pasa a "Autorizado" a cualquier proveedor "Registrado", aunque su expediente esté vacío, y le envía credenciales;
- el expediente sólo se revisa con SUP-003 al validar cada factura, cuando el proveedor ya tiene acceso al portal.

HU-04 dejó el expediente del proveedor fuera de su alcance; esta HU lo cubre con el mismo patrón de configuración. La historia completa, sus reglas (RN-HU21-01 a RN-HU21-03, RD-01 a RD-11) y sus preguntas abiertas están en `docs/stories/new/HU-21 Requisitos de alta del proveedor.md`.

## What Changes

- **Catálogo persistente de requisitos de alta** (`supplier_document_types`). Cada requisito tiene:
  - una clave inmutable, que es el valor de `documents.document_type` en el expediente;
  - un nombre en español y una descripción;
  - un nivel por tipo de proveedor (persona moral nacional, persona física nacional e internacional): Obligatorio, Opcional o No aplica.

  Incluye los 12 documentos actuales del expediente y el nuevo `POWER_OF_ATTORNEY` ("Poderes"). Para la persona moral, los siete documentos de la solicitud son obligatorios: Acta constitutiva, Poderes, Cédula fiscal, Identificación del representante legal, Comprobante de domicilio del representante legal, Comprobante de domicilio y Estado de cuenta bancario. El internacional no tiene requisitos, como hoy.
- **Pantalla Administración › Requisitos de alta** (`/admin/supplier-requirements`), exclusiva del rol `Administrador`:
  - una matriz de niveles por tipo de proveedor que se guarda en una sola transacción;
  - protección contra ediciones concurrentes mediante la huella `config_version`;
  - auditoría de cada cambio.
- **Requisitos definidos por el Administrador:** alta, edición de nombre y descripción, desactivación y reactivación. Su clave es `REQUISITO_<id>` y nunca se borran. Los requisitos del sistema sólo cambian de nivel.
- **Panel "Requisitos de alta" en el expediente**, que sustituye a "Expediente Anexo A":
  - checklist con los exigibles primero, cada uno cargado o "Pendiente";
  - aviso "Faltan N requisitos obligatorios" o "Requisitos de alta completos";
  - la carga ofrece sólo los requisitos que aplican; el servidor rechaza con 400 los demás, antes de escribir el archivo;
  - los documentos de requisitos que dejaron de aplicar siguen descargables en "Otros documentos del expediente".
- **BREAKING — Autorización condicionada:** un proveedor "Registrado" con requisitos exigibles pendientes no se autoriza, ni se le crea usuario ni cuenta en Keycloak. El resumen lo lista con los pendientes y la auditoría y el log lo cuentan en `requirements_incomplete`. En el listado sólo tienen casilla los "Registrado" con requisitos completos, y la nueva columna "Requisitos de alta" muestra "Completos" o "Faltan N".
- **Botón "Autorizar proveedor" en el expediente**, con diálogo de confirmación. Usa el mismo `POST /suppliers/authorize` y las mismas reglas que la autorización masiva.
- **BREAKING — SUP-003 según la configuración:** evalúa los mismos requisitos exigibles y su mensaje nombra los pendientes. Para un proveedor nacional cambia lo exigido:
  - "Poderes" es nuevo y obligatorio para la persona moral;
  - la Opinión de cumplimiento pasa a opcional (P-01);
  - los dos comprobantes de domicilio dejan de ser alternativos (P-04).

  Para el internacional, SUP-003 sólo se evalúa si se le configura algún requisito obligatorio.
- **Se conserva** la propuesta económica exigible cuando el alta es por cotización o licitación, y la advertencia de vigencia de tres meses (SUP-004), que no bloquea la autorización.
- **Migración** `0016_supplier_document_types`: crea la tabla y siembra los 13 requisitos del sistema. No cambia el estatus de ningún proveedor ni sus documentos.

**Fuera de alcance** (detalle en la sección 3 de la HU):
- adjuntar documentos en el formulario de alta o en la plantilla de Excel;
- revisar el contenido de los documentos, o restringir formatos por requisito;
- exigencias condicionales configurables (por ejemplo, el poder notarial "sólo en caso de…");
- que un documento vencido bloquee la autorización;
- desautorizar a proveedores ya autorizados cuando cambia la configuración;
- estatus "Inactivo" y reactivación de proveedores;
- avisos por correo de requisitos pendientes;
- archivos mínimos de la factura (HU-04).

## Capabilities

### New Capabilities
- `requisitos-alta-proveedor`: catálogo de requisitos de alta y su configuración por tipo de proveedor. Cubre:
  - acceso exclusivo del Administrador;
  - matriz de niveles y requisitos del Administrador;
  - requisitos que aplican a cada proveedor y validación del tipo al cargar;
  - checklist del expediente;
  - protección contra ediciones concurrentes;
  - auditoría.

### Modified Capabilities
- `acceso-proveedores`:
  - "Estatus 'Autorizado'": la transición también puede hacerse desde el expediente y exige los requisitos de alta completos;
  - "Selección de proveedores en el listado": columna "Requisitos de alta" y casilla sólo con requisitos completos;
  - "Reglas de la autorización masiva": los proveedores con requisitos pendientes no se autorizan;
  - "Resumen de la autorización" y "Auditoría del acceso de proveedores": nuevo grupo `requirements_incomplete`;
  - nuevo requisito "Autorización desde el expediente".
- `motor-validacion`:
  - nuevo requisito "Expediente mínimo según los requisitos de alta configurados" (SUP-003);
  - "Reglas nacionales que no aplican a la factura internacional": SUP-003 sólo no aplica cuando el internacional no tiene requisitos obligatorios.
- `integridad-datos`:
  - la restricción de enumeraciones incluye los niveles de requisito de alta;
  - nuevo requisito de integridad del catálogo de requisitos de alta: unicidad de clave y de nombre sin distinguir mayúsculas, y requisitos del sistema siempre activos.
- `observabilidad`: el evento `supplier.bulk_authorize` agrega `requirements_incomplete`.

## Impact

- **Código:**
  - `app/core/constants.py`: enumeración `RequirementProfile`; se eliminan `SUPPLIER_REQUIREMENTS`, `SUPPLIER_DOCUMENT_LABELS`, `OPTIONAL_SUPPLIER_DOCUMENTS` y `ALTERNATIVE_SUPPLIER_DOCUMENTS`;
  - `app/models/__init__.py`: modelo `SupplierDocumentType`;
  - `app/schemas/__init__.py`: `SupplierDocumentTypeCreate` y `SupplierDocumentTypeUpdate`;
  - nuevo `app/services/supplier_requirements_service.py`; `app/services/supplier_service.py` pierde `supplier_requirement_status()`;
  - `app/services/supplier_access_service.py`: verificación de requisitos en `authorize()` y en el resumen;
  - `app/rules/supplier_rules.py` y `app/services/validation_engine.py`: SUP-003;
  - `app/routers/admin.py`: rutas `/admin/supplier-requirements*`;
  - `app/routers/suppliers.py`: expediente, listado y carga de documentos;
  - plantillas: nueva `admin/supplier_requirements.html`; cambios en `suppliers/detail.html`, `suppliers/list.html` y `base.html`; script del diálogo de autorización en `app/static/js/`.
- **Esquema:** nueva revisión Alembic `0016_supplier_document_types`, posterior a `0015_keycloak_identity`.
- **Rutas nuevas:**
  - `GET /admin/supplier-requirements` y `POST /admin/supplier-requirements`;
  - `POST /admin/supplier-requirements/types`;
  - `POST /admin/supplier-requirements/types/{type_id}`;
  - `POST /admin/supplier-requirements/types/{type_id}/status`.
- **Datos demo:** `scripts/seed_db.py` carga a los proveedores demo los requisitos que les aplican según el catálogo, incluido "Poderes", para que las 10 facturas demo conserven su resultado.
- **Pruebas:**
  - nuevo `tests/test_requisitos_alta.py`;
  - ajustes en `test_acceso_proveedores.py`, `test_datos_proveedor.py`, `test_factura_internacional.py`, `test_archivos.py`, `test_observabilidad.py`, `test_migraciones.py`, `test_integridad.py`, `test_permissions.py` y en los fixtures que autorizan proveedores;
  - suite Playwright `tests/hu`: HU-02, HU-03 y HU-10 cargan los requisitos antes de autorizar; nueva especificación de HU-21.
- **Documentación:** `README.md` (requisitos de alta, autorización y SUP-003).
- **Despliegue:** en un ambiente con proveedores ya autorizados sin "Poderes", SUP-003 bloqueará el envío de sus facturas hasta que lo carguen (P-07). Se puede desplegar con "Poderes" en Opcional y endurecerlo después desde la pantalla.
- **Sin cambios:** dependencias, extensiones globales y tamaño máximo de archivo (`almacenamiento-documentos`), archivos mínimos de la factura (`archivos-minimos-factura`) y estados de la factura (`flujo-facturas`).
