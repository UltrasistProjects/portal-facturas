## Context

La HU-21 (`docs/stories/new/HU-21 Requisitos de alta del proveedor.md`) pide parametrizar los documentos mínimos para dar de alta a un proveedor y exigirlos antes de autorizarlo. Sus reglas derivadas (RD-01 a RD-11) no están confirmadas por negocio, pero sus preguntas abiertas sólo cambian valores iniciales que el Administrador ajusta desde la pantalla.

Estado actual del PoC (rutas relativas a la raíz de la PoC):

- **Expediente del proveedor:** `SUPPLIER_REQUIREMENTS` en `app/core/constants.py` lista los documentos por tipo de persona (11 para moral, 8 para física), con nombres en `SUPPLIER_DOCUMENT_LABELS`. `supplier_requirement_status()` (`app/services/supplier_service.py`) arma una fila por documento con `present`, `expired`, `required` y `note`, y decide la obligatoriedad con `_requirement()`:
  - son opcionales fijos `SUPPLIER_CONTRACT`, `DUE_DILIGENCE` y `LOCATION`;
  - `ECONOMIC_PROPOSAL` es obligatoria si `Supplier.economic_proposal`;
  - `ADDRESS_PROOF` y `LEGAL_REP_ADDRESS_PROOF` son alternativos.
- **Consumidores de esa función:**
  - el expediente (`_supplier_detail_page` en `app/routers/suppliers.py`);
  - la carga `POST /suppliers/{supplier_id}/documents`, que valida el tipo con `supplier_requirement_status(supplier, [])` y responde 400 "Tipo de Anexo A invalido";
  - el motor (`app/services/validation_engine.py`), que la llama con **todos** los documentos de `supplier_id` (las facturas también guardan `supplier_id`) y pasa las filas a `supplier_rules()` para SUP-003 y SUP-004.
- **SUP-003/SUP-004:** `app/rules/supplier_rules.py`; para el internacional resultan `NOT_APPLICABLE` con `NOT_FOR_INTERNATIONAL`. Un `FAIL` de SUP-003 (`ERROR`) impide el envío (`submission_service`).
- **Autorización:** `supplier_access_service.authorize()` bloquea los proveedores seleccionados (`with_for_update`) y procesa cada uno en un punto de guardado:
  1. omite a quien no está `REGISTERED`;
  2. marca conflicto si su correo lo usa otro usuario;
  3. pasa a `ACTIVE`, crea usuario y cuenta de Keycloak;
  4. audita `SUPPLIER_BULK_AUTHORIZED` con listas de ids, confirma y envía credenciales.

  `authorization_summary()` reconstruye el resumen leyendo esas listas como enteros. El listado usa `supplier_authorize.js` para la selección y el modal de confirmación.
- **Patrón de configuración (HU-04):** `invoice_document_types` y `document_requirements_service.py`:
  - `sort_key` (sistema por id de siembra, luego Administrador por nombre);
  - `config_version` (SHA-256);
  - bloqueo consultivo `pg_advisory_xact_lock` con `CONFIG_LOCK_KEY = 4_0400_0001`;
  - `_flush` que traduce la unicidad a 409;
  - auditoría `old/new` por clave y origen;
  - `parse_requirement` e `INVALID_REQUIREMENT` en `app/schemas`.
- **Datos demo:** `scripts/seed_db.py` carga a los dos proveedores demo (moral y física, ambos `ACTIVE`) un documento por cada clave de `SUPPLIER_REQUIREMENTS`. No hay proveedores demo `REGISTERED`.
- **Pruebas:**
  - una base PostgreSQL temporal por sesión con el seed cargado;
  - `scripts/check.py` ejecuta ruff, `alembic check`, pytest con cobertura ≥ 93 % y `pip-audit`;
  - `tests/test_acceso_proveedores.py` y `tests/test_observabilidad.py` autorizan proveedores recién registrados;
  - la suite Playwright `tests/hu` también lo hace (HU-02, HU-03, HU-10).

## Goals / Non-Goals

