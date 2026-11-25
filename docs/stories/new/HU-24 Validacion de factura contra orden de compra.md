# HU-24 · Registro y validación de factura contra la orden de compra (Ferromex)

| Campo | Valor |
| --- | --- |
| ID | HU-24 |
| Rol | Proveedor (registro y envío), PMO y Administrador (consulta de órdenes de compra) |
| Módulo | B. Gestión de facturas del proveedor |
| Prioridad | Alta. Condiciona el registro y el envío de toda factura en la rama `ferromex` (sustituye el control por contrato de HU-12, HU-13 y HU-22) |
| Origen | Documento de negocio "REQUERIMIENTO DE AJUSTES PORTAL DE PROVEEDORES FINAL" (`docs/source-of-truth/ferromex/`), con la aclaración del equipo del 2026-11-24: "se elimina el apartado de contratos, lo que se evalúa es una OC asociada" |
| Rama | `ferromex`. No se integra a `dev`, `qa` ni `main` de ULTRASIST |
| Requisito funcional | Nuevo; se propone como RF-21 en la versión Ferromex de la ERS. Modifica RF-12 y RF-13 (registro y envío de factura nacional) y retira RF-20 (HU-22) |
| Regla de negocio | RN-HU24-01 a RN-HU24-12, de la solicitud (sección 5.1). Reglas derivadas RD-01 a RD-16 (sección 5.2) |
| Change OpenSpec sugerido | `ferromex-validacion-orden-compra` |
| Capacidades nuevas | `orden-compra`, `registro-factura-extraccion` |
| Capacidades modificadas | `flujo-facturas`, `motor-validacion`, `archivos-minimos-factura`, `factura-internacional`, `integridad-datos`, `interfaz-usuario` |
| Capacidades retiradas | `requisitos-alta-contrato`, `trazabilidad-contratos` (las tablas se conservan sin uso, P-02) |
| Estado | Lista para `/opsx:propose`. P-01 a P-04 respondidas por negocio el 2026-11-24 (sección 5.3). Las demás preguntas sólo cambian valores iniciales, una severidad o una tolerancia; no cambian la estructura |
| Estimación | Por definir en el refinamiento |
| Versión / fecha | 1.1 · 2026-11-24 · Equipo Técnico (1.0: versión inicial; 1.1: respuestas a P-01 a P-04) |

## Cómo usar este documento con OpenSpec

En la rama `ferromex`, ejecutar `/opsx:propose ferromex-validacion-orden-compra` con este documento como entrada. Cada sección alimenta un artefacto:

| Artefacto OpenSpec | Secciones de esta HU |
| --- | --- |
| `proposal.md` — Why | 1, 2 |
| `proposal.md` — What Changes | 3, 6, 7 |
| `proposal.md` — Capabilities | Tabla de metadatos, 8, 9 |
| `proposal.md` — Impact | 11 |
| `specs/orden-compra/spec.md` | 8.1 (se copia tal cual bajo `## ADDED Requirements`) |
| `specs/registro-factura-extraccion/spec.md` | 8.2 (se copia tal cual bajo `## ADDED Requirements`) |
| `specs/flujo-facturas/spec.md`, `specs/motor-validacion/spec.md`, `specs/archivos-minimos-factura/spec.md`, `specs/integridad-datos/spec.md`, `specs/interfaz-usuario/spec.md`, `specs/requisitos-alta-contrato/spec.md`, `specs/trazabilidad-contratos/spec.md` | 9 (bloques listos para copiar, o la instrucción exacta del cambio cuando el bloque vigente es largo) |
| `design.md` | 4, 5, 10 (las preguntas de 5.3 van a "Open Questions") |
| `tasks.md` | 11, 13 |

---

## 1. Historia de usuario

**Texto de la solicitud (ortografía normalizada, resumen fiel del documento):**

> Proceso:
> 1. Paso 1. Cargar PDF y XML (puede ser sólo PDF), aplicar el OCR y obtener los datos de la factura y/o del XML.
> 2. Paso 2. Mostrar los datos obtenidos del lado derecho y del lado izquierdo la imagen del PDF de la factura, para comparar los datos. Validación 1: datos de PROVEEDOR (que exista el RFC, el nombre del proveedor y el régimen fiscal) y de CLIENTE (FERROMEX: RFC, nombre del cliente, régimen fiscal, uso de CFDI y los que ya hacemos actualmente del ejemplo de ULTRASIST).
> 3. Paso 3. Enviar factura. Validación 2, cuando el proveedor da clic en "Enviar": se valida contra la Orden de Compra, simulando con datos que tengamos en la aplicación. La O.C. va a ser el contrato: la entidad ORDEN_COMPRA sustituye a la entidad CONTRATOS.

**Aclaración del equipo (2026-11-24):**

> Se elimina el apartado de contratos; lo que se evalúa es una OC asociada.

**Redacción como HU:**

> Yo como proveedor requiero cargar el PDF de mi factura (y su XML si lo tengo), que el sistema obtenga sus datos, me los muestre junto a la imagen de la factura validando los datos del proveedor y de FERROMEX, y que al enviarla la valide contra la orden de compra indicada en sus conceptos, para que sólo lleguen a PMO facturas que cuadran con lo que FERROMEX pidió y recibió.

**Reformulación:**

- **Como** Proveedor nacional de FERROMEX,
- **quiero** registrar mi factura a partir de sus archivos, revisar lo que el sistema leyó contra la imagen de la factura y enviarla,
- **para** que el sistema compruebe sin captura manual que la factura es mía, que está emitida a FERROMEX y que corresponde, encabezado y partida por partida, a una orden de compra con la mercancía o el servicio ya entregados.

**Términos de la solicitud y su equivalente en el sistema:**

| Término de la solicitud | En el sistema |
| --- | --- |
| Paso 1 / Paso 2 / Paso 3 | El asistente "Registrar factura" (`/invoices/new`), que hoy es Información → Documentos → Envío, pasa a ser **Archivos → Revisión → Envío** |
| OCR | Extracción de datos del PDF. Con XML, los datos fiscales salen del XML (`parse_cfdi`); sin XML, del texto del PDF (PyMuPDF) y, si el PDF no tiene texto (escaneado), del analizador documental configurado (`DocumentAnalyzer`) |
| Validación 1 | Reglas del Paso 2: proveedor (nuevas `PRV-001` a `PRV-003`) y cliente (las Reglas de Validación nacionales vigentes `XML-002`, `XML-003`, `XML-004`, `XML-005`, `XML-009`, `XML-010` y `XML-011`, con los datos de FERROMEX) |
| Validación 2 | Reglas nuevas `OC-001` a `OC-012`, evaluadas al dar clic en "Enviar" |
| Entidad ORDEN_COMPRA (O.C.) | Nueva tabla `purchase_orders`: encabezado (Convenio, RFC, Nombre, Fecha, Total, Impuestos) y detalle `DATA` (JSONB) con las partidas de SAP |
| Convenio | Número de la orden de compra en SAP (en la factura de ejemplo, `OC/25704872`; en SAP, "Convenios 25704872") |
| Txt.brv | Texto breve del material en la partida de la O.C.; es la llave para encontrar la partida que corresponde a cada concepto de la factura |
| Docto Material / Fecha Conta | Documento de material y fecha contable de la entrada de mercancía (historial de pedido en SAP, movimiento 101 "WE"). Si traen dato, el material o servicio se entregó |
| "La O.C. va a ser el contrato" / "se elimina el apartado de contratos" | Se retiran del portal el módulo Contratos, sus requisitos de alta (HU-22), su trazabilidad de montos y todas las reglas que comparan contra el contrato. La orden de compra ocupa su lugar como control de la factura. Las tablas de contratos se conservan en la base sin uso (P-02) |
| Simulando con datos que tengamos en la aplicación | Las órdenes de compra viven en la base del portal, sembradas como datos demo y consultables en el portal. La integración con SAP queda fuera de esta HU |

## 2. Contexto y motivación

La rama `ferromex` adapta la PoC de ULTRASIST a FERROMEX (commit `7250a34`: marca, realm de Keycloak, textos y correos). El flujo de la factura sigue siendo el de ULTRASIST, que no corresponde a la operación de FERROMEX:

- **El control es el contrato, no la orden de compra.** El proveedor elige un contrato activo en el Paso 1 y las reglas comparan contra él: monto autorizado (FIN-001, FIN-006), moneda (FIN-003), proyecto (CON-002), vigencia (CON-003, SUP-002), tecnología autorizada (CON-004, SEM-001) y documentos del contrato (DOC-005). En FERROMEX cada compra se formaliza con una orden de compra (convenio) en SAP, con partidas, precio neto y entrada de mercancía; no hay un contrato con monto global por proveedor.
- **La orden de compra es un archivo más.** Hoy la "Orden de compra" es un PDF que el proveedor sube con cada factura (DOC-003, `PURCHASE_ORDER`) y nadie lee su contenido. FERROMEX quiere que la factura se compare contra los datos de la O.C.
- **El proveedor captura datos que ya vienen en sus archivos.** El Paso 1 pide número de factura, periodo, proyecto y líder de proyecto. Los datos fiscales están en el XML y en el PDF.
- **El XML es obligatorio.** FERROMEX acepta facturas sólo con PDF: los datos se obtienen del PDF.
- **No se valida al emisor.** Ninguna regla compara el RFC emisor del CFDI con el RFC del proveedor registrado; tampoco su nombre ni su régimen fiscal.
- **Los datos del receptor son de ULTRASIST.** Las Reglas de Validación nacionales siguen sembradas con `ULT940623AG0` y C.P. 03930 (`0007_validation_rules_catalogs`), pendientes de los datos fiscales de FERROMEX.
- **No se sabe si lo facturado se entregó.** Nada impide facturar una partida sin entrada de mercancía.

