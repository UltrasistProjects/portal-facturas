# EP-02 · Validación de facturas por PMO

| Campo | Valor |
| --- | --- |
| ID | EP-02 |
| Rol | PMO (rol `INTERNAL` en el portal) |
| Módulo (ERS v1.3) | D. Módulo de Validación |
| Historias | HU-18, HU-19, HU-20 |
| Requisitos funcionales | RF-17, RF-18, RF-10 |
| Reglas de negocio | RN-HU20-01, RN-HU20-02, RN-HU20-03 |
| Prioridad | Alta (alcance comprometido del MVP) |
| Depende de | EP-01: facturas "Enviadas" (HU-13 y HU-16) y el modelo de estatus (DT-01 de EP-01). HU-05 y HU-08: plantillas y destinatarios de correo (implementadas) |
| Habilita | HU-17 de EP-01 (consulta de estatus y observaciones por el proveedor) |
| Estado | Lista para refinamiento. Cada HU se detalla en `docs/stories/new/` con el formato de HU-04 antes de `/opsx:propose` |
| Estimación | Tamaños relativos en la sección 3. La estimación se hace en el refinamiento |
| Versión / fecha | 1.0 · 2026-09-28 · Equipo Técnico |

## Cómo usar este documento

Igual que en EP-01:

- la épica fija las decisiones transversales (sección 5), el punto de partida por HU (sección 6), las preguntas para negocio (sección 7) y el orden de entrega (sección 8);
- cada HU se redacta en `docs/stories/new/` y se propone con el change sugerido en la sección 3.

El modelo de estatus de la factura **no se redefine aquí**. Su dueño es EP-01 (DT-01). Esta épica sólo agrega las transiciones del PMO y resuelve los estatus de ClickBalance (DT-06).

---

## 1. Objetivo

El PMO revisa en un solo lugar las facturas que envían los proveedores:

- ve su contenido, sus documentos soporte y el resultado de las validaciones automáticas;
- decide con tres botones —Autorizada, Rechazada u Observaciones— y registra sus observaciones;
- el portal notifica automáticamente a Recepción de Facturas o al proveedor, según la decisión.

**Valor:** la autorización del PMO dispara el aviso a Recepción de Facturas para el pago (minuta, sección "Notificaciones", aviso a `recepcionfacturas@ultrasist.com.mx`). La vía de corrección (Observaciones) evita que el proveedor rehaga la factura completa por un documento faltante.

## 2. Alcance

### Dentro del alcance

- Bandeja de facturas con estatus, proveedor, número de factura, monto, origen y fecha de envío, con filtros (HU-18).
- Detalle de revisión (HU-19), con:
  - la factura y sus soportes visibles en el navegador;
  - los datos del CFDI o los importes capturados del Invoice;
  - el resultado de las validaciones automáticas;
  - el historial de revisiones.
- Decisión con tres botones, observaciones obligatorias para Rechazada y Observaciones, y los correos de RN-HU20-02 y RN-HU20-03 (HU-20).
- Auditoría de cada decisión con usuario, fecha y observaciones (RNF "Trazabilidad y auditoría").

### Fuera del alcance

| Tema | Motivo |
| --- | --- |
| Pasos de ClickBalance del PoC ("Lista para ClickBalance" y "Carga manual a ClickBalance") | No aparecen en el ERS ni en la minuta. Ver P-01 y DT-06 |
| Asignación de facturas a revisores, tiempos de atención y recordatorios | Ninguna fuente lo pide |
| Aviso al PMO cuando llega una factura | Ninguna fuente lo pide. Se podría agregar como un evento nuevo de HU-05 y HU-08 |
| Exportación del listado | Ninguna fuente lo pide |
| Edición de los datos de la factura por el PMO | El PMO decide y el proveedor corrige en "Observaciones" |
| Aceptación de cancelaciones | Pertenece a HU-14 (EP-01, P-09) |
| Reversión de una decisión ya tomada | Ver P-05 |

## 3. Historias de la épica

