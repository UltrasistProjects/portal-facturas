## Context

La HU-04 (`docs/stories/new/HU-04 Definicion de archivos requeridos por tipo de proveedor.md`) pide que el Administrador defina, por origen del proveedor, qué archivos de la factura son obligatorios. Sus reglas derivadas (RD-01 a RD-10) no están confirmadas por negocio, pero sus preguntas abiertas sólo cambian valores iniciales que el Administrador puede ajustar.

Estado actual del PoC (rutas relativas a la raíz de la PoC):

- **Tipos de documento:** enumeración fija `DocumentType` (9 valores) en `app/core/constants.py`. Las plantillas derivan el nombre de la clave (`t.value.replace('_',' ').title()`, que produce "Invoice Xml") en `invoices/documents.html` y `invoices/detail.html`.
- **Reglas documentales:** `app/rules/document_rules.py` fija DOC-001 (`CRITICAL`) y DOC-002 a DOC-004 (`ERROR`) para todos los proveedores. Las reglas son funciones puras: reciben datos ya cargados y devuelven `ValidationOutcome`. El helper `outcome()` de `app/rules/base.py` sólo produce `PASS`, `FAIL`, `WARNING` o `NOT_EVALUATED`.
- **Score:** `calculate_score` ya excluye `NOT_APPLICABLE` y `NOT_EVALUATED` del denominador.
- **Carga documental** (`POST /invoices/{id}/documents`), en este orden:
  1. CSRF;
  2. visibilidad de la factura;
  3. `ensure_editable` (409);
  4. tipo dentro de `DocumentType` (400 "Tipo documental invalido");
  5. `LocalFileStorage._save`, que valida extensión global, tamaño y contenido antes de escribir.

  Cualquier extensión permitida sirve para cualquier tipo.
- **Configuración:** `/admin/rules` es de sólo lectura sobre `BUSINESS_RULES`. No existe ninguna configuración persistente editable.
- **Proveedores:** `suppliers.origin` (`NATIONAL`/`INTERNATIONAL`) viene de HU-01 (`0002_supplier_bulk_import`). Los proveedores demo son nacionales. El alta individual sólo crea nacionales y la carga masiva deja a los internacionales en `REGISTERED`, así que hoy no existe en la interfaz un proveedor internacional activo.
- **Pruebas:**
  - una base PostgreSQL temporal por sesión, compartida por todas las pruebas y con el seed cargado;
  - `scripts/check.py` ejecuta ruff, `alembic check` (Alembic 1.16.5), pytest con cobertura ≥ 93 % y `pip-audit`.

## Goals / Non-Goals

**Goals:**
- Primera configuración persistente del portal: el catálogo y los niveles por origen viven en la base de datos, y el Administrador los cambia sin despliegue.
- Un proveedor internacional puede cumplir la parte documental: no se le exige el XML ni el PDF del CFDI, y sí el Invoice.
- Sin cambios de resultado para los proveedores nacionales con la configuración inicial. Las 10 facturas demo conservan su score y su estado.
- Niveles fijos garantizados en la pantalla, en el servidor y en la base de datos.

**Non-Goals:**
- Expediente del proveedor (Anexo A), SUP-003/SUP-004 y el expediente del internacional (P-02, HU-16).
- Reglas XML, SUP y de contrato para facturas internacionales: hasta HU-16, una factura internacional no llega a `PREVALIDATED`.
- Exigencias condicionales o por contrato, proyecto o tipo de persona. Tamaño máximo por tipo.
- Revalidar al enviar a revisión (HU-13).
- JavaScript nuevo y pruebas de interfaz en navegador: el comportamiento visual se verifica manualmente.

## Decisions

### D1. Una tabla `invoice_document_types` con una columna de nivel por origen
Columnas:
- `id`;
- `code` (`VARCHAR(60)`, igual que `documents.document_type`, único);
- `name` (`VARCHAR(80)`) y `description` (`VARCHAR(300)`, `NULL`);
- `formats` (`VARCHAR(4)[]`);
- `is_system` y `is_active`;
- `national_requirement` e `international_requirement` (`enum_column(DocumentRequirement)`);
- `created_at` y `updated_at`.

`enum_column` recibe un nombre opcional para su `CHECK`: el `CHECK` de una enumeración se llama como la enumeración, y dos columnas de la misma tabla con `DocumentRequirement` chocarían. Se llaman `ck_invoice_document_types_national_requirement` y `ck_invoice_document_types_international_requirement`.