**Ejemplo de la solicitud (anexo al documento):**

| Dato | Factura 3668 (PDF) | O.C. / Convenio 25704872 (SAP) |
| --- | --- | --- |
| Proveedor | SOCORRO PATRICIA GONZALEZ HERNANDEZ · `GOHS60031745A` · régimen 612 | 3100002663 GONZALEZ HERNA… |
| Cliente | INTERMODAL MEXICO · `IME010718PU3` · régimen 601 · uso G03 · C.P. 11700 | — |
| Referencia a la O.C. | Concepto: "LTH TIPO L-31T-900 AR BATERIA (OC/25704872)" | Convenio 25704872, fecha 09.12.2025 |
| Partida | 1.00 · H87 - PZ · precio unitario 3,559.05 · importe 3,559.05 | Pos. 10 · Material E20080 · Txt.brv "LTH TIPO L-31T-900 AR" · Ctd.pedido 1 · PZA · Prc.neto 3,559.05 MXN · Grupo art. ELECTRICO · Almacén GUADAL_1 ST |
| Impuestos | Traslado 002 IVA · base 3,559.05 · tasa 0.160000 · importe 569.45 | — |
| Totales | Subtotal 3,559.05 · IVA 569.45 · Total 4,128.50 · MXN · PPD · forma 99 | — |
| Entrega | — | Historial de pedido: WE · 101 · Docto. material 5000527117 · Fecha contab. 16.12.2025 |

## 3. Alcance

### Dentro del alcance

- **Entidad Orden de compra** (`purchase_orders`) con el encabezado y el detalle `DATA` del documento (sección 6.1), sembrada con datos demo, entre ellos el convenio 25704872 del ejemplo.
- **Consulta de órdenes de compra** para PMO y Administrador: listado paginado con búsqueda por convenio, RFC o nombre, y detalle con sus partidas. Sustituye al menú "Contratos".
- **Asistente de registro en tres pasos:**
  - **Paso 1 · Archivos:** PDF obligatorio y XML opcional; el sistema crea la factura en "Borrador" y extrae sus datos. Sin captura de número de factura, periodo, proyecto ni contrato.
  - **Paso 2 · Revisión:** imagen del PDF a la izquierda y datos extraídos a la derecha (encabezado, emisor, receptor, conceptos, impuestos y totales), con el resultado de la Validación 1 y los documentos soporte configurados.
  - **Paso 3 · Envío:** el botón "Enviar" ejecuta la Validación 2 contra la O.C. y, si no hay bloqueos, la factura pasa a "Enviada".
- **Extracción de datos:** del XML cuando existe; del texto del PDF cuando no; y del analizador documental configurado cuando el PDF no tiene texto. Parser de la representación impresa del CFDI 4.0 (sección 6.3).
- **Validación 1:** reglas nuevas del proveedor (`PRV-001` a `PRV-003`) y Reglas de Validación del receptor con los datos de FERROMEX.
- **Validación 2:** reglas nuevas `OC-001` a `OC-012` contra el encabezado y las partidas de la O.C., incluida la entrega.
- **Factura ligada a su O.C.:** la factura apunta a su orden de compra con `invoices.purchase_order_id`; `invoices.contract_id` se conserva sin uso.
- **Retiro de contratos del portal:** módulo, menú, pantalla de requisitos del contrato, reglas y pruebas (sección 6.6). Las tablas y sus datos se conservan sin uso (P-02).
- **Proveedor internacional contra O.C.** (P-04): captura el número de O.C. en su Invoice y se valida contra el encabezado y la entrega de la orden (sección 6.7).
- **Archivos de la factura:** XML pasa a Opcional para el proveedor nacional; "Orden de compra", "Contrato" y "Anexo del contrato" pasan a No aplica.
- Migración, datos demo y recorrido de prueba manual (`data/pruebas-ferromex/`) rehechos sobre órdenes de compra.

### Fuera del alcance

| Tema | Motivo / dónde se atiende |
| --- | --- |
| Integración en línea con SAP (consulta del convenio, del historial de pedido o de la entrada de mercancía) | La solicitud pide simular con datos de la aplicación. La entidad se diseña con los nombres de SAP para conectarla después (P-05) |
| Alta, edición o carga masiva de órdenes de compra desde el portal | Las O.C. vienen de SAP; en esta HU se siembran y sólo se consultan (P-05) |
| Factura parcial (varias facturas contra una O.C.) o una factura contra varias O.C. | La solicitud compara el subtotal contra el total de la O.C. y busca una sola O.C. (P-06, P-07) |
| Extracción y validación por partida del Invoice internacional | El Invoice no es un CFDI y no tiene formato fijo; se valida encabezado y entrega (sección 6.7, P-15) |
| Borrar las tablas o los datos de contratos | Negocio decidió conservarlas sin uso (P-02) |
| Verificar el CFDI ante el SAT | Ni el PoC ni la solicitud lo piden |
| Corregir a mano los datos extraídos en el Paso 2 | La solicitud pide mostrarlos para comparar. Si la extracción falla, el proveedor carga el XML (P-08) |
| OCR local (Tesseract u otro) | El PDF del ejemplo tiene texto. Para escaneados se usa el analizador documental ya previsto (`DOCUMENT_AI_PROVIDER`) (P-09) |
| Cambios a la revisión de PMO, al pago, al complemento de pago y a la cancelación | Sin cambios, salvo que el detalle muestra la O.C. en lugar del contrato |

## 4. Situación actual del PoC (rama `ferromex`, commit `d54531c`)

| Aspecto | Hoy | Brecha para HU-24 |
| --- | --- | --- |
| Paso 1 del registro | `invoices/new.html`: contrato activo (obligatorio), número de factura, periodo `MM/AAAA`, proyecto, líder y número de O.C. opcional. `create_invoice()` exige contrato propio y `ACTIVE`; la moneda inicial es la del contrato | El Paso 1 pasa a ser la carga del PDF y el XML; los datos salen de los archivos |
| Paso 2 del registro | `invoices/documents.html`: checklist de archivos mínimos y carga uno por uno | Debe mostrar la imagen del PDF y los datos extraídos lado a lado, con la Validación 1 |
| Visor del PDF | `document_view_service.render_page()` ya convierte páginas a PNG y `GET /invoices/{id}/documents/{doc}/pages/{n}` las sirve | Se reutiliza en el Paso 2 |
| Envío | `POST /invoices/{id}/submit` → `submission_service`: corre el motor y pasa a "Enviada" si no hay bloqueos | Se conserva; el motor agrega la Validación 2 |
| Datos del XML | `parse_cfdi()` extrae UUID, emisor (RFC y nombre), receptor, totales, moneda, forma y método de pago, uso de CFDI y conceptos (descripción, cantidad, valor unitario, importe, impuestos) | Faltan régimen del emisor, serie y folio, unidad (`ClaveUnidad`, `Unidad`), `NoIdentificacion`, `ObjetoImp` y el IVA por concepto con su tasa |
| Datos del PDF | `pdf_service.analyze_pdf()` sólo cuenta páginas y texto; no hay parser de la representación impresa. Los analizadores de Azure están como esqueleto; el de demo (`LocalMockAnalyzer`) no extrae campos | Parser de la representación impresa del CFDI y uso del analizador para PDF sin texto |
| Validación del emisor | No existe. XML-008 sólo exige que haya RFC emisor | Nuevas `PRV-001` a `PRV-003` |
| Datos de FERROMEX como receptor | Reglas nacionales configurables `XML-002` (RFC), `XML-003` (método de pago), `XML-004` (forma de pago), `XML-005` (usos de CFDI), `XML-009` (razón social), `XML-010` (C.P.) y `XML-011` (régimen), sembradas con `ULT940623AG0` y 03930 | Se conservan; cambian los valores sembrados (P-01) |
| Orden de compra | Sólo el documento `PURCHASE_ORDER` por factura (DOC-003, Obligatorio nacional) y el texto libre `invoices.purchase_order_number` | Nueva entidad con encabezado y partidas |
| Contratos | `contracts`, `contract_amendments`, `contract_document_types`, `documents.contract_id`, `invoices.contract_id`; `app/routers/contracts.py`, `contract_service.py`, `contract_requirements_service.py`, `contracts/*.html`, `admin/contract_requirements.html`; menú "Contratos" y "Requisitos mínimos › Alta de contrato" | Se retiran |
| Reglas contra el contrato | SUP-002, CON-001 a CON-004, DOC-005, FIN-001, FIN-003, FIN-006 y SEM-001 | Se retiran; las sustituyen las `OC-*` |
| Factura sin XML | DOC-001 es Obligatorio para el nacional; sin XML no hay UUID (FIN-004) ni datos fiscales | XML Opcional; UUID y datos desde el PDF |
| Datos demo y recorrido manual | `seed_db.py`: 3 contratos activos y 10 facturas; `data/pruebas-ferromex/`: contrato "Monitoreo de Flota Ferroviaria" de $45,000, A-1001 autorizada y pagada, A-1002 rechazada por exceder el monto | Se rehacen sobre órdenes de compra |

