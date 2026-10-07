# HU-22 · Requisitos de alta del contrato

| Campo | Valor |
| --- | --- |
| ID | HU-22 |
| Rol | Administrador |
| Módulo | A. Administración y Configuración |
| Prioridad | Por confirmar con negocio. Condiciona qué contratos pueden facturarse (HU-12, HU-13, HU-15, HU-16) |
| Origen | Solicitud de negocio del 2026-10-02 (nueva), con la aclaración del equipo de la misma fecha. No está en el documento de HUs ni en la ERS v1.4 |
| Requisito funcional | Nuevo; se propone como RF-20 en la siguiente versión de la ERS. Modifica RF-19 (HU-21, propuesto) |
| Regla de negocio | RN-HU22-01 a RN-HU22-04, de la solicitud (sección 5.1). Reglas derivadas RD-01 a RD-13 (sección 5.2) |
| Change OpenSpec sugerido | `requisitos-alta-contrato` |
| Capacidad nueva | `requisitos-alta-contrato` |
| Capacidades modificadas | `requisitos-alta-proveedor`, `motor-validacion`, `integridad-datos`, `listados-paginados`, `observabilidad` |
| Estado | Lista para `/opsx:propose` **después de archivar** `requisitos-alta-proveedor` (HU-21): sus deltas modifican esa capacidad y parten de las versiones de HU-21 de `integridad-datos` y `observabilidad`. Las preguntas abiertas (sección 5.3) sólo cambian valores iniciales o una severidad; no cambian la estructura |
| Estimación | Por definir en el refinamiento |
| Versión / fecha | 1.0 · 2026-10-02 · Equipo Técnico |

## Cómo usar este documento con OpenSpec

Con `requisitos-alta-proveedor` ya archivado, ejecutar `/opsx:propose requisitos-alta-contrato` con este documento como entrada. Cada sección alimenta un artefacto:

| Artefacto OpenSpec | Secciones de esta HU |
| --- | --- |
| `proposal.md` — Why | 1, 2 |
| `proposal.md` — What Changes | 3, 6 |
| `proposal.md` — Capabilities | Tabla de metadatos, 8, 9 |
| `proposal.md` — Impact | 11 |
| `specs/requisitos-alta-contrato/spec.md` | 8 (se copia tal cual bajo `## ADDED Requirements`) |
| `specs/requisitos-alta-proveedor/spec.md`, `specs/motor-validacion/spec.md`, `specs/integridad-datos/spec.md`, `specs/listados-paginados/spec.md`, `specs/observabilidad/spec.md` | 9 (bloques listos para copiar, o la instrucción exacta del cambio cuando el bloque vigente es largo) |
| `design.md` | 4, 5, 10 (las preguntas de 5.3 van a "Open Questions") |
| `tasks.md` | 11, 13 |

---

## 1. Historia de usuario

**Texto de la solicitud (2026-10-02, ortografía normalizada):**

> Para el alta de cada contrato del proveedor también requerimos una sección de configuración de requisitos o documentos, los cuales pueden ser opcionales u obligatorios, en donde destacan: Contrato (obligatorio), Orden de compra (opcional) y Anexos (opcional). Con la parametrización de los requisitos para dar de alta el contrato, ahora sí, al momento de dar de alta el contrato y querer activarlo, me debe pedir estos requisitos, los cuales se marquen como obligatorios, y que algunos pueden ser opcionales.

**Aclaración del equipo (2026-10-02):**

> La sección vive en el módulo de Requisitos mínimos y parametriza los adjuntos obligatorios para asignar un contrato a un proveedor. Hay requisitos que hoy están en el alta del proveedor que pasan al alcance del contrato.

**Redacción como HU:**

> Yo como administrador requiero parametrizar en Requisitos mínimos los documentos para dar de alta un contrato de un proveedor, marcando cada uno como obligatorio u opcional, para que el sistema me los pida al dar de alta el contrato y no me permita activarlo mientras falte alguno obligatorio.

**Reformulación:**

- **Como** Administrador del portal,
- **quiero** definir en Requisitos mínimos qué documentos son requisito de un contrato y si cada uno es Obligatorio, Opcional o No aplica,
- **para** que cada contrato me pida esos documentos y el sistema no lo active (no permita facturar contra él) mientras le falte alguno obligatorio.

**Términos de la solicitud y su equivalente en el sistema:**

| Término de la solicitud | En el sistema |
| --- | --- |
| Dar de alta el contrato | **Contratos › Agregar contrato** (`POST /contracts`). Hoy el contrato nace activo (`ACTIVE`); con esta HU nace "Registrado" (`REGISTERED`) |
| Activarlo | Nueva acción **Activar contrato**: pasa de "Registrado" a "Activo" (`ACTIVE`). Sólo un contrato activo se ofrece al facturar (spec `flujo-facturas`) y cumple SUP-002 |
| Requisitos o documentos del contrato | Nuevo expediente del contrato: documentos ligados al contrato (`documents.contract_id`), en una página de detalle del contrato que hoy no existe |
| Sección de configuración / módulo de Requisitos mínimos | **Administración › Requisitos mínimos › Alta de contrato**, junto a los archivos de la factura (HU-04) y los requisitos de alta del proveedor (HU-21) |
| Contrato | El contrato firmado con ULTRASIST, en el contrato y no en el expediente del proveedor |
| Orden de compra | La orden de compra que respalda la contratación. Es distinta de la orden de compra de cada factura (HU-04, regla DOC-003) |
| Anexos | Anexos del contrato (técnico, económico, de alcance…). Puede haber varios archivos |
| Requisitos que pasan del alta del proveedor al contrato | "Contrato" (`SUPPLIER_CONTRACT`), que HU-21 conserva como opcional en el expediente del proveedor. "Propuesta económica" queda como pregunta (P-01) |

## 2. Contexto y motivación

Los Lineamientos de facturación 2024 v1.4.1 ponen el contrato como prerrequisito de toda factura y lo condicionan al expediente del proveedor. En 1.i dicen: "Debe existir contrato vigente entre el Asociado y Ultrasist S.A. de C.V., para ello debe estar dado de alta en el catálogo de Asociados con el cumplimiento al 100% de los requisitos detallados en el 'Anexo A'". El Anexo A se titula "De los requisitos para elaborar contrato".

Hoy el PoC registra el contrato sin respaldo documental:

- **El contrato nace activo.** `POST /contracts` crea el contrato con `status = ACTIVE` (valor por defecto del modelo). El proveedor puede facturar contra él en ese momento, sin que exista el documento firmado.
- **El contrato no tiene documentos.** `documents` sólo se liga a una factura (`invoice_id`) o al expediente del proveedor (`supplier_id`). No existe una página de detalle del contrato donde cargarlos.
- **El "Contrato" vive en el lugar equivocado.** HU-21 conserva `SUPPLIER_CONTRACT` como requisito opcional del expediente del proveedor. Un proveedor puede tener varios contratos, y un único documento en su expediente no dice a cuál corresponde.
- **DOC-005 no revisa nada.** La regla "Contrato/anexo disponible" resulta `PASS` con que la factura tenga un contrato asociado (`contract_available = bool(contract)`), aunque nadie haya cargado el contrato ni sus anexos.
- **El contrato y sus anexos se piden en cada factura.** HU-04 ofrece "Contrato" y "Anexo del contrato" como archivos opcionales de cada factura, porque no había otro lugar donde guardarlos.

Esta HU completa la serie de configuraciones de documentos mínimos con el mismo patrón que HU-04 y HU-21: catálogo persistente, pantalla de administración, huella de concurrencia y auditoría.

**Tres configuraciones de documentos, cada una con su alcance:**

| Concepto | Qué es | Cuándo se entrega | Configuración | Qué bloquea |
| --- | --- | --- | --- | --- |
| Archivos de la factura (HU-04) | XML, PDF o Invoice, orden de compra del periodo, Vo.Bo., soportes | Con **cada** factura | Requisitos mínimos › Archivos de factura, por origen | El envío de la factura |
| Requisitos de alta del proveedor (HU-21) | Acta constitutiva, poderes, cédula fiscal, identificaciones, comprobantes, estado de cuenta | **Una vez**, antes de autorizar al proveedor | Requisitos mínimos › Alta de proveedor, por tipo de proveedor | La autorización del proveedor y, con SUP-003, el envío de sus facturas |
| Requisitos de alta del contrato (esta HU) | Contrato firmado, orden de compra de la contratación, anexos | **Una vez por contrato**, antes de activarlo; se pueden agregar después | Requisitos mínimos › Alta de contrato | La activación del contrato y, con DOC-005, el envío de las facturas de ese contrato |

## 3. Alcance

### Dentro del alcance

- Catálogo persistente de requisitos del contrato, con nombre en español, descripción, un nivel (Obligatorio, Opcional o No aplica) y si admite varios archivos. Requisitos del sistema iniciales: Contrato (obligatorio fijo), Orden de compra (opcional) y Anexos (opcional).
- Pantalla **Administración › Requisitos mínimos › Alta de contrato** para fijar el nivel de cada requisito.
- Alta, edición, desactivación y reactivación de requisitos definidos por el Administrador.
- Nuevo estatus del contrato "Registrado". El alta crea el contrato "Registrado" y lo lleva a su expediente.
- Página de detalle del contrato (expediente del contrato) con sus datos, el panel **Requisitos del contrato** (checklist y aviso "Faltan N requisitos obligatorios"), la carga y descarga de documentos y el historial de enmiendas.
- Acción **Activar contrato**, que exige el contrato "Registrado", el proveedor "Autorizado" y los requisitos obligatorios completos.
- Columnas "Estatus" (en español) y "Requisitos" ("Completos" o "Faltan N") en el listado de contratos, con liga al expediente.
- DOC-005 evaluada con la misma configuración: una sola definición del contrato completo.
- Traslado de "Contrato" (`SUPPLIER_CONTRACT`) fuera de los requisitos de alta del proveedor (HU-21).
- Menú **Requisitos mínimos** que agrupa las tres configuraciones de documentos.
- Auditoría de la configuración, de los documentos y de la activación, y protección contra ediciones concurrentes.
- Migración que conserva activos los contratos existentes.

### Fuera del alcance

| Tema | Motivo / dónde se atiende |
| --- | --- |
| Adjuntar documentos en el formulario de alta del contrato | El documento necesita un contrato al cual ligarse. El alta lleva directo al expediente del contrato, que los pide (RD-06) |
| Revisar el contenido de cada documento | Lo revisa el Administrador antes de activar. El sistema sólo verifica que el documento esté cargado |
| Formatos por requisito | Se conserva la validación global de `almacenamiento-documentos`, como en HU-21 |
| Vigencia de los documentos del contrato | La vigencia que importa es la del contrato (`start_date`, `end_date`), que ya revisa SUP-002 |
| Exigencias condicionales (por ejemplo, orden de compra obligatoria sólo arriba de cierto monto) | Un requisito es Obligatorio u Opcional para todos los contratos (RD-01) |
| Desactivar, cancelar o regresar a "Registrado" un contrato activo; editar los datos del contrato | No existe esa transición ni esa edición hoy (sólo la enmienda del monto). Sin cambios (P-07) |
| Trasladar al contrato los documentos "Contrato" ya cargados en expedientes de proveedor | No se sabe a qué contrato corresponde cada uno (RD-11). El Administrador los descarga del expediente y los carga en el contrato |
| Que el Proveedor vea o cargue los documentos de su contrato | El Proveedor no tiene acceso al módulo Contratos hoy (P-08) |
| Visor en el portal ("Ver") de los documentos del contrato | Sólo descarga, como el expediente del proveedor |
| Cambiar los archivos de la factura (HU-04): "Contrato", "Anexo del contrato" y "Orden de compra" por factura | Se configuran en Archivos de factura sin cambios de código (P-02, P-03) |
| Avisos por correo de contratos por activar | No lo pide la solicitud |

