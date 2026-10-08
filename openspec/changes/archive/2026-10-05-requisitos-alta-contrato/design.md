## Context

La HU-22 (`docs/stories/new/HU-22 Requisitos de alta del contrato.md`) pide parametrizar los documentos para dar de alta un contrato y exigirlos antes de activarlo. Sus reglas derivadas (RD-01 a RD-13) no están confirmadas por negocio. Sus preguntas abiertas sólo cambian valores sembrados, la configuración de HU-04 o la severidad de DOC-005.

Estado actual del PoC (rutas relativas a la raíz de la PoC):

- **Contratos:** `app/routers/contracts.py` tiene sólo el listado (`_contracts_page`, con búsqueda y paginación en SQL), el alta (`create_contract`) y la enmienda del monto (`amend_contract`, que usa `contract_service.amend_authorized_amount`).
  - El alta crea `Contract(**data, created_by, updated_by)` sin `status`, así que toma el valor por defecto del modelo, `ContractStatus.ACTIVE`. Después audita `CONTRACT_CREATED` y redirige al listado con `?q=<proyecto>&ok=created`.
  - No hay página de detalle. `contracts/list.html` muestra `{{ c.status }}` crudo y siempre con la clase `status-accepted`.
  - El listado es para PMO y Administrador; el alta y las enmiendas, sólo para Administrador.
- **Uso del estatus:**
  - `invoices.py` ofrece al proveedor sólo sus contratos `ACTIVE` y rechaza otro con 400 "El contrato no está activo";
  - SUP-002 (`supplier_rules`) exige `ACTIVE` y la fecha de hoy dentro de la vigencia;
  - nada asigna `INACTIVE`.
- **Documentos:** `Document` tiene `invoice_id` y `supplier_id`. Los documentos de factura llenan ambos; los del expediente del proveedor sólo `supplier_id`.
  - `supplier_requirements_service.expedient_documents()` y `download_supplier_document()` identifican el expediente por `supplier_id` con `invoice_id IS NULL`.
  - `LocalFileStorage._save(scope, entity_id, upload)` guarda en `<scope>/<id>/<uuid>.<ext>` y valida extensión, contenido y tamaño. Ya existen `save_invoice_file` y `save_supplier_file`.
  - `log_upload(document_type, stored, **owner)` emite `document.uploaded` con el dueño que recibe.
- **DOC-005:** `document_rules(..., contract_available: bool)` en `app/rules/document_rules.py`; `validation_engine` le pasa `bool(invoice.contract)`.
- **Patrones a reutilizar:**
  - **HU-04** (`document_requirements_service.py`): `sort_key`, `config_version`, `pg_advisory_xact_lock`, `_flush` que traduce la unicidad a 409, y niveles fijos con `FIXED_REQUIREMENTS`, `FIXED_REQUIREMENT_REASONS` y `fixed_requirement()`. Al guardar, un nivel fijo ausente se ignora y uno distinto del fijo responde 409.
  - **HU-21** (`supplier_requirements_service.py`):
    - checklist con `RequirementRow`, `OtherDocument`, `Checklist` y `pending_label`;
    - pendientes por página sin N+1 (`pending_requirements`);
    - `applicable_type()` antes de escribir el archivo;
    - `save_requirements` con campos `<perfil>__<code>`;
    - base común de validadores de nombre y descripción en `app/schemas`;
    - modal de confirmación en `supplier_authorize.js` con el texto en `data-confirm`.
- **Pruebas:**
  - base PostgreSQL temporal por sesión con el seed;
  - `scripts/check.py`: ruff, `alembic check`, pytest con cobertura ≥ 93 % y `pip-audit`;
  - `conftest.py` ya tiene `add_expedient_documents`, `load_requirements` y `registered_suppliers`;
  - crean `Contract(...)` sin `status`: `test_archivos_minimos.py`, `test_factura_internacional.py`, `test_integridad.py`, `test_listados_paginados.py` y `test_registro_envio.py`;
  - `test_contratos.py` y `test_listados_paginados.py` esperan la redirección del alta al listado.
- **Datos demo:** `seed_db.py` crea tres contratos con `status="ACTIVE"` explícito (persona moral, persona física e internacional) y sin documentos.

## Goals / Non-Goals

**Goals:**
- Los documentos de un contrato viven en el contrato. El Administrador configura cuáles se piden sin despliegue.
- Ningún contrato se factura sin su contrato firmado: la activación lo exige, y DOC-005 lo verifica en cada factura editable.
- Una sola definición del contrato completo para el expediente, el listado, la activación y DOC-005.
- "Contrato" deja de pedirse en el expediente del proveedor, sin perder los documentos ya cargados.
- Las tres configuraciones de documentos quedan agrupadas en el menú "Requisitos mínimos".

