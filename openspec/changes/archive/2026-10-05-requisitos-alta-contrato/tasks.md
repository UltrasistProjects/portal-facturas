> Todas las rutas son relativas a la raíz de la PoC (`PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress-V1/PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress/`). Cada grupo termina con `ruff` limpio y con la suite verde sobre PostgreSQL (`DOCKER_CONTEXT=default docker compose up -d --wait db`). Requisito previo: `requisitos-alta-proveedor` archivado (sus requisitos ya están en `openspec/specs`).

## 1. Constantes, modelo, migración y fixtures

- [x] 1.1 `app/core/constants.py`:
  - `ContractStatus.REGISTERED` y `CONTRACT_STATUS_LABELS` ("Registrado", "Activo", "Inactivo") (D4);
  - `FIXED_CONTRACT_REQUIREMENTS` y su motivo "Todo contrato activo tiene su contrato firmado";
  - `FIXED_SUPPLIER_REQUIREMENTS` para `SUPPLIER_CONTRACT` (No aplica en los tres perfiles) y su motivo "Se carga en cada contrato" (D5).
- [x] 1.2 `app/models/__init__.py`:
  - modelo `ContractDocumentType` (D1), con `uq_contract_document_types_code`, el índice único funcional `uq_contract_document_types_name_lower`, `ck_contract_document_types_system_active`, `ck_contract_document_types_fixed_levels` y `enum_column(DocumentRequirement, "ck_contract_document_types_requirement")`;
  - `Document.contract_id` (`restrict("contracts.id")`, con índice) y `ck_documents_contract_owner` (D2);
  - `Contract.status` por defecto `REGISTERED`;
  - `ck_supplier_document_types_fixed_levels` en `SupplierDocumentType`.

  Añadir el modelo a `__all__` y actualizar el docstring de `InvoiceDocumentType`, que menciona los catálogos que comparten `documents.document_type`.
- [x] 1.3 Revisión `alembic/versions/0017_contract_document_types.py`, conforme a D13:
  - upgrade: tabla y siembra de los 3 requisitos; `documents.contract_id` con su llave foránea, índice y `CHECK`; `CHECK` de `contracts.status` con `REGISTERED`; `SUPPLIER_CONTRACT` en No aplica con su `CHECK`;
  - downgrade con `NotImplementedError` si hay contratos `REGISTERED`, documentos con `contract_id` o requisitos `REQ_CONTRATO_%`.

  Verificar `alembic check` sin diferencias.
- [x] 1.4 `tests/conftest.py`: helpers `contract_document(db, contract_id, code)` y `active_contract(db, supplier_id, **values)`, que crea en la sesión recibida un contrato `ACTIVE` con un documento `SIGNED_CONTRACT` vigente (D15). Sustituyen los `Contract(...)` de los proveedores internacionales de `test_archivos_minimos.py` y `test_factura_internacional.py`, que facturan contra su contrato. Los de `test_integridad.py` y `test_listados_paginados.py` no dependen del estatus, y el de `test_registro_envio.py` ya es `INACTIVE` a propósito.
- [x] 1.5 `scripts/seed_db.py` (D14): `add_document` acepta `contract_id` y guarda en `contracts/<id>/` sin `supplier_id`. Cargar un `SIGNED_CONTRACT` en cada uno de los tres contratos demo, que siguen `ACTIVE`.
- [x] 1.6 Pruebas en `tests/test_integridad.py` (spec `integridad-datos`):
  - `contracts.status = 'PENDIENTE'` rechazado;
  - `contract_document_types.requirement = 'MANDATORY'` rechazado;
  - `SIGNED_CONTRACT` en `OPTIONAL` rechazado;
  - requisito del sistema desactivado rechazado;
  - `ANEXOS` repetido con otra capitalización rechazado;
  - `SUPPLIER_CONTRACT` en `OPTIONAL` rechazado;
  - documento con `contract_id` e `invoice_id` rechazado;
  - borrado de un contrato con documentos rechazado.
- [x] 1.7 Pruebas en `tests/test_migraciones.py`:
  - añadir `contract_document_types` a `DOMAIN_TABLES`;
  - desde `0016`, con contratos `ACTIVE` y documentos `SUPPLIER_CONTRACT`, el upgrade deja los 3 requisitos sembrados, los contratos `ACTIVE`, `SUPPLIER_CONTRACT` en No aplica y los documentos con su `document_type`;
  - el downgrade sin datos nuevos funciona y regresa `SUPPLIER_CONTRACT` a Opcional · Opcional · No aplica;
  - con un contrato `REGISTERED`, un documento de contrato o un requisito del Administrador, el downgrade lanza `NotImplementedError`.