## 4. Situación actual del PoC

| Aspecto | Hoy | Brecha para HU-22 |
| --- | --- | --- |
| Alta del contrato | Formulario "+ Agregar contrato" en `contracts/list.html`; `create_contract()` en `app/routers/contracts.py` crea el contrato y regresa al listado buscando el proyecto ("Contrato creado") | Debe nacer "Registrado" y llevar a su expediente |
| Estatus del contrato | `ContractStatus` (`ACTIVE`, `INACTIVE`) en `app/core/constants.py`; `Contract.status` vale `ACTIVE` por defecto. Ninguna operación cambia el estatus. El listado muestra el valor crudo ("ACTIVE") siempre con el estilo de "aceptada" | No existe un estatus previo a la activación ni etiquetas en español |
| Detalle del contrato | No existe. Todo está en el listado, incluidas las enmiendas del monto en un `<details>` | Hace falta una página donde pedir y cargar los documentos |
| Documentos del contrato | `documents` tiene `invoice_id` y `supplier_id`; no tiene `contract_id`. `LocalFileStorage` guarda en `invoices/<id>` o `suppliers/<id>` | Nueva columna y nueva carpeta `contracts/<id>` |
| "Contrato" en el expediente del proveedor | `0016_supplier_document_types` (HU-21) siembra `SUPPLIER_CONTRACT` · Contrato · Opcional · Opcional · No aplica | Debe salir del alta del proveedor |
| Contrato y anexo en cada factura | HU-04: `CONTRACT` y `CONTRACT_ANNEX` Opcional para ambos orígenes; `PURCHASE_ORDER` Obligatorio (DOC-003) | Sin cambios de código (P-02, P-03) |
| DOC-005 | `document_rules(..., contract_available=bool(contract))` en `app/rules/document_rules.py`: `PASS` "Contrato/anexo disponible" si la factura tiene contrato; `FAIL` "Falta contrato/anexo" (`ERROR`) si no | No revisa los documentos del contrato |
| SUP-002 | `supplier_rules()`: contrato `ACTIVE` y fecha de hoy dentro de su vigencia (`CRITICAL`) | Sin cambios: un contrato "Registrado" no cumple |
| Alta de factura | `invoices.py` ofrece sólo contratos `ACTIVE` del proveedor y rechaza otro con 400 "El contrato no está activo" | Sin cambios: cubre al contrato "Registrado" |
| Permisos | Listado de contratos: PMO y Administrador. Alta y enmiendas: Administrador. Proveedor: sin acceso | Se conservan para el expediente del contrato |
| Datos demo (`scripts/seed_db.py`) | Tres contratos con `status="ACTIVE"` explícito y sin documentos | Deben cargar el "Contrato" para que DOC-005 conserve su resultado |
| Patrón de configuración | HU-04 (`/admin/required-documents`, niveles fijos con candado) y HU-21 (`/admin/supplier-requirements`, checklist del expediente) | Se reutiliza tal cual |
| Menú | "Archivos mínimos" y "Requisitos de alta" sueltos en Administración (`base.html`) | Se agrupan en "Requisitos mínimos" |

## 5. Reglas de negocio

### 5.1 De la solicitud

| ID | Regla | Fuente |
| --- | --- | --- |
| RN-HU22-01 | Los documentos requeridos para dar de alta un contrato se parametrizan en la configuración del sistema, cada uno como obligatorio u opcional | Solicitud: "requerimos una sección de configuración de requisitos o documentos, los cuales pueden ser opcionales u obligatorios" |
| RN-HU22-02 | Un contrato sólo puede activarse con todos sus requisitos obligatorios cargados | Solicitud: "al momento de dar de alta el contrato y querer activarlo, me debe pedir estos requisitos" |
| RN-HU22-03 | Los requisitos iniciales son Contrato (obligatorio), Orden de compra (opcional) y Anexos (opcional) | Solicitud: "en donde destacan: …" |
| RN-HU22-04 | Los requisitos del alta del proveedor que corresponden al contrato pasan al alcance del contrato | Aclaración del equipo (2026-10-02) |

### 5.2 Derivadas

Fundamentadas en las fuentes del proyecto; ninguna está confirmada todavía por negocio:

| ID | Regla | Fundamento |
| --- | --- | --- |
| RD-01 | Cada requisito tiene un solo nivel, igual para todos los contratos: no se distingue por origen ni por tipo de persona del proveedor | La solicitud da un nivel por documento. El contrato es el mismo instrumento para un proveedor nacional y uno internacional |
| RD-02 | Hay tres niveles: Obligatorio, Opcional y No aplica, la enumeración `DocumentRequirement` de HU-04 y HU-21. "No aplica" deja de pedir un requisito del sistema sin borrarlo | Solicitud: "obligatorios" y "opcionales". Los requisitos del sistema no se desactivan (RD-12), así que "No aplica" es la forma de dejar de pedirlos |
| RD-03 | "Contrato" es Obligatorio fijo: el Administrador no puede cambiar su nivel | Solicitud: "Contrato – Obligatorio". Lineamientos 1.i: "Debe existir contrato vigente". Un contrato activo sin el documento firmado no tiene respaldo. Mismo mecanismo que los niveles fijos de HU-04 |
| RD-04 | El contrato nace "Registrado" y sólo la activación lo pasa a "Activo". Un contrato "Registrado" no se ofrece al facturar y no cumple SUP-002 | Solicitud: "al momento de dar de alta el contrato y querer activarlo". Las reglas actuales ya exigen `ACTIVE` |
| RD-05 | Para activar un contrato se exige, con la configuración vigente y en la misma transacción: (a) que el contrato esté "Registrado"; (b) que su proveedor esté "Autorizado"; (c) que tenga cargados todos sus requisitos obligatorios | (c) RN-HU22-02. (b) Lineamientos 1.i: para que exista contrato vigente el Asociado "debe estar dado de alta … con el cumplimiento al 100%" del Anexo A, que HU-21 verifica al autorizar (P-05) |
| RD-06 | Los requisitos se cargan en el expediente del contrato, después del alta. El alta crea el contrato "Registrado" y lleva a su expediente, que pide los requisitos; la activación los verifica | El documento necesita un contrato al cual ligarse. Mismo flujo que HU-21 (RD-06): el alta lleva al expediente y la activación verifica |
| RD-07 | Un requisito admite un archivo o varios, según el catálogo. Con un archivo, una carga nueva reemplaza al vigente. Con varios, cada carga agrega un archivo, y el Administrador puede reemplazar uno en particular. Un requisito se cumple con al menos un documento vigente (`is_current`) de su tipo en el contrato | "Anexos", en plural. Un contrato puede tener anexo técnico, económico y de alcance |
| RD-08 | Los documentos se cargan con el contrato "Registrado" o "Activo": una orden de compra o un anexo pueden llegar después de la activación. Sólo el Administrador carga; el PMO consulta y descarga; el Proveedor no tiene acceso | Permisos actuales del módulo Contratos. Los anexos se agregan durante la vida del contrato |
| RD-09 | La configuración no cambia el estatus de nadie. Un contrato "Activo" sigue activo aunque después se agregue un requisito obligatorio. Los contratos que existen al aplicar la migración quedan "Activo" | Mismo criterio que la RD-08 de HU-21. Cambiar el estatus de contratos en uso cortaría la facturación sin decisión de nadie |
| RD-10 | DOC-005 usa la misma configuración que la activación: `PASS` si el contrato de la factura tiene sus requisitos obligatorios cargados; `FAIL` con los pendientes en otro caso. Conserva su severidad `ERROR` | El nombre de la regla ("Contrato/anexo disponible") ya dice eso. Dos definiciones del contrato completo se contradirían, igual que la RD-09 de HU-21 con SUP-003 |
| RD-11 | "Contrato" (`SUPPLIER_CONTRACT`) sale de los requisitos de alta del proveedor: queda fijo en No aplica para los tres tipos de proveedor y deja de ofrecerse. Los documentos ya cargados siguen visibles y descargables en "Otros documentos del expediente"; no se trasladan solos al contrato | RN-HU22-04. Un proveedor puede tener varios contratos y el documento de su expediente no dice a cuál corresponde |
| RD-12 | Los requisitos del sistema no se editan ni se desactivan; sólo cambia su nivel, salvo el de "Contrato". Los del Administrador se desactivan, nunca se borran. Los documentos nunca se borran: un reemplazo deja el anterior con `is_current = false` | Mismo criterio que la RD-10 de HU-21. Spec `integridad-datos`: "Prohibición de borrado físico de evidencia fiscal" |
| RD-13 | Los documentos del contrato no forman parte del expediente del proveedor ni de la factura: no cuentan para el checklist de HU-21, SUP-003, la carga documental de la factura ni DOC-009 | Son tres alcances distintos (tabla de la sección 2) |

### 5.3 Preguntas abiertas para negocio

Ninguna bloquea `/opsx:propose`. P-01 a P-04 cambian valores iniciales o la configuración de HU-04, sin cambios de estructura. P-05 a P-08 deciden reglas que ya tienen un valor aplicado.

| ID | Pregunta | Valor aplicado mientras tanto | Impacto de la respuesta |
| --- | --- | --- | --- |
| P-01 | La "Propuesta económica autorizada por el Líder de ULTRASIST" (Anexo A) es por contratación, no por proveedor. ¿Pasa también al contrato? | Se queda en el alta del proveedor (HU-21), exigible si el alta es por cotización o licitación | Se agrega como requisito del sistema del contrato y `ECONOMIC_PROPOSAL` se fija en No aplica en el proveedor, igual que "Contrato" (RD-11). El indicador `suppliers.economic_proposal` pierde su uso |
| P-02 | Con el contrato y sus anexos en el contrato, ¿se dejan de ofrecer "Contrato" y "Anexo del contrato" en cada factura (HU-04)? | Sin cambios: siguen Opcional en cada factura | El Administrador los pone en No aplica en Archivos de factura, sin cambios de código. Recomendación del equipo: No aplica |
| P-03 | ¿La orden de compra del contrato sustituye a la orden de compra de cada factura (DOC-003)? | No. La del contrato respalda la contratación; la de la factura, el periodo facturado (`purchase_order_number`) | Si la sustituye, "Orden de compra" de la factura pasa a Opcional o No aplica en Archivos de factura |
| P-04 | ¿Un contrato puede tener varias órdenes de compra? | Sí: "Orden de compra" admite varios archivos | Se cambia el valor sembrado antes de desplegar (no se edita desde la pantalla, D8) |
| P-05 | ¿Activar un contrato exige que el proveedor esté "Autorizado"? | Sí (RD-05 b) | Si no, se quita esa condición; SUP-001 sigue impidiendo facturar a un proveedor no autorizado |
| P-06 | Los contratos activos que existen hoy no tienen documentos. ¿Sus facturas deben bloquearse por DOC-005 hasta que se cargue el contrato? | Sí: DOC-005 conserva su severidad `ERROR`. El listado los marca con "Faltan 1" | Como "Contrato" es fijo, no se puede relajar desde la pantalla. Si no deben bloquearse, DOC-005 se despliega como `WARNING` durante la transición |
| P-07 | ¿Hace falta desactivar un contrato activo o regresarlo a "Registrado"? | No: ninguna transición sale de "Activo" | HU nueva |
| P-08 | ¿El Proveedor debe ver los documentos de su contrato? | No, como hoy | HU nueva |

