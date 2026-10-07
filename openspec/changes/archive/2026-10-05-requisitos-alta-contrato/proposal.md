## Why

Negocio pidió (2026-10-02, HU-22) parametrizar en Requisitos mínimos los documentos para dar de alta un contrato de un proveedor (Contrato obligatorio; Orden de compra y Anexos opcionales) y que el sistema los exija antes de activarlo. El equipo aclaró que los requisitos del alta del proveedor que corresponden al contrato pasan al contrato. Los Lineamientos de facturación (1.i) ponen el contrato vigente como prerrequisito de toda factura.

Hoy el PoC no lo cumple:
- `POST /contracts` crea el contrato activo (`ACTIVE`), y el proveedor puede facturar contra él sin que exista el documento firmado;
- el contrato no tiene dónde guardar documentos: `documents` sólo se liga a facturas o al expediente del proveedor, y no hay página de detalle del contrato;
- "Contrato" (`SUPPLIER_CONTRACT`) vive como requisito opcional del expediente del proveedor (HU-21), aunque un proveedor puede tener varios contratos;
- DOC-005 ("Contrato/anexo disponible") resulta `PASS` con que la factura tenga un contrato asociado, sin revisar documentos.

La historia completa, sus reglas (RN-HU22-01 a RN-HU22-04, RD-01 a RD-13) y sus preguntas abiertas están en `docs/stories/new/HU-22 Requisitos de alta del contrato.md`.

## What Changes

- **Catálogo persistente de requisitos del contrato** (`contract_document_types`). Cada requisito tiene clave inmutable, nombre y descripción en español, un único nivel (Obligatorio, Opcional o No aplica) y si admite varios archivos. Requisitos del sistema: `SIGNED_CONTRACT` ("Contrato", Obligatorio fijo, un archivo), `CONTRACT_PURCHASE_ORDER` ("Orden de compra", Opcional, varios) y `CONTRACT_ANNEXES` ("Anexos", Opcional, varios).
- **Pantalla Administración › Requisitos mínimos › Alta de contrato** (`/admin/contract-requirements`), exclusiva del rol `Administrador`:
  - niveles que se guardan en una transacción, con "Contrato" bloqueado (candado, 409 si se manipula);
  - requisitos del Administrador (`REQ_CONTRATO_<id>`): alta, edición de nombre y descripción, desactivación y reactivación;
  - huella `config_version` y auditoría.
- **Menú "Requisitos mínimos"** que agrupa "Archivos de factura" (HU-04), "Alta de proveedor" (HU-21) y "Alta de contrato". Las rutas existentes no cambian.
- **BREAKING — El contrato nace "Registrado"** (`ContractStatus.REGISTERED`). No se ofrece al facturar ni cumple SUP-002 hasta activarse. El alta lleva al expediente del contrato en lugar de regresar al listado. Los contratos existentes siguen "Activo".
- **Expediente del contrato** (`GET /contracts/{contract_id}`), para PMO y Administrador:
  - datos, historial de enmiendas y panel "Requisitos del contrato" con checklist y aviso "Faltan N requisitos obligatorios";
  - carga de documentos sólo para el Administrador (`POST /contracts/{contract_id}/documents`), con contrato "Registrado" o "Activo";
  - descarga segura.

  Los documentos se ligan sólo al contrato (`documents.contract_id`, sin `supplier_id` ni `invoice_id`) y se guardan en `contracts/<id>/`. Un requisito de un archivo reemplaza al vigente; uno de varios agrega o reemplaza el elegido. Nada se borra.
- **Acción "Activar contrato"** (`POST /contracts/{contract_id}/activate`). Exige, en una transacción y con la configuración vigente: contrato "Registrado", proveedor "Autorizado" y requisitos obligatorios completos. Tiene diálogo de confirmación sin diálogos nativos y botón deshabilitado con el motivo.
- **Listado de contratos** con estatus en español, columna "Requisitos" ("Completos" o "Faltan N") y liga al expediente.
- **BREAKING — DOC-005 según los requisitos del contrato:** `PASS` si el contrato de la factura tiene sus requisitos obligatorios; `FAIL` con los pendientes en otro caso. Las facturas editables de contratos activos sin contrato firmado dejan de poder enviarse hasta que se cargue (P-06 de la HU).
- **"Contrato" sale del alta del proveedor:** `SUPPLIER_CONTRACT` queda fijo en No aplica para los tres tipos de proveedor, con candado en la pantalla de HU-21 y `CHECK` en la base. Sus documentos ya cargados siguen descargables en "Otros documentos del expediente".
- **Migración** `0017_contract_document_types`:
  - crea el catálogo y siembra los 3 requisitos;
  - agrega `documents.contract_id`, amplía el `CHECK` de `contracts.status` y fija `SUPPLIER_CONTRACT`;
  - no cambia el estatus de ningún contrato.

**Fuera de alcance** (detalle en la sección 3 de la HU):
- adjuntar documentos en el formulario de alta del contrato;
- revisar el contenido o restringir formatos por requisito;
- vigencia de los documentos del contrato y exigencias condicionales;
- desactivar o editar contratos, más allá de la enmienda del monto;
- trasladar solos al contrato los documentos `SUPPLIER_CONTRACT` ya cargados;
- acceso del Proveedor al expediente de su contrato;
- cambios en los archivos de la factura (HU-04).

