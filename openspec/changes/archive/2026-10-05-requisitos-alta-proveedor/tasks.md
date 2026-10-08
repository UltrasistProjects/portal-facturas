> Todas las rutas son relativas a la raíz de la PoC (`PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress-V1/PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress/`). Cada grupo termina con `ruff` limpio y con la suite verde sobre PostgreSQL (`DOCKER_CONTEXT=default docker compose up -d --wait db`).

## 1. Constantes, modelo y migración

- [x] 1.1 `app/core/constants.py`:
  - enumeración `RequirementProfile` (`PERSONA_MORAL`, `PERSONA_FISICA`, `INTERNATIONAL`) con etiquetas ("Persona moral", "Persona física", "Internacional") y plurales para los mensajes (D2);
  - conservar `QUOTATION_DOCUMENT` y `DATED_SUPPLIER_DOCUMENTS`;
  - no eliminar todavía las constantes del expediente: se quitan en 3.5, cuando ya no tengan usos.
- [x] 1.2 `app/models/__init__.py`: modelo `SupplierDocumentType` (D1) con:
  - `UniqueConstraint` sobre `code` (`uq_supplier_document_types_code`);
  - índice único funcional `uq_supplier_document_types_name_lower` sobre `lower(name)`;
  - `CheckConstraint("is_active OR NOT is_system")` (`ck_supplier_document_types_system_active`);
  - `enum_column(DocumentRequirement, "ck_supplier_document_types_<columna>")` en los tres niveles, por defecto `NOT_APPLICABLE`.

  Añadirlo a `__all__`. Actualizar el docstring de `InvoiceDocumentType`, que menciona las claves del Anexo A.
- [x] 1.3 Revisión `alembic/versions/0016_supplier_document_types.py` (D11): tabla, restricciones y siembra de los 13 requisitos del sistema en el orden y con los valores de la sección 6.3 de la HU (incluido `POWER_OF_ATTORNEY`).
  - El downgrade borra la tabla, o lanza `NotImplementedError` si hay requisitos del Administrador o documentos `POWER_OF_ATTORNEY`/`REQUISITO_%`.
  - Verificar `alembic check` sin diferencias, incluido el índice funcional.
- [x] 1.4 Pruebas en `tests/test_integridad.py` (spec `integridad-datos`):
  - `persona_moral_requirement = 'MANDATORY'` rechazado;
  - `TAX_STATUS` desactivado por SQL rechazado;
  - `PODERES` repetido con otra capitalización rechazado.
- [x] 1.5 Pruebas en `tests/test_migraciones.py`:
  - añadir `supplier_document_types` a `DOMAIN_TABLES`;
  - desde `0015` con un proveedor y documentos de expediente, el upgrade deja los 13 requisitos activos con sus valores iniciales, el proveedor conserva su estatus y los documentos su `document_type`;
  - el downgrade de `0016` sin datos nuevos funciona;
  - con un requisito del Administrador, o con un documento `POWER_OF_ATTORNEY`, lanza `NotImplementedError`.

## 2. Servicio de requisitos de alta

- [x] 2.1 `app/schemas/__init__.py` (D4):
  - extraer a una base común los validadores de nombre (3 a 80 caracteres, espacios colapsados) y descripción (hasta 300, vacía equivale a `NULL`) de `DocumentTypeUpdate`; `DocumentTypeUpdate` hereda de ella y agrega `formats`, sin cambiar su comportamiento;
  - `SupplierDocumentTypeUpdate` (nombre y descripción) y `SupplierDocumentTypeCreate` (además, los tres niveles con `parse_requirement`, por defecto `NOT_APPLICABLE`).
- [x] 2.2 `app/services/supplier_requirements_service.py`, parte de lectura (D2, D3):
  - `profile(supplier)`, `catalog`, `sort_key` (sistema por id de siembra, luego Administrador por nombre) y `requirement(type, profile)`;
  - `applicable` y `exigible`, con la regla de `ECONOMIC_PROPOSAL` cuando `economic_proposal` y su nivel no es `NOT_APPLICABLE`;
  - consulta de los documentos del expediente: `supplier_id`, `invoice_id IS NULL`, `is_current`;
  - `checklist(db, supplier)`: filas con requisito, nivel efectivo, documento, advertencia de vigencia (93 días) y nota; más los "otros documentos";
  - `pending(...)` y `pending_label` ("Falta 1 requisito obligatorio", "Faltan N requisitos obligatorios", "Requisitos de alta completos");
  - `pending_counts(db, suppliers)` en dos consultas (D8);
  - `config_version`.