## 6. Catálogo de requisitos y configuración inicial

### 6.1 Estatus del contrato

| Estatus | Valor | Etiqueta | Cómo se llega | Se ofrece al facturar | SUP-002 |
| --- | --- | --- | --- | --- | --- |
| Registrado | `REGISTERED` (nuevo) | "Registrado" | Alta del contrato | No | `FAIL` |
| Activo | `ACTIVE` | "Activo" | Activación (o contrato existente al migrar) | Sí | `PASS` dentro de su vigencia |
| Inactivo | `INACTIVE` | "Inactivo" | Ninguna operación hoy (P-07) | No | `FAIL` |

### 6.2 Niveles

Se reutiliza la enumeración `DocumentRequirement`.

| Nivel | Valor | En el expediente del contrato | Al activar | En DOC-005 |
| --- | --- | --- | --- | --- |
| Obligatorio | `REQUIRED` | Se pide y el checklist lo marca "Obligatorio" | Si falta, el contrato no se activa | Si falta, `FAIL` |
| Opcional | `OPTIONAL` | Se ofrece y el checklist lo marca "Opcional" | No se exige | No se exige |
| No aplica | `NOT_APPLICABLE` | No se ofrece; si se envía, se rechaza | No se exige | No se exige |

### 6.3 Requisitos del sistema y valores iniciales

| Solicitud | Clave | Nombre | Descripción (ayuda en el expediente) | Nivel | Varios archivos |
| --- | --- | --- | --- | --- | --- |
| Contrato – Obligatorio | `SIGNED_CONTRACT` | **Contrato** | Contrato firmado con ULTRASIST | Obligatorio (fijo, RD-03) | No |
| Orden de Compra – Opcional | `CONTRACT_PURCHASE_ORDER` | **Orden de compra** | Orden de compra que respalda la contratación | Opcional | Sí (P-04) |
| Anexos – Opcional | `CONTRACT_ANNEXES` | **Anexos** | Anexos del contrato: técnico, económico, de alcance u otros | Opcional | Sí |

Las claves son nuevas y distintas de las de los archivos de la factura (`CONTRACT`, `CONTRACT_ANNEX` y `PURCHASE_ORDER` de HU-04), para que una clave identifique un solo catálogo (D10).

### 6.4 Requisitos definidos por el Administrador

- **Campos:** nombre (3 a 80 caracteres, único sin distinguir mayúsculas), descripción opcional (hasta 300 caracteres), nivel (preseleccionado en "No aplica", así que crear un requisito no cambia nada hasta que el Administrador lo decida) y "Admite varios archivos".
- **Clave:** la genera el sistema con el formato `REQ_CONTRATO_<id>` (por ejemplo, `REQ_CONTRATO_4`) y no cambia.
- **Edición:** nombre y descripción. El nivel se cambia desde la configuración; "Admite varios archivos" no cambia después del alta (D8).
- **Desactivación:** el requisito deja de pedirse y de exigirse y pasa a la sección "Requisitos inactivos". Conserva su nivel para cuando se reactive.
- **Ejemplo de uso:** "Convenio de confidencialidad" por contrato (Lineamientos 1.iii) o "Acta de inicio del proyecto", sin cambios de código.

### 6.5 "Contrato" fuera de los requisitos de alta del proveedor

| Clave | Antes (HU-21) | Después (esta HU) |
| --- | --- | --- |
| `SUPPLIER_CONTRACT` | Opcional · Opcional · No aplica | No aplica · No aplica · No aplica, **fijo**, con candado y el motivo "Se carga en cada contrato" |

Los documentos `SUPPLIER_CONTRACT` ya cargados conservan su tipo y se listan, descargables, en "Otros documentos del expediente" (comportamiento de HU-21 para requisitos que dejaron de aplicar).

### 6.6 Reglas afectadas

| Código | Qué evalúa | Severidad | Cambio |
| --- | --- | --- | --- |
| DOC-005 | Contrato y anexos disponibles | `ERROR` | Evalúa los requisitos obligatorios del contrato de la factura con la configuración vigente. El mensaje de `FAIL` nombra los pendientes (RD-10) |
| SUP-002 | Contrato vigente | `CRITICAL` | Sin cambios. Un contrato "Registrado" no cumple porque no es `ACTIVE` |
| SUP-003 | Expediente del proveedor | `ERROR` | Sin cambios de código; deja de contar "Contrato" porque pasa a No aplica (que ya era Opcional, así que tampoco cambia su resultado) |

## 7. Flujo de uso

**Administrador: configuración**

1. Entra a **Administración › Requisitos mínimos › Alta de contrato** (`GET /admin/contract-requirements`).
2. Ve una fila por requisito activo con su nombre, descripción, "Varios archivos" (Sí o No) y un selector de nivel. "Contrato" muestra "Obligatorio" con candado y el motivo "Todo contrato activo tiene su contrato firmado".
3. Cambia los niveles y pulsa **Guardar configuración** (`POST /admin/contract-requirements`). El sistema valida, guarda en una transacción, audita y muestra "Configuración guardada", o "Sin cambios".
4. Para un documento que no está en el catálogo usa **Nuevo requisito** (`POST /admin/contract-requirements/types`). Edita uno propio (`POST /admin/contract-requirements/types/{type_id}`) o lo desactiva y reactiva (`POST /admin/contract-requirements/types/{type_id}/status`).

**Administrador: alta y activación de un contrato**

5. En **Contratos › Agregar contrato** captura proveedor, proyecto, líder, tecnología, monto, moneda y vigencia (`POST /contracts`). El contrato queda "Registrado" y el sistema lo lleva a su expediente (`GET /contracts/{contract_id}`) con el aviso "Contrato creado. Cargue sus requisitos para activarlo."
6. El panel **Requisitos del contrato** muestra primero los obligatorios, cada uno con sus archivos (nombre y fecha de carga) o "Pendiente", y el aviso "Faltan N requisitos obligatorios" o "Requisitos del contrato completos".
7. Carga cada documento desde **Agregar documento** (`POST /contracts/{contract_id}/documents`). El selector ofrece sólo los requisitos que aplican. En un requisito con varios archivos puede elegir "Reemplaza a" uno de los vigentes; si no elige, el archivo se agrega.
8. Con los requisitos completos y el proveedor "Autorizado", pulsa **Activar contrato** y confirma en el diálogo (`POST /contracts/{contract_id}/activate`). El expediente muestra "Contrato activado" y el estatus "Activo".
9. Si el botón está deshabilitado, el expediente dice por qué: "Cargue los requisitos obligatorios para activar" o "Autorice al proveedor para activar el contrato" (con liga a su expediente).
10. Si mientras tanto faltó un requisito obligatorio (por ejemplo, otro Administrador acaba de hacer obligatoria la orden de compra), el contrato no se activa y el expediente muestra "No se activó el contrato: faltan requisitos obligatorios (Orden de compra)".

**Listado de contratos (PMO y Administrador)**

11. Cada contrato muestra su estatus en español y la columna **Requisitos** con "Completos" o "Faltan N", incluidos los activos (RD-09). El proyecto liga al expediente del contrato.

**Proveedor**

12. Al registrar una factura sólo ve sus contratos activos, como hoy. Si el contrato de una factura editable perdió un requisito obligatorio, DOC-005 resulta `FAIL` con los pendientes y la factura no puede enviarse hasta que el Administrador los cargue.

## 8. Criterios de aceptación — spec `requisitos-alta-contrato`

Los requisitos de esta sección siguen el formato de delta de OpenSpec. Se copian tal cual a `openspec/changes/requisitos-alta-contrato/specs/requisitos-alta-contrato/spec.md`, bajo el encabezado `## ADDED Requirements`.

### Requirement: Catálogo de requisitos del contrato
El sistema SHALL mantener un catálogo persistente de los documentos que forman el expediente de un contrato (requisitos del contrato). Cada requisito SHALL tener:
- una clave inmutable, que es el valor que se guarda en `documents.document_type` de los documentos del contrato;
- un nombre en español y una descripción opcional, que se muestran en el expediente del contrato;
- si es un requisito del sistema o uno definido por el Administrador;
- si está activo;
- si admite varios archivos;
- un nivel: `REQUIRED` ("Obligatorio"), `OPTIONAL` ("Opcional") o `NOT_APPLICABLE` ("No aplica"), igual para todos los contratos.

El catálogo SHALL incluir estos requisitos del sistema con estos valores iniciales (clave · nombre · nivel · varios archivos):
- `SIGNED_CONTRACT` · Contrato · Obligatorio · No;
- `CONTRACT_PURCHASE_ORDER` · Orden de compra · Opcional · Sí;
- `CONTRACT_ANNEXES` · Anexos · Opcional · Sí.

#### Scenario: Catálogo inicial tras la migración
- **WHEN** se aplica la migración sobre una base con contratos existentes
- **THEN** el catálogo contiene los 3 requisitos del sistema, activos y con sus valores iniciales, y ningún contrato cambia de estatus

#### Scenario: Nombres en español
- **WHEN** el Administrador abre el expediente de un contrato
- **THEN** los requisitos se muestran por su nombre del catálogo (por ejemplo "Orden de compra" y "Anexos"), no por su clave

### Requirement: Configuración exclusiva del Administrador
La página `GET /admin/contract-requirements` y las operaciones `POST /admin/contract-requirements`, `POST /admin/contract-requirements/types`, `POST /admin/contract-requirements/types/{type_id}` y `POST /admin/contract-requirements/types/{type_id}/status` SHALL estar disponibles únicamente para el rol `Administrador`. Toda operación `POST` MUST exigir un token CSRF válido.

El menú de Administración SHALL agrupar bajo el título "Requisitos mínimos" las tres configuraciones de documentos: "Archivos de factura" (`/admin/required-documents`), "Alta de proveedor" (`/admin/supplier-requirements`) y "Alta de contrato" (`/admin/contract-requirements`). El grupo SHALL mostrarse sólo al rol `Administrador`.

#### Scenario: PMO sin acceso
- **WHEN** un usuario `PMO` solicita la página de configuración o envía cualquiera de sus operaciones
- **THEN** la respuesta es HTTP 403 y la configuración no cambia