## 5. Reglas de negocio

### 5.1 De la solicitud

| ID | Regla |
| --- | --- |
| RN-HU24-01 | El proveedor carga el PDF de la factura y, si lo tiene, su XML. El PDF basta para registrar la factura |
| RN-HU24-02 | El sistema obtiene los datos de la factura del XML y/o del PDF (OCR) |
| RN-HU24-03 | El sistema muestra los datos obtenidos a la derecha y la imagen del PDF a la izquierda, para compararlos |
| RN-HU24-04 | Validación 1, proveedor: existen el RFC, el nombre del proveedor y el régimen fiscal |
| RN-HU24-05 | Validación 1, cliente (FERROMEX): RFC, nombre, régimen fiscal, uso de CFDI y las validaciones del receptor que ya se hacen |
| RN-HU24-06 | La Validación 2 se ejecuta cuando el proveedor da clic en "Enviar" |
| RN-HU24-07 | La entidad ORDEN_COMPRA sustituye a CONTRATOS, con los campos Convenio, RFC, Nombre, Fecha, Total, Impuestos y DATA (sección 6.1) |
| RN-HU24-08 | La O.C. se obtiene de la descripción de los conceptos (por ejemplo `OC/25704872`) y se busca por el campo Convenio |
| RN-HU24-09 | Encabezado: OC de la factura vs Convenio; RFC; nombre del proveedor; subtotal de la factura vs Total; IVA trasladado tasa 0.160000 vs Impuestos |
| RN-HU24-10 | Por cada concepto, la partida de la O.C. se encuentra comparando la descripción del concepto con `Txt.brv`; deben coincidir cantidad (`Ctd.Pedido`), unidad (`Unidad.Pedido`), importe (`Prc.Neto`) y moneda (`Moneda`) |
| RN-HU24-11 | El importe del IVA de cada concepto se acumula y debe ser igual a Impuestos de la O.C. |
| RN-HU24-12 | `Docto Material` y `Fecha Conta` de la partida deben traer dato: indican que el material o servicio se entregó. Sólo se valida que traigan dato |

### 5.2 Derivadas

| ID | Regla |
| --- | --- |
| RD-01 | El registro crea la factura en "Borrador" al cargar el PDF. El número de factura es `Serie` + `Folio` del CFDI (o "Factura <n>" del PDF); el periodo se toma del mes de la fecha de emisión (`MM/AAAA`). Proyecto y líder dejan de pedirse |
| RD-02 | Con XML, el XML es la fuente de los datos fiscales y el PDF sólo se muestra. Sin XML, los datos salen del PDF. Si el XML y el PDF traen UUID distintos, la factura no se registra (409 "El PDF y el XML no corresponden a la misma factura") |
| RD-03 | Si no se obtienen del PDF los datos esenciales (UUID, RFC emisor, RFC receptor, fecha, subtotal, total, moneda y al menos un concepto), el sistema lo indica y pide el XML; la factura queda en "Borrador" |
| RD-04 | La Validación 1 se ejecuta al terminar la extracción y se vuelve a ejecutar si se reemplaza el PDF o el XML. Se muestra en el Paso 2 y no cambia el estatus |
| RD-05 | `PRV-001` (CRITICAL): el RFC emisor coincide con el RFC del proveedor del usuario, que está registrado y "Autorizado". `PRV-002` (ERROR): el nombre del emisor coincide con la razón social del proveedor, sin distinguir mayúsculas, acentos ni signos. `PRV-003` (ERROR): el régimen fiscal del emisor viene en la factura y existe activo en el catálogo de regímenes |
| RD-06 | El número de O.C. se busca en las descripciones de los conceptos con el patrón `OC` seguido de `/`, `-`, `:` o espacios y de 6 a 10 dígitos, con o sin paréntesis. Todos los conceptos que lo traigan deben citar la misma O.C.; los que no lo traigan se buscan en esa misma O.C. |
| RD-07 | La O.C. se busca por Convenio exacto. Sólo se consideran las O.C. cuyo RFC sea el del proveedor del usuario: una O.C. de otro proveedor responde igual que una inexistente |
| RD-08 | La partida de cada concepto se encuentra comparando `Txt.brv` con la descripción del concepto sin distinguir mayúsculas, acentos, espacios ni signos: la descripción debe contener el `Txt.brv` completo (ejemplo: "LTH TIPO L-31T-900 AR BATERIA (OC/25704872)" contiene "LTH TIPO L-31 T-900 AR"). Si coincide más de una partida, se toma la de `Txt.brv` más largo; si hay empate, la regla falla por ambigüedad |
| RD-09 | Cada partida de la O.C. se usa a lo más por un concepto de la factura |
| RD-10 | La unidad de la factura (`ClaveUnidad` y `Unidad`) coincide con `Unidad.Pedido` mediante una tabla de equivalencias sembrada (por ejemplo `H87`, `PZ`, `PZA` y `PIEZA` son la misma unidad) (P-10) |
| RD-11 | Importe del concepto vs O.C.: se compara el precio unitario de la factura con `Prc.Neto` y el importe con `Ctd.Pedido × Prc.Neto`. Con cantidad 1 equivale a la regla literal (importe = `Prc.Neto`) (P-11) |
| RD-12 | Los montos se comparan redondeados a centavos con tolerancia de ±0.01 por redondeo (P-12) |
| RD-13 | El IVA de la factura (OC-006) es la suma de los traslados `002` con tasa `0.160000` de todos los conceptos; si no hay detalle por concepto, el `TotalImpuestosTrasladados` del comprobante |
| RD-14 | `CRITICAL` y `ERROR` bloquean el envío; `WARNING` no. La Validación 2 también se puede ejecutar con "Verificar" sin cambiar el estatus (spec `flujo-facturas`, "Verificación sin cambio de estatus") |
| RD-15 | Al enviar, la factura queda ligada a su O.C. (`purchase_order_id`) y el resultado de cada regla guarda en su evidencia los valores de la O.C. leídos en ese momento |
| RD-16 | Una O.C. con una factura propia "Enviada", "En revisión", "Autorizada" o "Pagada" no admite otra factura (`OC-012`, CRITICAL). Las facturas "Rechazadas" o "Canceladas" no cuentan (P-06) |

### 5.3 Preguntas abiertas para negocio

| ID | Pregunta | Respuesta o propuesta mientras no haya respuesta |
| --- | --- | --- |
| **P-01** | ¿Cuáles son los datos fiscales del receptor? El ejemplo está emitido a **INTERMODAL MÉXICO** (`IME010718PU3`, régimen 601, C.P. 11700), no a Ferrocarril Mexicano | **Respondida (2026-11-24): sí.** El receptor es INTERMODAL MEXICO · `IME010718PU3` · 601 · G03 · 11700, sembrado en las Reglas de Validación nacionales y editable por el Administrador |
| **P-02** | ¿Se elimina por completo la información de contratos (tablas y datos) o sólo se oculta? | **Respondida (2026-11-24): sólo se dejan de usar.** Las tablas `contracts`, `contract_amendments`, `contract_document_types` y las columnas `invoices.contract_id` y `documents.contract_id` se conservan con sus datos; el portal deja de leerlas y escribirlas, y la factura apunta a la orden de compra (`invoices.purchase_order_id`) |
| **P-03** | ¿"Importe = Prc.Neto" es literal? En SAP `Prc.Neto` es por unidad ("por 1"): con cantidad 2 el importe es el doble | **Respondida (2026-11-24): se acepta RD-11.** Precio unitario vs `Prc.Neto` e importe vs `Ctd.Pedido × Prc.Neto` |
| **P-04** | ¿Los proveedores internacionales facturan a FERROMEX por este portal? Si sí, ¿contra O.C.? | **Respondida (2026-11-24): sí, contra O.C.** Ver sección 6.7 |
| P-05 | ¿Cómo llegarán las O.C. al portal: integración con SAP, archivo periódico o captura? | Sembradas y de sólo consulta en esta HU |
| P-06 | ¿Una O.C. se puede facturar en varias facturas (parcialidades por partida o por entrega)? | No: subtotal = Total de la O.C. y una sola factura vigente por O.C. (RD-16) |
| P-07 | ¿Una factura puede cubrir varias O.C.? | No: `OC-001` falla si los conceptos citan O.C. distintas |
| P-08 | Si la extracción del PDF se equivoca, ¿el proveedor puede corregir datos en el Paso 2? | No: carga el XML o reemplaza el PDF |
| P-09 | ¿Qué servicio de OCR se usará para PDF escaneados (Azure Document Intelligence u otro)? | El analizador configurado; en demo, PDF sin texto se rechaza pidiendo el XML |
| P-10 | ¿Cuál es la tabla oficial de equivalencias entre la unidad SAT y la unidad de SAP? | Tabla sembrada con las unidades del ejemplo y las más comunes (sección 6.5) |
| P-11 | ¿Moneda distinta de MXN con tipo de cambio? | Se exige la misma moneda (`OC-010`), sin conversión |
| P-12 | ¿Tolerancia de redondeo en montos? | ±0.01 |
| P-13 | ¿Severidad de la entrega pendiente (`OC-011`)? ¿Bloquea o sólo advierte? | ERROR: bloquea el envío |
| P-14 | ¿Se valida la fecha de la factura contra la fecha de la O.C. o la fecha de entrega (`Fe.Entrega`)? | No en esta HU; se muestran en el detalle |
| P-15 | Proveedor internacional: ¿cómo se identifica en SAP (RFC genérico `XEXX010101000` o número de acreedor) y se requiere validar sus partidas? | La O.C. se liga al proveedor por `supplier_id`; se validan encabezado y entrega, no las partidas (sección 6.7) |