*Alternativas:*
- Tabla de requisitos (origen, tipo, nivel): con dos orígenes fijos añade uniones y filas ausentes que hay que interpretar.
- Constantes en código: el Administrador no podría cambiar nada sin un despliegue, que es justo lo que pide la HU.

### D2. Catálogo mixto: tipos del sistema y tipos soporte del Administrador
Los 10 tipos del sistema (`is_system = true`) llegan con la migración. El Administrador agrega tipos soporte. "Definir" los archivos incluye poder nombrar documentos que hoy no existen, como los soportes del Invoice extranjero (P-03).

*Alternativa:* catálogo cerrado. "Definir" quedaría reducido a elegir de una lista, y cada soporte nuevo exigiría un despliegue.

### D3. Niveles fijos en tres capas
1. **Pantalla:** texto con candado y motivo, sin `<select>`, así que el campo no se envía.
2. **Servidor:** si el formulario trae un nivel fijo distinto del fijo, responde 409 con "<nombre> tiene un nivel fijo para proveedores nacionales|internacionales". Si trae el mismo valor, se ignora.
3. **Base de datos:** `CHECK ck_invoice_document_types_fixed_levels`.

La lista de claves fijas y sus niveles vive en `app/core/constants.py` (`FIXED_REQUIREMENTS`), junto con el motivo que muestra la pantalla.

*Alternativa:* protegerlos sólo en la pantalla. Una petición manipulada o un `UPDATE` dejaría al Nacional sin XML y rompería RN-HU13-01.

### D4. Códigos de regla: DOC-001 a DOC-004 se conservan; DOC-008 y DOC-009 son nuevas
`document_rules` recorre un mapeo fijo de tipo a regla, código y severidad:
- `INVOICE_XML` → DOC-001, `CRITICAL`;
- `INVOICE_PDF` → DOC-002, `ERROR`;
- `PURCHASE_ORDER` → DOC-003, `ERROR`;
- `APPROVAL` → DOC-004, `ERROR`;
- `FOREIGN_INVOICE` → DOC-008, `CRITICAL`.

Cada una resulta `PASS`/`FAIL` si su tipo es Obligatorio para el origen, y `NOT_APPLICABLE` en otro caso. DOC-009 (`ERROR`) produce un resultado por cada otro tipo activo Obligatorio, con `source_document = code`.

El orden de los resultados es DOC-001 a DOC-007, DOC-008 y DOC-009 en el orden del catálogo (D15). DOC-005 a DOC-007 no cambian.

*Alternativas:*
- Una sola regla agregada: pierde el detalle por archivo y cambia el score.
- Renumerar todo: confunde los resultados históricos, el README y la guía de validación (caso "Documento faltante" con DOC-004).

### D5. La configuración se lee en cada prevalidación, sin caché
`run_validation` consulta el catálogo dentro de su transacción. Los `ValidationResult` guardados son la foto de lo exigido en ese momento. Una factura fuera de los estados editables no se vuelve a prevalidar (`ensure_prevalidatable`), así que conserva sus resultados (RD-08).

*Alternativa:* revalidar al enviar. Decidirlo le toca a HU-13, cuyo envío es "previa validación".

### D6. Sin llave foránea de `documents.document_type` al catálogo
La columna también guarda claves del expediente del Anexo A (`TAX_STATUS`, `SAT_OPINION`, etc.) en documentos de proveedor. La aplicación valida el tipo al cargar (D16).

*Alternativa:* llave foránea. Obligaría a meter el expediente del Anexo A en el catálogo de factura.

### D7. `formats` como arreglo con `CHECK`; el mapeo a extensiones vive en código
- **Restricción:** `CHECK (cardinality(formats) >= 1 AND formats <@ ARRAY['PDF','PNG','JPEG','XML','TXT']::varchar[])`.
- **Mapeo:** `FORMAT_EXTENSIONS = {"PDF": (".pdf",), "PNG": (".png",), "JPEG": (".jpg", ".jpeg"), "XML": (".xml",), "TXT": (".txt",)}` en `app/core/constants.py`. Una prueba verifica que la unión de sus extensiones es exactamente `ALLOWED_EXTENSIONS` de `file_service.py`, para que las dos listas no diverjan.
- **Mensaje de formatos:** los formatos se muestran en el orden de `FORMAT_EXTENSIONS` y separados por coma: "PDF, PNG, JPEG, TXT".