#### Scenario: Proveedor sin acceso
- **WHEN** un usuario `Proveedor` solicita la página de configuración o envía cualquiera de sus operaciones
- **THEN** la respuesta es HTTP 403 y la configuración no cambia

#### Scenario: Envío sin token CSRF
- **WHEN** un Administrador envía `POST /admin/contract-requirements` sin token CSRF o con uno inválido
- **THEN** la respuesta es HTTP 403 y la configuración no cambia

#### Scenario: Menú de Requisitos mínimos
- **WHEN** un Administrador abre cualquier página del portal
- **THEN** el menú muestra el grupo "Requisitos mínimos" con "Archivos de factura", "Alta de proveedor" y "Alta de contrato", y un PMO no ve el grupo

### Requirement: Configuración de los requisitos del contrato
La página de configuración SHALL mostrar una fila por cada requisito activo, con su nombre, su descripción, si admite varios archivos y un selector de nivel. Primero aparecen los requisitos del sistema, en el orden del catálogo, y después los del Administrador, por nombre.

El nivel de `SIGNED_CONTRACT` SHALL ser fijo en Obligatorio: la página lo muestra como texto con el ícono de candado y el motivo "Todo contrato activo tiene su contrato firmado", sin selector. Una petición que intente cambiarlo SHALL rechazarse con HTTP 409 y el mensaje "Contrato tiene un nivel fijo", sin guardar ningún cambio.

Al guardar, el sistema SHALL validar todos los niveles recibidos y actualizar en una sola transacción los que cambiaron. Un nivel distinto de `REQUIRED`, `OPTIONAL` o `NOT_APPLICABLE`, o la falta del nivel de un requisito activo con nivel editable, SHALL rechazar el guardado completo con HTTP 400. Si ningún nivel cambió, el sistema SHALL informar "Sin cambios" sin modificar nada.

#### Scenario: Hacer obligatoria la orden de compra
- **WHEN** el Administrador cambia "Orden de compra" a Obligatorio y guarda
- **THEN** la página muestra "Configuración guardada", y el expediente de un contrato "Registrado" sin orden de compra la muestra como "Obligatorio · Pendiente" y la cuenta entre los obligatorios pendientes

#### Scenario: Dejar de pedir los anexos
- **WHEN** el Administrador cambia "Anexos" a No aplica y guarda
- **THEN** el expediente de un contrato ya no ofrece "Anexos" en el formulario de carga

#### Scenario: Contrato con nivel fijo
- **WHEN** el Administrador abre la configuración
- **THEN** la fila "Contrato" muestra "Obligatorio" con candado y el motivo "Todo contrato activo tiene su contrato firmado", sin selector

#### Scenario: Petición manipulada sobre el Contrato
- **WHEN** la petición trae `OPTIONAL` como nivel de `SIGNED_CONTRACT`, junto con otros cambios válidos
- **THEN** la respuesta es HTTP 409 con el mensaje "Contrato tiene un nivel fijo" y no se guarda ningún cambio

#### Scenario: Guardar sin cambios
- **WHEN** el Administrador guarda la configuración sin modificar ningún nivel
- **THEN** la página muestra "Sin cambios" y no se agrega ningún registro de auditoría

#### Scenario: Nivel inválido
- **WHEN** la petición trae `MANDATORY` como nivel de un requisito, junto con otros cambios válidos
- **THEN** la respuesta es HTTP 400 con el mensaje "Nivel de exigencia inválido" y no se guarda ningún cambio

### Requirement: Requisitos del contrato definidos por el Administrador
El Administrador SHALL poder dar de alta requisitos con un nombre de 3 a 80 caracteres, una descripción opcional de hasta 300 caracteres, un nivel (preseleccionado en "No aplica") y si admite varios archivos (preseleccionado en "No"). El sistema SHALL:
- normalizar el nombre, recortando los espacios de los extremos y colapsando los internos repetidos;
- rechazar con HTTP 409 un nombre que ya use otro requisito del contrato, sin distinguir mayúsculas;
- asignar al requisito la clave `REQ_CONTRATO_<id>`, que no cambia.

El Administrador SHALL poder editar el nombre y la descripción de estos requisitos, y desactivarlos o reactivarlos. Si admite varios archivos MUST NOT cambiar después del alta. Un requisito inactivo MUST NOT ofrecerse en el expediente del contrato ni exigirse al activar o en DOC-005, y SHALL conservar su nivel para cuando se reactive. Los requisitos del sistema MUST NOT editarse ni desactivarse; sólo cambia su nivel, salvo el de `SIGNED_CONTRACT`.

#### Scenario: Alta de un requisito
- **WHEN** el Administrador da de alta "Convenio de confidencialidad", Obligatorio y de un solo archivo
- **THEN** existe un requisito activo con clave `REQ_CONTRATO_<id>` que aparece en la configuración, y el expediente de un contrato "Registrado" lo muestra como "Obligatorio · Pendiente"

#### Scenario: Nombre repetido
- **WHEN** el Administrador da de alta un requisito con el nombre "  ORDEN de   compra "
- **THEN** la respuesta es HTTP 409 con el mensaje "Ya existe un requisito con ese nombre" y no se crea ningún requisito

#### Scenario: Desactivación y reactivación
- **WHEN** el Administrador desactiva "Convenio de confidencialidad", que era Obligatorio
- **THEN** el expediente ya no lo pide, la activación y DOC-005 ya no lo exigen, y los documentos ya cargados de ese tipo siguen listados y descargables; al reactivarlo vuelve a ser Obligatorio

#### Scenario: Requisito del sistema
- **WHEN** el Administrador envía la edición o la desactivación de "Anexos"
- **THEN** la respuesta es HTTP 409 con el mensaje "Los requisitos del sistema no se pueden editar ni desactivar" y el requisito no cambia

### Requirement: Estatus del contrato
Un contrato SHALL tener uno de estos estatus, que la interfaz muestra en español: `REGISTERED` ("Registrado"), `ACTIVE` ("Activo") o `INACTIVE` ("Inactivo"). El alta de un contrato SHALL crearlo "Registrado". La única transición SHALL ser de "Registrado" a "Activo", mediante la activación. Un contrato "Registrado" MUST NOT ofrecerse en el formulario de alta de factura ni aceptarse en él, y no cumple SUP-002.

#### Scenario: Alta de contrato
- **WHEN** el Administrador crea un contrato
- **THEN** el contrato queda "Registrado", el sistema redirige a `/contracts/{contract_id}` con el aviso "Contrato creado. Cargue sus requisitos para activarlo." y se registra `CONTRACT_CREATED`

#### Scenario: Contrato registrado al facturar
- **WHEN** el proveedor de un contrato "Registrado" abre el formulario de alta de factura
- **THEN** el contrato no se ofrece; si el proveedor envía su identificador, la respuesta es HTTP 400 "El contrato no está activo" y no se crea la factura

#### Scenario: Contratos existentes
- **WHEN** se aplica la migración sobre una base con contratos `ACTIVE` sin documentos
- **THEN** los contratos siguen "Activo" y sus proveedores pueden seguir registrando facturas con ellos

### Requirement: Expediente del contrato
`GET /contracts/{contract_id}` SHALL mostrar a los roles `Administrador` y `PMO` el expediente del contrato:
- sus datos: proveedor (con liga a su expediente y su estatus), proyecto, líder, tecnología autorizada, monto, moneda, vigencia y estatus;
- el panel "Requisitos del contrato" con los requisitos que aplican (activos con nivel Obligatorio u Opcional), primero los obligatorios y después los opcionales, cada grupo en el orden del catálogo. De cada requisito SHALL mostrar su nombre, su nivel, su descripción si la tiene y sus documentos vigentes (nombre del archivo, fecha de carga y liga de descarga), o "Pendiente";
- el aviso "Falta 1 requisito obligatorio", "Faltan N requisitos obligatorios" o "Requisitos del contrato completos";
- "Otros documentos del contrato": los documentos vigentes de tipos que ya no aplican, descargables y sin contar para los requisitos;
- el historial de enmiendas del monto.

Un requisito SHALL cumplirse con al menos un documento vigente (`is_current`) de su tipo ligado al contrato. Para el rol `Proveedor`, la página y la descarga SHALL responder HTTP 403. Un contrato inexistente SHALL responder HTTP 404. El listado de contratos SHALL ligar cada proyecto a su expediente.

`GET /contracts/{contract_id}/documents/{document_id}/download` SHALL descargar un documento del contrato con las reglas de "Descarga segura de documentos" (spec `almacenamiento-documentos`), y SHALL responder HTTP 404 si el documento no pertenece al contrato de la URL.

#### Scenario: Requisitos pendientes
- **WHEN** el Administrador abre el expediente de un contrato "Registrado" sin documentos, con la configuración inicial
- **THEN** el panel muestra "Contrato" como "Obligatorio · Pendiente" e indica "Falta 1 requisito obligatorio", y muestra "Orden de compra" y "Anexos" como "Opcional · Pendiente"

#### Scenario: Requisitos completos con varios anexos
- **WHEN** el contrato tiene cargados el contrato firmado y dos anexos
- **THEN** el panel indica "Requisitos del contrato completos" y lista los dos archivos bajo "Anexos"

#### Scenario: PMO consulta
- **WHEN** un PMO abre el expediente de un contrato y descarga su contrato firmado
- **THEN** ve los datos, el panel y los documentos, descarga el archivo como adjunto, y no ve el formulario de carga ni el botón "Activar contrato"

#### Scenario: Proveedor sin acceso
- **WHEN** un usuario `Proveedor` solicita el expediente de un contrato propio o la descarga de uno de sus documentos
- **THEN** la respuesta es HTTP 403

#### Scenario: Documento de otro contrato
- **WHEN** se solicita `/contracts/{A}/documents/{D}/download` y `D` pertenece al contrato `B`
- **THEN** la respuesta es HTTP 404

### Requirement: Carga de documentos del contrato
`POST /contracts/{contract_id}/documents` SHALL estar disponible sólo para el rol `Administrador`, con token CSRF, para un contrato "Registrado" o "Activo". Recibe el tipo, el archivo y, para un requisito con varios archivos, opcionalmente el documento al que reemplaza. Antes de escribir el archivo, el sistema SHALL rechazar con HTTP 400:
- un tipo que no aplica al contrato (No aplica, inactivo o inexistente), con el mensaje "El documento no aplica a este contrato";
- un documento a reemplazar que no es un documento vigente del mismo tipo y del mismo contrato, con el mensaje "El documento a reemplazar no corresponde a este requisito".

Las verificaciones existentes de contenido y tamaño (spec `almacenamiento-documentos`) SHALL mantenerse. El archivo SHALL guardarse en `contracts/<contract_id>/<uuid>.<ext>` y el documento SHALL ligarse sólo al contrato (`contract_id`), sin `invoice_id` ni `supplier_id`. Al guardar:
- en un requisito de un solo archivo, el documento vigente de ese tipo, si existe, SHALL quedar con `is_current = false` y el nuevo SHALL guardar su id en `replaced_document_id`;
- en un requisito con varios archivos, el nuevo SHALL agregarse; si se indicó el documento a reemplazar, ése SHALL quedar con `is_current = false` y el nuevo SHALL guardar su id en `replaced_document_id`.