| HU | Título | RF | RN | Depende de | Change OpenSpec sugerido | Tamaño relativo |
| --- | --- | --- | --- | --- | --- | --- |
| HU-18 | Consulta de facturas por PMO | RF-17 | — | HU-13, HU-16 (EP-01) | `bandeja-y-detalle-pmo` | S |
| HU-19 | Visualización de detalle de factura por PMO | RF-18 | — | HU-18 | el mismo que HU-18 | M |
| HU-20 | Cambio de estatus de factura | RF-10 | RN-HU20-01, RN-HU20-02, RN-HU20-03 | HU-19 | `cambio-estatus-factura` | M |

**Agrupación en changes:**

- **HU-18 y HU-19 van juntas:** HU-19 es la pantalla a la que lleva el listado de HU-18, y ninguna de las dos cambia estatus.
- **HU-20 va aparte:** cambia estatus, envía correos y retira los pasos de ClickBalance.

HU-20 se llamaba "HU1" en el documento de HUs; el ERS v1.2 la renombró.

## 4. Punto de partida

### 4.1 Lo que la épica reutiliza

| Capacidad | Estado actual | Uso en la épica |
| --- | --- | --- |
| Listado (spec `flujo-facturas`) | `GET /invoices`: `INTERNAL` ve todas las facturas. Busca por folio, número, proyecto y razón social, filtra por estatus y pagina de 25 en 25, ordenado por `created_at DESC`. La consulta es constante, sin N+1 | Base de HU-18 |
| Detalle (`invoices/detail.html`) | Datos del CFDI tomados del XML, conciliación con el contrato, matriz de evidencia por categoría con el resumen de `calculate_score` y documentos con descarga | Base de HU-19 |
| Descarga de documentos (`almacenamiento-documentos`) | Siempre como adjunto (`attachment`, `application/octet-stream`). La CSP incluye `frame-ancestors 'none'` y `X-Frame-Options: DENY` | Limita la visualización de HU-19 (DT-03) |
| Revisión (`invoices/review.html`) | Página aparte con cuatro botones: Aceptar, Solicitar corrección, Rechazar y "Solo agregar comentario". Los comentarios son opcionales. `ensure_can_accept` impide aceptar con un `FAIL` crítico. Tabla `reviews` y auditoría | Base de HU-20 |
| Plantillas (HU-05) | `INVOICE_AUTHORIZED` (`numero_factura`, `proveedor`, `monto`), `INVOICE_REJECTED` e `INVOICE_OBSERVATIONS` (`numero_factura`, `observaciones`), con textos predeterminados conforme a RN-HU20-02 y RN-HU20-03 | HU-20 |
| Destinatarios y envío (HU-08) | Autorizada va al buzón Recepción de Facturas; Rechazada y Observaciones van al correo del proveedor. Copias por evento, bitácora y envío después del commit | HU-20 |
| Bloqueo de fila | `with_for_update()` ya se usa en la autorización de proveedores (`supplier_access_service.py`) | Patrón para DT-04 |

### 4.2 Brechas encontradas en el PoC

| # | Brecha | Dónde | Se atiende en |
| --- | --- | --- | --- |
| B-01 | La decisión está en otra página, pero RF-18 dice: "Desde esta pantalla, el PMO ejecuta el cambio de estatus" | `GET /invoices/{id}/review` | HU-19 y HU-20 (DT-04) |
| B-02 | Hay cuatro botones y los comentarios son opcionales; HU-20 pide tres botones y RN-HU20-01, un campo de observaciones | `invoices/review.html`, `review_invoice` | HU-20 |
| B-03 | Ningún cambio de estatus de la factura envía correo | README, "Limitaciones" | HU-20 (DT-05) |
| B-04 | Un PDF no se puede ver en el navegador, sólo descargar | Spec `almacenamiento-documentos` | HU-19 (DT-03) |
| B-05 | El listado no muestra el origen ni la fecha de envío, no filtra por origen y ordena por fecha de creación | `search_invoices` e `invoices/list.html` | HU-18 (DT-02) |
| B-06 | Dos PMO pueden decidir sobre la misma factura a la vez: `get_visible_invoice` usa `db.get`, sin bloqueo de fila, y ambas decisiones se confirman | `invoice_repository.py`, `review_action` | HU-20 (DT-04) |
| B-07 | El detalle sólo muestra el último comentario (`invoices.comments`), no el historial de revisiones | `invoices/detail.html` | HU-19 (DT-07) |
| B-08 | En una factura internacional, la sección "Datos CFDI" queda vacía y no tiene equivalente | `invoices/detail.html` | HU-19 |