*Alternativas:*
- JSONB: no admite un `CHECK` sencillo.
- Tabla de formatos: sobredimensionada para cinco valores fijos.

### D8. Huella `config_version` y serialización de las escrituras
- **Cálculo:** `config_version` es el SHA-256 del JSON canónico de `[(code, national_requirement, international_requirement, is_active)]` de todos los tipos, ordenados por `code`. Viaja en un campo oculto del formulario de la matriz. Sin estado en el servidor, como `expected_sha256` en HU-01.
- **Bloqueo:** toda escritura de configuración (matriz, alta, edición y cambio de estado) toma primero `pg_advisory_xact_lock(CONFIG_LOCK_KEY)`, una constante del servicio. El bloqueo se libera al terminar la transacción. Así, dos guardados simultáneos no pueden calcular la misma huella antes de que el otro confirme, y un alta concurrente no se cuela entre la verificación y la actualización.

*Alternativas:*
- `SELECT … FOR UPDATE` sobre las filas: no bloquea las inserciones de tipos nuevos.
- Bloqueo pesimista en la pantalla: innecesario en una pantalla de uso ocasional.
- Última escritura gana: descartaría en silencio el cambio de otro Administrador.

### D9. Clave `SOPORTE_<id>` asignada tras el `flush`
Se inserta con una clave provisional (`SOPORTE_PENDIENTE_<uuid4 hex>`, 50 caracteres) y, tras el `flush`, se reemplaza por `SOPORTE_<id>` en la misma transacción, como el folio interno de la factura.

*Alternativa:* derivar la clave del nombre. Cambiaría al renombrar y choca con acentos y espacios.

### D10. Revisión Alembic `0003_invoice_document_types`
- **Upgrade:** crea la tabla con sus restricciones y siembra los 10 tipos del sistema con `op.bulk_insert`, en el orden de la sección 6.2 de la HU. Las restricciones son:
  - `uq_invoice_document_types_code`;
  - índice único funcional `uq_invoice_document_types_name_lower` sobre `lower(name)`;
  - `ck_invoice_document_types_formats`, `ck_invoice_document_types_system_active` y `ck_invoice_document_types_fixed_levels`;
  - los dos `CHECK` de enumeración que genera `enum_column`.
- **Downgrade:** lanza `NotImplementedError`, con un mensaje que remite a restaurar un respaldo, si hay tipos soporte o documentos `FOREIGN_INVOICE` o `SOPORTE_%`. En otro caso borra la tabla; la personalización de niveles se pierde y el código anterior vuelve a sus reglas fijas.

*Alternativa:* editar revisiones anteriores. Lo prohíbe la regla "Una revisión por cambio de modelo".

### D11. Pantalla sin JavaScript nuevo
`/admin/required-documents` usa formularios HTML normales, compatibles con la CSP `default-src 'self'`:
1. **Matriz:** un solo `<form>` con un `<select>` por celda editable. Los campos se llaman `national__<code>` e `international__<code>`.
2. **Alta de tipo soporte:** nombre, descripción, casillas de formatos y dos `<select>` preseleccionados en "No aplica".
3. **Tipos del Administrador:** un formulario de edición por tipo, dentro de un `<details>`, y un botón Desactivar o Reactivar.
4. **Tipos inactivos:** sección aparte.

Los errores vuelven a pintar la página con el mensaje y el código HTTP (400, 404 o 409), como `_users_page` en `admin.py`. El servicio lanza `InvalidInputError` (400), `NotFoundError` (404, nueva en `app/core/errors.py`) o `BusinessRuleError` (409). Un guardado correcto redirige con 303 a la misma página con `?ok=<clave>`: `saved` muestra "Configuración guardada", `unchanged` muestra "Sin cambios", y `created`, `updated` y `status` confirman las operaciones sobre tipos soporte.

*Alternativa:* guardado celda por celda con `fetch`. Más peticiones y auditoría fragmentada, sin ganancia para una pantalla de pocas filas.

### D12. `DocumentType` conserva sólo las claves que usa el código
La enumeración suma `FOREIGN_INVOICE` y sigue sirviendo al parser (`INVOICE_XML`), al seed y a `document_rules`. Nombres, descripciones, formatos y niveles viven sólo en la tabla.

*Alternativa:* duplicar nombres y formatos en constantes. Serían dos fuentes que se desincronizan.