Ningún documento SHALL borrarse.

#### Scenario: Carga del contrato firmado
- **WHEN** el Administrador carga `contrato.pdf` como "Contrato" en un contrato "Registrado"
- **THEN** el documento queda vigente, ligado al contrato, en `contracts/<contract_id>/`, y el panel deja de mostrar "Contrato" como pendiente

#### Scenario: Reemplazo del contrato firmado
- **WHEN** el contrato ya tiene un "Contrato" vigente y el Administrador carga otro
- **THEN** el anterior queda con `is_current = false` y sigue en la base de datos, y el nuevo guarda su id en `replaced_document_id`

#### Scenario: Segundo anexo
- **WHEN** el contrato tiene un anexo vigente y el Administrador carga otro sin indicar a cuál reemplaza
- **THEN** los dos anexos quedan vigentes

#### Scenario: Anexo en un contrato activo
- **WHEN** el Administrador carga un anexo en un contrato "Activo"
- **THEN** el anexo se guarda y el contrato sigue "Activo"

#### Scenario: Tipo que no aplica
- **WHEN** se envía un documento con `document_type = INCORPORATION_ACT` a un contrato
- **THEN** la respuesta es HTTP 400 con el mensaje "El documento no aplica a este contrato" y no se escribe ningún archivo en `storage/`

#### Scenario: PMO intenta cargar
- **WHEN** un PMO envía `POST /contracts/{contract_id}/documents`
- **THEN** la respuesta es HTTP 403 y no se escribe ningún archivo en `storage/`

### Requirement: Activación del contrato
`POST /contracts/{contract_id}/activate` SHALL estar disponible sólo para el rol `Administrador`, con token CSRF. En una transacción, con la fila del contrato bloqueada, el sistema SHALL verificar con la configuración vigente:
- que el contrato esté "Registrado"; si no, HTTP 409 "Sólo se puede activar un contrato Registrado";
- que su proveedor esté "Autorizado"; si no, HTTP 409 "No se activó el contrato: el proveedor no está autorizado";
- que tenga cargados todos sus requisitos obligatorios; si no, HTTP 409 "No se activó el contrato: faltan requisitos obligatorios (<nombre>, <nombre>)", con los nombres en el orden del catálogo.

Si todo se cumple, el contrato SHALL pasar a "Activo", con `updated_at` y `updated_by` del Administrador, y el sistema SHALL redirigir a su expediente con el aviso "Contrato activado". Una activación rechazada MUST NOT cambiar el contrato.

En el expediente de un contrato "Registrado", el Administrador SHALL ver el botón "Activar contrato":
- con el proveedor "Autorizado" y los requisitos completos, el botón SHALL pedir confirmación en un diálogo de la página con el texto "Se activará el contrato <proyecto> de <razón social>. El proveedor podrá registrar facturas con él.";
- con el proveedor sin autorizar, SHALL mostrarse deshabilitado con "Autorice al proveedor para activar el contrato" y la liga a su expediente;
- con requisitos pendientes, SHALL mostrarse deshabilitado con "Cargue los requisitos obligatorios para activar".

El botón MUST NOT mostrarse al rol `PMO` ni en un contrato que no está "Registrado". La página MUST NOT usar diálogos nativos, scripts ni estilos en línea.

#### Scenario: Activación
- **WHEN** el Administrador carga el contrato firmado de un contrato "Registrado" cuyo proveedor está "Autorizado", pulsa "Activar contrato" y confirma
- **THEN** el contrato queda "Activo", el expediente muestra "Contrato activado" y el proveedor ve el contrato en el formulario de alta de factura

#### Scenario: Requisitos incompletos
- **WHEN** el Administrador abre el expediente de un contrato "Registrado" sin contrato firmado
- **THEN** el botón "Activar contrato" está deshabilitado con "Cargue los requisitos obligatorios para activar"

#### Scenario: Petición manipulada
- **WHEN** el Administrador envía `POST /contracts/{contract_id}/activate` para un contrato sin contrato firmado
- **THEN** la respuesta es HTTP 409 con "No se activó el contrato: faltan requisitos obligatorios (Contrato)" y el contrato sigue "Registrado"

#### Scenario: Proveedor no autorizado
- **WHEN** el contrato tiene sus requisitos completos y su proveedor está "Registrado"
- **THEN** el botón está deshabilitado con "Autorice al proveedor para activar el contrato", y la petición directa responde HTTP 409 "No se activó el contrato: el proveedor no está autorizado"

#### Scenario: Requisito agregado mientras se activaba
- **WHEN** el Administrador A abre el expediente de un contrato con los requisitos completos, el Administrador B hace obligatoria la orden de compra y después A activa el contrato
- **THEN** la respuesta es HTTP 409 con "No se activó el contrato: faltan requisitos obligatorios (Orden de compra)" y el contrato sigue "Registrado"

#### Scenario: Contrato ya activo
- **WHEN** el Administrador envía la activación de un contrato "Activo"
- **THEN** la respuesta es HTTP 409 con "Sólo se puede activar un contrato Registrado" y no se agrega ningún registro de auditoría

#### Scenario: PMO intenta activar
- **WHEN** un PMO envía `POST /contracts/{contract_id}/activate`
- **THEN** la respuesta es HTTP 403 y el contrato no cambia

### Requirement: Requisitos en el listado de contratos
El listado de contratos SHALL mostrar el estatus de cada contrato en español, con un estilo distinto para "Registrado", "Activo" e "Inactivo", y la columna "Requisitos" con "Completos" o "Faltan N", calculada con la configuración vigente, también para los contratos activos. Los requisitos de los contratos de la página SHALL calcularse sin una consulta por contrato.

#### Scenario: Contrato por activar
- **WHEN** el Administrador abre `/contracts` y un contrato "Registrado" no tiene su contrato firmado
- **THEN** ese contrato muestra "Registrado" y "Faltan 1", y su proyecto liga a su expediente

#### Scenario: Contrato activo sin documentos
- **WHEN** existe un contrato "Activo" de antes de la migración, sin documentos
- **THEN** el listado lo muestra "Activo" con "Faltan 1"

### Requirement: Protección contra ediciones concurrentes
La página de configuración SHALL incluir la huella `config_version` de la configuración que muestra: el SHA-256 de la clave, el nivel y el estado activo de todos los requisitos del contrato. Si al guardar la huella recibida falta o no coincide con la de la configuración vigente, el sistema SHALL responder HTTP 409 sin guardar ningún cambio.

#### Scenario: Dos Administradores editan a la vez
- **WHEN** los Administradores A y B abren la configuración, A guarda un cambio y después B guarda el suyo
- **THEN** B recibe HTTP 409 con el mensaje "La configuración cambió mientras la editaba. Recargue la página." y sólo persiste el cambio de A

### Requirement: Auditoría de los requisitos del contrato
Cada cambio guardado SHALL generar un registro de auditoría con el `user_id` del Administrador:
- `CONTRACT_REQUIREMENTS_UPDATED` al guardar la configuración, con el nivel anterior y el nuevo de cada requisito que cambió;
- `CONTRACT_DOCUMENT_TYPE_CREATED` al dar de alta un requisito, con su clave, nombre, nivel y si admite varios archivos;
- `CONTRACT_DOCUMENT_TYPE_UPDATED` al editar un requisito, con los valores anteriores y nuevos de los campos que cambiaron;
- `CONTRACT_DOCUMENT_TYPE_STATUS_CHANGED` al desactivar o reactivar un requisito;
- `CONTRACT_DOCUMENT_UPLOADED` o `CONTRACT_DOCUMENT_REPLACED` al cargar un documento, con su tipo y el contrato;
- `CONTRACT_STATUS_CHANGED` al activar un contrato, con `old_value = {"status": "REGISTERED"}` y `new_value = {"status": "ACTIVE"}`.

Una operación rechazada o un guardado sin cambios MUST NOT generar registros de auditoría.

#### Scenario: Cambio de nivel auditado
- **WHEN** el Administrador cambia "Orden de compra" de Opcional a Obligatorio y guarda
- **THEN** `audit_logs` contiene un registro `CONTRACT_REQUIREMENTS_UPDATED` con su `user_id`, `old_value = {"CONTRACT_PURCHASE_ORDER": "OPTIONAL"}` y `new_value = {"CONTRACT_PURCHASE_ORDER": "REQUIRED"}`

#### Scenario: Activación auditada
- **WHEN** el Administrador activa un contrato
- **THEN** `audit_logs` contiene `CONTRACT_STATUS_CHANGED` sobre ese contrato, con su `user_id`

#### Scenario: Operación rechazada sin auditoría
- **WHEN** una operación de configuración, de carga o de activación se rechaza con HTTP 400, 403 o 409
- **THEN** no se agrega ningún registro a `audit_logs`

## 9. Deltas sobre capacidades existentes

Todas parten de las specs **después de archivar** `requisitos-alta-proveedor` (HU-21).

### 9.1 `requisitos-alta-proveedor`

Destino: `openspec/changes/requisitos-alta-contrato/specs/requisitos-alta-proveedor/spec.md`. Los requisitos modificados reproducen el bloque completo vigente (sección 8 de HU-21) con los cambios aplicados: "Contrato" pasa a No aplica fijo.

