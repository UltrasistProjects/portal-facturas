# HU-04 · Definición de archivos requeridos por tipo de proveedor

| Campo | Valor |
| --- | --- |
| ID | HU-04 |
| Rol | Administrador |
| Módulo | A. Administración y Configuración |
| Prioridad | Alta (alcance comprometido del MVP) |
| Origen | Documento de HUs (literal) — `HUs Portal Proveedores ULTRASIST_v2.docx` |
| Requisito funcional | RF-04 (ERS v1.3). Lo consumen RF-07 (HU-12) y RF-14 (HU-15) |
| Regla de negocio | Sin RN oficial (ERS §4.1). Reglas derivadas RD-01 a RD-10 (sección 5) |
| Change OpenSpec sugerido | `archivos-minimos-por-tipo-proveedor` |
| Capacidad nueva | `archivos-minimos-factura` |
| Capacidades modificadas | `motor-validacion`, `integridad-datos` |
| Estado | Lista para `/opsx:propose`. Las preguntas abiertas (sección 5.3) sólo cambian valores iniciales que el Administrador puede ajustar; no cambian la estructura |
| Estimación | Por definir en el refinamiento |
| Versión / fecha | 1.0 · 2026-09-25 · Equipo Técnico |

## Cómo usar este documento con OpenSpec

Ejecutar `/opsx:propose archivos-minimos-por-tipo-proveedor` con este documento como entrada. Cada sección alimenta un artefacto:

| Artefacto OpenSpec | Secciones de esta HU |
| --- | --- |
| `proposal.md` — Why | 1, 2 |
| `proposal.md` — What Changes | 3, 6 |
| `proposal.md` — Capabilities | Tabla de metadatos, 8, 9 |
| `proposal.md` — Impact | 11 |
| `specs/archivos-minimos-factura/spec.md` | 8 (se copia tal cual bajo `## ADDED Requirements`) |
| `specs/motor-validacion/spec.md`, `specs/integridad-datos/spec.md` | 9 (bloques listos para copiar) |
| `design.md` | 4, 5, 10 (las preguntas de 5.3 van a "Open Questions") |
| `tasks.md` | 11, 13 |

---

## 1. Historia de usuario

**Texto literal (documento de HUs):**

> Yo como administrador requiero definir los archivos mínimos que debe subir el proveedor cuando se trate un proveedor “Nacional” o “internacional” para poder enviar su factura.

**Reformulación:**

- **Como** Administrador del portal,
- **quiero** definir, para cada origen de proveedor (Nacional o Internacional), qué archivos de la factura son obligatorios, cuáles son opcionales y cuáles no aplican,
- **para** que el proveedor sepa qué debe cargar y el sistema no le permita enviar la factura a revisión sin esos archivos.

En esta HU, "tipo de proveedor" es el **origen** (`suppliers.origin`: Nacional / Internacional) que registró HU-01. No es el tipo de persona física o moral (`supplier_type`), que sólo determina el expediente del Anexo A.

**Regla de negocio asociada:** ninguna oficial (ERS §3.5 y §4.1: "HU-04 · Sin RN"). Las reglas de la sección 5 se derivan de las fuentes del proyecto.

## 2. Contexto y motivación

El Alcance del MVP (minuta del 21-sep-2026) separa dos flujos de carga:

- **Proveedores nacionales:** "carga de PDF y XML; documentos soporte".
- **Proveedores extranjeros:** "carga de Invoice en PDF y documentos soporte".

La ERS convierte esa diferencia en RF-04, un "requisito base de configuración": el Administrador define los archivos mínimos por origen, y el registro de la factura los exige, tanto la nacional (RF-07, HU-12: "cargar los archivos mínimos necesarios que fueron definidos desde la configuración del sistema") como la internacional (RF-14, HU-15).

Hoy el PoC exige los mismos cuatro archivos a todos los proveedores, fijos en código (DOC-001 a DOC-004: XML, PDF, orden de compra y Vo.Bo.). Eso tiene dos problemas:

- **Un proveedor internacional no puede cumplir:** no emite CFDI, así que DOC-001 ("Falta XML CFDI", `CRITICAL`) bloquearía siempre su factura.
- **Cambiar un requisito exige un despliegue:** por ejemplo, definir los documentos soporte del extranjero cuando se analicen los tres ejemplos de invoices acordados en la minuta (responsable: Octavio Rivera, 22-sep-2026).

HU-01 dejó el origen Nacional/Internacional en el catálogo de proveedores precisamente para esta HU.

**Archivos de la factura frente a expediente del proveedor.** Son dos conceptos distintos y esta HU sólo cubre el primero:

| Concepto | Qué es | Cuándo se entrega | Dónde vive |
| --- | --- | --- | --- |
| Archivos mínimos de la factura (esta HU) | XML, PDF o Invoice, orden de compra, Vo.Bo. y soportes | Con **cada** factura | Carga documental de la factura; reglas DOC |
| Expediente del proveedor (Anexo A) | Constancia de Situación Fiscal, Opinión del SAT, estado de cuenta, etc. | **Una vez**, para contratar (Lineamientos 1.i: "De los requisitos para elaborar contrato") | Detalle del proveedor; reglas SUP-003 y SUP-004 |

## 3. Alcance

### Dentro del alcance

- Catálogo persistente de tipos de documento de factura, con nombre en español, descripción y formatos admitidos. Incluye los nueve tipos actuales y el nuevo tipo "Invoice (PDF)".
- Pantalla **Administración › Archivos mínimos** para fijar el nivel de cada tipo por origen: Obligatorio, Opcional o No aplica.
- Niveles fijos que el Administrador no puede cambiar: XML y PDF del CFDI para el Nacional, Invoice para el Internacional.
- Alta, edición, desactivación y reactivación de tipos de documento soporte definidos por el Administrador.
- Carga documental de la factura limitada a los tipos que aplican al origen del proveedor y a los formatos de cada tipo.
- Checklist de la carga documental con obligatorios, opcionales y pendientes.
- Reglas documentales del motor según la configuración: un archivo obligatorio faltante deja la factura en "Requiere corrección" y por tanto no puede enviarse a revisión.
- Auditoría de la configuración y protección contra ediciones concurrentes.
- Migración con valores iniciales que conservan el comportamiento actual para los proveedores nacionales.

### Fuera del alcance

| Tema | Motivo / dónde se atiende |
| --- | --- |
| Expediente del proveedor (Anexo A) y reglas SUP-003/SUP-004 | Requisito para contratar, no archivo de la factura (RD-02). Sin cambios |
| Expediente del proveedor internacional (HU-01 lo remitió a esta HU) | El Anexo A sólo cubre personas mexicanas y ninguna fuente define el equivalente extranjero. Pregunta abierta P-02; se propone resolverlo en HU-16, que valida los "datos del proveedor" extranjero |
| Estatus "Cargada" y "Enviada" | HU-12, HU-13, HU-15 y HU-16. Esta HU usa los estados actuales del PoC |
| Duplicados del Invoice por nombre de archivo | HU-15 |
| Reglas XML, de contrato y de proveedor para facturas internacionales (hoy fallan porque no hay XML) | HU-16. Esta HU sólo resuelve la parte documental |
| "Acuse de cancelación" | HU-14: se exige al cancelar, no al enviar |
| Exigencias condicionales, como los complementos de pago previos "cuando aplique" | RD-09 |
| Exigencias por contrato, proyecto o tipo de persona | La HU sólo distingue Nacional e Internacional (RD-01) |
| Tamaño máximo por tipo de documento | Se conserva el límite global `MAX_UPLOAD_MB` |
| Otros catálogos administrables | HU-07 |