- [x] 2.3 Parte de escritura (D4):
  - `CONFIG_LOCK_KEY = 21_2100_0001` y `pg_advisory_xact_lock`;
  - `save_requirements`: huella (409), niveles recibidos para cada requisito activo y perfil (400 "Nivel de exigencia inválido"), cambios en una transacción, "Sin cambios" sin auditoría;
  - `create_type` con clave `REQUISITO_<id>` tras el `flush`, `update_type` y `set_active`;
  - 409 para requisitos del sistema ("Los requisitos del sistema no se pueden editar ni desactivar") y para nombre repetido ("Ya existe un requisito con ese nombre"), traduciendo también la violación de `uq_supplier_document_types_name_lower`;
  - auditoría `SUPPLIER_REQUIREMENTS_UPDATED`, `SUPPLIER_DOCUMENT_TYPE_CREATED`, `SUPPLIER_DOCUMENT_TYPE_UPDATED` y `SUPPLIER_DOCUMENT_TYPE_STATUS_CHANGED`, con claves `persona_moral`, `persona_fisica` e `international`.
- [x] 2.4 Pruebas unitarias del servicio en `tests/test_requisitos_alta.py`:
  - catálogo inicial (13 requisitos, nombres en español);
  - requisitos aplicables y exigibles de persona moral, persona física e internacional con la configuración inicial;
  - propuesta económica exigible por cotización;
  - documento de más de tres meses: advertencia y cuenta como cargado;
  - documento de un requisito que dejó de aplicar: sólo en "otros documentos";
  - un documento de factura con `supplier_id` no cumple un requisito.

## 3. Expediente, carga de documentos y SUP-003

- [x] 3.1 `app/routers/suppliers.py`, carga `POST /suppliers/{supplier_id}/documents` (D9): validar el tipo contra los requisitos aplicables antes de `save_supplier_file`; 400 "El documento no aplica a este proveedor". Permisos sin cambios.
- [x] 3.2 `_supplier_detail_page` y `suppliers/detail.html` (D13):
  - panel "Requisitos de alta": exigibles primero, estado, nota, advertencia de vigencia, aviso de faltantes o "Sin requisitos de alta configurados para <tipo>";
  - "Otros documentos del expediente" con descarga;
  - selector de carga con los aplicables y los exigibles marcados "(obligatorio)".
- [x] 3.3 `app/services/validation_engine.py` y `app/rules/supplier_rules.py` (D10):
  - el motor obtiene el checklist y los pendientes del servicio (sólo expediente);
  - SUP-003: `PASS` "Expediente mínimo disponible"; `FAIL` "Expediente del proveedor incompleto. Pendientes: …" en el orden del catálogo; `NOT_APPLICABLE` con `NOT_FOR_INTERNATIONAL` sólo si el internacional no tiene requisitos obligatorios;
  - SUP-004 sin cambios.
- [x] 3.4 `scripts/seed_db.py` (D14): cargar a cada proveedor demo un documento por requisito aplicable según el catálogo, incluido "Poderes".
- [x] 3.5 Eliminar `supplier_requirement_status()`, `_requirement()`, `SUPPLIER_REQUIREMENTS`, `SUPPLIER_DOCUMENT_LABELS`, `OPTIONAL_SUPPLIER_DOCUMENTS` y `ALTERNATIVE_SUPPLIER_DOCUMENTS`, y sus usos en código, scripts y pruebas.
- [x] 3.6 Pruebas (spec `requisitos-alta-proveedor`, checklist y carga):
  - requisitos pendientes: "Faltan 4 requisitos obligatorios" con los cuatro pendientes;
  - requisitos completos;
  - `INCORPORATION_ACT` a una persona física: 400 y sin archivo en `storage/`;
  - internacional con la configuración inicial: "Sin requisitos de alta configurados para proveedores internacionales".

  Ajustar `test_datos_proveedor.py` y `test_archivos.py` al checklist y al mensaje nuevo.