## 6. Modelo de datos y reglas

### 6.1 Entidad Orden de compra (`purchase_orders`)

| Campo de la solicitud | Columna | Tipo | Reglas |
| --- | --- | --- | --- |
| \*Convenio | `convenio` | `BIGINT` | Obligatorio, único, > 0 |
| \*RFC | `rfc` | `VARCHAR(13)` | Obligatorio; formato de RFC (12 o 13) |
| \*Nombre | `supplier_name` | `VARCHAR(150)` | Obligatorio |
| \*Fecha | `order_date` | `DATE` | Obligatorio |
| \*Total | `total` | `NUMERIC(18,2)` (`Money`) | Obligatorio, > 0. Suma de las partidas sin impuestos (es lo que compara el subtotal) |
| \*Impuestos | `taxes` | `NUMERIC(18,2)` (`Money`) | Obligatorio, ≥ 0 |
| \*DATA | `data` | `JSONB` | Obligatorio; estructura de la sección 6.2, al menos una partida |
| — | `supplier_id` | FK `suppliers.id`, nulo permitido | Se resuelve por RFC al sembrar (nacional) o se asigna explícitamente (internacional, cuyo RFC en SAP es genérico). Las reglas del nacional usan `rfc`; las del internacional, `supplier_id` (sección 6.7) |
| — | `created_at`, `updated_at` | `UTCDateTime` | — |

`invoices.purchase_order_id` (FK `RESTRICT`, nulo permitido, con índice) es la nueva liga de la factura. `invoices.contract_id` se conserva sin uso (P-02): ninguna factura nueva lo llena. `invoices.purchase_order_number` guarda el número detectado (`OC-001`) aunque la O.C. no exista.

### 6.2 Estructura de `DATA`

Se conservan las etiquetas de SAP del documento, para la futura integración:

```json
{
  "items": [
    {
      "Material": "E20080",
      "Txt.brv": "LTH TIPO L-31 T-900 AR",
      "Ctd.Pedido": "1",
      "Unidad.Pedido": "PZA",
      "Fe.Entrega": "30.12.2025",
      "Prc.Neto": "3559.05",
      "Moneda": "MXN",
      "Grupo.Art": "ELECTRICO",
      "Almacen": "GUADALAJARA_1 STATION 1",
      "Docto Material": "5000527117",
      "Fecha Conta": "16.12.2025"
    }
  ]
}
```

| Etiqueta | Uso | Contra la factura |
| --- | --- | --- |
| `Material` | Se muestra | — |
| `Txt.brv` | **Llave** de la partida (RD-08) | Descripción del concepto |
| `Ctd.Pedido` | `OC-007` | Cantidad |
| `Unidad.Pedido` | `OC-008` | Unidad (RD-10) |
| `Fe.Entrega` | Se muestra | — |
| `Prc.Neto` | `OC-009` | Precio unitario e importe (RD-11) |
| `Moneda` | `OC-010` | Moneda del comprobante |
| `Grupo.Art`, `Almacen` | Se muestran | — |
| `Docto Material`, `Fecha Conta` | `OC-011`: sólo que traigan dato | — |

Montos y cantidades se guardan como texto decimal con punto, para no perder precisión en JSON. El servicio valida la estructura al sembrar: etiquetas obligatorias `Txt.brv`, `Ctd.Pedido`, `Unidad.Pedido`, `Prc.Neto` y `Moneda`.

### 6.3 Datos extraídos de la factura

| Dato | XML (CFDI 4.0) | PDF (representación impresa) |
| --- | --- | --- |
| UUID | `TimbreFiscalDigital@UUID` | "FOLIO FISCAL (UUID)" |
| Serie y folio | `Comprobante@Serie`, `@Folio` | "Factura 3668" |
| Fecha | `Comprobante@Fecha` | "FECHA Y HORA DE EMISIÓN DE CFDI" |
| Emisor | `Emisor@Rfc`, `@Nombre`, `@RegimenFiscal` | Encabezado: nombre, RFC y "RÉGIMEN FISCAL: 612 - …" |
| Receptor | `Receptor@Rfc`, `@Nombre`, `@RegimenFiscalReceptor`, `@UsoCFDI`, `@DomicilioFiscalReceptor` | Bloque "CLIENTE": nombre, RFC, "USO CFDI", "DOMICILIO FISCAL", "REGIMEN FISCAL" |
| Conceptos | `Concepto@Cantidad`, `@ClaveUnidad`, `@Unidad`, `@NoIdentificacion`, `@Descripcion`, `@ValorUnitario`, `@ObjetoImp`, `@Importe`, `Traslado@Impuesto/@TasaOCuota/@Importe` | Tabla "CONCEPTOS": Cantidad, Unidad, No. Identificación, Descripción, Precio Unitario, Objeto Imp., Importe; "Impuestos: Traslados: 002 IVA Base - … Tasa - 0.160000 Importe - $ …" |
| Totales | `@SubTotal`, `Impuestos@TotalImpuestosTrasladados`, `@Total` | "SUBTOTAL", "TRASLADO IVA TASA 0.160000", "TOTAL" |
| Moneda, forma y método de pago, tipo | `@Moneda`, `@FormaPago`, `@MetodoPago`, `@TipoDeComprobante` | "MONEDA", "FORMA DE PAGO", "MÉTODO DE PAGO", "TIPO DE COMPROBANTE" |

La extracción guarda en `documents.metadata_json` del documento de origen (`INVOICE_XML` o `INVOICE_PDF`) los datos y su fuente (`xml`, `pdf_text` o `ocr`).

### 6.4 Reglas de validación

**Validación 1 (Paso 2):**

| Código | Severidad | Compara | PASS | FAIL |
| --- | --- | --- | --- | --- |
| `PRV-001` | CRITICAL | RFC emisor vs RFC del proveedor del usuario | "RFC del emisor corresponde al proveedor" | "El RFC emisor <rfc> no corresponde al proveedor <rfc>" |
| `PRV-002` | ERROR | Nombre del emisor vs razón social del proveedor (normalizados) | "Nombre del emisor coincide" | "El nombre del emisor no coincide con el proveedor" |
| `PRV-003` | ERROR | Régimen fiscal del emisor presente y activo en el catálogo `TAX_REGIME` | "Régimen fiscal del emisor válido" | "Falta el régimen fiscal del emisor" / "Régimen fiscal <clave> no válido" |
| `XML-002`, `XML-005`, `XML-009`, `XML-010`, `XML-011` | Las vigentes | Receptor: RFC, usos de CFDI, razón social, C.P. y régimen | Sin cambios | Sin cambios |
| `XML-003`, `XML-004`, `XML-006`, `XML-007`, `XML-008` | Las vigentes | Método y forma de pago, UUID, moneda, datos esenciales | Sin cambios; con PDF sin XML se evalúan sobre los datos del PDF | Sin cambios |

**Validación 2 (Paso 3, "Enviar"):**

| Código | Severidad | Compara | PASS | FAIL |
| --- | --- | --- | --- | --- |
| `OC-001` | CRITICAL | O.C. detectada en los conceptos (RD-06) | "Orden de compra <n> detectada" | "No se encontró el número de orden de compra en los conceptos" / "Los conceptos citan órdenes de compra distintas: <n>, <n>" |
| `OC-002` | CRITICAL | Factura OC vs `Convenio` (RD-07) | "Orden de compra <n> encontrada" | "La orden de compra <n> no existe para el proveedor" |
| `OC-003` | CRITICAL | RFC emisor vs `RFC` | "RFC coincide con la orden de compra" | "RFC no coincide con la orden de compra" |
| `OC-004` | ERROR | Nombre del emisor vs `Nombre` (normalizados) | "Nombre coincide con la orden de compra" | "Nombre no coincide con la orden de compra" |
| `OC-005` | ERROR | Subtotal vs `Total` | "Subtotal igual al total de la orden de compra" | "Subtotal <x> distinto del total de la orden de compra <y>" |
| `OC-006` | ERROR | IVA tasa 0.160000 acumulado vs `Impuestos` (RD-13) | "IVA igual a los impuestos de la orden de compra" | "IVA <x> distinto de los impuestos de la orden de compra <y>" |
| `OC-007` | ERROR | Por concepto: partida encontrada por `Txt.brv` (RD-08, RD-09) | "Concepto <n>: partida <Txt.brv>" | "Concepto <n>: sin partida en la orden de compra" / "…: coincide con varias partidas" |
| `OC-008` | ERROR | Por concepto: cantidad vs `Ctd.Pedido` y unidad vs `Unidad.Pedido` (RD-10) | "Concepto <n>: cantidad y unidad coinciden" | "Concepto <n>: cantidad <x> vs <y>" / "unidad <x> vs <y>" |
| `OC-009` | ERROR | Por concepto: precio e importe vs `Prc.Neto` (RD-11) | "Concepto <n>: importe coincide" | "Concepto <n>: importe <x> vs <y>" |
| `OC-010` | ERROR | Moneda del comprobante vs `Moneda` de cada partida usada | "Moneda coincide con la orden de compra" | "Moneda <x> distinta de la orden de compra <y>" |
| `OC-011` | ERROR | Por partida usada: `Docto Material` y `Fecha Conta` con dato (RN-HU24-12) | "Concepto <n>: entrega registrada" | "Concepto <n>: la partida no tiene entrada de mercancía" |
| `OC-012` | CRITICAL | O.C. sin otra factura vigente (RD-16) | "Orden de compra sin otra factura vigente" | "La orden de compra ya tiene la factura <folio>" |