## 4. Situación actual del PoC

| Aspecto | Hoy | Brecha para HU-04 |
| --- | --- | --- |
| Tipos de documento de factura | Enumeración fija `DocumentType` (9 valores) en `app/core/constants.py` | No es configurable y no hay tipo para el Invoice extranjero |
| Nombres que ve el usuario | Se derivan de la clave: `t.value.replace('_',' ').title()` produce "Invoice Xml", "Purchase Order", "Approval" | Sin nombres en español ni descripción |
| Archivos exigidos | `app/rules/document_rules.py` fija DOC-001 (XML, `CRITICAL`) y DOC-002 a DOC-004 (PDF, orden de compra, Vo.Bo., `ERROR`) para todos | No distingue el origen: el Internacional siempre fallaría DOC-001 |
| Formatos por tipo | Cualquier extensión permitida sirve para cualquier tipo: se puede cargar un PDF como `INVOICE_XML` | Sin formatos por tipo; la minuta pide el Invoice "en PDF" |
| Página de carga documental | El selector y el checklist muestran los 9 tipos, todos como "Pendiente" | No distingue obligatorio de opcional ni oculta lo que no aplica |
| Configuración | `/admin/rules` es de sólo lectura sobre `BUSINESS_RULES` ("La edición persistente queda para una versión posterior") | No existe ninguna configuración persistente editable desde la aplicación |
| Origen del proveedor | `suppliers.origin` (`NATIONAL` / `INTERNATIONAL`) desde HU-01 | Base de la configuración; sin cambio |
| Bloqueo del envío | `POST /invoices/{id}/submit` exige `PREVALIDATED`, y la prevalidación sólo llega ahí sin ningún `FAIL` | Sin cambio: un archivo obligatorio faltante (`FAIL`) ya impide enviar |
| Expediente Anexo A | `SUPPLIER_REQUIREMENTS` por tipo de persona; reglas SUP-003 y SUP-004 | Fuera del alcance (RD-02) |

## 5. Reglas de negocio

### 5.1 Oficiales

Ninguna. La ERS registra HU-04 "Sin RN" (§4.1).

### 5.2 Derivadas

Fundamentadas en las fuentes del proyecto; ninguna está confirmada todavía por negocio:

| ID | Regla | Fundamento |
| --- | --- | --- |
| RD-01 | El nivel de exigencia de cada archivo se define por origen del proveedor (Nacional o Internacional) y aplica igual a todos los proveedores de ese origen | HU literal. RF-04: "La configuración deberá diferenciar el conjunto de archivos mínimos para proveedores Nacional y para proveedores Internacional" |
| RD-02 | Los archivos mínimos son archivos de la factura. El expediente del proveedor (Anexo A) no se configura aquí y SUP-003/SUP-004 no cambian | RF-04 remite a RF-07 y RF-14 (registro de la factura). HU-12: "registra cada una de mis facturas y cargar los archivos mínimos". El Anexo A se titula "De los requisitos para elaborar contrato" |
| RD-03 | Hay tres niveles: Obligatorio, Opcional y No aplica (sección 6.1) | La minuta distingue los archivos principales de los "documentos soporte", y el Requerimiento del portal añade la "documentación adicional requerida por el proceso" |
| RD-04 | Hay niveles fijos. El Nacional siempre entrega XML y PDF del CFDI y nunca el Invoice. El Internacional siempre entrega el Invoice en PDF y nunca el XML ni el PDF del CFDI | Minuta: "nacionales: carga de PDF y XML"; "extranjeros: carga de Invoice en PDF". RN-HU13-01 busca el folio en el XML. HU-15 detecta duplicados por el nombre del Invoice |
| RD-05 | Valores iniciales del Nacional: XML, PDF, orden de compra y Vo.Bo. obligatorios; contrato, anexo, complementos de pago y documentación adicional opcionales. Conservan el comportamiento actual | Reglas DOC-001 a DOC-004 actuales. Requerimiento del portal: "Como mínimo: Factura (PDF), Archivo XML, Orden de compra". Lineamientos 1.iv y 2.c (Vo.Bo.) |
| RD-06 | Valores iniciales del Internacional: Invoice, orden de compra y Vo.Bo. obligatorios; contrato, anexo y documentación adicional opcionales; complementos de pago "No aplica" | Lineamientos 1.iv exige el Vo.Bo. a todo Asociado. El Requerimiento del portal no distingue origen. El complemento de pago es un CFDI. A confirmar (P-01) |
| RD-07 | Cada tipo admite formatos definidos (sección 6.2). Los tipos del Administrador eligen entre PDF, PNG, JPEG, XML y TXT | Minuta: "Invoice en PDF". Spec `almacenamiento-documentos`: extensiones permitidas del sistema |
| RD-08 | La configuración se aplica en cada prevalidación. Una factura que ya salió de los estados editables conserva sus resultados. Una factura editable se evalúa con la configuración vigente al volver a prevalidarse | Los resultados de validación son la evidencia de la decisión. Spec `flujo-facturas`: estados editables `DRAFT`, `REQUIRES_CORRECTION` y `VALIDATION_FAILED` |
| RD-09 | No hay exigencias condicionales: un archivo es obligatorio u opcional para todas las facturas del origen. "Complementos de pago previos (cuando aplique)" queda como opcional | La HU sólo distingue por origen. Decidir "cuando aplique" requiere datos de pagos que el MVP no tiene |
| RD-10 | Los tipos del sistema no se editan ni se desactivan. Los del Administrador se desactivan, nunca se borran. Los documentos cargados conservan su tipo y siguen visibles aunque el tipo deje de aplicar | Los documentos son evidencia fiscal (spec `integridad-datos`, "Prohibición de borrado físico de evidencia fiscal") |

### 5.3 Preguntas abiertas para negocio

Ninguna bloquea `/opsx:propose`. P-01, P-03 y P-04 sólo cambian valores que el Administrador ajusta desde la pantalla. P-02 afecta a otra HU.

| ID | Pregunta | Valor aplicado mientras tanto | Impacto de la respuesta |
| --- | --- | --- | --- |
| P-01 | ¿El proveedor internacional debe entregar orden de compra y Vo.Bo. con cada Invoice? | Ambos obligatorios (RD-06) | Se ajusta en la pantalla o en la siembra de la migración |
| P-02 | ¿Qué expediente, equivalente al Anexo A, debe entregar el proveedor internacional? | Fuera de HU-04. SUP-003 sigue aplicando el Anexo A según el tipo de persona | Lo resuelve HU-16. Hasta entonces una factura internacional no llega a `PREVALIDATED` por SUP-003 ni por las reglas XML |
| P-03 | ¿Qué documentos soporte acompañan al Invoice extranjero? Se sabrá con los ejemplos acordados en la minuta | Ninguno adicional a los de RD-06 | El Administrador los crea como tipos soporte, sin cambios de código |
| P-04 | ¿Los complementos de pago previos deben exigirse "cuando aplique"? | Opcionales (RD-09) | Una exigencia condicional requiere una HU nueva |