**Non-Goals:**
- Adjuntar archivos en el formulario de alta del contrato, o editar sus datos (más allá de la enmienda del monto).
- Transiciones que salgan de "Activo" (desactivar, cancelar, regresar a "Registrado").
- Formatos, vigencia o exigencias condicionales por requisito.
- Mover solos al contrato los documentos `SUPPLIER_CONTRACT` del expediente del proveedor.
- Acceso del Proveedor al expediente de su contrato, o un visor "Ver" de sus documentos.
- Cambiar los archivos de la factura (HU-04) o la orden de compra por factura (DOC-003).

## Decisions

### D1. Tabla `contract_document_types` con un solo nivel
Columnas: `id`, `code`, `name`, `description`, `is_system`, `is_active`, `requirement` (`DocumentRequirement`, por defecto `NOT_APPLICABLE`), `allows_multiple` y `created_at`. Restricciones:
- `uq_contract_document_types_code`;
- índice único funcional `uq_contract_document_types_name_lower` sobre `lower(name)`;
- `ck_contract_document_types_system_active` (`is_active OR NOT is_system`);
- `ck_contract_document_types_fixed_levels` (`code <> 'SIGNED_CONTRACT' OR requirement = 'REQUIRED'`);
- `enum_column(DocumentRequirement, "ck_contract_document_types_requirement")`.

*Alternativas:* agregar un "alcance" a `supplier_document_types`, o reutilizar `invoice_document_types`. Las dos mezclan una matriz por perfil u origen con un nivel único, y la RD-02 de HU-04 separa los catálogos. Una columna por origen como HU-04 no tiene fuente que la pida (RD-01); se agrega si negocio la pide.

### D2. `documents.contract_id`, dueño único
`contract_id` es una llave foránea `RESTRICT` a `contracts`, con índice. Un documento del contrato no lleva `supplier_id` ni `invoice_id`; lo garantiza `ck_documents_contract_owner` (`contract_id IS NULL OR (invoice_id IS NULL AND supplier_id IS NULL)`). Los archivos se guardan en `contracts/<id>/` con un nuevo `LocalFileStorage.save_contract_file()`.

*Alternativa:* llenar también `supplier_id`, como los documentos de factura. Las consultas de HU-21 (`expedient_documents`, la descarga del expediente y el motor) toman el expediente por `supplier_id` con `invoice_id IS NULL`, y el contrato firmado aparecería en "Otros documentos del expediente". Habría que agregar `contract_id IS NULL` en cada una, y una omisión no la detecta ninguna restricción.

### D3. Servicio `contract_requirements_service`
Replica la estructura de `supplier_requirements_service` sin el perfil. Parte de lectura:
- `catalog`, `sort_key`, `applicable`, `required` y `config_version` (SHA-256 de clave, nivel y estado activo);
- `contract_documents(db, contract_ids)`: documentos vigentes por contrato y por clave, en una consulta y como **lista**, porque un requisito puede tener varios archivos;
- `checklist(db, contract)`: filas con requisito, nivel y documentos, más "otros documentos";
- `pending_label` y `pending_requirements(db, contracts)` para el listado (D10).

Parte de escritura:
- `CONFIG_LOCK_KEY = 22_2200_0001`;
- `save_requirements`, con campos `requirement__<code>`;
- `create_type`, `update_type` y `set_active`, con los mensajes de HU-21;
- `applicable_type`, `upload` (D6) y `activate` (D7).

Reutiliza `parse_requirement`, `INVALID_REQUIREMENT`, `audit` y la base de validadores de nombre y descripción de `app/schemas`. Los esquemas nuevos son `ContractDocumentTypeUpdate` (nombre y descripción) y `ContractDocumentTypeCreate` (además, nivel y `allows_multiple`).

*Alternativa:* un servicio genérico para HU-21 y HU-22. Las dimensiones difieren (tres perfiles frente a nivel único con varios archivos); la abstracción costaría más que la repetición. Es el mismo criterio que el D4 de HU-21.

### D4. Estatus `REGISTERED`
- `ContractStatus.REGISTERED` y `CONTRACT_STATUS_LABELS` ("Registrado", "Activo", "Inactivo").
- `Contract.status` toma `REGISTERED` por defecto. `create_contract` lo asigna explícitamente.
- La migración amplía el `CHECK` del estatus y no toca filas existentes (RD-09).
- `invoices.py` y SUP-002 no cambian: ya exigen `ACTIVE`.