**Goals:**
- El expediente del proveedor vive en la base de datos y el Administrador lo configura por tipo de proveedor sin despliegue.
- Ningún proveedor llega a "Autorizado" (ni recibe credenciales) con requisitos exigibles pendientes.
- Una sola definición del expediente mínimo para el checklist, el listado, la autorización y SUP-003.
- Las 10 facturas demo conservan su resultado; los proveedores demo quedan con requisitos completos.

**Non-Goals:**
- Adjuntar documentos en el alta o en la carga masiva; revisar su contenido; formatos por requisito.
- Exigencias condicionales configurables, salvo la propuesta económica existente.
- Bloquear la autorización por vigencia; cambiar SUP-004.
- Cambiar el estatus de proveedores ya autorizados; estatus "Inactivo".
- Avisos por correo de requisitos pendientes.

## Decisions

### D1. Tabla `supplier_document_types` con una columna de nivel por tipo de proveedor
Columnas:
- `id`;
- `code` (`VARCHAR(60)`, igual que `documents.document_type`, único: `uq_supplier_document_types_code`);
- `name` (`VARCHAR(80)`) y `description` (`VARCHAR(300)`, `NULL`);
- `is_system` y `is_active`, con `CHECK (is_active OR NOT is_system)` (`ck_supplier_document_types_system_active`);
- `persona_moral_requirement`, `persona_fisica_requirement` e `international_requirement`: `enum_column(DocumentRequirement, "ck_supplier_document_types_<columna>")`, con valor por defecto `NOT_APPLICABLE`;
- `created_at` y `updated_at`.

Índice único `uq_supplier_document_types_name_lower` sobre `lower(name)`.

*Alternativas:*
- Columnas nuevas en `invoice_document_types`: mezcla dos catálogos con dimensiones distintas (origen frente a tipo de persona) y la RD-02 de HU-04 los separa.
- Tabla (perfil, tipo, nivel): con tres perfiles fijos añade uniones y filas ausentes que hay que interpretar.

### D2. Tipo de proveedor como enumeración derivada
`RequirementProfile` (`PERSONA_MORAL`, `PERSONA_FISICA`, `INTERNATIONAL`) en `app/core/constants.py`, con etiquetas ("Persona moral", "Persona física", "Internacional") y plurales para los mensajes ("personas morales", "personas físicas", "proveedores internacionales"). Una función la deriva: `INTERNATIONAL` si `origin = INTERNATIONAL`; si no, según `supplier_type`. Las claves de la auditoría y de los campos de la matriz son `persona_moral`, `persona_fisica` e `international`.

*Alternativa:* el nombre `SupplierProfile`, que ya usa un esquema de `app/schemas`.

### D3. Servicio único `supplier_requirements_service`
Responsabilidades:
- **Lectura:** `catalog()`, `profile(supplier)`, `applicable(types, supplier)` (activos y no `NOT_APPLICABLE`) y `exigible(types, supplier)` (los `REQUIRED`, más `ECONOMIC_PROPOSAL` si `supplier.economic_proposal` y su nivel no es `NOT_APPLICABLE`).
- **Evaluación:** `checklist(db, supplier)` devuelve filas con requisito, nivel efectivo, documento vigente, advertencia de vigencia (`DATED_SUPPLIER_DOCUMENTS`, 93 días como hoy) y nota. También devuelve los "otros documentos": vigentes de tipos que no aplican. `pending(...)` devuelve los exigibles sin documento vigente.
- **Por página:** `pending_counts(db, suppliers)` para el listado.
- **Escritura:** `save_requirements`, `create_type`, `update_type` y `set_active`, con huella, bloqueo y auditoría.

Sólo cuentan los documentos del expediente: `supplier_id = X AND invoice_id IS NULL AND is_current`. Esto también corrige la consulta actual del motor, que incluía los documentos de las facturas.

Se eliminan `supplier_requirement_status()`, `_requirement()`, `SUPPLIER_REQUIREMENTS`, `SUPPLIER_DOCUMENT_LABELS`, `OPTIONAL_SUPPLIER_DOCUMENTS` y `ALTERNATIVE_SUPPLIER_DOCUMENTS`. Se conservan `QUOTATION_DOCUMENT` y `DATED_SUPPLIER_DOCUMENTS`, que son reglas por clave.