## 6. Catálogo de tipos de documento y configuración inicial

### 6.1 Niveles de exigencia

| Nivel | Valor | En la carga documental | En la prevalidación |
| --- | --- | --- | --- |
| Obligatorio | `REQUIRED` | Se ofrece y el checklist lo marca "Obligatorio" | Si falta, su regla DOC resulta `FAIL` y la factura queda en `REQUIRES_CORRECTION` |
| Opcional | `OPTIONAL` | Se ofrece y el checklist lo marca "Opcional" | No se exige |
| No aplica | `NOT_APPLICABLE` | No se ofrece; si se envía, se rechaza | No se exige |

### 6.2 Tipos del sistema y valores iniciales

La clave es el valor que ya guarda `documents.document_type`, así que los documentos existentes no cambian. El candado (🔒) marca un nivel fijo (RD-04).

| Clave | Nombre | Descripción (ayuda al proveedor) | Formatos | Nacional | Internacional | Regla |
| --- | --- | --- | --- | --- | --- | --- |
| `INVOICE_XML` | XML del CFDI | Archivo XML del CFDI timbrado | XML | Obligatorio 🔒 | No aplica 🔒 | DOC-001 (`CRITICAL`) |
| `INVOICE_PDF` | PDF del CFDI | Representación impresa del CFDI | PDF | Obligatorio 🔒 | No aplica 🔒 | DOC-002 (`ERROR`) |
| `FOREIGN_INVOICE` (nuevo) | Invoice (PDF) | Factura del proveedor extranjero | PDF | No aplica 🔒 | Obligatorio 🔒 | DOC-008 (`CRITICAL`) |
| `PURCHASE_ORDER` | Orden de compra | Orden de compra que ampara el servicio facturado | PDF, PNG, JPEG, TXT | Obligatorio | Obligatorio | DOC-003 (`ERROR`) |
| `APPROVAL` | Vo.Bo. del líder de proyecto | Visto bueno del líder de proyecto sobre los entregables del periodo facturado | PDF, PNG, JPEG, TXT | Obligatorio | Obligatorio | DOC-004 (`ERROR`) |
| `CONTRACT` | Contrato | Contrato firmado con ULTRASIST | PDF, PNG, JPEG, TXT | Opcional | Opcional | DOC-009 (`ERROR`) |
| `CONTRACT_ANNEX` | Anexo del contrato | Anexo firmado del contrato | PDF, PNG, JPEG, TXT | Opcional | Opcional | DOC-009 (`ERROR`) |
| `PAYMENT_COMPLEMENT_XML` | Complemento de pago (XML) | XML de complementos de pago previos, cuando aplique | XML | Opcional | No aplica | DOC-009 (`ERROR`) |
| `PAYMENT_COMPLEMENT_PDF` | Complemento de pago (PDF) | PDF de complementos de pago previos, cuando aplique | PDF | Opcional | No aplica | DOC-009 (`ERROR`) |
| `ADDITIONAL` | Documentación adicional | Cualquier otro documento que respalde la factura | PDF, PNG, JPEG, XML, TXT | Opcional | Opcional | DOC-009 (`ERROR`) |

Los formatos corresponden a estas extensiones: PDF → `.pdf`; PNG → `.png`; JPEG → `.jpg`, `.jpeg`; XML → `.xml`; TXT → `.txt`. TXT se conserva en los tipos de soporte porque los datos demo usan archivos `.txt`.

### 6.3 Tipos de documento soporte del Administrador

- **Campos:** nombre (3 a 80 caracteres, único sin distinguir mayúsculas), descripción opcional (hasta 300 caracteres), al menos un formato y un nivel por origen. Los niveles aparecen preseleccionados en "No aplica", de modo que crear un tipo no cambia nada para los proveedores hasta que el Administrador lo decida.
- **Clave:** la genera el sistema con el formato `SOPORTE_<id>` (por ejemplo, `SOPORTE_12`) y no cambia.
- **Regla:** DOC-009 cuando el tipo es obligatorio para el origen de la factura.
- **Edición:** nombre, descripción y formatos. Los niveles se cambian desde la configuración.
- **Desactivación:** el tipo deja de ofrecerse y de exigirse y pasa a la sección "Tipos inactivos". Conserva sus niveles para cuando se reactive.
- **Tipos del sistema:** no se editan ni se desactivan. Sólo sus niveles no fijos se cambian.

### 6.4 Reglas documentales

| Código | Qué evalúa | Severidad | Cuando el tipo no es obligatorio para el origen |
| --- | --- | --- | --- |
| DOC-001 | XML del CFDI | `CRITICAL` | `NOT_APPLICABLE` |
| DOC-002 | PDF del CFDI | `ERROR` | `NOT_APPLICABLE` |
| DOC-003 | Orden de compra | `ERROR` | `NOT_APPLICABLE` |
| DOC-004 | Vo.Bo. del líder de proyecto | `ERROR` | `NOT_APPLICABLE` |
| DOC-005 a DOC-007 | Sin cambios: contrato disponible, complemento, procesabilidad | — | — |
| DOC-008 (nueva) | Invoice (PDF) | `CRITICAL` | `NOT_APPLICABLE` |
| DOC-009 (nueva) | Cada otro tipo obligatorio, con un resultado por tipo y su clave en `source_document` | `ERROR` | No se genera resultado |

`NOT_APPLICABLE` no altera el score. Las reglas DOC-001 a DOC-004 conservan su código y su significado; sólo cambian sus mensajes, que pasan a usar el nombre del tipo.

## 7. Flujo de uso

**Administrador**

1. Entra a **Administración › Archivos mínimos** (`GET /admin/required-documents`).
2. Ve una fila por tipo activo, con sus formatos y un selector de nivel para Nacional y otro para Internacional. Los niveles fijos se muestran como texto con candado y su motivo, sin selector:
   - "El proveedor nacional factura con CFDI".
   - "El proveedor internacional factura con Invoice".
3. Cambia los niveles y pulsa **Guardar configuración** (`POST /admin/required-documents`). El sistema valida, guarda los cambios en una transacción, audita y muestra "Configuración guardada", o "Sin cambios" si no cambió nada.
4. Para agregar un documento que no está en el catálogo, usa **Nuevo tipo de documento soporte** (`POST /admin/required-documents/types`). El tipo aparece en la configuración.
5. Edita un tipo soporte (`POST /admin/required-documents/types/{type_id}`), o lo desactiva y reactiva (`POST /admin/required-documents/types/{type_id}/status`).

**Proveedor (efecto de la configuración)**

6. En la **Carga documental** de una factura, el selector ofrece sólo los tipos que aplican al origen de su proveedor, con sus formatos. El checklist muestra primero los obligatorios, cada uno como cargado o "Pendiente", y el aviso "Faltan N archivos obligatorios" o "Archivos obligatorios completos".
7. Al **Procesar y prevalidar**, cada archivo obligatorio faltante produce "Falta <nombre>" y la factura queda en "Requiere corrección". No puede enviarse a revisión hasta cargar los archivos y volver a prevalidar.