*Alternativa:* usar `INACTIVE` como "por activar". Confunde un contrato pendiente con uno dado de baja (P-07).

### D5. Niveles fijos con el patrón de HU-04
- **Constantes:** `FIXED_CONTRACT_REQUIREMENTS = {"SIGNED_CONTRACT": REQUIRED}` con su motivo "Todo contrato activo tiene su contrato firmado". `FIXED_SUPPLIER_REQUIREMENTS = {"SUPPLIER_CONTRACT": {perfil: NOT_APPLICABLE …}}` con el motivo "Se carga en cada contrato".
- **Al guardar:** en las dos pantallas, un nivel fijo ausente del formulario se ignora; uno presente y distinto responde 409 ("Contrato tiene un nivel fijo" y "Contrato tiene un nivel fijo para <plural del perfil>", con `REQUIREMENT_PROFILE_PLURALS`).
- **Pantalla:** la celda muestra el nivel con candado y el motivo, sin selector.
- **Base de datos:** el `CHECK` de D1 y `ck_supplier_document_types_fixed_levels` (`code <> 'SUPPLIER_CONTRACT' OR` los tres niveles en `NOT_APPLICABLE`).

*Alternativa:* sin niveles fijos, como el D12 de HU-21. Aquí un error sí rompe algo: contratos activos sin respaldo, o el contrato firmado de vuelta en el expediente del proveedor.

### D6. Carga y reemplazo
`POST /contracts/{contract_id}/documents` (`Administrador`, CSRF) recibe `document_type`, `upload` y, opcional, `replaces_document_id`.
- **Antes de escribir el archivo:**
  - 404 si el contrato no existe; 409 si no está "Registrado" ni "Activo";
  - `applicable_type()` responde 400 "El documento no aplica a este contrato";
  - si viene `replaces_document_id`, debe ser un documento vigente del mismo tipo y del mismo contrato, o 400 "El documento a reemplazar no corresponde a este requisito".
- **Reemplazo:** con `allows_multiple = false` se reemplaza el vigente del tipo, si existe; con `true`, sólo el indicado. El reemplazado queda `is_current = false` y el nuevo guarda `replaced_document_id`.
- **Registro:** auditoría `CONTRACT_DOCUMENT_UPLOADED` o `CONTRACT_DOCUMENT_REPLACED` (`new = {"type", "contract_id"}`) y `log_upload(..., contract_id=…)`.

`allows_multiple` se fija al crear el requisito y no se edita: al pasar de varios a uno quedarían varios vigentes sin una regla para elegir. Si P-04 cambia la orden de compra a un solo archivo, se ajusta la siembra antes de desplegar.

### D7. Activación
`POST /contracts/{contract_id}/activate` (`Administrador`, CSRF) ejecuta en una transacción:
1. `SELECT … FOR UPDATE` del contrato;
2. si no está `REGISTERED`, 409 "Sólo se puede activar un contrato Registrado";
3. si su proveedor no está `ACTIVE`, 409 "No se activó el contrato: el proveedor no está autorizado";
4. pendientes con la configuración vigente leída en la misma transacción; si hay, 409 "No se activó el contrato: faltan requisitos obligatorios (<nombres>)";
5. `status = ACTIVE`, `updated_at`/`updated_by`, auditoría `CONTRACT_STATUS_CHANGED` y redirección a `/contracts/{id}?ok=activated`.

Las respuestas 409 vuelven a mostrar el expediente con el mensaje, sin cambios ni auditoría.

*Alternativas:* activar solo al completar los requisitos (la solicitud pide "querer activarlo", y el Administrador puede esperar la firma o el inicio de la vigencia) o activación masiva desde el listado (no lo pide la solicitud).

### D8. DOC-005 con los requisitos del contrato
`document_rules()` deja de recibir `contract_available: bool` y recibe `contract_pending: list[str] | None` (`None` si la factura no tiene contrato). `validation_engine` lo calcula con `contract_requirements_service.pending_names(db, invoice.contract)`.
- `None` → `FAIL` "Falta contrato/anexo";
- lista vacía → `PASS` "Contrato/anexo disponible";
- con nombres → `FAIL` "Faltan documentos del contrato: <nombres>".

La severidad sigue en `ERROR`. Los documentos de la factura no cuentan (RD-13). Las facturas fuera de los estados editables conservan sus resultados, como hoy.