Las reglas por concepto (`OC-007` a `OC-009`, `OC-011`) generan un resultado por concepto, con `source_reference` "Concepto <n>". Si `OC-001` u `OC-002` fallan, `OC-003` a `OC-012` resultan `NOT_APPLICABLE` con el mensaje "Sin orden de compra"; si `OC-007` falla para un concepto, sus `OC-008`, `OC-009` y `OC-011` resultan `NOT_APPLICABLE`.

### 6.5 Equivalencias de unidad (valores iniciales)

| Unidad de SAP | Equivalentes en la factura |
| --- | --- |
| `PZA` | `H87`, `PZ`, `PZA`, `PIEZA` |
| `SER` | `E48`, `SERV`, `SERVICIO` |
| `KG` | `KGM`, `KG` |
| `LT` | `LTR`, `L`, `LT` |
| `M` | `MTR`, `M` |
| `ACT` | `ACT`, `ACTIVIDAD` |

Se comparan sin distinguir mayúsculas. La unidad de la factura se toma de `ClaveUnidad` y de `Unidad` (en el PDF, "H87 - PZ"); coincide si cualquiera es equivalente a `Unidad.Pedido`.

### 6.6 Retiro de contratos del portal

Negocio decidió conservar las tablas y sus datos (P-02): se retira todo lo que las lee o escribe, no el esquema.

| Se retira | Detalle |
| --- | --- |
| Rutas | `/contracts*` (listado, alta, enmiendas, expediente, documentos, activación) y `/admin/contract-requirements*` |
| Menú | "Contratos" (lo sustituye "Órdenes de compra") y "Requisitos mínimos › Alta de contrato" |
| Tablas y columnas | **Se conservan sin uso**: `contracts`, `contract_amendments`, `contract_document_types`, `documents.contract_id` e `invoices.contract_id`, con sus restricciones y datos. Los modelos ORM se conservan (marcados como obsoletos en su docstring) para que `alembic check` no proponga borrarlas; ningún servicio, ruta ni regla los usa |
| Código | `app/routers/contracts.py`, `app/services/contract_service.py`, `app/services/contract_requirements_service.py`, `app/rules/contract_rules.py`, plantillas `contracts/*` y `admin/contract_requirements.html`, `contract_activate.js`. `ContractStatus` se conserva porque lo usa el `CHECK` de `contracts.status` |
| Reglas | SUP-002, CON-001 a CON-004, DOC-005, FIN-001, FIN-003, FIN-006 y SEM-001 |
| Archivos de la factura (HU-04) | `CONTRACT`, `CONTRACT_ANNEX` y `PURCHASE_ORDER` pasan a No aplica en ambos orígenes (DOC-003 resulta `NOT_APPLICABLE`); `INVOICE_XML` pasa a Opcional para el nacional |
| Captura de la factura | Contrato, proyecto, líder de proyecto y periodo capturado; `invoices.project_name` y `project_leader` admiten nulo y dejan de mostrarse |
| Pruebas | `test_contratos.py`, `test_requisitos_contrato.py` y los casos de contrato del resto de la suite |

**Se conservan:** SUP-001, SUP-003, SUP-004, DOC-001, DOC-002, DOC-004, DOC-006 a DOC-009, XML-001 a XML-011, FIN-002, FIN-004, FIN-005 y DAT-001.

### 6.7 Proveedor internacional contra orden de compra (P-04)

El Invoice del proveedor internacional no es un CFDI: no hay XML, RFC, régimen ni uso de CFDI, y su PDF no tiene formato fijo. Su flujo (HU-15, HU-16) conserva la carga del Invoice y la captura de sus datos, sin contrato, y agrega la orden de compra:

- **Captura:** el formulario del Invoice pide el **número de orden de compra** (obligatorio, 6 a 10 dígitos) en lugar del contrato. Si el texto del Invoice trae `OC/<número>`, se propone en el campo.
- **Identidad del proveedor:** la O.C. se busca por Convenio y por `supplier_id` del proveedor del usuario (su RFC en SAP es genérico, P-15).
- **Reglas al enviar:**

| Regla | Internacional |
| --- | --- |
| `OC-001` | Número de O.C. capturado: `PASS` si tiene el formato; `FAIL` "Capture el número de orden de compra" |
| `OC-002` | Igual que el nacional, pero por `supplier_id` |
| `OC-003` | `NOT_APPLICABLE` "No aplica para proveedores internacionales" (sin RFC) |
| `OC-004` | Razón social del proveedor vs `Nombre` (normalizados), `WARNING` |
| `OC-005` | Subtotal capturado vs `Total` |
| `OC-006` | Impuestos capturados vs `Impuestos` |
| `OC-007` a `OC-009` | `NOT_APPLICABLE` "Sin partidas en el Invoice" (P-15) |
| `OC-010` | Moneda capturada vs `Moneda` de todas las partidas |
| `OC-011` | Todas las partidas de la O.C. con `Docto Material` y `Fecha Conta` |
| `OC-012` | Igual que el nacional |
| `PRV-001` a `PRV-003` | `NOT_APPLICABLE` (las cubren INT-001 y el expediente del proveedor) |

- **Validación 1 del internacional:** las reglas `INT-001` a `INT-004` vigentes, con los datos de FERROMEX (INTERMODAL MEXICO) configurados por el Administrador.
- La demo siembra una orden de compra en USD del proveedor internacional demo, con entrada de mercancía.

## 7. Flujo de uso

1. El proveedor entra a **Facturas › Registrar factura**.
2. **Paso 1 · Archivos:** carga el PDF (obligatorio) y el XML (opcional) y da clic en "Continuar". El sistema:
   1. valida formatos y tamaño (spec `almacenamiento-documentos`);
   2. extrae los datos (sección 6.3) y verifica que el PDF y el XML sean la misma factura (RD-02);
   3. verifica el número de factura duplicado y el UUID duplicado;
   4. crea la factura en "Borrador" con sus documentos y lleva al Paso 2.

   Si faltan datos esenciales (RD-03), muestra "No pudimos leer los datos de la factura en el PDF. Adjunte el XML." y no crea la factura.
3. **Paso 2 · Revisión:** a la izquierda, la imagen de cada página del PDF; a la derecha, las tarjetas **Factura** (serie y folio, UUID, fecha, tipo, moneda, forma y método de pago), **Proveedor** (RFC, nombre, régimen), **Cliente** (RFC, nombre, régimen, uso de CFDI, C.P.), **Conceptos** (cantidad, unidad, descripción, precio unitario, objeto de impuesto, importe, IVA y la O.C. detectada) y **Totales**. Cada dato validado muestra su resultado (✓ o ✗ con el valor esperado). Debajo, el checklist de documentos soporte configurados (por ejemplo, Vo.Bo.) con su carga.
4. El proveedor puede reemplazar el PDF o el XML (se vuelven a extraer y a validar) o cargar soportes.
5. **Paso 3 · Envío:** "Enviar" ejecuta la Validación 1 y la Validación 2 con la configuración vigente y la O.C. del momento.
   - Sin bloqueos: la factura pasa a "Enviada", queda ligada a su O.C. y se muestra el resultado.
   - Con bloqueos: la factura sigue en "Borrador" o "Cargada" y se muestra la matriz de validación con cada diferencia contra la O.C. (encabezado y partida por partida).
6. PMO revisa la factura como hoy; el detalle muestra la O.C. ligada (encabezado y partidas) en lugar del contrato.
7. PMO y Administrador consultan **Órdenes de compra** (listado y detalle).
8. El proveedor internacional registra su Invoice como hoy (HU-15), captura el número de O.C. en lugar de elegir contrato, y al enviar se valida contra el encabezado y la entrega de la orden (sección 6.7).

## 8. Criterios de aceptación

### 8.1 Spec `orden-compra`

### Requirement: Entidad Orden de compra
El sistema SHALL guardar cada orden de compra en `purchase_orders` con `convenio` (entero positivo, único), `rfc` (12 o 13 caracteres), `supplier_name` (hasta 150), `order_date`, `total` (> 0), `taxes` (≥ 0) y `data` (JSONB con `items`, al menos una partida con `Txt.brv`, `Ctd.Pedido`, `Unidad.Pedido`, `Prc.Neto` y `Moneda`). La factura SHALL ligarse a su orden de compra con `invoices.purchase_order_id` (llave foránea que impide borrar una orden de compra con facturas).

#### Scenario: Convenio repetido
- **WHEN** se inserta una segunda orden de compra con `convenio = 25704872`
- **THEN** la base de datos rechaza la operación

#### Scenario: Total no positivo
- **WHEN** se inserta una orden de compra con `total = 0`
- **THEN** la base de datos rechaza la operación

#### Scenario: Borrado de una orden de compra facturada
- **WHEN** se borra una orden de compra ligada a una factura
- **THEN** la base de datos rechaza la operación