*Alternativa:* conservar las constantes para SUP-003 y usar la tabla sólo para autorizar. Serían dos definiciones del expediente mínimo que se contradicen en la misma pantalla.

### D4. Reutilizar el código de HU-04 sin generalizarlo
El servicio nuevo replica la estructura de `document_requirements_service` y reutiliza piezas existentes:
- `parse_requirement` e `INVALID_REQUIREMENT`;
- `violates`, `audit` y `DOCUMENT_REQUIREMENT_LABELS`;
- los validadores de nombre (3 a 80 caracteres, espacios colapsados) y descripción (hasta 300) de `DocumentTypeUpdate`: se extraen a una base común de la que heredan `DocumentTypeUpdate` (que agrega `formats`) y los nuevos `SupplierDocumentTypeUpdate` y `SupplierDocumentTypeCreate` (que agrega los tres niveles con `parse_requirement`). `document_type_message` formatea los errores de ambos.

Bloqueo consultivo propio: `CONFIG_LOCK_KEY = 21_2100_0001`, con la convención HU de las demás llaves. `sort_key` con el mismo criterio que HU-04: la migración siembra los requisitos en el orden del catálogo de la HU.

*Alternativa:* un módulo genérico de "catálogos de documentos configurables". Hay dos casos con dimensiones y reglas distintas (formatos y niveles fijos sólo en HU-04); la abstracción costaría más que la repetición.

### D5. Verificación de requisitos dentro de `authorize()`
En el ciclo por proveedor, después de omitir a los no `REGISTERED` y antes del conflicto de correo, `authorize()` calcula sus pendientes. Si tiene alguno, lo agrega a `outcome["requirements_incomplete"]` y continúa, sin punto de guardado porque no hay nada que revertir.

Lecturas:
- el catálogo, una vez por operación;
- los documentos vigentes del expediente de los seleccionados, en una consulta.

Ambas ocurren dentro de la transacción que ya bloquea las filas de `suppliers`. Un documento se carga y reemplaza en su propia transacción y nunca se borra, así que la lectura es estable para la decisión.

`AuthorizationResult`, `AuthorizationSummary`, el registro `SUPPLIER_BULK_AUTHORIZED` y el evento `supplier.bulk_authorize` suman el grupo `requirements_incomplete`.

*Alternativas:*
- Verificar en el router: la autorización masiva y la individual podrían divergir.
- Verificar después de Keycloak: crearía cuentas que habría que revertir.

### D6. Resumen: ids en la auditoría, pendientes recalculados
`requirements_incomplete` se guarda como lista de enteros, igual que las demás, así que `authorization_summary()` no cambia de forma. Al mostrar el resumen, los nombres de los pendientes se recalculan con `pending()`, igual que el estado del correo se lee de la bitácora (D5 de HU-02).

*Alternativa:* guardar los códigos pendientes en `new_value`. Cambia la forma que `authorization_summary()` lee como listas de enteros y fija nombres que el Administrador puede renombrar.

### D7. Autorización desde el expediente con el endpoint existente
El panel "Acceso al portal" de un proveedor `REGISTERED` muestra un `<form method="post" action="/suppliers/authorize">` con un `supplier_ids` oculto. Con requisitos completos, el botón abre el mismo modal de Bootstrap que el listado. Con pendientes, se muestra `disabled` con la explicación.

`supplier_authorize.js` se generaliza para servir a los dos formularios: el texto de confirmación se toma de un atributo `data-` del formulario. No hay scripts ni estilos en línea (CSP `default-src 'self'`, change `interfaz-sin-dialogos-nativos`). Tras confirmar, la respuesta es la misma redirección al listado con el resumen.

*Alternativas:*
- `POST /suppliers/{supplier_id}/authorize`: duplicaría reglas, auditoría y pruebas.
- Volver al expediente: requeriría un parámetro de retorno validado contra redirecciones abiertas, sin ganancia funcional.