## 2. Servicio de requisitos del contrato

- [x] 2.1 `app/schemas/__init__.py`: `ContractDocumentTypeUpdate` (nombre y descripción, sobre la base común de validadores de HU-21) y `ContractDocumentTypeCreate` (además `requirement` con `parse_requirement`, por defecto `NOT_APPLICABLE`, y `allows_multiple`, por defecto `false`).
- [x] 2.2 `app/services/file_service.py`: `LocalFileStorage.save_contract_file(contract_id, upload)` sobre `_save("contracts", …)`.
- [x] 2.3 `app/services/contract_requirements_service.py`, parte de lectura (D3):
  - `catalog`, `sort_key`, `applicable` y `required`;
  - `config_version` (clave, nivel y estado activo);
  - `contract_documents(db, contract_ids)`: documentos vigentes con `contract_id`, como listas por clave;
  - `checklist(db, contract)`: filas con requisito, nivel y documentos, más "otros documentos";
  - `pending_names(db, contract)`, `pending_label` ("Falta 1 requisito obligatorio", "Faltan N requisitos obligatorios", "Requisitos del contrato completos") y `pending_requirements(db, contracts)` en dos consultas;
  - `applicable_type(db, code)` con 400 "El documento no aplica a este contrato".
- [x] 2.4 Parte de escritura (D3, D5):
  - `CONFIG_LOCK_KEY = 22_2200_0001` y `pg_advisory_xact_lock`;
  - `save_requirements` con campos `requirement__<code>`: huella (409); nivel fijo de `SIGNED_CONTRACT` ignorado si falta y 409 "Contrato tiene un nivel fijo" si difiere; 400 "Nivel de exigencia inválido"; "Sin cambios" sin auditoría;
  - `create_type` con clave `REQ_CONTRATO_<id>` tras el `flush`, `update_type` y `set_active`;
  - 409 para requisitos del sistema y nombres repetidos, traduciendo también la violación del índice de nombre;
  - auditoría `CONTRACT_REQUIREMENTS_UPDATED`, `CONTRACT_DOCUMENT_TYPE_CREATED`, `CONTRACT_DOCUMENT_TYPE_UPDATED` y `CONTRACT_DOCUMENT_TYPE_STATUS_CHANGED`.
- [x] 2.5 Pruebas unitarias del servicio en `tests/test_requisitos_contrato.py`:
  - catálogo inicial (3 requisitos, nombres en español);
  - requisitos que aplican y obligatorios con la configuración inicial;
  - varios archivos vigentes cumplen un requisito;
  - un documento de un requisito que dejó de aplicar sólo aparece en "otros documentos";
  - un documento "Contrato" de factura (HU-04) no cumple el requisito del contrato.

## 3. Contratos: alta, expediente, carga y descarga

- [x] 3.1 `create_contract` en `app/routers/contracts.py`: asigna `REGISTERED` y redirige a `/contracts/{id}?ok=created` (spec `listados-paginados`). Ajustar `test_contratos.py` y `test_listados_paginados.py`.
- [x] 3.2 `GET /contracts/{contract_id}` y `app/templates/contracts/detail.html` (D9):
  - datos, proveedor con liga y estatus, y estatus del contrato;
  - panel "Requisitos del contrato" con aviso de faltantes y "Otros documentos del contrato";
  - historial de enmiendas;
  - avisos `created` y `activated`;
  - 403 para Proveedor y 404 si no existe.
- [x] 3.3 `POST /contracts/{contract_id}/documents` (D6): permisos, CSRF y estatus "Registrado" o "Activo"; validaciones antes de escribir; reemplazo según `allows_multiple` y `replaces_document_id`; auditoría `CONTRACT_DOCUMENT_UPLOADED` o `CONTRACT_DOCUMENT_REPLACED`; `log_upload(..., contract_id=…)`. Formulario de carga con el selector "Reemplaza a" sólo para requisitos con varios archivos.
- [x] 3.4 `GET /contracts/{contract_id}/documents/{document_id}/download`, con las reglas de `download_supplier_document` y la verificación de `contract_id`.
- [x] 3.5 Pruebas de los escenarios de "Estatus del contrato", "Expediente del contrato" y "Carga de documentos del contrato":
  - permisos de PMO y Proveedor;
  - documento de otro contrato y tipo que no aplica, sin escribir en `storage/`;
  - reemplazo con uno y con varios archivos;
  - anexo en un contrato activo;
  - contrato "Registrado" no ofrecido al facturar.

  Prueba en `tests/test_observabilidad.py` del evento `document.uploaded` con `contract_id`.