## 8. Criterios de aceptación — spec `archivos-minimos-factura`

Los requisitos de esta sección siguen el formato de delta de OpenSpec. Se copian tal cual a `openspec/changes/archivos-minimos-por-tipo-proveedor/specs/archivos-minimos-factura/spec.md`, bajo el encabezado `## ADDED Requirements`.

### Requirement: Catálogo de tipos de documento de factura
El sistema SHALL mantener un catálogo persistente de los tipos de documento que se cargan en una factura. Cada tipo SHALL tener:
- una clave inmutable, que es el valor que se guarda en `documents.document_type`;
- un nombre en español y una descripción opcional, que se muestran al proveedor;
- los formatos admitidos, entre `PDF` (`.pdf`), `PNG` (`.png`), `JPEG` (`.jpg`, `.jpeg`), `XML` (`.xml`) y `TXT` (`.txt`);
- si es un tipo del sistema o uno definido por el Administrador;
- si está activo;
- un nivel de exigencia para proveedores nacionales y otro para internacionales: `REQUIRED` ("Obligatorio"), `OPTIONAL` ("Opcional") o `NOT_APPLICABLE` ("No aplica").

El catálogo SHALL incluir estos tipos del sistema con estos valores iniciales (clave · nombre · formatos · Nacional · Internacional):
- `INVOICE_XML` · XML del CFDI · XML · Obligatorio · No aplica;
- `INVOICE_PDF` · PDF del CFDI · PDF · Obligatorio · No aplica;
- `FOREIGN_INVOICE` · Invoice (PDF) · PDF · No aplica · Obligatorio;
- `PURCHASE_ORDER` · Orden de compra · PDF, PNG, JPEG, TXT · Obligatorio · Obligatorio;
- `APPROVAL` · Vo.Bo. del líder de proyecto · PDF, PNG, JPEG, TXT · Obligatorio · Obligatorio;
- `CONTRACT` · Contrato · PDF, PNG, JPEG, TXT · Opcional · Opcional;
- `CONTRACT_ANNEX` · Anexo del contrato · PDF, PNG, JPEG, TXT · Opcional · Opcional;
- `PAYMENT_COMPLEMENT_XML` · Complemento de pago (XML) · XML · Opcional · No aplica;
- `PAYMENT_COMPLEMENT_PDF` · Complemento de pago (PDF) · PDF · Opcional · No aplica;
- `ADDITIONAL` · Documentación adicional · PDF, PNG, JPEG, XML, TXT · Opcional · Opcional.

#### Scenario: Catálogo inicial tras la migración
- **WHEN** se aplica la migración sobre una base con facturas y documentos existentes
- **THEN** el catálogo contiene los 10 tipos del sistema, activos y con sus valores iniciales, y cada documento existente conserva su `document_type`

#### Scenario: Nombres en español
- **WHEN** un proveedor abre la carga documental de una factura
- **THEN** los tipos se muestran por su nombre del catálogo (por ejemplo "Orden de compra" y "Vo.Bo. del líder de proyecto"), no por su clave

### Requirement: Configuración exclusiva del Administrador
La página `GET /admin/required-documents` y las operaciones `POST /admin/required-documents`, `POST /admin/required-documents/types`, `POST /admin/required-documents/types/{type_id}` y `POST /admin/required-documents/types/{type_id}/status` SHALL estar disponibles únicamente para el rol `ADMIN`. Toda operación `POST` MUST exigir un token CSRF válido.

#### Scenario: PMO sin acceso
- **WHEN** un usuario con rol `INTERNAL` solicita la página de configuración o envía cualquiera de sus operaciones
- **THEN** la respuesta es HTTP 403 y la configuración no cambia

#### Scenario: Proveedor sin acceso
- **WHEN** un usuario con rol `PROVIDER` solicita la página de configuración o envía cualquiera de sus operaciones
- **THEN** la respuesta es HTTP 403 y la configuración no cambia

#### Scenario: Envío sin token CSRF
- **WHEN** un Administrador envía `POST /admin/required-documents` sin token CSRF o con uno inválido
- **THEN** la respuesta es HTTP 403 y la configuración no cambia

### Requirement: Configuración de los archivos mínimos por origen
La página de configuración SHALL mostrar una fila por cada tipo activo, con su nombre, sus formatos y un selector de nivel para Nacional y otro para Internacional. Primero aparecen los tipos del sistema, en el orden del catálogo, y después los del Administrador, por nombre.

Al guardar, el sistema SHALL validar todos los niveles recibidos y actualizar en una sola transacción los que cambiaron. Un nivel distinto de `REQUIRED`, `OPTIONAL` o `NOT_APPLICABLE`, o la falta del nivel de un tipo activo con nivel editable, SHALL rechazar el guardado completo con HTTP 400. Si ningún nivel cambió, el sistema SHALL informar "Sin cambios" sin modificar nada.

#### Scenario: Exigir un documento al proveedor internacional
- **WHEN** el Administrador cambia "Contrato" a Obligatorio en la columna Internacional y guarda
- **THEN** la página muestra "Configuración guardada" y la carga documental de una factura de un proveedor internacional muestra "Contrato" como Obligatorio

#### Scenario: Dejar de exigir la orden de compra al proveedor nacional
- **WHEN** el Administrador cambia "Orden de compra" a Opcional en la columna Nacional y guarda
- **THEN** la carga documental de una factura de un proveedor nacional muestra "Orden de compra" como Opcional

#### Scenario: Guardar sin cambios
- **WHEN** el Administrador guarda la configuración sin modificar ningún nivel
- **THEN** la página muestra "Sin cambios" y no se agrega ningún registro de auditoría

#### Scenario: Nivel inválido
- **WHEN** la petición trae `MANDATORY` como nivel de un tipo, junto con otros cambios válidos
- **THEN** la respuesta es HTTP 400 con el mensaje "Nivel de exigencia inválido" y no se guarda ningún cambio

### Requirement: Archivos fijos por origen
Estos niveles SHALL ser fijos:
- `INVOICE_XML` e `INVOICE_PDF`: Obligatorio para Nacional y No aplica para Internacional;
- `FOREIGN_INVOICE`: No aplica para Nacional y Obligatorio para Internacional.

La página de configuración SHALL mostrar esos niveles como texto con el ícono de candado y su motivo, sin selector. Una petición que intente cambiarlos SHALL rechazarse con HTTP 409 sin guardar ningún cambio.

#### Scenario: Niveles fijos en la pantalla
- **WHEN** el Administrador abre la configuración
- **THEN** la fila "XML del CFDI" muestra "Obligatorio" con candado en Nacional y "No aplica" con candado en Internacional, con el motivo "El proveedor nacional factura con CFDI", y no tiene selectores

#### Scenario: Petición manipulada
- **WHEN** la petición trae `OPTIONAL` como nivel Nacional de `INVOICE_XML`, junto con otros cambios válidos
- **THEN** la respuesta es HTTP 409 con el mensaje "XML del CFDI tiene un nivel fijo para proveedores nacionales" y no se guarda ningún cambio