### Requirement: Datos demo de órdenes de compra
La demo SHALL sembrar órdenes de compra de los proveedores demo nacionales, entre ellas el convenio 25704872 del ejemplo de la solicitud (proveedor `GOHS60031745A`, Total 3,559.05, Impuestos 569.45, una partida "LTH TIPO L-31 T-900 AR", 1 PZA a 3,559.05 MXN con entrada de mercancía), una orden con una partida sin entrada de mercancía y una orden con dos partidas.

#### Scenario: Orden del ejemplo sembrada
- **WHEN** se siembra la demo
- **THEN** existe la orden de compra 25704872 con una partida cuyo `Docto Material` es `5000527117`

### Requirement: Consulta de órdenes de compra
El menú "Órdenes de compra" SHALL mostrar a PMO y Administrador el listado paginado en SQL (convenio, fecha, RFC, nombre, total, impuestos, número de partidas y facturas ligadas), con búsqueda por convenio, RFC o nombre, y el detalle de cada orden con su encabezado, sus partidas con todas las etiquetas de `DATA` y sus facturas ligadas. El Proveedor MUST NOT acceder al listado ni al detalle.

#### Scenario: Búsqueda por convenio
- **WHEN** PMO busca `25704872`
- **THEN** el listado muestra sólo esa orden de compra

#### Scenario: Detalle con partidas
- **WHEN** el Administrador abre la orden 25704872
- **THEN** ve el encabezado y la partida con Material `E20080`, Txt.brv, cantidad, unidad, fecha de entrega, precio neto, moneda, grupo, almacén, documento de material y fecha contable

#### Scenario: Proveedor sin acceso
- **WHEN** un Proveedor abre `/purchase-orders`
- **THEN** la respuesta es HTTP 403

### Requirement: Validación de la factura contra la orden de compra
Al enviar una factura nacional (y al verificarla), el motor SHALL evaluar `OC-001` a `OC-012` según la sección 6.4 de la HU-24, con la orden de compra vigente al momento, y SHALL guardar en la evidencia de cada resultado los valores de la orden leídos. `CRITICAL` y `ERROR` SHALL impedir el envío. Al enviarse, la factura SHALL quedar ligada a su orden de compra.

#### Scenario: Factura del ejemplo
- **WHEN** el proveedor `GOHS60031745A` envía la factura 3668 (concepto "LTH TIPO L-31T-900 AR BATERIA (OC/25704872)", 1.00 H87 - PZ, 3,559.05, IVA 569.45, MXN)
- **THEN** `OC-001` a `OC-012` resultan `PASS`, la factura pasa a "Enviada" y queda ligada a la orden 25704872

#### Scenario: Sin número de orden de compra
- **WHEN** ningún concepto trae el texto `OC/<número>`
- **THEN** `OC-001` resulta `FAIL` "No se encontró el número de orden de compra en los conceptos", `OC-002` a `OC-012` resultan `NOT_APPLICABLE` y el envío no procede

#### Scenario: Orden de otro proveedor
- **WHEN** el concepto cita una orden de compra cuyo RFC es de otro proveedor
- **THEN** `OC-002` resulta `FAIL` "La orden de compra <n> no existe para el proveedor"

#### Scenario: Subtotal distinto
- **WHEN** el subtotal de la factura es 3,600.00 y el Total de la orden es 3,559.05
- **THEN** `OC-005` resulta `FAIL` con esperado 3,559.05 y detectado 3,600.00

#### Scenario: IVA distinto
- **WHEN** la suma del IVA tasa 0.160000 de los conceptos es 570.00 y los Impuestos de la orden son 569.45
- **THEN** `OC-006` resulta `FAIL`

#### Scenario: Concepto sin partida
- **WHEN** un concepto describe "BATERIA LTH L-40" y ninguna partida de la orden tiene un `Txt.brv` contenido en esa descripción
- **THEN** `OC-007` resulta `FAIL` para ese concepto y sus `OC-008`, `OC-009` y `OC-011` resultan `NOT_APPLICABLE`

#### Scenario: Txt.brv con espacios distintos
- **WHEN** el concepto dice "LTH TIPO L-31T-900 AR BATERIA" y la partida "LTH TIPO L-31 T-900 AR"
- **THEN** `OC-007` resulta `PASS` para ese concepto

#### Scenario: Cantidad distinta
- **WHEN** el concepto factura 2 piezas y la partida tiene `Ctd.Pedido` 1
- **THEN** `OC-008` resulta `FAIL` "Concepto 1: cantidad 2 vs 1"

#### Scenario: Unidad equivalente
- **WHEN** el concepto tiene unidad "H87 - PZ" y la partida `Unidad.Pedido` "PZA"
- **THEN** `OC-008` resulta `PASS`

#### Scenario: Importe distinto
- **WHEN** el concepto tiene importe 3,600.00 y la partida `Prc.Neto` 3,559.05 con cantidad 1
- **THEN** `OC-009` resulta `FAIL` "Concepto 1: importe 3600.00 vs 3559.05"

#### Scenario: Moneda distinta
- **WHEN** la factura está en USD y la partida en MXN
- **THEN** `OC-010` resulta `FAIL`

#### Scenario: Mercancía no entregada
- **WHEN** la partida usada no tiene `Docto Material` o `Fecha Conta`
- **THEN** `OC-011` resulta `FAIL` "Concepto 1: la partida no tiene entrada de mercancía" y el envío no procede

#### Scenario: Orden ya facturada
- **WHEN** la orden 25704872 ya tiene una factura "Enviada" y se envía otra factura que la cita
- **THEN** `OC-012` resulta `FAIL` con el folio de la primera y el envío no procede

#### Scenario: Orden con factura cancelada
- **WHEN** la única factura de la orden está "Cancelada" y se envía otra factura que la cita
- **THEN** `OC-012` resulta `PASS`

### Requirement: Factura internacional contra la orden de compra
El registro del Invoice internacional SHALL pedir el número de orden de compra en lugar del contrato. Al enviarlo, el motor SHALL evaluar las reglas `OC-*` según la sección 6.7 de la HU-24, buscando la orden por Convenio y por el proveedor del usuario (`supplier_id`).

#### Scenario: Invoice que cuadra con su orden
- **WHEN** el proveedor internacional demo envía un Invoice con la orden de compra sembrada, subtotal, impuestos y moneda iguales a los de la orden, y la orden tiene entrada de mercancía
- **THEN** `OC-001`, `OC-002`, `OC-004`, `OC-005`, `OC-006`, `OC-010`, `OC-011` y `OC-012` resultan `PASS`, `OC-003` y `OC-007` a `OC-009` resultan `NOT_APPLICABLE` y la factura pasa a "Enviada"

#### Scenario: Orden de otro proveedor
- **WHEN** el proveedor internacional captura el número de una orden de compra de otro proveedor
- **THEN** `OC-002` resulta `FAIL` "La orden de compra <n> no existe para el proveedor"

#### Scenario: Sin número de orden de compra
- **WHEN** el proveedor internacional guarda los datos del Invoice sin número de orden de compra
- **THEN** el formulario muestra "Capture el número de orden de compra" con HTTP 400

### Requirement: Contratos conservados sin uso
Las tablas y columnas de contratos SHALL conservarse con sus datos y restricciones, y ninguna ruta, servicio, regla ni plantilla del portal SHALL leerlas o escribirlas. Las facturas creadas a partir de esta HU SHALL tener `contract_id` nulo.

#### Scenario: Datos de contratos después de la migración
- **WHEN** se migra una base con contratos, enmiendas y facturas ligadas a contratos
- **THEN** las tablas y sus filas siguen presentes, las facturas conservan su `contract_id` y `/contracts` responde HTTP 404

#### Scenario: Factura nueva
- **WHEN** un proveedor registra una factura después de la migración
- **THEN** la factura tiene `contract_id` nulo

### 8.2 Spec `registro-factura-extraccion`

### Requirement: Registro de la factura a partir de sus archivos
El Paso 1 del registro SHALL pedir el PDF de la factura (obligatorio) y el XML (opcional) y SHALL NOT pedir contrato, número de factura, periodo, proyecto ni líder de proyecto. Con los archivos válidos, el sistema SHALL extraer los datos, crear la factura en "Borrador" con número `Serie`+`Folio` (o el número impreso), periodo `MM/AAAA` de la fecha de emisión y moneda del comprobante si está activa en el catálogo, guardar ambos documentos y llevar al Paso 2. Las verificaciones de proveedor autorizado y de usuario vinculado de `flujo-facturas` SHALL conservarse.

#### Scenario: Sólo PDF
- **WHEN** un proveedor nacional autorizado carga sólo el PDF de la factura 3668
- **THEN** la factura se crea en "Borrador" con número `3668`, periodo `01/2026`, UUID `A328F91A-DDDD-4624-89AC-877819F5B540` y moneda MXN, y la respuesta lleva al Paso 2

#### Scenario: PDF y XML
- **WHEN** el proveedor carga el PDF y el XML de la misma factura
- **THEN** los datos fiscales se toman del XML y ambos documentos quedan ligados a la factura

#### Scenario: PDF y XML de facturas distintas
- **WHEN** el UUID del PDF es distinto del UUID del XML
- **THEN** la respuesta es HTTP 409 "El PDF y el XML no corresponden a la misma factura" y no se crea la factura