## 5. Decisiones transversales

Los estatus que usa esta épica son los de DT-01 de EP-01:

- **Entrada:** "Enviada" (`UNDER_REVIEW`).
- **Salidas:** "Autorizada" (`ACCEPTED`), "Rechazada" (`REJECTED`) y "Observaciones" (`REQUIRES_CORRECTION`).

### DT-01 · El rol PMO es `INTERNAL`

- HU-18 y HU-19 son de lectura para `INTERNAL` y `ADMIN`, como hoy.
- HU-20 permite decidir a `INTERNAL` y a `ADMIN`, como hoy. P-02 confirma si el Administrador debe perder esa facultad por separación de funciones.
- `PROVIDER` recibe HTTP 403 en cualquier acción de decisión.

### DT-02 · La bandeja muestra primero lo pendiente

Para `INTERNAL` y `ADMIN`, `GET /invoices` abre filtrada en "Enviada" y ordenada por `submitted_at` ascendente, para atender primero lo que más ha esperado. Al elegir "Todos los estatus" u otro estatus, vuelve al orden de hoy (`created_at DESC`).

- **Columnas:** folio interno, número de factura, proveedor, origen (Nacional o Internacional), monto con moneda, estatus, fecha de envío y número de advertencias de la validación.
- **Filtros:** estatus, origen y la búsqueda que ya existe.
- **Visibilidad:** el ERS pide "las facturas registradas por los proveedores", así que todos los estatus quedan disponibles con el filtro; la bandeja por omisión sólo muestra las pendientes.

Se conserva una sola ruta para todos los roles, con valores por omisión según el rol. El proveedor sigue viendo sólo sus facturas. HU-18 decide si hace falta el índice `(status, submitted_at)`.

### DT-03 · Visualización de documentos en el navegador

**Propuesta:** una ruta nueva `GET /invoices/{id}/documents/{doc}/view`.

- **Formatos:**
  - PDF, PNG y JPEG se sirven con el MIME que corresponde a la extensión verificada al cargarlos, con `Content-Disposition: inline` y `X-Content-Type-Options: nosniff`;
  - XML y TXT se muestran como texto escapado dentro de una página del portal, nunca interpretados por el navegador. El XML del CFDI además sigue mostrándose como datos en "Datos CFDI".
- **Cómo se abre:** en una pestaña nueva. La CSP del portal (`frame-ancestors 'none'`) y `X-Frame-Options: DENY` no se relajan para incrustar documentos en un marco.
- **Autorización:** la misma que la descarga. El proveedor sólo ve documentos de sus facturas y el documento debe pertenecer a la factura de la URL. Así el proveedor también puede usar "Ver" (HU-17).
- **Descarga:** conserva `attachment`.
- **Efecto en las specs:** se agrega el requisito "Visualización segura" a `almacenamiento-documentos`.

**Riesgo a verificar:** la CSP que se aplique al PDF debe permitir el visor integrado de Chrome, Edge y Firefox (RNF de compatibilidad). Una directiva como `sandbox` puede impedir el visor de Chromium. Si no se encuentra una combinación segura, la alternativa es incluir pdf.js en `app/static/vendor/`.

### DT-04 · La decisión se toma en el detalle, sin carreras

- **Dónde:** el panel "Decisión" aparece en el detalle cuando la factura está "Enviada" y el rol puede decidir. `GET /invoices/{id}/review` redirige al detalle, por compatibilidad.
- **Botones:** tres, "Autorizada", "Rechazada" y "Observaciones". El botón "Solo agregar comentario" se retira; el valor `COMMENT` se conserva en la enumeración para las revisiones históricas.
- **Observaciones (RN-HU20-01):** son obligatorias para "Rechazada" y "Observaciones".
  - Si faltan (texto vacío después de recortar espacios), la respuesta es HTTP 400 con "Capture las observaciones".
  - Para "Autorizada" no se piden.
  - Sin JavaScript, el campo está siempre visible con la nota "obligatorio para Rechazar u Observaciones".
  - Con JavaScript, el campo aparece al elegir uno de esos botones, que es lo que pide la RN ("despliega un campo"). El script va en un archivo externo, sin código en línea, por la CSP.
