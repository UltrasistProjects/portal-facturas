> Todas las rutas son relativas a la raíz de la PoC (`PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress-V1/PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress/`). Cada grupo termina con `ruff` limpio y con la suite verde sobre PostgreSQL (`docker compose up -d --wait db`).

## 1. Constantes, modelo y migración

- [x] 1.1 `app/core/constants.py`:
  - `DocumentType.FOREIGN_INVOICE`;
  - enumeración `DocumentRequirement` (`REQUIRED`, `OPTIONAL`, `NOT_APPLICABLE`) con `DOCUMENT_REQUIREMENT_LABELS` ("Obligatorio", "Opcional", "No aplica");
  - `FORMAT_EXTENSIONS` (D7);
  - `FIXED_REQUIREMENTS`: clave → niveles fijos por origen y motivo (D3).
- [x] 1.2 `app/models/__init__.py`: modelo `InvoiceDocumentType` (D1) con:
  - `UniqueConstraint` sobre `code`;
  - índice único funcional sobre `lower(name)`;
  - `CheckConstraint` de formatos, de tipo del sistema activo y de niveles fijos;
  - `enum_column(DocumentRequirement)` en los dos niveles.

  Añadirlo a `__all__`.
- [x] 1.3 Revisión `alembic/versions/0003_invoice_document_types.py` (D10): tabla, restricciones y siembra de los 10 tipos del sistema en el orden de la HU. El downgrade borra la tabla, o lanza `NotImplementedError` si hay tipos soporte o documentos `FOREIGN_INVOICE`/`SOPORTE_%`. Verificar `alembic check` sin diferencias, incluido el índice funcional (riesgo documentado en el design).
- [x] 1.4 Pruebas en `tests/test_integridad.py` (spec `integridad-datos`):
  - nivel `MANDATORY` rechazado;
  - nivel fijo de `INVOICE_XML` cambiado por SQL rechazado;
  - `PURCHASE_ORDER` desactivado por SQL rechazado;
  - `ORDEN DE COMPRA` repetido rechazado;
  - `formats` vacío o `{DOCX}` rechazado.
- [x] 1.5 Pruebas en `tests/test_migraciones.py`:
  - añadir `invoice_document_types` a `DOMAIN_TABLES`;
  - desde `0002` con una factura y sus documentos, el upgrade deja los 10 tipos activos con sus valores iniciales y los documentos conservan su `document_type`;
  - el downgrade de `0003` sin datos nuevos funciona;
  - con un tipo soporte, o con un documento `FOREIGN_INVOICE`, lanza `NotImplementedError`.

## 2. Servicio de archivos mínimos

- [x] 2.1 `app/schemas/__init__.py`: `DocumentTypeCreate` y `DocumentTypeUpdate`.
  - Nombre normalizado (recorte y espacios internos colapsados) de 3 a 80 caracteres.
  - Descripción de hasta 300 caracteres; vacía equivale a `NULL`.
  - `formats` con al menos un elemento ("Seleccione al menos un formato"), todos de `FORMAT_EXTENSIONS`.
  - En el alta, niveles de `DocumentRequirement`, por defecto `NOT_APPLICABLE`.
  - Mensajes en español mediante `validation_message`.
- [x] 2.2 `app/services/document_requirements_service.py`, parte de lectura (D14, D15):
  - `catalog`, `offered_types`, `required_types` y `type_names`;
  - la función única de orden;
  - `config_version` (D8);
  - `formats_label` ("PDF, PNG, JPEG, TXT");
  - `extension_allowed(type, filename)`.