- [x] 3.7 Pruebas del motor (spec `motor-validacion`):
  - A-CORRECTA: SUP-003 `PASS` y resultados iguales a antes;
  - requisito del Administrador obligatorio agregado después: SUP-003 `FAIL` con el pendiente, el envío no procede y el proveedor sigue autorizado;
  - persona moral sin opinión de cumplimiento: SUP-003 `PASS`;
  - internacional con "Estado de cuenta bancario" obligatorio: SUP-003 `FAIL`; con la configuración inicial, `NOT_APPLICABLE`.

  Ajustar `test_factura_internacional.py`. Restaurar la configuración al terminar cada prueba.

## 4. Autorización

- [x] 4.1 `app/services/supplier_access_service.py` (D5, D6):
  - verificación de requisitos después de omitir a los no `REGISTERED` y antes del conflicto de correo;
  - catálogo una vez y documentos de los seleccionados en una consulta;
  - grupo `requirements_incomplete` en `AuthorizationResult`, en `SUPPLIER_BULK_AUTHORIZED`, en el evento `supplier.bulk_authorize` y en `AuthorizationSummary`, con los nombres de los pendientes recalculados al mostrar el resumen.
- [x] 4.2 Listado `suppliers/list.html` y `_suppliers_page` (D8):
  - columna "Requisitos de alta" ("Completos" o "Faltan N");
  - casilla sólo para "Registrado" con requisitos completos; "Faltan N requisitos" con liga al expediente para los demás "Registrado";
  - grupo "No autorizado: faltan requisitos de alta (<nombres>)" en el resumen.
- [x] 4.3 Autorización desde el expediente (D7):
  - formulario con `supplier_ids` oculto hacia `POST /suppliers/authorize` en el panel "Acceso al portal", sólo para el Administrador y proveedores "Registrado";
  - botón deshabilitado con "Cargue los requisitos obligatorios para autorizar" si hay pendientes;
  - `app/static/js/supplier_authorize.js` generalizado para el modal del listado y el del expediente (texto desde un atributo `data-`), sin scripts ni estilos en línea.
- [x] 4.4 Fixture o helper en `tests/conftest.py` que carga los requisitos exigibles de un proveedor. Usarlo en `test_acceso_proveedores.py` y `test_observabilidad.py` donde hoy se autoriza un proveedor recién registrado.
- [x] 4.5 Pruebas (spec `acceso-proveedores` y `observabilidad`):
  - 2 proveedores, uno sin "Poderes": uno "Autorizado", el otro sigue "Registrado" sin usuario local, sin cuenta en Keycloak y sin correo;
  - resumen con "No autorizado: faltan requisitos de alta (Poderes, Estado de cuenta bancario)";
  - auditoría con `requirements_incomplete` y sin `SUPPLIER_STATUS_CHANGED`/`USER_CREATED` para él;
  - log `supplier.bulk_authorize` con `requirements_incomplete = 1` y sin nombres de requisitos;
  - listado: sin casilla y "Faltan 3 requisitos" para un "Registrado" incompleto; filtro por estatus;
  - expediente: botón habilitado con requisitos completos, deshabilitado con pendientes, ausente para PMO, Proveedor y autorizados;
  - petición manipulada con un proveedor incompleto: sigue "Registrado".

## 5. Pantalla de administración