```markdown
## MODIFIED Requirements

### Requirement: Catálogo de requisitos de alta
El sistema SHALL mantener un catálogo persistente de los documentos que forman el expediente del proveedor (requisitos de alta). Cada requisito SHALL tener:
- una clave inmutable, que es el valor que se guarda en `documents.document_type` de los documentos del expediente;
- un nombre en español y una descripción opcional, que se muestran en el expediente;
- si es un requisito del sistema o uno definido por el Administrador;
- si está activo;
- un nivel para cada tipo de proveedor (persona moral, persona física e internacional): `REQUIRED` ("Obligatorio"), `OPTIONAL` ("Opcional") o `NOT_APPLICABLE` ("No aplica").

El tipo de proveedor SHALL determinarse así: un proveedor con `origin = INTERNATIONAL` es Internacional, sin importar su tipo de persona; uno nacional es Persona moral o Persona física según su `supplier_type`.

El catálogo SHALL incluir estos requisitos del sistema con estos valores (clave · nombre · persona moral · persona física · internacional):
- `INCORPORATION_ACT` · Acta constitutiva · Obligatorio · No aplica · No aplica;
- `POWER_OF_ATTORNEY` · Poderes · Obligatorio · No aplica · No aplica;
- `TAX_STATUS` · Cédula fiscal · Obligatorio · Obligatorio · No aplica;
- `LEGAL_REP_ID` · Identificación del representante legal · Obligatorio · No aplica · No aplica;
- `LEGAL_REP_ADDRESS_PROOF` · Comprobante de domicilio del representante legal · Obligatorio · No aplica · No aplica;
- `ADDRESS_PROOF` · Comprobante de domicilio · Obligatorio · Obligatorio · No aplica;
- `BANK_STATEMENT` · Estado de cuenta bancario · Obligatorio · Obligatorio · No aplica;
- `OFFICIAL_ID` · Identificación oficial · No aplica · Obligatorio · No aplica;
- `SAT_OPINION` · Opinión de cumplimiento · Opcional · Opcional · No aplica;
- `ECONOMIC_PROPOSAL` · Propuesta económica · Opcional · Opcional · No aplica;
- `DUE_DILIGENCE` · Debida diligencia · Opcional · No aplica · No aplica;
- `LOCATION` · Ubicación · Opcional · Opcional · No aplica;
- `SUPPLIER_CONTRACT` · Contrato · No aplica · No aplica · No aplica, fijo: el contrato firmado se carga en cada contrato (capacidad `requisitos-alta-contrato`).

#### Scenario: Catálogo inicial tras la migración
- **WHEN** se aplican las migraciones sobre una base con proveedores y documentos de expediente existentes
- **THEN** el catálogo contiene los 13 requisitos del sistema, activos y con los valores anteriores; ningún proveedor cambia de estatus y cada documento conserva su `document_type`

#### Scenario: Nombres en español
- **WHEN** el Administrador abre el expediente de un proveedor
- **THEN** los requisitos se muestran por su nombre del catálogo (por ejemplo "Cédula fiscal" y "Poderes"), no por su clave

#### Scenario: Contrato cargado antes en el expediente
- **WHEN** un proveedor tenía cargado un documento `SUPPLIER_CONTRACT` antes de la migración de `requisitos-alta-contrato`
- **THEN** su expediente ya no lista "Contrato" entre los requisitos, y "Otros documentos del expediente" lo lista y permite descargarlo

### Requirement: Configuración de los requisitos por tipo de proveedor
La página de configuración SHALL mostrar una fila por cada requisito activo, con su nombre, su descripción y un selector de nivel para Persona moral, otro para Persona física y otro para Internacional. Primero aparecen los requisitos del sistema, en el orden del catálogo, y después los del Administrador, por nombre.

Los tres niveles de `SUPPLIER_CONTRACT` SHALL ser fijos en No aplica: la página los muestra como texto con el ícono de candado y el motivo "Se carga en cada contrato", sin selectores. Una petición que intente cambiarlos SHALL rechazarse con HTTP 409 y el mensaje "Contrato tiene un nivel fijo para <tipo de proveedor en plural>" (por ejemplo, "personas morales"), sin guardar ningún cambio.

Al guardar, el sistema SHALL validar todos los niveles recibidos y actualizar en una sola transacción los que cambiaron. Un nivel distinto de `REQUIRED`, `OPTIONAL` o `NOT_APPLICABLE`, o la falta de un nivel editable de un requisito activo, SHALL rechazar el guardado completo con HTTP 400. Si ningún nivel cambió, el sistema SHALL informar "Sin cambios" sin modificar nada.

#### Scenario: Hacer opcional un requisito
- **WHEN** el Administrador cambia "Poderes" a Opcional en la columna Persona moral y guarda
- **THEN** la página muestra "Configuración guardada", y el expediente de una persona moral "Registrado" sin poderes muestra "Poderes" como "Opcional · Pendiente" y no lo cuenta entre los obligatorios pendientes

#### Scenario: Exigir un requisito al proveedor internacional
- **WHEN** el Administrador cambia "Estado de cuenta bancario" a Obligatorio en la columna Internacional y guarda
- **THEN** el expediente de un proveedor internacional muestra "Estado de cuenta bancario" como Obligatorio, y el proveedor no puede autorizarse sin ese documento

#### Scenario: Contrato con nivel fijo
- **WHEN** el Administrador abre la configuración
- **THEN** la fila "Contrato" muestra "No aplica" con candado en las tres columnas y el motivo "Se carga en cada contrato", sin selectores

#### Scenario: Petición manipulada sobre el Contrato
- **WHEN** la petición trae `OPTIONAL` como nivel de Persona moral de `SUPPLIER_CONTRACT`, junto con otros cambios válidos
- **THEN** la respuesta es HTTP 409 con el mensaje "Contrato tiene un nivel fijo para personas morales" y no se guarda ningún cambio

#### Scenario: Guardar sin cambios
- **WHEN** el Administrador guarda la configuración sin modificar ningún nivel
- **THEN** la página muestra "Sin cambios" y no se agrega ningún registro de auditoría

#### Scenario: Nivel inválido
- **WHEN** la petición trae `MANDATORY` como nivel de un requisito, junto con otros cambios válidos
- **THEN** la respuesta es HTTP 400 con el mensaje "Nivel de exigencia inválido" y no se guarda ningún cambio

### Requirement: Requisitos que aplican a cada proveedor
Los requisitos que aplican a un proveedor SHALL ser los requisitos activos cuyo nivel para su tipo de proveedor es Obligatorio u Opcional. Los requisitos exigibles SHALL ser los Obligatorios y, si el alta es por cotización o licitación (`economic_proposal`), también "Propuesta económica" cuando su nivel no es No aplica. Un requisito SHALL cumplirse con un documento vigente (`is_current`) de su tipo en el expediente del proveedor (`invoice_id` nulo); la antigüedad del documento no afecta el cumplimiento.

`POST /suppliers/{supplier_id}/documents` SHALL rechazar con HTTP 400 y el mensaje "El documento no aplica a este proveedor", antes de escribir el archivo, un tipo que no aplica al proveedor: con nivel No aplica para su tipo, inactivo o inexistente. Las verificaciones existentes de permisos, contenido y tamaño SHALL mantenerse.

#### Scenario: Persona moral nacional
- **WHEN** con la configuración inicial se abre el expediente de una persona moral nacional
- **THEN** se piden como obligatorios Acta constitutiva, Poderes, Cédula fiscal, Identificación del representante legal, Comprobante de domicilio del representante legal, Comprobante de domicilio y Estado de cuenta bancario; se ofrecen como opcionales Opinión de cumplimiento, Propuesta económica, Debida diligencia y Ubicación; no se ofrecen Identificación oficial ni Contrato

#### Scenario: Persona física nacional
- **WHEN** con la configuración inicial se abre el expediente de una persona física nacional
- **THEN** se piden como obligatorios Identificación oficial, Cédula fiscal, Comprobante de domicilio y Estado de cuenta bancario, y no se ofrecen Acta constitutiva, Poderes ni Contrato

#### Scenario: Proveedor internacional con la configuración inicial
- **WHEN** con la configuración inicial se abre el expediente de un proveedor internacional
- **THEN** el panel muestra "Sin requisitos de alta configurados para proveedores internacionales" y el proveedor puede autorizarse sin documentos

#### Scenario: Alta por cotización
- **WHEN** una persona moral tiene `economic_proposal` y "Propuesta económica" es Opcional para Persona moral
- **THEN** su expediente muestra "Propuesta económica" como Obligatorio, con la nota "Alta por cotización o licitación", y el proveedor no puede autorizarse sin ella

#### Scenario: Documento que no aplica
- **WHEN** se envía un documento con `document_type = SUPPLIER_CONTRACT` al expediente de una persona moral
- **THEN** la respuesta es HTTP 400 con el mensaje "El documento no aplica a este proveedor" y no se escribe ningún archivo en `storage/`
```

### 9.2 `motor-validacion`

Destino: `openspec/changes/requisitos-alta-contrato/specs/motor-validacion/spec.md`.

```markdown
## ADDED Requirements

### Requirement: Contrato y anexos disponibles según los requisitos del contrato
Al validar una factura, DOC-005 (`ERROR`) SHALL evaluar los requisitos obligatorios del contrato de la factura con la configuración vigente (capacidad `requisitos-alta-contrato`):
- `PASS` con el mensaje "Contrato/anexo disponible" si cada requisito obligatorio activo tiene al menos un documento vigente ligado al contrato;
- `FAIL` con el mensaje "Faltan documentos del contrato: <nombre>, <nombre>" si falta alguno, con los nombres en el orden del catálogo;
- `FAIL` con el mensaje "Falta contrato/anexo" si la factura no tiene contrato.

Los documentos de la factura y del expediente del proveedor MUST NOT contar para DOC-005. Un `FAIL` SHALL impedir el envío. Una factura que ya salió de los estados editables SHALL conservar su resultado aunque la configuración o los documentos del contrato cambien después.

#### Scenario: Factura demo con contrato completo
- **WHEN** se valida la factura demo A-CORRECTA después de la migración y de `reset_demo`
- **THEN** DOC-005 resulta `PASS` con "Contrato/anexo disponible"

#### Scenario: Contrato activo sin contrato firmado
- **WHEN** se valida una factura editable cuyo contrato "Activo" existía antes de la migración y no tiene documentos
- **THEN** DOC-005 resulta `FAIL` con "Faltan documentos del contrato: Contrato" y el envío no procede

#### Scenario: Requisito obligatorio agregado después de la activación
- **WHEN** el Administrador hace obligatoria la orden de compra y se valida una factura editable de un contrato activo sin orden de compra
- **THEN** DOC-005 resulta `FAIL` con "Faltan documentos del contrato: Orden de compra", el envío no procede y el contrato sigue "Activo"

#### Scenario: Contrato cargado en la factura
- **WHEN** una factura tiene cargado un documento "Contrato" de los archivos de la factura (HU-04) y su contrato no tiene contrato firmado
- **THEN** DOC-005 resulta `FAIL` con "Faltan documentos del contrato: Contrato"

## MODIFIED Requirements

### Requirement: Reglas documentales según los archivos mínimos configurados
(Se reproduce completo el bloque vigente de `openspec/specs/motor-validacion/spec.md`, con un solo cambio: la viñeta
"- DOC-005, DOC-006 y DOC-007 no cambian."
se sustituye por
"- DOC-005 se evalúa conforme a "Contrato y anexos disponibles según los requisitos del contrato"; DOC-006 y DOC-007 no cambian."
Los seis escenarios vigentes se conservan sin cambios.)
```

### 9.3 `integridad-datos`

Destino: `openspec/changes/requisitos-alta-contrato/specs/integridad-datos/spec.md`.