### Requirement: Tipos de documento soporte definidos por el Administrador
El Administrador SHALL poder dar de alta tipos de documento soporte con un nombre de 3 a 80 caracteres, una descripción opcional de hasta 300 caracteres, al menos un formato y un nivel para cada origen, preseleccionado en "No aplica". El sistema SHALL:
- normalizar el nombre, recortando los espacios de los extremos y colapsando los internos repetidos;
- rechazar un nombre que ya use otro tipo, sin distinguir mayúsculas;
- asignar al tipo la clave `SOPORTE_<id>`, que no cambia.

El Administrador SHALL poder editar el nombre, la descripción y los formatos de estos tipos, y desactivarlos o reactivarlos. Un tipo inactivo MUST NOT ofrecerse en la carga documental ni exigirse en la prevalidación, y SHALL conservar sus niveles para cuando se reactive. Los tipos del sistema MUST NOT editarse ni desactivarse.

#### Scenario: Alta de un tipo soporte
- **WHEN** el Administrador da de alta "Reporte de horas" con formato PDF, Obligatorio para Internacional y No aplica para Nacional
- **THEN** existe un tipo activo con clave `SOPORTE_<id>` que aparece en la configuración; la carga documental de una factura internacional lo muestra como Obligatorio y la de una nacional no lo ofrece

#### Scenario: Nombre repetido
- **WHEN** el Administrador da de alta un tipo con el nombre "  orden   de COMPRA "
- **THEN** la respuesta es HTTP 409 con el mensaje "Ya existe un tipo de documento con ese nombre" y no se crea ningún tipo

#### Scenario: Sin formatos
- **WHEN** el Administrador da de alta un tipo sin seleccionar ningún formato
- **THEN** la respuesta es HTTP 400 con el mensaje "Seleccione al menos un formato" y no se crea ningún tipo

#### Scenario: Cambio de formatos
- **WHEN** el Administrador edita "Reporte de horas" para admitir PDF y PNG
- **THEN** la siguiente carga de `horas.png` como "Reporte de horas" se acepta, y los documentos ya cargados de ese tipo no cambian

#### Scenario: Desactivación y reactivación
- **WHEN** el Administrador desactiva "Reporte de horas", que era Obligatorio para Internacional
- **THEN** la carga documental ya no lo ofrece, la prevalidación ya no lo exige y los documentos ya cargados de ese tipo siguen listados y descargables en el detalle de la factura; al reactivarlo vuelve a ser Obligatorio para Internacional

#### Scenario: Tipo del sistema
- **WHEN** el Administrador envía la edición o la desactivación de "Orden de compra"
- **THEN** la respuesta es HTTP 409 con el mensaje "Los tipos de documento del sistema no se pueden editar ni desactivar" y el tipo no cambia

### Requirement: Carga documental según el origen del proveedor
La página de carga documental de una factura SHALL ofrecer sólo los tipos activos cuyo nivel para el origen del proveedor de la factura sea Obligatorio u Opcional, cada uno con su nombre y sus formatos. `POST /invoices/{invoice_id}/documents` SHALL rechazar con HTTP 400, antes de escribir el archivo:
- un tipo que no se ofrece para esa factura, con el mensaje "El tipo de documento no aplica a esta factura";
- un archivo cuya extensión no corresponde a los formatos del tipo, con el mensaje "Formato no admitido para <nombre>. Formatos admitidos: <formatos>".

Las verificaciones existentes de contenido, tamaño y estado editable SHALL mantenerse.

#### Scenario: Tipos ofrecidos a un proveedor nacional
- **WHEN** con la configuración inicial se abre la carga documental de una factura de un proveedor nacional
- **THEN** se ofrecen XML del CFDI, PDF del CFDI, Orden de compra, Vo.Bo. del líder de proyecto, Contrato, Anexo del contrato, Complemento de pago (XML), Complemento de pago (PDF) y Documentación adicional, y no se ofrece Invoice (PDF)

#### Scenario: Tipos ofrecidos a un proveedor internacional
- **WHEN** con la configuración inicial se abre la carga documental de una factura de un proveedor internacional
- **THEN** se ofrecen Invoice (PDF), Orden de compra, Vo.Bo. del líder de proyecto, Contrato, Anexo del contrato y Documentación adicional, y no se ofrecen el XML ni el PDF del CFDI ni los complementos de pago

#### Scenario: Tipo que no aplica
- **WHEN** se envía un documento con `document_type = INVOICE_XML` a una factura de un proveedor internacional
- **THEN** la respuesta es HTTP 400 con el mensaje "El tipo de documento no aplica a esta factura" y no se escribe ningún archivo en `storage/`

#### Scenario: Tipo inexistente
- **WHEN** se envía un documento con `document_type = OTRO`
- **THEN** la respuesta es HTTP 400 con el mensaje "El tipo de documento no aplica a esta factura" y no se escribe ningún archivo en `storage/`

#### Scenario: Formato no admitido por el tipo
- **WHEN** se envía `factura.png` como `INVOICE_PDF` a una factura de un proveedor nacional
- **THEN** la respuesta es HTTP 400 con el mensaje "Formato no admitido para PDF del CFDI. Formatos admitidos: PDF" y no se escribe ningún archivo en `storage/`

### Requirement: Checklist de archivos mínimos
La página de carga documental SHALL listar los tipos ofrecidos, primero los obligatorios y después los opcionales, cada grupo en el orden del catálogo. De cada tipo SHALL mostrar su nivel, sus formatos, su descripción si la tiene y su estado: el nombre y el tamaño del documento vigente, o "Pendiente". La página SHALL indicar "Falta 1 archivo obligatorio", "Faltan N archivos obligatorios" o "Archivos obligatorios completos". Los documentos de tipos que ya no se ofrecen MUST NOT contarse y SHALL seguir listados y descargables en el detalle de la factura.

#### Scenario: Obligatorios pendientes
- **WHEN** con la configuración inicial una factura de un proveedor nacional sólo tiene cargados el XML y el PDF del CFDI
- **THEN** el checklist muestra "Orden de compra" y "Vo.Bo. del líder de proyecto" como "Obligatorio · Pendiente" y la página indica "Faltan 2 archivos obligatorios"

#### Scenario: Obligatorios completos
- **WHEN** esa factura tiene además la orden de compra y el Vo.Bo.
- **THEN** la página indica "Archivos obligatorios completos"

#### Scenario: Documento de un tipo que dejó de aplicar
- **WHEN** una factura nacional tiene cargada su orden de compra y el Administrador cambia "Orden de compra" a No aplica en la columna Nacional
- **THEN** la carga documental ya no ofrece ni lista la orden de compra, y el detalle de la factura la sigue listando y permite descargarla

### Requirement: Protección contra ediciones concurrentes
La página de configuración SHALL incluir la huella `config_version` de la configuración que muestra: el SHA-256 de la clave, los niveles y el estado activo de todos los tipos. Si al guardar la huella recibida falta o no coincide con la de la configuración vigente, el sistema SHALL responder HTTP 409 sin guardar ningún cambio.

#### Scenario: Dos Administradores editan a la vez
- **WHEN** los Administradores A y B abren la configuración, A guarda un cambio y después B guarda el suyo
- **THEN** B recibe HTTP 409 con el mensaje "La configuración cambió mientras la editaba. Recargue la página." y sólo persiste el cambio de A