### D9. Expediente del contrato y descarga
- **`GET /contracts/{contract_id}`:** PMO y Administrador; 403 para Proveedor y 404 si no existe.
- **Contenido:** datos (proveedor con liga a su expediente y su estatus), panel "Requisitos del contrato", "Otros documentos del contrato", historial de enmiendas de solo lectura y, para el Administrador, el formulario de carga y la sección de activación.
- **Formulario de carga:** el selector "Reemplaza a" sólo se ofrece para requisitos con varios archivos. Sin JavaScript, el servidor ignora un `replaces_document_id` vacío.
- **Descarga:** `GET /contracts/{contract_id}/documents/{document_id}/download` con las mismas reglas que `download_supplier_document`, comprobando `doc.contract_id == contract_id`.
- **Avisos:** `?ok=created` muestra "Contrato creado. Cargue sus requisitos para activarlo." y `?ok=activated` muestra "Contrato activado".

### D10. Listado sin N+1
`_contracts_page` agrega, sobre los contratos de la página, una consulta de documentos vigentes (`contract_id IN (…)`) y una del catálogo (`pending_requirements`). Muestra:
- el estatus con `CONTRACT_STATUS_LABELS` y clases distintas por estatus;
- la columna "Requisitos" ("Completos" o "Faltan N");
- el proyecto con liga al expediente.

### D11. Diálogo de activación
Nuevo `app/static/js/contract_activate.js`, con el patrón de `supplier_authorize.js`:
- formulario `#activate-form` con `data-confirm`;
- modal Bootstrap con el texto pintado con `textContent`;
- sin JavaScript, el formulario se envía sin confirmación.

El modal se agrega a `contracts/detail.html`. No hay diálogos nativos ni scripts en línea (CSP `default-src 'self'`).

*Alternativa:* generalizar `supplier_authorize.js`. Mezcla la selección masiva del listado de proveedores con una acción individual; el script nuevo es corto.

### D12. Menú "Requisitos mínimos"
En `base.html`, bajo un `nav-label` "Requisitos mínimos":
- "Archivos de factura" (`/admin/required-documents`);
- "Alta de proveedor" (`/admin/supplier-requirements`);
- "Alta de contrato" (`/admin/contract-requirements`).

Los títulos de las páginas y sus rutas no cambian. Las especificaciones Playwright de HU-04 y HU-21 que navegan por el texto del menú se ajustan.

*Alternativa:* una sola página con pestañas. Mezcla tres rutas, tres huellas y tres suites de pruebas sin ganancia funcional.

### D13. Migración `0017_contract_document_types`
Posterior a `0016_supplier_document_types`.
- **Upgrade:**
  1. crea `contract_document_types` y siembra `SIGNED_CONTRACT`, `CONTRACT_PURCHASE_ORDER` y `CONTRACT_ANNEXES` en ese orden;
  2. agrega `documents.contract_id`, su índice, su llave foránea y `ck_documents_contract_owner`;
  3. reemplaza el `CHECK` de `contracts.status` para admitir `REGISTERED`;
  4. pone `SUPPLIER_CONTRACT` en `NOT_APPLICABLE` en sus tres niveles y agrega `ck_supplier_document_types_fixed_levels`.

  No cambia el estatus de ningún contrato ni ningún documento.
- **Downgrade:** lanza `NotImplementedError` si hay contratos `REGISTERED`, documentos con `contract_id` o requisitos del Administrador. Si no, revierte en orden inverso y regresa `SUPPLIER_CONTRACT` a Opcional · Opcional · No aplica.

`alembic check` debe quedar sin diferencias.

*Alternativas:* editar `0016` para no sembrar `SUPPLIER_CONTRACT` (prohibido por "Una revisión por cambio de modelo", y sus documentos se mostrarían con la clave cruda) o borrar la fila (dejaría sin nombre a los documentos ya cargados).

### D14. Datos demo
`seed_db.py` carga un documento `SIGNED_CONTRACT` en cada uno de los tres contratos demo, que siguen `ACTIVE`. `add_document` recibe `contract_id` y guarda en `contracts/<id>/` sin `supplier_id`. Así DOC-005 resulta `PASS` y las 10 facturas demo conservan su resultado.