### D13. Un patrón reutilizable de configuración persistente
La combinación de tabla, pantalla de administración, huella con bloqueo consultivo y auditoría con valores anterior y nuevo queda como patrón para HU-05, HU-06 y HU-08. No se generaliza todavía: una abstracción con un solo uso sería prematura.

### D14. Las reglas siguen siendo puras; el servicio carga la configuración
El nuevo `app/services/document_requirements_service.py` concentra el acceso al catálogo:
- `catalog(db)`: todos los tipos, en el orden de D15;
- `offered_types(db, origin)`: activos, Obligatorios u Opcionales para el origen;
- `required_types(db, origin)`: activos y Obligatorios para el origen;
- `type_names(db)`: diccionario de clave a nombre;
- `config_version(types)`;
- `save_requirements(...)`, `create_type(...)`, `update_type(...)` y `set_active(...)`, que validan, auditan y lanzan `BusinessRuleError` o `InvalidInputError` con los mensajes de la spec.

`run_validation` pasa a `document_rules(present, required, origin, processable, contract_available)` los tipos exigidos como objetos simples (clave y nombre). Así las reglas se prueban sin base de datos, como hoy.

`app/rules/base.py` suma el helper `not_applicable(code, category, severity, message, source_document)`. La severidad se conserva para que la matriz de evidencia muestre la severidad que tendría la regla. El score no cambia porque excluye `NOT_APPLICABLE`.

### D15. Orden del catálogo
Primero van los tipos del sistema, por `id`, que la siembra asigna en el orden de la sección 6.2 de la HU. Después los del Administrador, por `lower(name)`. Una sola función de orden en el servicio sirve a la matriz, al selector, al checklist y a DOC-009.

*Alternativa:* una columna `sort_order`. Nadie la edita en esta HU y sólo añadiría una restricción más.

### D16. Orden de las verificaciones al cargar un documento
1. CSRF.
2. Factura visible (404).
3. `ensure_editable` (409).
4. Tipo dentro de `offered_types` para el origen del proveedor de la factura (400 "El tipo de documento no aplica a esta factura"). Cubre tipos inexistentes, inactivos y No aplica.
5. Extensión del nombre original dentro de los formatos del tipo (400 "Formato no admitido para <nombre>. Formatos admitidos: <formatos>").
6. `LocalFileStorage` con sus verificaciones actuales de extensión global, tamaño y contenido.

Los pasos 4 y 5 ocurren antes de leer o escribir el archivo. Sus errores vuelven a pintar `invoices/documents.html` con HTTP 400, igual que hoy los errores de contenido, en lugar de la página genérica de error.

### D17. Reglas de validación de la matriz
El guardado sigue este orden:
1. Huella ausente o distinta: 409. Va primero porque una página vieja puede carecer de un tipo nuevo, y "Recargue la página" es más útil que "falta un nivel".
2. Algún nivel fuera de la enumeración, o falta el nivel de una celda editable de un tipo activo: 400 "Nivel de exigencia inválido".
3. Nivel fijo distinto del fijo: 409.
4. Si no hay diferencias, "Sin cambios" sin escribir ni auditar.
5. En otro caso, se actualizan las filas y se escribe un único registro `INVOICE_DOCUMENT_REQUIREMENTS_UPDATED` con los valores anterior y nuevo por tipo y origen.

Los campos de claves desconocidas o de tipos inactivos se ignoran: no se escriben, así que no hay nada que proteger.

### D18. Cambio de estado con destino explícito
`POST /admin/required-documents/types/{type_id}/status` recibe `active=true|false`, no un conmutador. Así, dos Administradores que pulsan Desactivar a la vez no reactivan el tipo por accidente. Si el tipo ya tiene ese estado, no hay cambio ni auditoría.

Otros casos:
- un tipo inexistente responde 404;
- un tipo del sistema responde 409.

Un tipo soporte desactivado conserva su nombre, así que un alta con el mismo nombre responde 409 "Ya existe un tipo de documento con ese nombre". Se reactiva en lugar de duplicarse.

### D19. Nombres en español en el detalle de la factura
`invoice_detail` pasa `type_names(db)` a la plantilla. Un documento cuyo tipo no esté en el catálogo muestra su clave como respaldo.

### D20. Pruebas aisladas de la configuración compartida
La base de pruebas es una sola por sesión. `tests/test_archivos_minimos.py` usa un fixture que:
1. guarda los niveles y el estado de los tipos del sistema;
2. al terminar, los restaura y borra los tipos soporte creados, sus documentos y sus resultados DOC-009.