### Requirement: Auditoría de la configuración de archivos mínimos
Cada cambio guardado SHALL generar un registro de auditoría con el `user_id` del Administrador:
- `INVOICE_DOCUMENT_REQUIREMENTS_UPDATED` al guardar la configuración, con el nivel anterior y el nuevo de cada tipo y origen que cambió;
- `INVOICE_DOCUMENT_TYPE_CREATED` al dar de alta un tipo, con su clave, nombre, formatos y niveles;
- `INVOICE_DOCUMENT_TYPE_UPDATED` al editar un tipo, con los valores anteriores y nuevos de los campos que cambiaron;
- `INVOICE_DOCUMENT_TYPE_STATUS_CHANGED` al desactivar o reactivar un tipo.

Una operación rechazada o un guardado sin cambios MUST NOT generar registros de auditoría.

#### Scenario: Cambio de nivel auditado
- **WHEN** el Administrador cambia "Orden de compra" de Obligatorio a Opcional en la columna Internacional y guarda
- **THEN** `audit_logs` contiene un registro `INVOICE_DOCUMENT_REQUIREMENTS_UPDATED` con su `user_id`, `old_value = {"PURCHASE_ORDER": {"international": "REQUIRED"}}` y `new_value = {"PURCHASE_ORDER": {"international": "OPTIONAL"}}`

#### Scenario: Alta auditada
- **WHEN** el Administrador da de alta "Reporte de horas"
- **THEN** `audit_logs` contiene un registro `INVOICE_DOCUMENT_TYPE_CREATED` con la clave `SOPORTE_<id>`, el nombre, los formatos y los dos niveles

#### Scenario: Operación rechazada sin auditoría
- **WHEN** una operación de configuración se rechaza con HTTP 400, 403 o 409
- **THEN** no se agrega ningún registro a `audit_logs`

## 9. Deltas sobre capacidades existentes

### 9.1 `motor-validacion`

Destino: `openspec/changes/archivos-minimos-por-tipo-proveedor/specs/motor-validacion/spec.md`.

```markdown
## ADDED Requirements

### Requirement: Reglas documentales según los archivos mínimos configurados
En cada prevalidación, el motor SHALL leer la configuración vigente de archivos mínimos para el origen del proveedor de la factura. Un tipo está presente cuando la factura tiene un documento vigente (`is_current`) de ese tipo. Las reglas documentales SHALL evaluarse así:
- DOC-001 (XML del CFDI, `CRITICAL`), DOC-002 (PDF del CFDI, `ERROR`), DOC-003 (Orden de compra, `ERROR`), DOC-004 (Vo.Bo. del líder de proyecto, `ERROR`) y DOC-008 (Invoice (PDF), `CRITICAL`) resultan `PASS` o `FAIL` cuando su tipo es Obligatorio para ese origen, y `NOT_APPLICABLE` en otro caso;
- DOC-009 (`ERROR`) genera un resultado por cada otro tipo activo que sea Obligatorio para ese origen, con la clave del tipo en `source_document`;
- los mensajes usan el nombre del tipo: "<nombre> presente" o "Falta <nombre>"; en `NOT_APPLICABLE`, "No requerido para proveedores nacionales" o "No requerido para proveedores internacionales";
- DOC-005, DOC-006 y DOC-007 no cambian.

Un `FAIL` de cualquiera de estas reglas SHALL dejar la factura en `REQUIRES_CORRECTION`. Una factura que ya salió de los estados editables SHALL conservar sus resultados aunque la configuración cambie después. Una factura editable SHALL evaluarse con la configuración vigente al volver a prevalidarse.

#### Scenario: Proveedor nacional sin Vo.Bo.
- **WHEN** con la configuración inicial se prevalida una factura de un proveedor nacional con XML del CFDI, PDF del CFDI y orden de compra, sin Vo.Bo.
- **THEN** DOC-001, DOC-002 y DOC-003 resultan `PASS`, DOC-004 resulta `FAIL` con severidad `ERROR` y el mensaje "Falta Vo.Bo. del líder de proyecto", DOC-008 resulta `NOT_APPLICABLE` y la factura queda en `REQUIRES_CORRECTION`

#### Scenario: Proveedor internacional sin Invoice
- **WHEN** se prevalida una factura de un proveedor internacional que no tiene Invoice (PDF)
- **THEN** DOC-008 resulta `FAIL` con severidad `CRITICAL` y el mensaje "Falta Invoice (PDF)", y DOC-001 y DOC-002 resultan `NOT_APPLICABLE` con el mensaje "No requerido para proveedores internacionales"

#### Scenario: Orden de compra opcional
- **WHEN** "Orden de compra" es Opcional para el origen del proveedor y se prevalida una factura sin orden de compra
- **THEN** DOC-003 resulta `NOT_APPLICABLE` y no descuenta puntos del score

#### Scenario: Tipo soporte obligatorio
- **WHEN** "Reporte de horas" es Obligatorio para Internacional y se prevalida una factura internacional sin ese documento
- **THEN** existe un resultado DOC-009 `FAIL` con `source_document = SOPORTE_<id>` y el mensaje "Falta Reporte de horas"

#### Scenario: Factura ya prevalidada
- **WHEN** una factura está en `PREVALIDATED` sin contrato cargado y el Administrador hace obligatorio "Contrato" para su origen
- **THEN** la factura sigue en `PREVALIDATED` con los mismos resultados y puede enviarse a revisión

#### Scenario: Factura editable prevalidada de nuevo
- **WHEN** una factura en `REQUIRES_CORRECTION` sin contrato cargado se vuelve a prevalidar después de que "Contrato" se hizo obligatorio para su origen
- **THEN** existe un resultado DOC-009 `FAIL` con el mensaje "Falta Contrato"
```

### 9.2 `integridad-datos`

Destino: `openspec/changes/archivos-minimos-por-tipo-proveedor/specs/integridad-datos/spec.md`. El requisito modificado reproduce el bloque completo vigente con los cambios aplicados.