- **Bloqueo crítico:** `ensure_can_accept` se conserva. No se autoriza una factura con un `FAIL` crítico.
- **Concurrencia (B-06):** la factura se lee con `with_for_update()` y se valida la transición. La segunda decisión simultánea recibe HTTP 409 con "La factura ya fue revisada", sin registrar otra revisión ni enviar otro correo.

### DT-05 · Correos de la decisión (RN-HU20-02 y RN-HU20-03)

El correo se envía con el servicio de HU-08 **después** de confirmar la decisión (DT-09 de EP-01).

| Decisión | Evento | Para | Variables |
| --- | --- | --- | --- |
| Autorizada | `INVOICE_AUTHORIZED` | Buzón Recepción de Facturas y las copias del evento | `numero_factura`, `proveedor`, `monto`, `folio_interno`, `estatus`, `fecha_estatus` |
| Rechazada | `INVOICE_REJECTED` | `suppliers.email` (el "correo de la entidad proveedores") y las copias | `numero_factura`, `observaciones`, `proveedor`, `monto`, `folio_interno`, `estatus`, `fecha_estatus` |
| Observaciones | `INVOICE_OBSERVATIONS` | Igual que Rechazada | Igual que Rechazada |

- **Monto:** `invoices.total` con `invoices.currency`. En la factura internacional es el total capturado (P-03).
- **Si el envío falla:**
  - la decisión se mantiene y la bitácora registra `FAILED`;
  - la pantalla avisa, por ejemplo: "Factura autorizada. No se pudo enviar el correo a Recepción de Facturas: <error>".
- **Reenvío:** se propone un botón "Reenviar notificación" en el detalle cuando el último envío de esa decisión falló, como el reenvío de credenciales de HU-03. Sin él, un correo de autorización perdido significa que Recepción no se entera de que debe pagar.

### DT-06 · ClickBalance queda fuera del flujo del MVP (P-01)

El ERS (§3.6) termina en "Autorizada" y ni el ERS ni la minuta mencionan ClickBalance.

**Propuesta para el change de HU-20:**

- retirar de la interfaz los botones "Marcar lista para ClickBalance" y "Confirmar carga manual a ClickBalance";
- migrar las facturas en `READY_FOR_CLICKBALANCE` y `UPLOADED_TO_CLICKBALANCE` a `ACCEPTED`, con un registro de auditoría `STATUS_MIGRATED`;
- retirar esos valores de la enumeración, de `ALLOWED_TRANSITIONS` y del seed demo (casos `CLICK-READY` y `CLICK-DONE`).

Si negocio decide conservarlo, quedan como pasos internos posteriores a "Autorizada" y el proveedor los ve como "Autorizada".

### DT-07 · Historial de revisiones visible

- **Qué muestra:** el detalle lista las revisiones de la factura (fecha, decisión, observaciones y revisor) a partir de la tabla `reviews`, junto con los envíos del proveedor (auditoría `INVOICE_SUBMITTED`).
- **Para qué:** el PMO ve las rondas anteriores cuando una factura vuelve de "Observaciones".
- **Para el proveedor (HU-17):** la misma lista, sin el nombre del revisor.

## 6. Brechas y alcance por HU

### HU-18 · Consulta de facturas por PMO

**Hoy:** el listado con búsqueda, filtro por estatus, paginación y consulta constante ya existe.

**Falta:** DT-02, que incluye la bandeja por omisión, el orden por fecha de envío, las columnas de origen, fecha de envío y advertencias, y el filtro por origen. También faltan las etiquetas de los estatus de DT-01 (EP-01).

**Criterios clave:**