- [x] 2.3 Escritura: `save_requirements` (D17), `create_type` (D9), `update_type` y `set_active` (D18).
  - Todas toman `pg_advisory_xact_lock(CONFIG_LOCK_KEY)` al empezar (D8).
  - Rechazan con `InvalidInputError` (400) o `BusinessRuleError` (409) y los mensajes exactos de la spec.
  - Traducen la violación de `uq_invoice_document_types_name_lower` a 409 "Ya existe un tipo de documento con ese nombre".
  - Auditan `INVOICE_DOCUMENT_REQUIREMENTS_UPDATED`, `INVOICE_DOCUMENT_TYPE_CREATED`, `INVOICE_DOCUMENT_TYPE_UPDATED` o `INVOICE_DOCUMENT_TYPE_STATUS_CHANGED` sólo cuando hay cambios.
- [x] 2.4 Prueba que verifica que la unión de las extensiones de `FORMAT_EXTENSIONS` es igual a `ALLOWED_EXTENSIONS` de `file_service.py`.

## 3. Motor de validación

- [x] 3.1 `app/rules/base.py`: helper `not_applicable(...)` que produce `NOT_APPLICABLE` con el mensaje dado y conserva la severidad (D14).
- [x] 3.2 `app/rules/document_rules.py` (D4):
  - DOC-001 a DOC-004 y DOC-008 según los tipos exigidos para el origen, con mensajes "<nombre> presente", "Falta <nombre>" o "No requerido para proveedores nacionales|internacionales";
  - DOC-009 por cada otro tipo exigido, con `source_document = code`;
  - DOC-005 a DOC-007 sin cambios.
- [x] 3.3 `app/services/validation_engine.py`: obtener `required_types(db, invoice.supplier.origin)` en cada prevalidación y pasarlo a `document_rules` (D5).
- [x] 3.4 Pruebas unitarias de `document_rules` en `tests/test_archivos_minimos.py`, sin base de datos:
  - nacional sin Vo.Bo.;
  - internacional sin Invoice;
  - orden de compra opcional, que no descuenta del score según `calculate_score`;
  - tipo soporte obligatorio (DOC-009).
- [x] 3.5 Verificar con `scripts/reset_demo.py` (o con la base de pruebas) que las 10 facturas demo conservan estado y score, y que D-SIN-VOBO sigue en `REQUIRES_CORRECTION` por DOC-004.

## 4. Carga documental y detalle de la factura

- [x] 4.1 `app/routers/invoices.py`, `documents_page`: pasar a la plantilla los tipos ofrecidos para el origen del proveedor, los documentos vigentes por clave y el conteo de obligatorios pendientes.
- [x] 4.2 `app/routers/invoices.py`, `upload_document`: aplicar los pasos 4 y 5 de D16 antes de `LocalFileStorage`, con errores 400 que vuelven a pintar `invoices/documents.html`. Retirar la validación contra `DocumentType`.
- [x] 4.3 `app/templates/invoices/documents.html`:
  - selector con nombre y formatos de los tipos ofrecidos;
  - checklist con obligatorios primero y opcionales después, cada uno con nivel, formatos, descripción y estado (documento vigente o "Pendiente");
  - aviso "Falta 1 archivo obligatorio", "Faltan N archivos obligatorios" o "Archivos obligatorios completos";
  - `accept` del archivo con la unión de extensiones de los tipos ofrecidos.
- [x] 4.4 `app/routers/invoices.py` e `invoices/detail.html`: nombre del catálogo de cada documento (`type_names`), con la clave como respaldo (D19).
- [x] 4.5 Pruebas (spec `archivos-minimos-factura`), con el fixture de restauración de D20 y un proveedor internacional activo creado en la base:
  - tipos ofrecidos a un proveedor nacional y a uno internacional;
  - nombres en español en la carga y en el detalle;
  - tipo que no aplica, tipo inexistente y formato no admitido: 400, con el mensaje de la spec y sin archivos nuevos en `storage/`;
  - checklist con "Faltan 2 archivos obligatorios" y con "Archivos obligatorios completos";
  - documento de un tipo que dejó de aplicar: no se lista en la carga y sí en el detalle, con descarga.
- [x] 4.6 Ajustar `tests/test_archivos.py` si alguna carga usa un formato que su tipo ya no admite. Cubrir el formato por tipo desde el endpoint.

## 5. Pantalla de administración