#### Scenario: Sin PDF
- **WHEN** el proveedor envía el Paso 1 sólo con XML
- **THEN** la respuesta es HTTP 400 "Adjunte el PDF de la factura" y no se crea la factura

#### Scenario: PDF ilegible
- **WHEN** el PDF no tiene texto y el analizador documental no está disponible, y no se adjuntó XML
- **THEN** la respuesta es HTTP 422 "No pudimos leer los datos de la factura en el PDF. Adjunte el XML." y no se crea la factura

#### Scenario: Número de factura repetido
- **WHEN** el número extraído ya existe en otra factura del mismo proveedor
- **THEN** la respuesta es HTTP 409 "Ya existe una factura con ese número para el proveedor" y no se crea la factura

### Requirement: Extracción de los datos del PDF
El sistema SHALL extraer de la representación impresa del CFDI 4.0 los datos de la sección 6.3 de la HU-24: del texto del PDF cuando lo tiene y, cuando no, del analizador documental configurado. La extracción SHALL guardar los datos y su fuente (`xml`, `pdf_text` u `ocr`) en `metadata_json` del documento.

#### Scenario: Conceptos de la factura 3668
- **WHEN** se extraen los datos del PDF de la factura 3668
- **THEN** se obtiene un concepto con cantidad 1.00, clave de unidad `H87`, unidad `PZ`, no. de identificación `L-31T-900`, descripción "LTH TIPO L-31T-900 AR BATERIA (OC/25704872)", precio unitario 3,559.05, objeto de impuesto `02`, importe 3,559.05 e IVA tasa 0.160000 por 569.45

#### Scenario: Emisor y receptor de la factura 3668
- **WHEN** se extraen los datos del PDF de la factura 3668
- **THEN** el emisor es `GOHS60031745A` · SOCORRO PATRICIA GONZALEZ HERNANDEZ · régimen `612`, y el receptor `IME010718PU3` · INTERMODAL MEXICO · régimen `601` · uso `G03` · C.P. `11700`

### Requirement: Revisión de los datos junto a la imagen de la factura
El Paso 2 SHALL mostrar a la izquierda las páginas del PDF de la factura como imagen y a la derecha los datos extraídos (factura, proveedor, cliente, conceptos con la O.C. detectada y totales), con el resultado de la Validación 1 junto a cada dato validado, y el checklist de documentos soporte configurados. Reemplazar el PDF o el XML SHALL volver a extraer y validar. El Paso 2 SHALL NOT cambiar el estatus de la factura.

#### Scenario: Revisión de la factura 3668
- **WHEN** el proveedor abre el Paso 2 de la factura 3668
- **THEN** ve la imagen de la página 1 a la izquierda y, a la derecha, los datos con `PRV-001`, `PRV-002`, `PRV-003`, `XML-002`, `XML-005`, `XML-009` y `XML-011` en `PASS`

#### Scenario: Factura emitida a otro cliente
- **WHEN** el RFC receptor es `ULT940623AG0`
- **THEN** el dato RFC del cliente muestra ✗ con el valor esperado configurado y `XML-002` resulta `FAIL`

### Requirement: Validación de los datos del proveedor
`PRV-001` a `PRV-003` SHALL evaluarse según la sección 6.4 de la HU-24 en la Validación 1 y otra vez al enviar.

#### Scenario: RFC emisor de otro proveedor
- **WHEN** el RFC emisor de la factura no es el RFC del proveedor del usuario
- **THEN** `PRV-001` resulta `FAIL` (`CRITICAL`) y el envío no procede

#### Scenario: Nombre con acentos y mayúsculas distintos
- **WHEN** el emisor es "Socorro Patricia González Hernández" y el proveedor "SOCORRO PATRICIA GONZALEZ HERNANDEZ"
- **THEN** `PRV-002` resulta `PASS`

#### Scenario: Sin régimen fiscal del emisor
- **WHEN** la factura no trae el régimen fiscal del emisor
- **THEN** `PRV-003` resulta `FAIL` "Falta el régimen fiscal del emisor"

## 9. Deltas sobre capacidades existentes

### 9.1 `flujo-facturas`

- **MODIFIED "Alta de factura con datos validados":** sustituir el punto 2 (esquema `InvoiceCreate` capturado) y el 3 (contrato) por "los archivos del Paso 1 y sus datos extraídos (spec `registro-factura-extraccion`)"; quitar "La factura de un proveedor nacional SHALL nacer con la moneda de su contrato"; quitar los escenarios "Periodo inválido", "Periodo sin formato estricto" y "Moneda inicial de la factura nacional"; en "Alta correcta", "con datos válidos y un contrato propio activo" pasa a "con el PDF de una factura propia". Los escenarios del proveedor inactivo, del usuario sin proveedor y del número repetido se conservan.
- **REMOVED "Contratos del proveedor en el formulario de alta".** Reason: el formulario ya no ofrece contratos. Migration: la orden de compra se obtiene de los conceptos (spec `orden-compra`).
- **MODIFIED "Envío a validación":** agregar que el envío evalúa también la Validación 2 y liga la factura a su orden de compra.

### 9.2 `motor-validacion`

```markdown
## REMOVED Requirements

### Requirement: Contrato y anexos disponibles según los requisitos del contrato
**Reason**: Se retira el módulo de contratos en la rama `ferromex` (HU-24).
**Migration**: La factura se controla contra su orden de compra (`OC-001` a `OC-012`, spec `orden-compra`).

### Requirement: Periodo del servicio dentro de la vigencia del contrato
**Reason**: Se retira el módulo de contratos en la rama `ferromex` (HU-24).
**Migration**: Sin sustituto en esta HU (P-14).
```

- **MODIFIED "Fuente única de reglas de negocio":** la lista de familias pasa a DOC, PRV, SUP, XML, FIN, DAT y OC; se quitan CON y SEM, y de FIN y SUP las reglas FIN-001, FIN-003, FIN-006 y SUP-002.
- **MODIFIED "Reglas documentales según los archivos mínimos configurados":** quitar la remisión de DOC-005.
- **MODIFIED "Reglas nacionales que no aplican a la factura internacional":** agregar `PRV-001` a `PRV-003`, `OC-003` y `OC-007` a `OC-009` como `NOT_APPLICABLE` para el internacional; las demás `OC-*` sí aplican (sección 6.7).

### 9.2 bis `factura-internacional`

- **MODIFIED** (el requisito del registro del Invoice): el contrato se sustituye por el número de orden de compra obligatorio (sección 6.7). Los escenarios que eligen un contrato pasan a capturar la orden.

### 9.3 `archivos-minimos-factura`

- **MODIFIED "Catálogo de tipos de documento de factura":** valores iniciales de la rama `ferromex`: `INVOICE_XML` Opcional · No aplica; `INVOICE_PDF` Obligatorio · No aplica; `PURCHASE_ORDER`, `CONTRACT` y `CONTRACT_ANNEX` No aplica · No aplica. Escenario: "Catálogo inicial tras la migración" con esos niveles.

### 9.4 `integridad-datos`

- **MODIFIED "Restricciones CHECK sobre estados, montos y vigencias":** agregar `purchase_orders.total > 0`, `purchase_orders.taxes >= 0` y `purchase_orders.convenio > 0`. Las restricciones de contratos se conservan sin cambios, porque las tablas se conservan (P-02).
- "Integridad del catálogo de requisitos del contrato" y "Documentos del contrato con un solo dueño" **se conservan**: siguen siendo ciertas sobre las tablas sin uso.
- **ADDED "Integridad de las órdenes de compra":** convenio único, `data` con `items` no vacío (`CHECK jsonb_array_length(data->'items') >= 1`) y FK `RESTRICT` desde `invoices.purchase_order_id`.

### 9.5 `interfaz-usuario`

- **MODIFIED** (el requisito del menú de navegación): "Contratos" pasa a "Órdenes de compra" (PMO y Administrador); "Requisitos mínimos" pierde "Alta de contrato". Los pasos del asistente se llaman "Archivos", "Revisión" y "Envío".

### 9.6 `requisitos-alta-contrato` y `trazabilidad-contratos`

Todos sus requisitos pasan a `## REMOVED Requirements`, cada uno con:

```markdown
**Reason**: Se retira el módulo de contratos en la rama `ferromex`; la factura se controla contra su orden de compra (HU-24).
**Migration**: Las tablas `contracts`, `contract_amendments` y `contract_document_types` se conservan con sus datos sin uso (P-02); la factura apunta a `purchase_orders`.
```

- `requisitos-alta-contrato`: Catálogo de requisitos del contrato; Configuración exclusiva del Administrador; Configuración de los requisitos del contrato; Requisitos del contrato definidos por el Administrador; Estatus del contrato; Expediente del contrato; Carga de documentos del contrato; Activación del contrato; Requisitos en el listado de contratos; Protección contra ediciones concurrentes; Auditoría de los requisitos del contrato; Acciones Editar y Eliminar en la configuración; Edición y eliminación lógica de los requisitos del contrato.
- `trazabilidad-contratos`: Campos de auditoría en contratos; Modificación versionada del monto autorizado; Validación auditable contra el monto vigente.

## 10. Notas de diseño (insumo para `design.md`)