- [x] 5.1 `app/routers/admin.py`: rutas `GET /admin/supplier-requirements`, `POST /admin/supplier-requirements`, `POST /admin/supplier-requirements/types`, `POST /admin/supplier-requirements/types/{type_id}` y `POST /admin/supplier-requirements/types/{type_id}/status`, exclusivas del `Administrador`, con CSRF y mensajes "Configuración guardada" / "Sin cambios".
- [x] 5.2 `app/templates/admin/supplier_requirements.html` (D13): matriz en un solo `<form>` (campos `<perfil>__<code>`) con `config_version` oculto; formularios de alta y edición; sección "Requisitos inactivos". Sin JavaScript nuevo.
- [x] 5.3 `app/templates/base.html`: enlace "Requisitos de alta" en Administración, después de "Archivos mínimos".
- [x] 5.4 Pruebas de permisos (`tests/test_permissions.py` y `test_requisitos_alta.py`): PMO y Proveedor reciben 403 en la página y en las cuatro operaciones; sin token CSRF, 403; el menú sólo aparece al Administrador.
- [x] 5.5 Pruebas de la matriz:
  - "Poderes" a Opcional en Persona moral: "Configuración guardada" y el expediente lo muestra "Opcional · Pendiente";
  - "Estado de cuenta bancario" Obligatorio en Internacional: el expediente internacional lo pide y la autorización lo exige;
  - guardar sin cambios: "Sin cambios" y sin auditoría;
  - `MANDATORY` con otros cambios válidos: 400 y nada se guarda;
  - huella vieja: 409 "La configuración cambió mientras la editaba. Recargue la página.";
  - auditoría `{"POWER_OF_ATTORNEY": {"persona_moral": "REQUIRED"}}` → `"OPTIONAL"`.
- [x] 5.6 Pruebas de los requisitos del Administrador:
  - alta de "Declaración de ISR por retenciones de salarios" con clave `REQUISITO_<id>`, auditada, y pedida en el expediente de una persona moral;
  - nombre "  cédula   FISCAL ": 409;
  - desactivación y reactivación: no se pide ni se exige, los documentos siguen descargables y el nivel vuelve;
  - edición o desactivación de "Cédula fiscal": 409;
  - las operaciones rechazadas no auditan.

## 6. Suite Playwright de HUs

- [x] 6.1 `tests/hu/lib/portal.ts`: helper que carga desde el expediente los requisitos exigibles de un proveedor; `tests/hu/fixtures/herramientas.py` genera los PDF de ejemplo.
- [x] 6.2 Ajustar `02-HU-02-autorizacion-masiva.spec.ts` para cargar los requisitos antes de autorizar. HU-03 y HU-10 usan los proveedores que autoriza HU-02 y no requieren cambios.
- [x] 6.3 Nueva `tests/hu/specs/19-HU-21-requisitos-alta.spec.ts` con evidencia:
  - configuración;
  - alta de una persona moral;
  - autorización bloqueada desde el listado y desde el expediente;
  - carga de requisitos;
  - autorización exitosa.

  Agregar HU-21 a `hu-catalogo.json`. Ejecutar con `MAIL_BACKEND=file` para no enviar correos reales.

## 7. Documentación y cierre

- [x] 7.1 `README.md`:
  - sección "Requisitos de alta del proveedor" (pantalla, niveles, requisitos del Administrador);
  - la autorización exige los requisitos y puede hacerse desde el expediente;
  - SUP-003 según la configuración;
  - nota de despliegue de P-07.
- [x] 7.2 `python scripts/check.py` en verde: ruff, formato, `alembic check`, pytest con cobertura ≥ 93 % y `pip-audit`.
- [x] 7.3 `reset_demo` reproduce el resultado de las 10 facturas demo; los dos proveedores demo muestran "Requisitos de alta completos". Verificado con el seed de la base de pruebas (`test_seed_con_el_modelo_de_estatus_del_ers`, `test_facturas_demo_sin_fallas_de_expediente`, `test_requisitos_del_expediente_por_tipo_de_persona`). `reset_demo` no se ejecutó sobre la base de desarrollo por su defecto conocido con el historial de contraseñas de Keycloak; esa base se respaldó, se migró y se le cargó "Poderes" a `proveedor1`.
- [x] 7.4 Prueba manual con `run` (navegador contra el portal en marcha y la especificación HU-21 de la suite; el alta, edición, desactivación y reactivación de requisitos del Administrador se cubren con pruebas HTTP para no dejar requisitos en la base de desarrollo, que impedirían el downgrade de `0016`). Encontró y corrigió que el formulario "Nuevo requisito" preseleccionaba "Obligatorio":
  - cambiar niveles;
  - crear, editar, desactivar y reactivar un requisito;
  - dar de alta una persona moral;
  - intentar autorizarla con pendientes desde el listado y desde el expediente;
  - completar los requisitos y autorizarla.
- [x] 7.5 `openspec validate requisitos-alta-proveedor --strict` sin errores.