### D15. Pruebas
- **Nuevo `tests/test_requisitos_contrato.py`:** un escenario por requisito de las specs, incluidos permisos, CSRF, concurrencia de la configuración, reemplazo con uno y varios archivos, activación con sus tres rechazos, el listado y DOC-005.
- **Helper en `conftest.py`:** `active_contract(supplier, **overrides)` crea un contrato `ACTIVE` con su contrato firmado. Sustituye los `Contract(...)` sin estatus de `test_archivos_minimos.py`, `test_factura_internacional.py`, `test_integridad.py`, `test_listados_paginados.py` y `test_registro_envio.py`.
- **Ajustes:**
  - `test_contratos.py` y `test_listados_paginados.py`: redirección del alta al expediente;
  - `test_requisitos_alta.py`: "Contrato" ya no se ofrece, y su candado;
  - `test_migraciones.py`: tabla nueva en `DOMAIN_TABLES`, upgrade sobre contratos y documentos existentes, y downgrade;
  - `test_integridad.py`, `test_observabilidad.py` y `test_permissions.py`.
- **Configuración compartida:** las pruebas que la modifican restauran los niveles, porque la base es compartida por la sesión.
- **Playwright:**
  - ajuste del menú en `05-HU-04-archivos-minimos.spec.ts` y `19-HU-21-requisitos-alta.spec.ts`;
  - nueva `20-HU-22-requisitos-contrato.spec.ts` y su entrada en `hu-catalogo.json`.

## Risks / Trade-offs

- [Contratos activos existentes sin documentos: DOC-005 `FAIL` bloquea el envío de sus facturas editables] → Los datos demo cargan el contrato (D14). En un ambiente con contratos reales, el listado los marca con "Faltan 1" y la carga funciona sobre contratos activos. Si negocio no acepta el bloqueo (P-06), DOC-005 se despliega como `WARNING` durante la transición; es un cambio de una línea en `document_rules`.
- [Pruebas y fixtures que crean contratos sin estatus nacen "Registrado"] → Helper `active_contract` (D15). Ruff no lo detecta, pero los fallos de SUP-002 y del alta de factura sí aparecen en pytest.
- [Un proveedor "Registrado" con su contrato listo no puede facturar] → El expediente del contrato dice por qué y liga al proveedor (D9). Si negocio no quiere la condición (P-05), se quita el paso 3 de D7.
- [La configuración cambia entre que el Administrador ve el checklist completo y activa] → La activación decide con la configuración leída en su transacción y responde 409 con lo que falta.
- [El proveedor sigue cargando "Contrato" y "Anexo del contrato" en cada factura] → No afecta DOC-005 (RD-13); sólo duplica archivos hasta que se responda P-02 desde Archivos de factura.
- [El menú cambia de texto] → Las especificaciones Playwright que navegan por el menú se ajustan en este change (D12).

## Migration Plan

1. Con `requisitos-alta-proveedor` ya archivado, aplicar `0017_contract_document_types` (`alembic upgrade head`): crea el catálogo, agrega `documents.contract_id` y fija `SUPPLIER_CONTRACT`. No cambia contratos ni documentos.
2. En la demo, `scripts/reset_demo.py` recrea los contratos con su contrato firmado (D14).
3. En un ambiente con contratos reales, antes de abrir la funcionalidad, el Administrador revisa la columna "Requisitos" del listado de contratos. Carga el contrato firmado de los activos marcados con "Faltan 1", o negocio decide P-06.
4. **Rollback:** desplegar la versión anterior y `alembic downgrade 0016_supplier_document_types`. Si ya hay contratos "Registrado", documentos de contrato o requisitos del Administrador, el downgrade se detiene (D13); se respalda y se decide manualmente.

## Open Questions

Preguntas de negocio de la sección 5.3 de la HU. Ninguna bloquea la implementación.

- **P-01:** ¿la Propuesta económica pasa también al contrato? Valor aplicado: se queda en el alta del proveedor.
- **P-02:** ¿se dejan de ofrecer "Contrato" y "Anexo del contrato" en cada factura? Valor aplicado: sin cambios; se resuelve en Archivos de factura sin código.
- **P-03:** ¿la orden de compra del contrato sustituye a la de cada factura? Valor aplicado: no.
- **P-04:** ¿la orden de compra admite varios archivos? Valor aplicado: sí.
- **P-05:** ¿activar exige proveedor "Autorizado"? Valor aplicado: sí.
- **P-06:** ¿se bloquean las facturas de contratos activos sin documentos? Valor aplicado: sí (DOC-005 `ERROR`).
- **P-07:** ¿hace falta desactivar un contrato o regresarlo a "Registrado"? Valor aplicado: no.
- **P-08:** ¿el Proveedor ve los documentos de su contrato? Valor aplicado: no.