- **Extracción en un servicio propio** (`invoice_extraction_service`): `extract(pdf, xml) -> ExtractedInvoice` con la fuente de cada dato. Extiende `parse_cfdi` (serie, folio, régimen del emisor, `ClaveUnidad`, `Unidad`, `NoIdentificacion`, `ObjetoImp`) sin romper a sus llamadores. El parser del PDF trabaja sobre el texto de PyMuPDF con expresiones por etiqueta (sección 6.3) y se prueba con el PDF del ejemplo y con los del generador de `data/pruebas-ferromex/_generador`.
- **OCR detrás de `DocumentAnalyzer.extract_fields`:** el de demo responde "no disponible"; Azure Document Intelligence (`prebuilt-invoice`) se conecta después (P-09).
- **El motor evalúa sobre los datos extraídos**, no sobre `parse_cfdi` directo: `run_validation` recibe `ExtractedInvoice` y aplica XML-* aunque la fuente sea el PDF.
- **Reglas nuevas** en `app/rules/supplier_identity_rules.py` (`PRV-*`) y `app/rules/purchase_order_rules.py` (`OC-*`), funciones puras probadas sin base de datos, como las vigentes. `purchase_order_service` resuelve la orden (RD-06, RD-07), el emparejamiento de partidas (RD-08, RD-09) y la orden ya facturada (RD-16, con `SELECT … FOR UPDATE` sobre la orden al enviar, para que dos envíos simultáneos no pasen ambos).
- **Normalización:** reutilizar `normalize_text` de `contract_rules.py` (se mueve a `app/rules/text.py` antes de borrar el módulo); para `Txt.brv` además se quitan los espacios.
- **Equivalencias de unidad** como constante en `app/core/constants.py` en esta HU; catálogo administrable si negocio lo pide (P-10).
- **Asistente:** `GET/POST /invoices/new` (Paso 1, `multipart`); `GET /invoices/{id}/review` (Paso 2, reutiliza `/documents/{doc}/pages/{n}`); `/invoices/{id}/documents` queda para soportes; `POST /invoices/{id}/submit` sin cambios de ruta.
- **Migración única** `0023_ferromex_purchase_orders`: crea `purchase_orders`; agrega `invoices.purchase_order_id`; **no borra** tablas ni columnas de contratos (P-02); `project_name` y `project_leader` admiten nulo; actualiza niveles de `invoice_document_types` (sección 9.3) y las Reglas de Validación del receptor nacionales e internacionales a INTERMODAL MEXICO (P-01). Downgrade con `NotImplementedError` si hay órdenes de compra o facturas ligadas a una orden.
- **Modelos de contratos sin uso:** `Contract`, `ContractAmendment` y `ContractDocumentType` se quedan en `app/models` con docstring "Obsoleto en la rama ferromex (HU-24)", sin relaciones desde `Supplier` ni `Invoice`, para que `alembic check` siga sin diferencias. Una prueba verifica que ningún módulo fuera de `app/models` y `alembic/` importa esos modelos.
- **Internacional:** `foreign_invoice_service.parse_data` agrega `purchase_order_number`; `purchase_order_service.resolve` busca por Convenio y `rfc` (nacional) o `supplier_id` (internacional).
- **Orden del trabajo:** primero la entidad y las reglas `OC-*` contra la factura actual (con XML), luego el asistente y la extracción del PDF, y al final el retiro de contratos, para mantener la suite en verde en cada paso.

## 11. Impacto

- **Código** (rutas relativas a la raíz de la PoC):
  - nuevos: `app/services/invoice_extraction_service.py`, `app/services/purchase_order_service.py`, `app/rules/supplier_identity_rules.py`, `app/rules/purchase_order_rules.py`, `app/rules/text.py`, `app/routers/purchase_orders.py`, plantillas `purchase_orders/list.html`, `purchase_orders/detail.html` e `invoices/review.html`;
  - modificados: `app/models/__init__.py`, `app/core/constants.py`, `app/schemas/__init__.py`, `app/services/xml_service.py`, `app/services/validation_engine.py`, `app/services/submission_service.py`, `app/rules/document_rules.py`, `app/rules/financial_rules.py`, `app/rules/supplier_rules.py`, `app/rules/semantic_rules.py`, `app/routers/invoices.py`, `app/routers/admin.py`, `app/routers/suppliers.py`, `app/main.py`, `app/templates/base.html`, `invoices/new.html`, `invoices/detail.html`, `invoices/documents.html`, `app/static/js/app.js`, `scripts/seed_db.py`, `scripts/reporte_monedas.py`;
  - eliminados: los archivos de código de la sección 6.6 (las tablas y los modelos ORM se conservan);
  - internacional: `app/services/foreign_invoice_service.py`, `components/foreign_invoice_fields.html`, `app/rules/international_rules.py`.
- **Esquema:** revisión Alembic `0023_ferromex_purchase_orders`, posterior a `0022_stored_files`. Sólo agrega; no borra tablas de contratos.
- **Rutas:** nuevas `GET /purchase-orders`, `GET /purchase-orders/{id}`, `GET /invoices/{id}/review`; cambia `POST /invoices/new` (multipart con archivos); se eliminan `/contracts*` y `/admin/contract-requirements*`.
- **Datos demo:** `seed_db.py` siembra órdenes de compra (sección 8.1) y rehace las 10 facturas demo con `OC/<convenio>` en sus conceptos; `data/demo_documents/` agrega el PDF y el XML de la factura 3668.
- **Recorrido manual:** `data/pruebas-ferromex/` se rehace: A-1001 contra una O.C. que cuadra (autorizada y pagada) y A-1002 rechazada por diferencia de importe contra la O.C. (en lugar de "excede el monto del contrato"); el generador agrega `OC/<convenio>` a los conceptos.
- **Pruebas:** nuevos `test_orden_compra.py`, `test_extraccion_factura.py` y `test_registro_por_archivos.py`; se eliminan `test_contratos.py` y `test_requisitos_contrato.py`; se ajustan `conftest.py` (fixture de orden de compra en lugar de contrato activo) y los ~20 módulos que crean contratos; suite Playwright `tests/hu`: HU-12/HU-13 con el nuevo asistente.
- **Documentación:** `README.md` (asistente, órdenes de compra, reglas nuevas y retiradas), `docs/source-of-truth/INDICE_HUs.md` y specs vigentes al archivar.
- **Sin cambios:** autenticación y Keycloak, notificaciones, plantillas, cancelación, pago y complemento de pago, catálogos, carga masiva y requisitos de alta del proveedor.

## 12. Dependencias

| Depende de | Motivo |
| --- | --- |
| PDF y XML reales de FERROMEX (al menos 3 facturas y sus O.C. de SAP) | Para probar el parser de la representación impresa más allá del ejemplo |
| Rama `ferromex` (commit `d54531c` o posterior) | Marca, realm y datos de prueba de Ferromex |

| La necesitan | Motivo |
| --- | --- |
| Integración con SAP (futura) | Cargará `purchase_orders` con la estructura de esta HU |

## 13. Definición de terminado

- [ ] Criterios de las secciones 8.1 y 8.2 cubiertos por pruebas automatizadas sobre PostgreSQL.
- [ ] El PDF de la factura 3668 del documento (sólo PDF, sin XML) se registra, se revisa en el Paso 2 y se envía con `OC-001` a `OC-012` en `PASS` contra la orden 25704872.
- [ ] Sin referencias a contratos en rutas, menú, plantillas, servicios ni reglas: `grep -ril contract app/` sólo encuentra `app/models` y `app/core/constants.py`. Las tablas de contratos y sus datos siguen en la base.
- [ ] Un Invoice internacional demo se envía contra su orden de compra en USD.
- [ ] Migración `0023` con `alembic check` sin diferencias y pruebas de upgrade desde `0022` con contratos y facturas existentes.
- [ ] `scripts/check.py` en verde: ruff, `alembic check`, pytest con cobertura ≥ 93 % y `pip-audit`.
- [ ] Datos demo y recorrido manual de `data/pruebas-ferromex/` actualizados y ejecutados.
- [ ] README actualizado.
- [ ] SonarQube sin incidencias nuevas en la rama.

## 14. Trazabilidad

| Elemento | Referencia |
| --- | --- |
| Solicitud | `docs/source-of-truth/ferromex/REQUERIMIENTO_DE_AJUSTES_PORTAL_DE_PROVEEDORES_FINAL.docx` |
| Factura de ejemplo | `docs/source-of-truth/ferromex/factura-ejemplo-3668.png` |
| Orden de compra de ejemplo (SAP) | `docs/source-of-truth/ferromex/sap-convenio-25704872.png` |
| HUs afectadas | HU-12, HU-13 (registro y envío), HU-19 (detalle PMO: O.C. en lugar de contrato), HU-04 (archivos mínimos) |
| HU retirada en la rama | HU-22 (requisitos de alta del contrato) |
| Reglas nuevas | `PRV-001` a `PRV-003`, `OC-001` a `OC-012` |
| Reglas retiradas | SUP-002, CON-001 a CON-004, DOC-005, FIN-001, FIN-003, FIN-006, SEM-001 |

## 15. Puntos a confirmar en la revisión

Resueltos por negocio el 2026-11-24: receptor INTERMODAL MÉXICO (P-01), contratos conservados sin uso (P-02), regla de importe RD-11 (P-03) e internacional contra O.C. (P-04). Quedan:

1. Facturación parcial de una O.C. y facturas con varias O.C. (P-06, P-07).
2. Severidad de la entrega pendiente. (P-13)
3. Identificación del proveedor internacional en SAP y validación de sus partidas. (P-15)