```markdown
## MODIFIED Requirements

### Requirement: Restricciones CHECK sobre estados, montos y vigencias
La base de datos SHALL rechazar:
- valores de estado, rol, tipo de proveedor, origen de proveedor, nivel de exigencia de archivo, severidad, estado de regla, decisión de revisión o estado de procesamiento que no pertenezcan a su enumeración;
- montos negativos en factura;
- `authorized_amount <= 0` en contratos y `new_amount <= 0` en enmiendas;
- `end_date < start_date` en contratos;
- `validation_score` fuera de 0..100;
- `confidence` fuera de 0..1.

`suppliers.status` SHALL ser una enumeración tipada (`REGISTERED`, `ACTIVE`, `INACTIVE`), `suppliers.origin` SHALL ser una enumeración tipada (`NATIONAL`, `INTERNATIONAL`), `invoice_document_types.national_requirement` e `invoice_document_types.international_requirement` SHALL ser enumeraciones tipadas (`REQUIRED`, `OPTIONAL`, `NOT_APPLICABLE`) y `contracts.status` SHALL ser una enumeración tipada (`ACTIVE`, `INACTIVE`).

#### Scenario: Estado inválido por SQL directo
- **WHEN** se ejecuta `UPDATE invoices SET status = 'APROBADA'`
- **THEN** la base de datos rechaza la operación

#### Scenario: Estatus de proveedor fuera de catálogo
- **WHEN** se ejecuta `UPDATE suppliers SET status = 'PENDIENTE'`
- **THEN** la base de datos rechaza la operación

#### Scenario: Nivel de exigencia fuera de catálogo
- **WHEN** se ejecuta `UPDATE invoice_document_types SET national_requirement = 'MANDATORY' WHERE code = 'ADDITIONAL'`
- **THEN** la base de datos rechaza la operación

#### Scenario: Monto negativo
- **WHEN** se intenta guardar una factura con `total = -1.00`
- **THEN** la base de datos rechaza la operación

#### Scenario: Vigencia invertida
- **WHEN** se intenta crear un contrato con `end_date` anterior a `start_date`
- **THEN** la base de datos rechaza la operación y el formulario muestra el error sin HTTP 500

#### Scenario: Score fuera de rango
- **WHEN** se intenta guardar `validation_score = 101`
- **THEN** la base de datos rechaza la operación

## ADDED Requirements

### Requirement: Integridad del catálogo de tipos de documento de factura
La base de datos SHALL imponer sobre `invoice_document_types`:
- unicidad de `code` y de `lower(name)`;
- `formats` con al menos un elemento, todos dentro de (`PDF`, `PNG`, `JPEG`, `XML`, `TXT`);
- que un tipo del sistema (`is_system`) esté siempre activo;
- los niveles fijos: `INVOICE_XML` e `INVOICE_PDF` con `national_requirement = 'REQUIRED'` e `international_requirement = 'NOT_APPLICABLE'`; `FOREIGN_INVOICE` con `national_requirement = 'NOT_APPLICABLE'` e `international_requirement = 'REQUIRED'`.

#### Scenario: Nivel fijo cambiado por SQL
- **WHEN** se ejecuta `UPDATE invoice_document_types SET national_requirement = 'OPTIONAL' WHERE code = 'INVOICE_XML'`
- **THEN** la base de datos rechaza la operación

#### Scenario: Tipo del sistema desactivado por SQL
- **WHEN** se ejecuta `UPDATE invoice_document_types SET is_active = false WHERE code = 'PURCHASE_ORDER'`
- **THEN** la base de datos rechaza la operación

#### Scenario: Nombre repetido con otra capitalización
- **WHEN** se inserta un tipo con `name = 'ORDEN DE COMPRA'`
- **THEN** la base de datos rechaza la operación

#### Scenario: Formatos inválidos
- **WHEN** se inserta un tipo con `formats` vacío o con `formats = '{DOCX}'`
- **THEN** la base de datos rechaza la operación
```

## 10. Notas de diseño (insumo para `design.md`)

| # | Decisión | Alternativas descartadas y motivo |
| --- | --- | --- |
| D1 | Una tabla `invoice_document_types` con una columna de nivel por origen (`national_requirement`, `international_requirement`) | Tabla de requisitos (origen, tipo, nivel): con sólo dos orígenes fijos añade uniones y filas ausentes que hay que interpretar. Constantes en código: el Administrador no podría cambiar nada sin un despliegue, que es justo lo que pide la HU |
| D2 | El catálogo combina tipos del sistema con tipos soporte creados por el Administrador | Catálogo fijo: "definir" quedaría reducido a elegir de una lista cerrada, y los soportes del extranjero aún no se conocen (P-03) |
| D3 | Los niveles fijos se protegen en tres capas: pantalla (texto con candado), servidor (409) y base de datos (`CHECK`) | Protegerlos sólo en la pantalla: una petición manipulada o un `UPDATE` dejaría al Nacional sin XML y rompería RN-HU13-01 |
| D4 | Se conservan DOC-001 a DOC-004 con su significado, se agrega DOC-008 para el Invoice y DOC-009 genérica para los demás, con un resultado por tipo y su clave en `source_document` | Una sola regla agregada: pierde el detalle por archivo y cambia el score. Renumerar todo: confunde los resultados históricos, el README y la guía de validación del PoC (caso "Documento faltante" con DOC-004) |
| D5 | La configuración se lee en cada prevalidación, sin caché. Los resultados guardados son la foto de lo exigido en ese momento (RD-08) | Revalidar al enviar: le toca decidirlo a HU-13, cuyo envío es "previa validación" |
| D6 | `documents.document_type` no tiene llave foránea al catálogo: esa columna también guarda claves del Anexo A (`TAX_STATUS`, `SAT_OPINION`, etc.), que no son tipos de factura. La aplicación valida el tipo al cargar | Llave foránea: obligaría a meter el expediente del Anexo A en el catálogo de factura |
| D7 | `formats` como `VARCHAR[]` con `CHECK (cardinality(formats) >= 1 AND formats <@ ARRAY[...])`. El mapeo de formato a extensiones vive en código, junto a `FILE_TYPES` de `file_service.py` | JSONB: no admite un `CHECK` sencillo. Tabla de formatos: sobredimensionada para cinco valores fijos |
| D8 | Huella `config_version` (SHA-256 de clave, niveles y estado activo de todos los tipos) en un campo oculto; si no coincide al guardar, 409. Sin estado en el servidor, como `expected_sha256` en HU-01 | Bloqueo pesimista: innecesario en una pantalla de uso ocasional. Última escritura gana: descartaría en silencio el cambio de otro Administrador |
| D9 | Clave `SOPORTE_<id>` asignada tras el `flush`, como el folio interno de la factura | Derivar la clave del nombre: cambiaría al renombrar y choca con acentos y espacios |
| D10 | Revisión Alembic `0003_invoice_document_types`: crea la tabla con sus restricciones y siembra los 10 tipos del sistema con los valores de la sección 6.2. El downgrade lanza `NotImplementedError` si hay tipos soporte o documentos `FOREIGN_INVOICE` o `SOPORTE_*`, porque revertir perdería datos | Editar revisiones anteriores: prohibido por la regla "Una revisión por cambio de modelo" |
| D11 | Pantalla en `/admin/required-documents` con formularios HTML normales, sin JavaScript nuevo. La matriz es un solo `<form>` y los niveles fijos se pintan como texto, no como `<select disabled>`, así que no se envían. Compatible con la CSP `default-src 'self'` | Guardado celda por celda con `fetch`: más peticiones y auditoría fragmentada, sin ganancia para una pantalla de pocas filas |
| D12 | `DocumentType` sigue listando las claves que usa el código (`INVOICE_XML` para el parser, etc.) y suma `FOREIGN_INVOICE`. Nombres, formatos y niveles viven sólo en la tabla | Duplicar nombres y formatos en constantes: dos fuentes que se desincronizan |
| D13 | Esta es la primera configuración persistente del portal. El patrón (tabla, pantalla de administración, auditoría y huella) queda disponible para HU-05, HU-06 y HU-08 | — |

**Riesgos y mitigaciones**

- **El Administrador exige un archivo que los proveedores no tienen** → sus facturas quedan en "Requiere corrección". El checklist dice qué falta, el cambio es reversible y queda auditado.
- **La configuración cambia con facturas en curso** → RD-08: las editables se evalúan con la nueva configuración y las demás conservan su resultado.
- **Las facturas internacionales siguen fallando las reglas XML y SUP-003** hasta HU-16 → es una limitación conocida. Esta HU sólo resuelve la parte documental; se documenta en el README.
- **Un tipo con documentos cargados se desactiva o deja de aplicar** → los documentos se conservan y siguen descargables en el detalle (RD-10).
- **Cambia el score de facturas nacionales** → no cambia con los valores iniciales: DOC-001 a DOC-004 conservan código, severidad y resultado. Los escenarios demo, como D-SIN-VOBO, se verifican con `reset_demo`.