```markdown
## MODIFIED Requirements

### Requirement: Restricciones CHECK sobre estados, montos y vigencias
(Se reproduce completo el bloque que deja HU-21 —sección 9.3 de su HU— con estos cambios:
1. En la primera viñeta, "nivel de exigencia de archivo o de requisito de alta" pasa a "nivel de exigencia de archivo, de requisito de alta o de requisito del contrato".
2. En el párrafo de enumeraciones tipadas, se agrega "`contract_document_types.requirement` SHALL ser una enumeración tipada (`REQUIRED`, `OPTIONAL`, `NOT_APPLICABLE`)" y `contracts.status` pasa a "(`REGISTERED`, `ACTIVE`, `INACTIVE`)".
3. Se agregan los dos escenarios siguientes; los vigentes se conservan.)

#### Scenario: Estatus de contrato fuera de catálogo
- **WHEN** se ejecuta `UPDATE contracts SET status = 'PENDIENTE'`
- **THEN** la base de datos rechaza la operación

#### Scenario: Nivel de requisito del contrato fuera de catálogo
- **WHEN** se ejecuta `UPDATE contract_document_types SET requirement = 'MANDATORY' WHERE code = 'CONTRACT_ANNEXES'`
- **THEN** la base de datos rechaza la operación

### Requirement: Integridad del catálogo de requisitos de alta
La base de datos SHALL imponer sobre `supplier_document_types`:
- unicidad de `code` y de `lower(name)`;
- que un requisito del sistema (`is_system`) esté siempre activo;
- que `SUPPLIER_CONTRACT` tenga No aplica en sus tres niveles.

#### Scenario: Requisito del sistema desactivado por SQL
- **WHEN** se ejecuta `UPDATE supplier_document_types SET is_active = false WHERE code = 'TAX_STATUS'`
- **THEN** la base de datos rechaza la operación

#### Scenario: Nombre repetido con otra capitalización
- **WHEN** se inserta un requisito con `name = 'PODERES'`
- **THEN** la base de datos rechaza la operación

#### Scenario: Contrato devuelto al alta del proveedor por SQL
- **WHEN** se ejecuta `UPDATE supplier_document_types SET persona_moral_requirement = 'OPTIONAL' WHERE code = 'SUPPLIER_CONTRACT'`
- **THEN** la base de datos rechaza la operación

## ADDED Requirements

### Requirement: Integridad del catálogo de requisitos del contrato
La base de datos SHALL imponer sobre `contract_document_types`:
- unicidad de `code` y de `lower(name)`;
- que un requisito del sistema (`is_system`) esté siempre activo;
- que `SIGNED_CONTRACT` sea siempre `REQUIRED`.

#### Scenario: Contrato opcional por SQL
- **WHEN** se ejecuta `UPDATE contract_document_types SET requirement = 'OPTIONAL' WHERE code = 'SIGNED_CONTRACT'`
- **THEN** la base de datos rechaza la operación

#### Scenario: Requisito del sistema desactivado por SQL
- **WHEN** se ejecuta `UPDATE contract_document_types SET is_active = false WHERE code = 'CONTRACT_ANNEXES'`
- **THEN** la base de datos rechaza la operación

#### Scenario: Nombre repetido con otra capitalización
- **WHEN** se inserta un requisito del contrato con `name = 'ANEXOS'`
- **THEN** la base de datos rechaza la operación

### Requirement: Documentos del contrato con un solo dueño
`documents.contract_id` SHALL ser una llave foránea a `contracts` con `ON DELETE RESTRICT`. La base de datos SHALL rechazar un documento con `contract_id` que tenga también `invoice_id` o `supplier_id`.

#### Scenario: Documento de contrato y de factura
- **WHEN** se ejecuta `UPDATE documents SET invoice_id = 1 WHERE contract_id IS NOT NULL`
- **THEN** la base de datos rechaza la operación

#### Scenario: Borrado de un contrato con documentos
- **WHEN** se ejecuta `DELETE FROM contracts WHERE id = X` y el contrato X tiene documentos
- **THEN** la base de datos rechaza la operación
```

### 9.4 `listados-paginados`

Destino: `openspec/changes/requisitos-alta-contrato/specs/listados-paginados/spec.md`.

```markdown
## MODIFIED Requirements

### Requirement: El alta muestra el registro creado
Tras crear un usuario o una clave de catálogo, el sistema SHALL redirigir al listado buscando el registro creado (correo del usuario o clave) con el aviso "Usuario creado" o "Clave agregada". El alta de un proveedor SHALL seguir llevando a su expediente, y el alta de un contrato SHALL llevar al expediente del contrato con el aviso "Contrato creado. Cargue sus requisitos para activarlo.".

#### Scenario: Usuario nuevo visible
- **WHEN** hay 40 usuarios y el Administrador crea "Joshua Bolaños Hernández" con `jobhdev@gmail.com`
- **THEN** llega a `/admin/users?q=jobhdev%40gmail.com&ok=created`, ve "Usuario creado" y el usuario en la lista

#### Scenario: Contrato nuevo
- **WHEN** hay 40 contratos y el Administrador crea el contrato del proyecto "Portal Proveedores 2027"
- **THEN** llega a `/contracts/{contract_id}` del contrato creado y ve "Contrato creado. Cargue sus requisitos para activarlo."
```

### 9.5 `observabilidad`

Destino: `openspec/changes/requisitos-alta-contrato/specs/observabilidad/spec.md`.

```markdown
## MODIFIED Requirements

### Requirement: Registro de eventos técnicos del flujo
(Se reproduce completo el bloque que deja HU-21 —sección 9.4 de su HU— con un solo cambio en la primera viñeta:
"- subida de documento: `invoice_id` o `supplier_id`, tipo documental, extensión y tamaño en bytes;"
pasa a
"- subida de documento: `invoice_id`, `supplier_id` o `contract_id`, tipo documental, extensión y tamaño en bytes;".
Se agrega el escenario siguiente; los vigentes se conservan.)

#### Scenario: Subida de documento de contrato registrada
- **WHEN** el Administrador carga el contrato firmado de un contrato
- **THEN** el log contiene un evento `document.uploaded` con `contract_id`, `document_type = "SIGNED_CONTRACT"`, `extension` y `size_bytes`, sin el nombre original del archivo
```

## 10. Notas de diseño (insumo para `design.md`)

| # | Decisión | Alternativas descartadas y motivo |
| --- | --- | --- |
| D1 | Tabla `contract_document_types` (`code`, `name`, `description`, `is_system`, `is_active`, `requirement`, `allows_multiple`, `created_at`) que reutiliza la enumeración `DocumentRequirement` | Agregar un "alcance" a `supplier_document_types`: mezcla una matriz por tipo de proveedor con un nivel único. Reutilizar `invoice_document_types`: mismo problema por origen, y la RD-02 de HU-04 separa los catálogos |
| D2 | Un solo nivel por requisito (RD-01) | Una columna por origen como HU-04: ninguna fuente distingue el contrato de un proveedor nacional del de uno internacional. Se agrega si negocio lo pide |
| D3 | `documents.contract_id` (llave foránea `RESTRICT`, con índice). Un documento del contrato no lleva `supplier_id` ni `invoice_id`, y un `CHECK` lo garantiza (`contract_id IS NULL OR (invoice_id IS NULL AND supplier_id IS NULL)`) | Llenar también `supplier_id`, como los documentos de factura: el expediente de HU-21 y su descarga identifican el expediente por `supplier_id` con `invoice_id` nulo, y el contrato firmado aparecería en "Otros documentos del expediente" del proveedor. Habría que filtrar `contract_id` en cuatro lugares de HU-21 |
| D4 | Un servicio `contract_requirements_service`: catálogo, requisitos que aplican, obligatorios, checklist, pendientes por contrato y por página, huella, guardado y auditoría. Lo usan el expediente, el listado, la carga, la activación y DOC-005. Reutiliza los validadores de nombre y descripción que HU-21 extrajo en `app/schemas` | Un servicio genérico para HU-21 y HU-22: los dos catálogos tienen dimensiones distintas (tres perfiles frente a nivel único y varios archivos); la abstracción costaría más que el código repetido |
| D5 | `ContractStatus.REGISTERED`, etiquetas `CONTRACT_STATUS_LABELS` y `Contract.status` con valor por defecto `REGISTERED`. La migración amplía el `CHECK` del estatus y no toca las filas existentes (RD-09) | Reutilizar `INACTIVE` como "por activar": confunde un contrato pendiente con uno dado de baja (P-07) |
| D6 | `POST /contracts/{contract_id}/activate`: `SELECT … FOR UPDATE` del contrato; verifica estatus, proveedor y requisitos en la misma transacción; las respuestas 409 vuelven a mostrar el expediente con el mensaje | Activar automáticamente al completar los requisitos: la solicitud pide "querer activarlo", y el Administrador puede esperar la firma o el inicio de la vigencia. Activar desde el listado de forma masiva: no lo pide la solicitud |
| D7 | Niveles fijos con el patrón de HU-04: constantes de nivel fijo y motivo, `CHECK` en la base (`ck_contract_document_types_fixed_levels` para `SIGNED_CONTRACT`; `ck_supplier_document_types_fixed_levels` para `SUPPLIER_CONTRACT`), candado en la pantalla y 409 al manipular la petición | Sin niveles fijos, como el D12 de HU-21: aquí el error sí rompe algo (contratos activos sin respaldo, o el contrato firmado de vuelta en el expediente del proveedor) |
| D8 | `allows_multiple` se fija al crear el requisito y no se edita. Con un archivo, la carga reemplaza al vigente; con varios, agrega o reemplaza el elegido en "Reemplaza a" | Hacerlo editable: al pasar de varios a uno quedarían varios vigentes y habría que decidir cuál se conserva. Si negocio cambia la orden de compra a un solo archivo (P-04), se ajusta la siembra antes de desplegar |
| D9 | Huella `config_version` (SHA-256 de clave, nivel y estado activo), igual que el D8 de HU-04 | Bloqueo pesimista o última escritura gana: mismos motivos que en HU-04 |
| D10 | Claves del sistema nuevas, distintas de las de la factura: `SIGNED_CONTRACT`, `CONTRACT_PURCHASE_ORDER`, `CONTRACT_ANNEXES`. Clave `REQ_CONTRATO_<id>` para los requisitos del Administrador, asignada tras el `flush` | Reutilizar `CONTRACT`, `PURCHASE_ORDER` o `CONTRACT_ANNEX`: `documents.document_type` no tiene llave foránea (D11 de HU-21) y la misma clave en dos catálogos haría ambiguos los reportes y la auditoría |
| D11 | Revisión Alembic `0017_contract_document_types`, posterior a `0016_supplier_document_types`: crea la tabla y siembra los 3 requisitos; agrega `documents.contract_id` con su índice y su `CHECK`; amplía el `CHECK` de `contracts.status`; deja `SUPPLIER_CONTRACT` en No aplica y agrega su `CHECK`. El downgrade lanza `NotImplementedError` si hay contratos "Registrado", documentos de contrato o requisitos del Administrador; si no, revierte todo y regresa `SUPPLIER_CONTRACT` a Opcional · Opcional · No aplica | Retirar `SUPPLIER_CONTRACT` de la siembra de HU-21: sus documentos ya cargados se mostrarían con la clave cruda en "Otros documentos del expediente". Editar `0016`: prohibido por la regla "Una revisión por cambio de modelo" |
| D12 | El menú agrupa las tres configuraciones bajo la etiqueta "Requisitos mínimos" (`nav-label` de `base.html`): "Archivos de factura", "Alta de proveedor" y "Alta de contrato". Las páginas y sus rutas no cambian | Una sola página con pestañas: mezcla tres rutas, tres huellas y tres suites de pruebas sin ganancia funcional. Dejar los enlaces sueltos: no responde a la "sección en el módulo de Requisitos mínimos" que pide la aclaración |
| D13 | Expediente del contrato en `contracts/detail.html` con formularios HTML normales. El diálogo de "Activar contrato" reutiliza el modal de confirmación de la autorización de proveedores, sin diálogos nativos ni scripts en línea (CSP `default-src 'self'`, change `interfaz-sin-dialogos-nativos`). El formulario de enmienda del monto se queda en el listado | Mover las enmiendas al expediente: cambia `trazabilidad-contratos` y `listados-paginados` ("Las acciones conservan la página") sin que la solicitud lo pida |
| D14 | DOC-005 recibe el contrato con sus documentos vigentes y los requisitos obligatorios; `document_rules()` deja de recibir `contract_available: bool` | Mantener `contract_available` y agregar otra regla: dos reglas sobre lo mismo, y DOC-005 seguiría sin revisar nada |
| D15 | Listado: los documentos vigentes de los contratos de la página se leen en una consulta y el catálogo en otra. Sin N+1 (spec `listados-paginados`) | Calcular por contrato: una consulta por fila |