## 4. Activación

- [x] 4.1 `contract_requirements_service.activate(db, contract_id, user_id)` (D7): bloqueo `FOR UPDATE`; las tres verificaciones con sus mensajes 409; `ACTIVE` con `updated_at`/`updated_by`; auditoría `CONTRACT_STATUS_CHANGED`.
- [x] 4.2 `POST /contracts/{contract_id}/activate` en `app/routers/contracts.py`: `Administrador` y CSRF; el 409 vuelve a mostrar el expediente con el mensaje; el éxito redirige con `ok=activated`.
- [x] 4.3 Sección de activación en `contracts/detail.html`, para el Administrador y con el contrato "Registrado":
  - botón con `data-confirm`;
  - deshabilitado con "Autorice al proveedor para activar el contrato" (con liga) o con "Cargue los requisitos obligatorios para activar".

  Nuevo `app/static/js/contract_activate.js` con el modal (D11).
- [x] 4.4 Pruebas de "Activación del contrato":
  - activación;
  - botón deshabilitado por requisitos y por proveedor;
  - petición manipulada;
  - requisito agregado entre la vista y la activación;
  - contrato ya activo sin auditoría;
  - PMO con 403;
  - auditoría `CONTRACT_STATUS_CHANGED`.

## 5. Listado de contratos

- [x] 5.1 `_contracts_page` y `contracts/list.html` (D10): estatus con `CONTRACT_STATUS_LABELS` y una clase por estatus; columna "Requisitos" con `pending_requirements`; proyecto con liga al expediente.
- [x] 5.2 Pruebas: contrato por activar con "Faltan 1"; contrato activo sin documentos con "Faltan 1"; número de consultas del listado independiente del número de contratos de la página.

## 6. DOC-005

- [x] 6.1 `app/rules/document_rules.py` y `app/services/validation_engine.py` (D8): `contract_pending` en lugar de `contract_available`, con los tres resultados y sus mensajes.
- [x] 6.2 Pruebas de "Contrato y anexos disponibles según los requisitos del contrato": factura demo A-CORRECTA en `PASS`; contrato activo sin contrato firmado en `FAIL` y envío bloqueado; requisito obligatorio agregado después de la activación; "Contrato" cargado en la factura que no cuenta. Revisar que las pruebas de `motor-validacion` sigan en verde con el helper de 1.4.

## 7. "Contrato" fuera del alta del proveedor

- [x] 7.1 `supplier_requirements_service.save_requirements` (D5): ignora los niveles de `SUPPLIER_CONTRACT` que faltan y responde 409 "Contrato tiene un nivel fijo para <plural del perfil>" si alguno difiere de No aplica.
- [x] 7.2 `admin/supplier_requirements.html`: la fila "Contrato" muestra "No aplica" con candado en las tres columnas y el motivo "Se carga en cada contrato", sin selectores.
- [x] 7.3 Pruebas en `tests/test_requisitos_alta.py` (y en `tests/test_datos_proveedor.py`, que usaba `SUPPLIER_CONTRACT` como ejemplo de documento opcional):
  - "Contrato" ya no se ofrece a persona moral ni física;
  - `SUPPLIER_CONTRACT` enviado al expediente responde 400;
  - candado en la pantalla;
  - petición manipulada responde 409;
  - un documento `SUPPLIER_CONTRACT` previo aparece en "Otros documentos del expediente".

## 8. Pantalla de administración y menú

- [x] 8.1 `app/routers/admin.py`: `GET` y `POST /admin/contract-requirements`, `POST /admin/contract-requirements/types`, `POST /admin/contract-requirements/types/{type_id}` y `POST /admin/contract-requirements/types/{type_id}/status`, sólo para `Administrador` y con CSRF; avisos "Configuración guardada" y "Sin cambios".
- [x] 8.2 `app/templates/admin/contract_requirements.html`:
  - un `<form>` con un selector por requisito activo, "Varios archivos" como texto, el candado de "Contrato" y la huella oculta;
  - formularios de alta (nivel preseleccionado en "No aplica" y "Admite varios archivos" en "No") y edición;
  - sección "Requisitos inactivos".