- [x] 5.1 `app/routers/admin.py`: `GET /admin/required-documents` y los POST de la matriz, alta, edición y estado.
  - Todas las rutas usan `require_roles(Role.ADMIN)` y `validate_csrf`.
  - Los errores vuelven a pintar la página con 400 o 409, y el éxito redirige con 303 y `?saved=1` o `?unchanged=1` (D11).
  - Un tipo inexistente responde 404.
- [x] 5.2 `app/templates/admin/required_documents.html` (D11):
  - matriz con `config_version` oculto, niveles fijos como texto con candado y motivo, y selectores en las celdas editables;
  - formulario de alta, edición de tipos soporte dentro de `<details>` y botones Desactivar o Reactivar;
  - sección "Tipos inactivos".

  Sin JavaScript nuevo. Estilos en `app/static/css/app.css` si hacen falta.
- [x] 5.3 `app/templates/base.html`: enlace "Archivos mínimos" en Administración.
- [x] 5.4 Pruebas de acceso en `tests/test_permissions.py` y `tests/test_archivos_minimos.py`:
  - `INTERNAL` y `PROVIDER` reciben 403 en el GET y en los cuatro POST;
  - un POST sin CSRF o con uno inválido recibe 403;
  - en ningún caso cambia la configuración ni se agrega auditoría.
- [x] 5.5 Pruebas de la matriz:
  - exigir "Contrato" al internacional;
  - "Orden de compra" opcional para el nacional;
  - guardar sin cambios muestra "Sin cambios" y no audita;
  - un nivel `MANDATORY` responde 400 sin guardar;
  - un nivel fijo manipulado responde 409 con su mensaje;
  - niveles fijos con candado y motivo, sin `<select>`;
  - dos Administradores: 409 "La configuración cambió mientras la editaba. Recargue la página." y sólo persiste el primero;
  - auditoría con `old_value` y `new_value` por tipo y origen.
- [x] 5.6 Pruebas de los tipos soporte:
  - alta de "Reporte de horas" con clave `SOPORTE_<id>`, auditada;
  - nombre repetido "  orden   de COMPRA " responde 409;
  - sin formatos responde 400;
  - cambio de formatos: se acepta `horas.png` y los documentos anteriores no cambian;
  - desactivación y reactivación: no se ofrece ni se exige, los documentos siguen en el detalle y el nivel vuelve;
  - edición o desactivación de un tipo del sistema responde 409;
  - las operaciones rechazadas no auditan.
- [x] 5.7 Pruebas del motor con la configuración (spec `motor-validacion`):
  - factura `PREVALIDATED` sin contrato: sigue `PREVALIDATED` y se envía a revisión después de hacer obligatorio "Contrato". Usar una factura nueva del proveedor 1, no las del seed;
  - factura en `REQUIRES_CORRECTION`: al volver a prevalidar aparece DOC-009 "Falta Contrato";
  - factura internacional: DOC-008 `FAIL`/`CRITICAL` y DOC-001/DOC-002 `NOT_APPLICABLE`;
  - tipo soporte obligatorio: DOC-009 con `source_document = SOPORTE_<id>`.

## 6. Documentación y cierre

- [x] 6.1 `README.md`:
  - reglas `DOC-001..009`;
  - sección "Configuración de archivos mínimos" (pantalla, niveles, niveles fijos y tipos soporte);
  - limitación de las facturas internacionales hasta HU-16;
  - procedimiento de la prueba manual con un proveedor internacional (T-01 del design).
- [x] 6.2 `python scripts/check.py` en verde: ruff, formato, `alembic check`, pytest con cobertura ≥ 93 % y `pip-audit`.
- [x] 6.3 Prueba manual con `run`: cambiar niveles; crear, editar, desactivar y reactivar un tipo soporte; cargar documentos como proveedor nacional e internacional; prevalidar.
- [x] 6.4 `openspec validate archivos-minimos-por-tipo-proveedor --strict` sin errores.