## 11. Impacto

| Área | Cambio |
| --- | --- |
| `app/core/constants.py` | `DocumentType.FOREIGN_INVOICE`; enumeración `DocumentRequirement` con etiquetas en español; mapeo de formato a extensiones; claves con nivel fijo |
| `app/models/__init__.py` | Modelo `InvoiceDocumentType` con restricciones de unicidad y `CHECK` |
| `alembic/versions/` | Nueva revisión `0003_invoice_document_types`, posterior a `0002_supplier_bulk_import` |
| `app/schemas/__init__.py` | `DocumentTypeCreate` y `DocumentTypeUpdate` (nombre, descripción, formatos) |
| `app/services/` | Nuevo `document_requirements_service.py`: tipos ofrecidos y exigidos por origen, validación de la matriz, huella y auditoría |
| `app/rules/document_rules.py` | DOC-001 a DOC-004 según la configuración; nuevas DOC-008 y DOC-009 |
| `app/services/validation_engine.py` | Pasa a `document_rules` los tipos exigidos para el origen del proveedor de la factura |
| `app/routers/admin.py` | Rutas `/admin/required-documents*` |
| `app/routers/invoices.py` | Página y carga documental con los tipos del origen y los formatos de cada tipo |
| `app/templates/admin/required_documents.html` | Nueva pantalla: matriz, alta, edición y tipos inactivos |
| `app/templates/invoices/documents.html` | Selector y checklist según la configuración |
| `app/templates/base.html` | Enlace "Archivos mínimos" en Administración |
| `README.md` | Reglas DOC actualizadas, sección de configuración de archivos mínimos y limitación de las facturas internacionales hasta HU-16 |
| `tests/` | Nuevo `test_archivos_minimos.py`, con un escenario por requisito; ajustes en `test_migraciones.py`, `test_integridad.py`, `test_archivos.py` y `test_permissions.py` |
| `scripts/seed_db.py` | Sin cambios funcionales: la migración siembra el catálogo y los escenarios demo nacionales conservan su resultado |
| `requirements.txt` / `requirements.lock` | Sin dependencias nuevas |

## 12. Dependencias

- **Depende de:** ninguna HU funcional (`DEPENDENCIAS_HUs.md`). Técnicamente usa `suppliers.origin`, introducido por HU-01 (change archivado `2026-09-25-carga-masiva-proveedores`).
- **Habilita** (con lo que cada HU recibe de esta):

| HU | Qué recibe de HU-04 | Qué le toca decidir a esa HU |
| --- | --- | --- |
| HU-12 | Tipos exigidos al Nacional y el checklist | El estatus "Cargada" y si los obligatorios se exigen también al registrar |
| HU-13 | Factura nacional con los obligatorios completos al prevalidar | Si el envío revalida con la configuración vigente (RD-08) |
| HU-15 | Tipo "Invoice (PDF)" y los soportes del Internacional | Duplicados por nombre de archivo del Invoice |
| HU-16 | DOC-008 y la exclusión del XML del CFDI para el Internacional | Reglas XML y SUP para internacionales y su expediente (P-02) |
| HU-14 | El catálogo de tipos de documento | Cómo modelar el "Acuse de cancelación", que se exige al cancelar y no al enviar |
| HU-07 | El primer catálogo administrable además del de proveedores | Si esta pantalla se integra a la administración de catálogos |
| HU-19 | Nombres en español de los tipos de documento | — |

## 13. Definición de terminado

- [ ] Change `archivos-minimos-por-tipo-proveedor` creado con proposal, specs, design y tasks; `openspec validate archivos-minimos-por-tipo-proveedor --strict` sin errores.
- [ ] Preguntas P-01 a P-04 respondidas por negocio o registradas como "Open Questions" en `design.md`.
- [ ] Cada escenario de las secciones 8 y 9 tiene al menos una prueba automatizada que pasa sobre la base PostgreSQL temporal de la sesión.
- [ ] La cobertura no baja del umbral vigente (`--cov-fail-under=93`).
- [ ] Revisión Alembic nueva; `alembic check` sin diferencias; downgrade conforme a D10.
- [ ] `scripts/check.py` en verde (ruff, pytest, `alembic check`, `pip-audit`).
- [ ] `reset_demo` reproduce el resultado de las 10 facturas demo; D-SIN-VOBO sigue en `REQUIRES_CORRECTION` por DOC-004.
- [ ] Prueba manual: cambiar niveles, crear, editar, desactivar y reactivar un tipo soporte, cargar documentos como proveedor nacional e internacional y prevalidar.
- [ ] README actualizado.
- [ ] Change archivado y specs sincronizadas (`/opsx:archive`).

## 14. Trazabilidad

| Elemento | Referencia |
| --- | --- |
| Alcance del MVP (minuta del 21-sep-2026) | Proveedor: "Proveedores nacionales: carga de PDF y XML; documentos soporte" y "Proveedores extranjeros: carga de Invoice en PDF y documentos soporte". Administrador: "Configurar parámetros y reglas de validación". Acuerdo: tres ejemplos de invoices extranjeros (22-sep-2026) |
| Documento de HUs | HU-04 (literal); HU-12: "cargar los archivos mínimos necesarios que fueron definidos desde la configuración del sistema" |
| Validación de HUs | HU-04 "Dentro del MVP": "Definir los archivos mínimos es configurar parámetros del sistema" (sección 2); sección 4.1, punto 1 |
| ERS v1.3 | §1.3 Proveedor Nacional / Internacional; §2.2; §3.2 RF-04, RF-07 y RF-14; §4.1 HU-04 ↔ RF-04 (sin RN); §4.2 "Configurar parámetros y reglas de validación" |
| Requerimiento del portal (`Requerimento_PortalFacturas.docx`) | "Documentos a cargar. Como mínimo: Factura (PDF), Archivo XML, Orden de compra, Complementos de pago previos (cuando aplique), Documentación adicional requerida por el proceso"; "validar que se cuente con la documentación mínima requerida" |
| Lineamientos de facturación 2024 v1.4.1 | 1.i y Anexo A (expediente para contratar, fuera de esta HU); 1.iv Vo.Bo. del líder de proyecto; 2.c facturas en PDF y XML con el Vo.Bo.; 2.e y 3.III complemento de pago posterior al pago |
| Guía de Validación Funcional del PoC | Caso "Documento faltante": sin Vo.Bo., DOC-004 aparece como incumplimiento |
| HU-01 | Origen Nacional/Internacional en el catálogo; remitió a HU-04 el expediente del proveedor internacional, que aquí se reasigna a HU-16 (P-02) |
| OpenSpec | Capacidad nueva `archivos-minimos-factura`; deltas en `motor-validacion` e `integridad-datos`; sin cambios en `almacenamiento-documentos` (extensiones globales) ni en `flujo-facturas` (estados editables) |