### D8. Listado sin N+1
`_suppliers_page` ya pagina en SQL. Para la página se ejecutan dos consultas:
- el catálogo;
- los `(supplier_id, document_type)` vigentes del expediente de los proveedores de la página.

Con eso `pending_counts` calcula "Faltan N" por proveedor. La casilla de selección se pinta sólo para `REGISTERED` con 0 pendientes. Cumple la spec `listados-paginados`.

### D9. Validación del tipo al cargar
`POST /suppliers/{supplier_id}/documents` sustituye `allowed = {row["code"] for row in supplier_requirement_status(supplier, [])}` por los códigos aplicables al proveedor. Un tipo inexistente, inactivo o `NOT_APPLICABLE` responde 400 "El documento no aplica a este proveedor" antes de `save_supplier_file`, así que no se escribe el archivo. Los permisos actuales (Administrador o el propio Proveedor; PMO 403) no cambian.

### D10. SUP-003 con la configuración
`validation_engine` obtiene de `supplier_requirements_service` las filas del checklist del proveedor (sólo expediente) y la lista de exigibles pendientes. `supplier_rules()` recibe esas filas con la misma forma de hoy (`present`, `expired`, `required`), así que el cálculo de SUP-004 no cambia. Además recibe el número de requisitos obligatorios del perfil.

SUP-003 se evalúa así:
- **Internacional sin requisitos exigibles:** `not_applicable(..., NOT_FOR_INTERNATIONAL)`.
- **Todos los demás casos:** `PASS` "Expediente mínimo disponible", o `FAIL` "Expediente del proveedor incompleto. Pendientes: …" con los nombres en el orden del catálogo.

SUP-004 conserva su lógica y sigue `NOT_APPLICABLE` para el internacional.

### D11. Migración `0016_supplier_document_types`
Posterior a `0015_keycloak_identity`.
- **Upgrade:** crea la tabla con sus restricciones y siembra los 13 requisitos del sistema en el orden y con los valores de la sección 6.3 de la HU (`is_system = true`). No toca `suppliers` ni `documents`.
- **Downgrade:** elimina la tabla. Lanza `NotImplementedError` si existen requisitos del Administrador o documentos `POWER_OF_ATTORNEY` o `REQUISITO_%`, porque revertir los dejaría sin catálogo.

`alembic check` debe quedar sin diferencias.

### D12. Sin niveles fijos
A diferencia de HU-04, ningún flujo depende de un requisito concreto. Una configuración equivocada sólo impide autorizar o enviar facturas; se ve en el checklist, es reversible y queda auditada.

*Alternativa:* fijar "Acta constitutiva: No aplica" para persona física, con un `CHECK` y candados en la pantalla, para un error que no rompe nada.

### D13. Pantalla y plantillas
- **`admin/supplier_requirements.html`:** un solo `<form>` con la matriz (campos `<perfil>__<code>`) y la huella `config_version` oculta; formularios de alta y edición; sección "Requisitos inactivos". Sin JavaScript nuevo. Enlace "Requisitos de alta" en `base.html`, después de "Archivos mínimos".
- **`suppliers/detail.html`:**
  - el panel "Expediente Anexo A" pasa a "Requisitos de alta", con los exigibles primero, el estado, el aviso de faltantes y "Otros documentos del expediente";
  - el selector de carga marca los exigibles como "(obligatorio)";
  - la nota "Autorícelo desde el listado" se sustituye por el botón (D7).
- **`suppliers/list.html`:** columna "Requisitos de alta", casilla condicionada y grupo "No autorizado: faltan requisitos de alta" en el resumen.

### D14. Datos demo
`seed_db.py` deja de iterar `SUPPLIER_REQUIREMENTS`. Para cada proveedor demo carga un documento por cada requisito aplicable según el catálogo sembrado por la migración, incluido "Poderes" para la persona moral. Así SUP-003 resulta `PASS` y las 10 facturas demo conservan su resultado.