- El PMO abre "Facturas" y ve sólo las "Enviadas", la más antigua primero, con las columnas de DT-02.
- El filtro "Origen: Internacional" muestra sólo facturas de proveedores internacionales.
- Con 30 facturas "Enviadas" hay dos páginas y el número de consultas SQL no depende del número de facturas.
- El listado responde en 3 s o menos con el volumen nominal que fije la HU (RNF de rendimiento, propuesto).
- Un proveedor que agrega los filtros del PMO a la URL sigue viendo sólo sus facturas.
- Una factura "Cancelada" desde "Enviada" ya no aparece en la bandeja por omisión.

**Decide la HU:** el volumen nominal para la prueba de rendimiento y si se agrega el índice.

**Capacidades:** modifica `flujo-facturas` (requisito "Listado de facturas filtrado y paginado en la base de datos").

### HU-19 · Visualización de detalle de factura por PMO

**Hoy:** el detalle ya muestra los datos del CFDI, la conciliación con el contrato, la matriz de evidencia y los documentos con descarga.

**Falta:**

- DT-03 ("Ver" en cada documento) y DT-07 (historial de revisiones);
- un bloque con los datos del proveedor: origen, RFC o país e identificador fiscal, correo y estatus;
- en la factura internacional, un bloque "Datos del Invoice" con los importes capturados (DT-06 de EP-01) en lugar de "Datos CFDI". La matriz de evidencia ya muestra cualquier categoría, incluidas las reglas INT;
- el panel de decisión de DT-04, que se entrega con HU-20.

**Criterios clave:**

- "Ver" en el PDF del CFDI abre una pestaña nueva con `Content-Type: application/pdf` y `Content-Disposition: inline`.
- "Ver" en un XML muestra su texto escapado, sin que el navegador lo interprete.
- Un proveedor que pide ver un documento de otra factura recibe HTTP 404, igual que con una ruta manipulada.
- En una factura internacional se ven los importes capturados y el resultado de INT-001 a INT-003.
- En una factura con dos rondas de "Observaciones", el historial muestra las dos observaciones con su fecha.

**Decide la HU:** qué CSP lleva la vista del PDF (riesgo de DT-03). Si el change de `factura-internacional` no se ha archivado todavía, el bloque "Datos del Invoice" pasa a ese change.

**Capacidades:** agrega el requisito "Visualización segura" a `almacenamiento-documentos` y modifica `flujo-facturas`.

### HU-20 · Cambio de estatus de factura

**Hoy:** existe la revisión en otra página, con cuatro botones, comentarios opcionales, `ensure_can_accept`, la tabla `reviews` y la auditoría. No envía correos.

**Falta:** DT-04, DT-05 y DT-06.

**Criterios clave:**

- Autorizar una factura "Enviada":
  - la factura pasa a "Autorizada", con `reviewed_at` y `reviewed_by`;
  - se registran la revisión y la auditoría;
  - Recepción de Facturas recibe "La factura número A-1024 del proveedor Servicios Digitales del Norte SA de CV por el monto $116,000.00 MXN ha sido Autorizada para su pago."
- Rechazar sin observaciones responde HTTP 400; la factura sigue "Enviada" y no se envía correo.
- Marcar "Observaciones" con un texto:
  - la factura pasa a "Observaciones";
  - el proveedor recibe un correo con la causa;
  - el proveedor puede corregir y reenviar la factura (EP-01).
- Decidir sobre una factura que no está "Enviada" responde HTTP 409.
- De dos decisiones simultáneas, una recibe HTTP 409 y sólo sale un correo.
- Si el servidor SMTP está caído, la decisión se aplica, la bitácora registra `FAILED` y la pantalla muestra el error.
- Un usuario `PROVIDER` que envía una decisión recibe HTTP 403.
- Unas observaciones que contienen `{{monto}}` llegan como texto literal (comportamiento actual de la composición).

**Decide la HU:** P-01, P-02, P-03, P-05 y P-06; si "Autorizar" pide confirmación; y si incluye el reenvío de notificación de DT-05.

**Capacidades:** modifica `flujo-facturas` ("Reglas de estado centralizadas en el servicio de facturas") e `integridad-datos` (enumeración de estatus). Puede crear una capacidad nueva `revision-pmo`.

## 7. Preguntas abiertas para negocio