## Capabilities

### New Capabilities
- `requisitos-alta-contrato`: catálogo de requisitos del contrato y su configuración. Cubre:
  - acceso exclusivo del Administrador y el menú "Requisitos mínimos";
  - niveles y nivel fijo de "Contrato";
  - requisitos del Administrador;
  - estatus del contrato ("Registrado", "Activo", "Inactivo");
  - expediente, carga y descarga de documentos del contrato;
  - activación;
  - requisitos en el listado de contratos;
  - protección contra ediciones concurrentes;
  - auditoría.

### Modified Capabilities
- `requisitos-alta-proveedor` (del change `requisitos-alta-proveedor`, que debe archivarse antes que éste):
  - "Catálogo de requisitos de alta": `SUPPLIER_CONTRACT` pasa a No aplica fijo;
  - "Configuración de los requisitos por tipo de proveedor": candado y 409 para `SUPPLIER_CONTRACT`;
  - "Requisitos que aplican a cada proveedor": "Contrato" ya no se ofrece.
- `motor-validacion`:
  - nuevo requisito "Contrato y anexos disponibles según los requisitos del contrato" (DOC-005);
  - "Reglas documentales según los archivos mínimos configurados" remite DOC-005 a ese requisito.
- `integridad-datos`:
  - "Restricciones CHECK sobre estados, montos y vigencias": `contracts.status` con `REGISTERED` y el nivel de `contract_document_types`;
  - "Integridad del catálogo de requisitos de alta": `SUPPLIER_CONTRACT` siempre No aplica;
  - nuevos requisitos "Integridad del catálogo de requisitos del contrato" y "Documentos del contrato con un solo dueño".
- `listados-paginados`: "El alta muestra el registro creado". El alta de un contrato lleva a su expediente.
- `observabilidad`: "Registro de eventos técnicos del flujo". La subida de documento registra `contract_id`.

## Impact

- **Código** (rutas relativas a la raíz de la PoC):
  - `app/core/constants.py`: `ContractStatus.REGISTERED` y sus etiquetas; niveles fijos y motivos de `SIGNED_CONTRACT` y `SUPPLIER_CONTRACT`;
  - `app/models/__init__.py`: modelo `ContractDocumentType`; `Document.contract_id` con su `CHECK`; `Contract.status` por defecto `REGISTERED`; `CHECK` de nivel fijo en `SupplierDocumentType`;
  - `app/schemas/__init__.py`: `ContractDocumentTypeCreate` y `ContractDocumentTypeUpdate`;
  - nuevo `app/services/contract_requirements_service.py`; `supplier_requirements_service.py` respeta el nivel fijo; `file_service.py` agrega `save_contract_file()`;
  - `app/rules/document_rules.py` y `app/services/validation_engine.py`: DOC-005;
  - `app/routers/contracts.py`: alta "Registrado", expediente, carga, descarga, activación y listado;
  - `app/routers/admin.py`: rutas `/admin/contract-requirements*` y candado en `/admin/supplier-requirements`;
  - plantillas: nuevas `contracts/detail.html` y `admin/contract_requirements.html`; cambios en `contracts/list.html`, `admin/supplier_requirements.html` y `base.html`; script del diálogo de activación en `app/static/js/`.
- **Esquema:** nueva revisión Alembic `0017_contract_document_types`, posterior a `0016_supplier_document_types`.
- **Rutas nuevas:**
  - `GET /contracts/{contract_id}`;
  - `POST /contracts/{contract_id}/documents`;
  - `GET /contracts/{contract_id}/documents/{document_id}/download`;
  - `POST /contracts/{contract_id}/activate`;
  - `GET /admin/contract-requirements` y `POST /admin/contract-requirements`;
  - `POST /admin/contract-requirements/types`, `POST /admin/contract-requirements/types/{type_id}` y `POST /admin/contract-requirements/types/{type_id}/status`.
- **Datos demo:** `scripts/seed_db.py` carga el contrato firmado de los tres contratos demo, que siguen `ACTIVE`, para que las 10 facturas demo conserven su resultado.
- **Pruebas:**
  - nuevo `tests/test_requisitos_contrato.py`;
  - ajustes en `test_contratos.py`, `test_requisitos_alta.py`, `test_archivos_minimos.py`, `test_factura_internacional.py`, `test_registro_envio.py`, `test_listados_paginados.py`, `test_observabilidad.py`, `test_migraciones.py`, `test_integridad.py`, `test_permissions.py` y `conftest.py` (contratos activos con su contrato firmado);
  - suite Playwright `tests/hu`: menú en HU-04 y HU-21; nueva especificación de HU-22.
- **Documentación:** `README.md` (requisitos del contrato, estatus "Registrado", activación y DOC-005).
- **Despliegue:** en un ambiente con contratos activos sin documentos, DOC-005 bloqueará el envío de sus facturas editables hasta que se cargue el contrato firmado. El listado los marca con "Faltan 1".
- **Orden de los changes:** archivar `requisitos-alta-proveedor` antes de archivar éste, porque sus deltas modifican requisitos que ese change agrega.
- **Sin cambios:** dependencias, `flujo-facturas` (ya exige contratos activos), `trazabilidad-contratos`, `almacenamiento-documentos` y `archivos-minimos-factura`.