**Riesgos y mitigaciones**

- **Contratos activos sin documentos** → con DOC-005 en `ERROR`, sus facturas editables no pueden enviarse hasta que el Administrador cargue el contrato firmado (P-06). Los datos demo no se ven afectados: `seed_db` carga el contrato de los tres contratos demo. En un ambiente con contratos reales, el listado marca a los afectados con "Faltan 1" y la carga funciona sobre contratos activos (RD-08).
- **Pruebas que crean contratos sin estatus** → con el nuevo valor por defecto nacen "Registrado" y fallan SUP-002 o el alta de factura. Ajustar los fixtures de `test_archivos_minimos.py`, `test_factura_internacional.py`, `test_integridad.py`, `test_listados_paginados.py` y `test_registro_envio.py` para crear contratos `ACTIVE` con su contrato firmado, con un helper común en `conftest.py`.
- **`test_contratos.py` y `test_listados_paginados.py` esperan la redirección al listado** → cambian a la redirección al expediente (sección 9.4).
- **Proveedor "Registrado" con contrato listo** → el contrato espera a que se autorice al proveedor. El expediente lo dice y liga al proveedor (P-05).
- **Orden de los changes** → `requisitos-alta-contrato` modifica `requisitos-alta-proveedor` y parte de las versiones de HU-21 de `integridad-datos` y `observabilidad`. Proponerlo antes de archivar HU-21 genera deltas contra requisitos que todavía no existen en `openspec/specs`.
- **Doble carga del contrato** → mientras P-02 no se responda, el proveedor puede seguir cargando "Contrato" y "Anexo del contrato" en cada factura. No afecta DOC-005 (RD-13), sólo duplica archivos.

## 11. Impacto

| Área | Cambio |
| --- | --- |
| `app/core/constants.py` | `ContractStatus.REGISTERED` y `CONTRACT_STATUS_LABELS`; niveles fijos y motivos de `SIGNED_CONTRACT` y `SUPPLIER_CONTRACT` (D7) |
| `app/models/__init__.py` | Modelo `ContractDocumentType`; `Document.contract_id` y `CHECK` de dueño único; `Contract.status` por defecto `REGISTERED`; `CHECK` de nivel fijo en `SupplierDocumentType` |
| `alembic/versions/` | Nueva revisión `0017_contract_document_types` (D11) |
| `app/schemas/__init__.py` | `ContractDocumentTypeCreate` y `ContractDocumentTypeUpdate` |
| `app/services/` | Nuevo `contract_requirements_service.py` (D4). `supplier_requirements_service.py`: nivel fijo de `SUPPLIER_CONTRACT` al guardar. `file_service.py`: `save_contract_file()` en `contracts/<id>` |
| `app/rules/document_rules.py` y `app/services/validation_engine.py` | DOC-005 con los requisitos del contrato (D14) |
| `app/routers/contracts.py` | Alta "Registrado" con redirección al expediente; `GET /contracts/{contract_id}`; carga y descarga de documentos; `POST /contracts/{contract_id}/activate`; requisitos y estatus en el listado |
| `app/routers/admin.py` | Rutas `/admin/contract-requirements*`; candado de `SUPPLIER_CONTRACT` en `/admin/supplier-requirements` |
| `app/templates/contracts/detail.html` | Nueva página: datos, panel "Requisitos del contrato", "Otros documentos del contrato", carga, enmiendas y botón "Activar contrato" con su diálogo |
| `app/templates/contracts/list.html` | Estatus en español, columna "Requisitos" y liga al expediente |
| `app/templates/admin/contract_requirements.html` | Nueva pantalla: niveles, alta, edición y requisitos inactivos |
| `app/templates/admin/supplier_requirements.html` | Fila "Contrato" con candado |
| `app/templates/base.html` | Grupo "Requisitos mínimos" en el menú (D12) |
| `app/static/js/` | Diálogo de activación, reutilizando el de la autorización de proveedores |
| `scripts/seed_db.py` | Carga el contrato firmado de los tres contratos demo (`contracts/<id>`), que siguen `ACTIVE` |
| `README.md` | Sección de requisitos del contrato, estatus "Registrado", activación y DOC-005 |
| `tests/` | Nuevo `test_requisitos_contrato.py`, con un escenario por requisito. Ajustes en `test_contratos.py`, `test_requisitos_alta.py`, `test_archivos_minimos.py`, `test_factura_internacional.py`, `test_registro_envio.py`, `test_listados_paginados.py`, `test_observabilidad.py`, `test_migraciones.py`, `test_integridad.py`, `test_permissions.py` y `conftest.py` |
| `tests/hu/` | Ajuste de `05-HU-04-archivos-minimos.spec.ts` y `19-HU-21-requisitos-alta.spec.ts` por el menú; nueva especificación de HU-22 con su evidencia y su entrada en `hu-catalogo.json` |
| `requirements.txt` / `requirements.lock` | Sin dependencias nuevas |

## 12. Dependencias

- **Depende de:** HU-21 (change `requisitos-alta-proveedor` archivado: catálogo de requisitos de alta, `SUPPLIER_CONTRACT` y patrón del checklist) y HU-02 (estatus "Autorizado" que exige la activación). Reutiliza el patrón de configuración y los niveles fijos de HU-04.
- **Modifica:** HU-21 ("Contrato" sale del alta del proveedor), la regla DOC-005 que consumen HU-12, HU-13 y HU-16, y el alta de contratos que hoy cubre `trazabilidad-contratos`.
- **Habilita** (con lo que cada HU recibe de esta):

| HU | Qué recibe de HU-22 | Qué le toca decidir a esa HU |
| --- | --- | --- |
| HU-04 | El contrato y sus anexos ya están en el contrato | Dejar de pedirlos por factura (P-02) y decidir la orden de compra por factura (P-03) |
| HU-13 y HU-16 | DOC-005 con el contrato completo | — |
| HU-18 y HU-19 | El PMO consulta el contrato firmado desde el expediente del contrato | Si el detalle de la factura liga al expediente de su contrato |

## 13. Definición de terminado

- [ ] Change `requisitos-alta-proveedor` archivado antes de proponer este.
- [ ] Change `requisitos-alta-contrato` creado con proposal, specs, design y tasks; `openspec validate requisitos-alta-contrato --strict` sin errores.
- [ ] Preguntas P-01 a P-08 respondidas por negocio o registradas como "Open Questions" en `design.md`.
- [ ] Cada escenario de las secciones 8 y 9 tiene al menos una prueba automatizada que pasa sobre la base PostgreSQL temporal de la sesión.
- [ ] La cobertura no baja del umbral vigente (`--cov-fail-under=93`).
- [ ] Revisión Alembic nueva; `alembic check` sin diferencias; downgrade conforme a D11.
- [ ] `scripts/check.py` en verde (ruff, pytest, `alembic check`, `pip-audit`).
- [ ] `reset_demo` reproduce el resultado de las 10 facturas demo; los tres contratos demo muestran "Activo" y "Requisitos del contrato completos", y DOC-005 resulta `PASS`.
- [ ] Suite Playwright de `tests/hu` en verde, con la nueva especificación de HU-22 y su evidencia en el PDF.
- [ ] Prueba manual: cambiar niveles; crear, editar, desactivar y reactivar un requisito; crear un contrato; intentar activarlo sin contrato firmado y con el proveedor sin autorizar; cargar el contrato y dos anexos; activarlo y registrar una factura con él.
- [ ] README actualizado.
- [ ] RF-20 incorporado a la siguiente versión de la ERS.
- [ ] Change archivado y specs sincronizadas (`/opsx:archive`).

## 14. Trazabilidad

| Elemento | Referencia |
| --- | --- |
| Solicitud de negocio (2026-10-02) | Texto de la sección 1: sección de configuración de requisitos del contrato, obligatorios u opcionales; pedirlos al dar de alta y activar el contrato. Lista: Contrato (obligatorio), Orden de compra (opcional), Anexos (opcional) |
| Aclaración del equipo (2026-10-02) | La configuración vive en Requisitos mínimos; los requisitos del alta del proveedor que corresponden al contrato pasan al contrato |
| Lineamientos de facturación 2024 v1.4.1 | 1.i: "Debe existir contrato vigente … para ello debe estar dado de alta en el catálogo de Asociados con el cumplimiento al 100% de los requisitos detallados en el 'Anexo A'". 1.iii: convenio de confidencialidad vigente. Anexo A: "De los requisitos para elaborar contrato", incluida la "Propuesta Económica autorizada por el Líder de ULTRASIST" |
| ERS v1.4 | RF-20 propuesto para esta HU. Modifica RF-19 (HU-21, propuesto) |
| HU-21 | Sección 6.3: `SUPPLIER_CONTRACT` Opcional, que esta HU fija en No aplica. Patrón del checklist y de la activación condicionada |
| HU-04 | Archivos de la factura `CONTRACT`, `CONTRACT_ANNEX` y `PURCHASE_ORDER` (P-02, P-03). Patrón de niveles fijos con candado |
| OpenSpec | Capacidad nueva `requisitos-alta-contrato`; deltas en `requisitos-alta-proveedor`, `motor-validacion`, `integridad-datos`, `listados-paginados` y `observabilidad`; sin cambios en `flujo-facturas` (ya exige contratos activos), `trazabilidad-contratos` (la activación actualiza `updated_at` y `updated_by` como cualquier modificación), `almacenamiento-documentos` ni `archivos-minimos-factura` |

## 15. Puntos a confirmar en la revisión

Interpretaciones de la solicitud que conviene validar con quien la hizo, además de las preguntas de 5.3:

1. **"Activar" es una acción explícita.** El contrato nace "Registrado" y el Administrador lo activa con un botón cuando tiene los requisitos; no se activa solo al completarlos.
2. **"Al dar de alta me debe pedir estos requisitos".** El alta crea el contrato y lleva a su expediente, donde el panel pide los requisitos; la activación los exige. No se agregan campos de archivo al formulario de alta.
3. **"Módulo de Requisitos mínimos".** Se interpreta como un grupo del menú de Administración con las tres configuraciones (factura, proveedor y contrato), cada una en su página.
4. **Requisitos que pasan del proveedor al contrato.** Sólo "Contrato". "Propuesta económica" es candidata, pero hoy depende de si el alta del proveedor fue por cotización; queda en P-01.
5. **Orden de compra del contrato frente a la de la factura.** Se tratan como documentos distintos; la de cada factura sigue siendo obligatoria (P-03).
6. **Proveedor autorizado para activar.** Se lee de los Lineamientos 1.i; si negocio no lo quiere, se quita sin afectar lo demás (P-05).