Ninguna bloquea el inicio de la épica. Cada una tiene un valor que se aplica mientras no haya respuesta.

| ID | Pregunta | Valor aplicado mientras tanto | HU | Impacto de la respuesta |
| --- | --- | --- | --- | --- |
| P-01 | ¿Los pasos de ClickBalance del PoC forman parte del MVP? | No: se retiran de la interfaz y se migran a "Autorizada" (DT-06) | HU-20 | Si forman parte, se conservan como pasos internos posteriores a "Autorizada" |
| P-02 | ¿El Administrador puede autorizar o rechazar facturas, o sólo el PMO? | Igual que hoy: `INTERNAL` y `ADMIN` | HU-20 | Si sólo el PMO, `ADMIN` queda con acceso de lectura |
| P-03 | En RN-HU20-02, ¿el "monto Z" es el total o el subtotal? | El total, con su moneda | HU-20 | Cambia la variable `monto` del correo |
| P-04 | ¿"Rechazada" es definitiva? (Es la misma pregunta que P-04 de EP-01) | Sí | HU-20 | Si no, "Rechazada" admite reenvío como "Observaciones" |
| P-05 | ¿El PMO puede revertir una decisión, por ejemplo una autorización por error? | No en el MVP | HU-20 | Si puede, hacen falta una transición nueva, un motivo obligatorio y un correo de corrección |
| P-06 | ¿Las observaciones deben elegirse de un catálogo de motivos o tener una longitud mínima? | Texto libre obligatorio, de hasta 2 000 caracteres | HU-20 | Un catálogo de motivos se administraría con HU-07 |

## 8. Secuencia de entrega

Plan conjunto con EP-01 (el mismo de su sección 8):

| Ola | EP-01 | EP-02 | Condición de inicio |
| --- | --- | --- | --- |
| 1 | `primer-acceso-proveedor` (HU-10) y `registro-envio-factura-nacional` (HU-12, HU-13) | — | Ninguna |
| 2 | `factura-internacional` (HU-15, HU-16) | `bandeja-y-detalle-pmo` (HU-18, HU-19) | Archivado el change de HU-12/13 |
| 3 | `cancelacion-factura` (HU-14) | `cambio-estatus-factura` (HU-20) | Olas 1 y 2 archivadas |
| 4 | `seguimiento-estatus-proveedor` (HU-17) | — | HU-20 archivada |

`DEPENDENCIAS_HUs.md` hace depender HU-18 de HU-13 y de HU-16. Para no esperar al flujo internacional, HU-18 y HU-19 pueden arrancar con las facturas nacionales; la columna de origen funciona desde el principio porque el origen existe desde HU-01. Lo específico del Invoice se integra cuando se archiva `factura-internacional`, en la misma ola.

## 9. Dependencias externas e integraciones pendientes

| Integración | Estado actual | Efecto en la épica | Mitigación |
| --- | --- | --- | --- |
| Servidor SMTP (HU-08) | En desarrollo se usa el transporte `file`. El README tiene la guía "Conectar el servidor SMTP" | **Crítico:** sin SMTP, Recepción de Facturas no recibe las autorizaciones y el proveedor no recibe los rechazos ni las observaciones | Conectar el servidor antes del piloto. Mientras tanto: bitácora, aviso en pantalla y reenvío (DT-05). Las pruebas usan `MAIL_BACKEND=file` |
| Muestras de invoices extranjeros (minuta) | No están en el repositorio | Definen qué muestra "Datos del Invoice" y qué reglas INT revisa el PMO | Se resuelve en HU-16 (EP-01) |

## 10. Riesgos y mitigaciones

- **Se pierde un correo de autorización y Recepción no procesa el pago.** Mitigación: bitácora, aviso con el error y botón de reenvío (DT-05); SMTP conectado antes del piloto.
- **El visor PDF no funciona con la CSP elegida.** Mitigación: probar en Chrome, Edge y Firefox; la alternativa es pdf.js incluido en el proyecto (DT-03).
- **Un PDF malicioso se abre en el navegador.** Mitigación: el contenido se verifica al cargarlo, el MIME sale de la extensión verificada y se envía `nosniff`; el documento no se incrusta en el portal y el visor del navegador lo aísla. El riesgo residual es aceptable para usuarios internos autenticados.
- **Dos PMO deciden la misma factura.** Mitigación: bloqueo de fila y HTTP 409 (DT-04).
- **Los usuarios del PoC se confunden con las etiquetas nuevas** ("Aceptada" pasa a "Autorizada"; "Solicitar corrección" pasa a "Observaciones"). Mitigación: README y escenarios demo actualizados en el mismo change.