### D15. Pruebas
- **Nuevo `tests/test_requisitos_alta.py`:** un escenario por requisito de las specs.
- **Helper compartido en `conftest.py`:** carga los requisitos exigibles de un proveedor; lo usan las pruebas que autorizan (`test_acceso_proveedores.py`, `test_observabilidad.py`).
- **Pruebas que modifican la configuración:** restauran los niveles al terminar, porque la base es compartida por la sesión.
- **Playwright:**
  - `tests/hu/lib/portal.ts` agrega un helper que carga desde el expediente los requisitos exigibles de un proveedor. Lo usan las especificaciones de HU-02, HU-03 y HU-10 antes de autorizar;
  - `tests/hu/fixtures/herramientas.py` genera los PDF de ejemplo;
  - nueva especificación `19-HU-21-requisitos-alta.spec.ts` y su entrada en `hu-catalogo.json`.

## Risks / Trade-offs

- [Proveedores ya autorizados sin "Poderes" o sin uno de los dos comprobantes de domicilio quedan con SUP-003 `FAIL` y no pueden enviar facturas] → Los datos demo los cargan (D14). En un ambiente con proveedores reales se despliega con "Poderes" en Opcional y se endurece cuando lo carguen (P-07). El listado los marca con "Faltan N".
- [La Opinión de cumplimiento pasa a opcional y SUP-003 se relaja frente a hoy] → Es el literal de la solicitud; P-01 lo confirma y el Administrador lo revierte desde la pantalla.
- [El Administrador hace obligatorio un documento que nadie tiene y nadie puede autorizarse] → El checklist dice qué falta, el cambio es reversible y queda auditado.
- [La configuración cambia entre que el Administrador ve el checklist completo y autoriza] → La autorización decide con la configuración vigente en su transacción. El resumen explica qué faltó.
- [Pruebas existentes asumen que basta "Registrado" para autorizar] → Helper común (D15). Las pruebas que cambian la configuración la restauran.
- [Un proveedor internacional no puede cargar documentos de expediente con la configuración inicial] → Coherente con P-06; el Administrador habilita requisitos en la columna Internacional cuando se definan.
- [Eliminar `SUPPLIER_REQUIREMENTS` rompe importaciones] → Se buscan y sustituyen todos los usos (`supplier_service`, `validation_engine`, `seed_db`, pruebas). Ruff y pytest lo detectan.

## Migration Plan

1. Aplicar `0016_supplier_document_types` (`alembic upgrade head`): crea y siembra el catálogo; no cambia proveedores ni documentos.
2. En la demo, `scripts/reset_demo.py` recrea los datos con los requisitos completos (D14). Si el reset falla por Keycloak, se restaura el respaldo que el propio script genera.
3. En un ambiente con proveedores reales y antes de abrir la pantalla a los usuarios, el Administrador revisa en el listado la columna "Requisitos de alta" y decide P-07: carga los documentos faltantes, o deja temporalmente "Poderes" en Opcional.
4. **Rollback:** desplegar la versión anterior y `alembic downgrade 0015_keycloak_identity`. Si ya hay requisitos del Administrador o documentos de "Poderes", el downgrade se detiene (D11); se respalda y se decide manualmente.

## Open Questions

Preguntas de negocio de la sección 5.3 de la HU. Ninguna bloquea la implementación; los valores aplicados se siembran en la migración y se ajustan desde la pantalla.

- **P-01:** ¿la Opinión de cumplimiento del SAT es obligatoria? Valor aplicado: Opcional.
- **P-02:** ¿qué requisitos son obligatorios para la persona física? Valor aplicado: Identificación oficial, Cédula fiscal, Comprobante de domicilio y Estado de cuenta bancario.
- **P-03:** ¿"Poderes" es obligatorio siempre, o sólo cuando el acta no da facultades? Valor aplicado: siempre.
- **P-04:** ¿se exigen los dos comprobantes de domicilio? Valor aplicado: los dos.
- **P-05:** ¿un documento con más de tres meses debe impedir la autorización? Valor aplicado: no.
- **P-06:** ¿qué requisitos tiene el proveedor internacional? Valor aplicado: ninguno.
- **P-07:** ¿se bloquean las facturas de proveedores ya autorizados a los que les falta un requisito nuevo? Valor aplicado: sí (SUP-003 `ERROR`).