Esto es posible porque no hay llave foránea, por D6. Las facturas internacionales de prueba se crean directamente en la base: un proveedor `INTERNATIONAL` activo con contrato y un usuario `PROVIDER`.

## Risks / Trade-offs

- **[Riesgo resuelto] `alembic check` reportaba una diferencia falsa en el índice funcional `lower(name)`** → con `Index(..., text("lower((name)::text)"))` en `__table_args__`, Alembic veía un borrado y una creación. El modelo declara el índice fuera de la clase con `func.lower(InvoiceDocumentType.name)`, la migración lo crea con `lower((name)::text)` y `alembic check` ya no reporta diferencias.
- **[Riesgo] El Administrador exige un archivo que los proveedores no tienen** → sus facturas quedan en "Requiere corrección". El checklist dice qué falta, el cambio es reversible y queda auditado.
- **[Riesgo] La configuración cambia con facturas en curso** → las editables se evalúan con la nueva configuración al volver a prevalidarse; las demás conservan su resultado (RD-08).
- **[Limitación] Las facturas internacionales siguen fallando las reglas XML y SUP-003 hasta HU-16** → se documenta en el README; esta HU sólo resuelve la parte documental.
- **[Riesgo] Un tipo con documentos cargados se desactiva o deja de aplicar** → los documentos se conservan y siguen descargables en el detalle (RD-10, D19).
- **[Cambio visible] Formatos por tipo para el proveedor nacional** → ya no se puede cargar un PDF como XML del CFDI. Es la corrección buscada. Los datos demo y las pruebas actuales usan combinaciones válidas; las cargas `.txt` de orden de compra y Vo.Bo. siguen admitidas.
- **[Riesgo] Cambian los mensajes de DOC-001 a DOC-004** ("Falta XML CFDI" pasa a "Falta XML del CFDI") → ninguna prueba ni lógica depende del texto; los resultados guardados conservan su mensaje histórico.
- **[Trade-off] Sin caché de la configuración** → una consulta adicional por prevalidación y por página de carga, despreciable frente al parseo de XML y PDF.

## Migration Plan

1. `alembic upgrade head` aplica `0003_invoice_document_types`: crea la tabla y siembra los 10 tipos. No toca `documents` ni `validation_results`.
2. Verificar con `scripts/reset_demo.py` que las 10 facturas demo conservan estado y score, y que D-SIN-VOBO sigue en `REQUIRES_CORRECTION` por DOC-004.
3. **Rollback:**
   - sin tipos soporte ni documentos `FOREIGN_INVOICE`/`SOPORTE_%`: `alembic downgrade 0002_supplier_bulk_import` y volver al código anterior;
   - con ellos: el downgrade se niega y se restaura un respaldo (`scripts/restore_backup.py`).

## Open Questions

Ninguna bloquea la implementación. P-01, P-03 y P-04 sólo cambian valores que el Administrador ajusta desde la pantalla, y P-02 afecta a otra HU.

- **P-01:** ¿el proveedor internacional debe entregar orden de compra y Vo.Bo. con cada Invoice? Mientras tanto: ambos Obligatorios (RD-06). Se ajusta en la pantalla o en la siembra.
- **P-02:** ¿qué expediente, equivalente al Anexo A, debe entregar el proveedor internacional? Fuera de HU-04; lo resuelve HU-16. Hasta entonces, SUP-003 aplica el Anexo A según el tipo de persona.
- **P-03:** ¿qué documentos soporte acompañan al Invoice extranjero? Se sabrá con los ejemplos acordados en la minuta. El Administrador los crea como tipos soporte, sin cambios de código.
- **P-04:** ¿los complementos de pago previos deben exigirse "cuando aplique"? Mientras tanto: Opcionales (RD-09). Una exigencia condicional requiere una HU nueva.
- **T-01 (técnica):** para la prueba manual con un proveedor internacional no existe hoy un camino en la interfaz, porque la carga masiva lo deja `REGISTERED` y la autorización es de HU-02. Propuesta: el README documenta el procedimiento (carga masiva y `UPDATE suppliers SET status = 'ACTIVE'`) y el seed no cambia, como pide la HU. Alternativa, si negocio la prefiere: agregar al seed un proveedor internacional demo, activo y con contrato.