## 11. Criterios de aceptación de la épica

Recorrido de extremo a extremo que debe funcionar al cerrar la épica:

1. El PMO abre la bandeja y ve las facturas "Enviadas", la más antigua primero, con su proveedor, número de factura, monto, origen y fecha de envío. Puede filtrar por estatus y por origen.
2. El PMO abre una factura y ve en el navegador el PDF del CFDI o el Invoice y sus soportes, junto con el resultado de las validaciones automáticas (XML o INT) y el historial de revisiones.
3. El PMO autoriza: la factura queda "Autorizada" y Recepción de Facturas recibe el correo con el número de factura, el proveedor y el monto.
4. El PMO rechaza o marca "Observaciones": el portal exige las observaciones y el proveedor recibe un correo con la causa. Una factura en "Observaciones" regresa a la bandeja cuando el proveedor la reenvía.
5. Si dos PMO deciden la misma factura, sólo se aplica una decisión.
6. Cada decisión queda auditada con usuario, fecha y observaciones, y cada correo queda en la bitácora de envíos.

## 12. Definición de terminado de la épica

- [ ] HU-18, HU-19 y HU-20 tienen su documento en `docs/stories/new/`, y sus changes están archivados con las specs sincronizadas.
- [ ] Las preguntas P-01 a P-06 están respondidas por negocio o registradas como "Open Questions" en el `design.md` del change correspondiente.
- [ ] El recorrido de la sección 11 está automatizado, incluido el regreso de una factura desde "Observaciones".
- [ ] `scripts/check.py` está en verde y la cobertura no baja de `--cov-fail-under=93`.
- [ ] La visualización en el navegador está probada manualmente en Chrome, Edge y Firefox.
- [ ] Los textos predeterminados de los correos de Autorizada, Rechazada y Observaciones están validados con un envío real a Recepción de Facturas y a un proveedor de prueba, con el SMTP conectado.
- [ ] El README describe la bandeja, la revisión, los correos y la salida de ClickBalance, según P-01.

## 13. Trazabilidad

| HU | RF | RN | Alcance del MVP (minuta del 21-sep-2026) | Validación de HUs |
| --- | --- | --- | --- | --- |
| HU-18 | RF-17 | — | Rol PMO: "Consultar las facturas registradas por los proveedores" | Nueva (cierre de cobertura) |
| HU-19 | RF-18 | — | Rol PMO: "Realizar la validación manual de las facturas cargadas" | Nueva (cierre de cobertura) |
| HU-20 | RF-10 | RN-HU20-01, RN-HU20-02, RN-HU20-03 | Rol PMO: "Modificar el estatus de la factura: Aceptada, Rechazada o Con observaciones" y "Registrar observaciones asociadas a la revisión". Notificaciones: aviso automático a `recepcionfacturas@ultrasist.com.mx` | Dentro del MVP (era "HU1") |

**Otras referencias:**

- ERS v1.3: §2.3 (roles), §3.4 (RNF: trazabilidad, rendimiento, compatibilidad y los tres botones), §3.5 (RN) y §3.6 (modelo de estados).
- Validación de HUs: la minuta dice "Aceptada" y "Con observaciones", y la HU dice "Autorizada" y "Observaciones". Se usa la nomenclatura del ERS v1.2.
- HU-05: tabla de dependencias hacia HU-20.
- Specs: `flujo-facturas`, `almacenamiento-documentos`, `proteccion-http`, `notificaciones-correo` y `plantillas-notificacion`.
- EP-01: DT-01 (modelo de estatus), DT-06 (importes del Invoice), DT-08 (reglas INT) y DT-09 (correos después del commit).