- [x] 8.3 `app/templates/base.html` (D12): `nav-label` "Requisitos mínimos" con "Archivos de factura", "Alta de proveedor" y "Alta de contrato".
- [x] 8.4 Pruebas de la spec `requisitos-alta-contrato`:
  - PMO y Proveedor con 403;
  - CSRF;
  - menú para Administrador y no para PMO;
  - hacer obligatoria la orden de compra y dejar de pedir los anexos;
  - candado y petición manipulada sobre el Contrato;
  - sin cambios y nivel inválido;
  - alta, nombre repetido, desactivación y reactivación, y requisito del sistema;
  - concurrencia;
  - auditoría y operaciones rechazadas sin auditoría.

  Añadir las rutas nuevas a `tests/test_permissions.py`.

## 9. Suite Playwright de HUs

- [x] 9.1 Ajustar la navegación por menú de `tests/hu/specs/05-HU-04-archivos-minimos.spec.ts` y `19-HU-21-requisitos-alta.spec.ts`. Los specs navegan por URL: sólo cambia el texto de los pasos ("Requisitos mínimos › Archivos de factura" y "› Alta de proveedor"). HU-04 corrió en verde; HU-21 no se corrió contra el portal de desarrollo porque autoriza un proveedor y enviaría credenciales por el SMTP real del `.env`.
- [x] 9.2 Nueva `tests/hu/specs/20-HU-22-requisitos-contrato.spec.ts`:
  - configuración y candado;
  - alta de un contrato que llega "Registrado" a su expediente;
  - activación deshabilitada;
  - carga del contrato y dos anexos;
  - activación con el diálogo;
  - el contrato ofrecido al proveedor al registrar una factura.

  Con su entrada en `hu-catalogo.json` y sus capturas de evidencia (`evidencias/HU-22/`, PASS). Usa al proveedor demo persona física: HU-12 exige que `proveedor1` tenga un solo contrato activo. `EVIDENCIA-PRUEBAS-HUs.pdf` no se regeneró: requiere la corrida completa con `MAIL_BACKEND=file`.

## 10. Documentación y cierre

- [x] 10.1 `README.md`:
  - sección "Requisitos del contrato" (pantalla, niveles, requisitos del Administrador);
  - estatus "Registrado" y activación;
  - DOC-005 según los documentos del contrato;
  - "Contrato" fuera del alta del proveedor;
  - nota de despliegue de P-06.
- [x] 10.2 `python scripts/check.py` en verde: ruff, formato, `alembic check`, pytest con cobertura ≥ 93 % y `pip-audit`.
- [x] 10.3 `reset_demo` reproduce el resultado de las 10 facturas demo. Los tres contratos demo muestran "Activo" y "Requisitos del contrato completos", y DOC-005 resulta `PASS`. Verificado con el seed de la base de pruebas (`test_facturas_demo_con_su_contrato_completo`, `test_contratos_demo_con_su_contrato_firmado` y las pruebas de demo existentes). `reset_demo` no se ejecutó sobre la base de desarrollo por su defecto conocido con el historial de contraseñas de Keycloak; esa base se respaldó (`backups/20261005-173101`), se migró a `0017` y se cargó el contrato firmado de los tres contratos demo con `add_signed_contract` del seed.
- [x] 10.4 Prueba manual en el navegador contra el portal en marcha: la especificación HU-22 de la suite (configuración y candado, alta "Registrado", activación deshabilitada, carga del contrato y dos anexos, activación con el diálogo y contrato ofrecido al proveedor) y una revisión visual del candado de "Contrato" en Alta de proveedor y del listado de contratos. Los cambios de nivel, el alta, edición, desactivación y reactivación de requisitos, el proveedor sin autorizar y el reemplazo de un anexo se cubren con pruebas HTTP, para no dejar requisitos del Administrador en la base de desarrollo (impedirían el downgrade de `0017`):
  - cambiar niveles; crear, editar, desactivar y reactivar un requisito;
  - crear un contrato e intentar activarlo sin contrato firmado y con el proveedor sin autorizar;
  - cargar el contrato y dos anexos y reemplazar uno;
  - activarlo y registrar una factura con él.
- [x] 10.5 `openspec validate requisitos-alta-contrato --strict` sin errores.
