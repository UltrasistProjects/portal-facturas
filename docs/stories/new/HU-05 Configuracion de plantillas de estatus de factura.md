# HU-05 · Configuración de plantillas de estatus de factura

| Campo | Valor |
| --- | --- |
| ID | HU-05 |
| Rol | Administrador |
| Módulo | A. Administración y Configuración |
| Prioridad | Alta (alcance comprometido del MVP) |
| Origen | Documento de HUs (literal) — `HUs Portal Proveedores ULTRASIST_v2.docx` |
| Requisito funcional | RF-05 (ERS v1.3) |
| Regla de negocio | Sin RN propia (ERS §4.1). El contenido mínimo de cada plantilla lo fijan RN-HU20-02, RN-HU20-03 y HU-14 (sección 5) |
| Change OpenSpec sugerido | `plantillas-estatus-factura` |
| Capacidad nueva | `plantillas-notificacion` |
| Capacidades modificadas | `integridad-datos`, `observabilidad` |
| Estado | Lista para `/opsx:propose`. Las reglas derivadas (sección 5) y las decisiones de diseño (sección 10) son propuestas del Equipo Técnico; los puntos de la sección 15 se confirman en la revisión de la HU |
| Estimación | Por definir en el refinamiento |
| Versión / fecha | 1.0 · 2026-09-25 · Equipo Técnico |

## Cómo usar este documento con OpenSpec

Ejecutar `/opsx:propose plantillas-estatus-factura` con este documento como entrada. Cada sección alimenta un artefacto:

| Artefacto OpenSpec | Secciones de esta HU |
| --- | --- |
| `proposal.md` — Why | 1, 2 |
| `proposal.md` — What Changes | 3, 6 |
| `proposal.md` — Capabilities | Tabla de metadatos, 8, 9 |
| `proposal.md` — Impact | 11 |
| `specs/plantillas-notificacion/spec.md` | 8 (se copia tal cual bajo `## ADDED Requirements`) |
| `specs/integridad-datos/spec.md`, `specs/observabilidad/spec.md` | 9 (bloques listos para copiar) |
| `design.md` | 4, 5, 10, 15 |
| `tasks.md` | 11, 13 |

Si la revisión cambia alguno de los puntos de la sección 15, se actualizan primero las secciones 5, 6, 8 y 10 de este documento.

---

## 1. Historia de usuario

**Texto literal (documento de HUs):**

> Yo como administrador requiero definir en la sección de configuración del sistema, los diferentes tipos de plantillas que se enviaran a los usuarios en los diferentes tipos de cambios de estatus de la factura “Autorizada”,”Rechazada”,”Observaciones” y “Cancelada”

**Reformulación:**

- **Como** Administrador del portal,
- **quiero** definir, en la sección de configuración, el asunto y el texto de los correos que el sistema envía cuando una factura pasa a "Autorizada", "Rechazada", "Observaciones" o "Cancelada",
- **para** ajustar la redacción de esas notificaciones sin cambiar el código y sin que se pierdan los datos que cada regla de negocio obliga a comunicar.

**Nota general del documento de HUs**, que aplica a todos los correos del sistema:

> NOTA: LOS CORREOS QUE SE MANDEN, SE DEBERAN CREAR PLANTILLAS DENTRO DE LA SECCIÓN DE CONFIGURACIÓN O PARÁMETROS DEL SISTEMA PARA QUE SEA FLEXIBLE.

## 2. Contexto y motivación

La minuta del 21-sep-2026 prioriza "la gestión de estatus y las notificaciones automáticas" y asigna al Administrador "Configurar correos y destinatarios de notificaciones". La ERS reparte esa función en dos requisitos: RF-05 (esta HU) define las plantillas y RF-13 (HU-08) los destinatarios. Los correos los disparan otras HU:

- **Autorizada, Rechazada y Observaciones:** HU-20, cuando el PMO pulsa uno de sus tres botones (RN-HU20-02 y RN-HU20-03).
- **Cancelada:** HU-14, cuando el proveedor solicita la cancelación con el acuse.

Las reglas de esas HU dictan qué debe decir cada correo: el número de factura, el proveedor, el monto, la causa o la fecha límite. Si el texto quedara fijo en el código, cualquier ajuste de redacción requeriría un despliegue, justo lo que la NOTA general pide evitar. Esta HU hace editable el texto y protege a la vez el contenido obligatorio: el Administrador puede cambiar la redacción, pero no quitar un dato que exige una regla de negocio.

Hoy el PoC no envía ningún correo y sus estatus de factura no coinciden con los de la ERS (sección 4). Por eso esta HU entrega las plantillas y el servicio que compone cada correo, pero no el envío.

## 3. Alcance

### Dentro del alcance

- Nueva opción **Plantillas de correo** en el menú Administración, exclusiva del Administrador.
- Cuatro plantillas, una por evento (Autorizada, Rechazada, Observaciones y Cancelada), creadas por el sistema con un texto predeterminado redactado a partir de las reglas de negocio.
- Edición del asunto y del cuerpo en texto plano, con variables `{{variable}}`.
- Catálogo de variables por plantilla, con las obligatorias que marca cada regla de negocio.
- Validación al guardar: longitudes, sintaxis, variables desconocidas y variables obligatorias ausentes.
- Vista previa con datos de ejemplo, sin guardar.
- Carga del texto predeterminado en el formulario, que no se aplica hasta que el Administrador guarda.
- Control de edición concurrente entre Administradores.
- Servicio que compone el asunto y el cuerpo de un correo a partir de la plantilla vigente, para HU-20 y HU-14.
- Auditoría de cada cambio y eventos de log.
- Modelo: tabla `notification_templates`, con las cuatro plantillas insertadas por la migración.

### Fuera del alcance

| Tema | Motivo / dónde se atiende |
| --- | --- |
| Enviar los correos: transporte SMTP, remitente, cola y reintentos | HU-08 (configuración de correos) y las HU que disparan cada aviso: HU-20 y HU-14 |
| Configurar destinatarios, incluido el buzón "Recepción de Facturas" | HU-08 (RF-13) |
| Disparar la notificación cuando cambia el estatus | HU-20 (Autorizada, Rechazada y Observaciones) y HU-14 (Cancelada) |
| Alinear los estatus del PoC con los de la ERS: `ACCEPTED` → "Autorizada", `REQUIRES_CORRECTION` → "Observaciones" y el nuevo "Cancelada" | HU-20 y HU-14. Los eventos de esta HU no dependen de esa enumeración (RD-02) |
| Plantillas de otros correos: credenciales (HU-03) y recuperación de contraseña | HU-03 agrega su evento al mismo catálogo. La recuperación de contraseña está fuera del MVP |
| Correo de prueba a una dirección real | HU-08, cuando exista el transporte |
| HTML, imágenes, adjuntos o editor enriquecido | RD-05 |
| Crear, eliminar o desactivar plantillas | RD-01 y RD-07 |
| Plantillas en otros idiomas | La interfaz del MVP es en español (ERS §3.4). Punto 1 de la sección 15 |
| Historial de versiones con opción de volver a una anterior | La auditoría conserva el texto anterior y el nuevo de cada cambio |

## 4. Situación actual del PoC

| Aspecto | Hoy | Brecha para HU-05 |
| --- | --- | --- |
| Sección de configuración | El menú Administración tiene Usuarios, Reglas y Audit Log. "Reglas" es de solo lectura y muestra `BUSINESS_RULES` de `app/core/constants.py` | No hay plantillas ni parámetros persistentes editables desde la interfaz |
| Envío de correo | No existe: no hay dependencia, configuración SMTP ni servicio de notificaciones | El envío queda fuera de esta HU, así que el servicio sólo compone el correo |
| Estatus de factura | `ACCEPTED` ("Aceptada"), `REJECTED` ("Rechazada") y `REQUIRES_CORRECTION` ("Requiere correccion"). No hay estatus de cancelación | Los nombres no coinciden con la ERS y "Cancelada" no existe. Los eventos de esta HU son independientes de la enumeración (RD-02) |
| Observaciones del PMO | `review_invoice` guarda el comentario, que es opcional, en `invoices.comments` y en `reviews.comments` | Es la fuente de `{{observaciones}}`. HU-20 lo hará obligatorio al rechazar u observar (RN-HU20-01) |
| Motor de plantillas | Jinja2 renderiza las páginas con autoescape | Renderizar con Jinja2 un texto escrito por el Administrador permitiría la inyección de plantillas del lado del servidor (SSTI). Se usa una sustitución propia (D2) |
| CSP | `default-src 'self'`: sin scripts ni estilos en línea | La vista previa se resuelve en el servidor, sin JavaScript (D5) |
| Auditoría | `audit_logs` guarda `old_value` y `new_value` en JSONB | Se reutiliza como historial de cambios de cada plantilla |
| Fechas y montos | `to_business` convierte a `America/Mexico_City` y el filtro `money` da el formato `$1,234.56` | Se reutilizan para `fecha_estatus`, `fecha_limite_cancelacion` y `monto` |
| Migraciones | La cabeza es `0002_supplier_bulk_import`. Las pruebas crean la base con `alembic upgrade head` | Una revisión nueva crea la tabla e inserta las cuatro plantillas predeterminadas |

## 5. Reglas de negocio

**Oficiales:** HU-05 no tiene RN propia (ERS §4.1). Su contenido lo acotan la NOTA general del documento de HUs (sección 1) y las reglas de las HU que envían cada correo:

| Evento | Fuente | Contenido obligatorio | Destinatario |
| --- | --- | --- | --- |
| Autorizada | RN-HU20-02 | "la factura número X del proveedor Y por el monto Z ha sido Autorizada para su pago" | Recepción de Facturas, definido en parámetros (HU-08) |
| Rechazada | RN-HU20-03 | "La factura número X ha sido “Rechazada” […] por la siguiente causa:" y la descripción del campo "Observaciones" | Campo "correo" del proveedor |
| Observaciones | RN-HU20-03 | "La factura número X […] tiene “Observaciones” por la siguiente causa:" y la descripción del campo "Observaciones" | Campo "correo" del proveedor |
| Cancelada | HU-14 | El "número de factura", el "nombre del proveedor" y la petición de aceptar la "Cancelación" antes de la Fecha Actual + 72 horas | Recepción de Facturas |

**Reglas derivadas**, propuestas por el Equipo Técnico a partir de las fuentes del proyecto:

| ID | Regla | Fundamento |
| --- | --- | --- |
| RD-01 | Hay exactamente una plantilla por evento. El Administrador la edita, pero no crea ni elimina plantillas | RF-05: "Deberá existir una plantilla configurable por cada tipo de cambio de estatus indicado" |
| RD-02 | Los eventos de notificación (`INVOICE_AUTHORIZED`, `INVOICE_REJECTED`, `INVOICE_OBSERVATIONS` e `INVOICE_CANCELLED`) no dependen de la enumeración de estatus de factura | El PoC nombra distinto los estatus y no tiene "Cancelada". Alinearlos es tarea de HU-20 y HU-14 |
| RD-03 | El destinatario lo fija la regla de negocio de cada evento y no se edita en la plantilla | RN-HU20-02, RN-HU20-03 y HU-14 nombran al destinatario. RF-13 (HU-08) configura la dirección de Recepción de Facturas |
| RD-04 | Cada plantilla exige en el cuerpo las variables que su regla de negocio obliga a comunicar | Sin esta regla, un cambio de redacción podría dejar de cumplir RN-HU20-02, RN-HU20-03 o HU-14 |
| RD-05 | El asunto y el cuerpo son texto plano, sin HTML | Menor superficie de ataque, compatible con la CSP y legible en cualquier cliente de correo (D7) |
| RD-06 | Las variables se escriben `{{variable}}` y se sustituyen tal cual, sin expresiones, filtros ni condiciones | La flexibilidad que pide la NOTA es de redacción, no de lógica. Una sintaxis sin lógica no puede ejecutar código (D2) |
| RD-07 | Las plantillas no se desactivan | RN-HU20-02, RN-HU20-03 y HU-14 dicen que el sistema "deberá" enviar cada correo |
| RD-08 | El texto predeterminado reproduce la redacción de las reglas de negocio. Cargarlo en el formulario no aplica nada hasta que el Administrador guarda | Da un punto de partida conforme a las RN y permite volver a él sin perder un texto por error |
| RD-09 | Asunto de 1 a 200 caracteres en una sola línea; cuerpo de 1 a 5000 caracteres | Los clientes de correo recortan los asuntos largos, y 5000 caracteres son más de una página de texto |
| RD-10 | Si la plantilla guardada no pasa la validación (por ejemplo, porque se modificó por SQL), el correo se compone con el texto predeterminado | Un error de plantilla no debe impedir una notificación que las RN hacen obligatoria |

## 6. Plantillas y variables

### 6.1 Eventos

| Código | Nombre en pantalla | Lo dispara | Destinatario |
| --- | --- | --- | --- |
| `INVOICE_AUTHORIZED` | Autorizada | HU-20: el PMO pulsa "Autorizada" | Recepción de Facturas |
| `INVOICE_REJECTED` | Rechazada | HU-20: el PMO pulsa "Rechazada" | Proveedor (correo del catálogo) |
| `INVOICE_OBSERVATIONS` | Observaciones | HU-20: el PMO pulsa "Observaciones" | Proveedor (correo del catálogo) |
| `INVOICE_CANCELLED` | Cancelada | HU-14: el proveedor solicita la cancelación con el acuse | Recepción de Facturas |

### 6.2 Variables

● obligatoria en el cuerpo · ○ disponible · — no disponible

| Variable | Contenido | Ejemplo | Autorizada | Rechazada | Observaciones | Cancelada |
| --- | --- | --- | --- | --- | --- | --- |
| `numero_factura` | Número de la factura que capturó el proveedor (`invoices.invoice_number`) | `A-1024` | ● | ● | ● | ● |
| `folio_interno` | Folio interno del portal | `FAC-2026-00042` | ○ | ○ | ○ | ○ |
| `proveedor` | Razón social del proveedor | `Servicios Digitales del Norte SA de CV` | ● | ○ | ○ | ● |
| `monto` | Total de la factura con su moneda | `$116,000.00 MXN` | ● | ○ | ○ | ○ |
| `estatus` | Nombre del evento | `Rechazada` | ○ | ○ | ○ | ○ |
| `fecha_estatus` | Fecha y hora del cambio de estatus, en la zona de negocio | `25/09/2026 10:30` | ○ | ○ | ○ | ○ |
| `observaciones` | Causa que capturó el PMO (RN-HU20-01) | `El subtotal del XML no coincide con el de la orden de compra.` | — | ● | ● | — |
| `fecha_limite_cancelacion` | Fecha límite para aceptar la cancelación: fecha de la solicitud + 72 horas (HU-14) | `28/09/2026 10:30` | — | — | — | ● |

Formatos: los montos llevan separador de miles, dos decimales y la moneda de la factura; las fechas usan `dd/mm/aaaa HH:MM` en la zona de negocio (`America/Mexico_City`).

### 6.3 Reglas del texto

- Una variable se escribe entre llaves dobles: `{{numero_factura}}`. Se admiten espacios interiores (`{{ numero_factura }}`) y los nombres van en minúsculas.
- No hay expresiones, filtros, condiciones ni ciclos: una variable sólo se reemplaza por su valor.
- Una llave sencilla (`{` o `}`) es texto normal. Unas llaves dobles sin cerrar en la misma línea son un error.
- El asunto ocupa una sola línea. El cuerpo conserva sus saltos de línea.
- Al guardar se recortan los espacios de los extremos del asunto y del cuerpo, y los saltos de línea `CRLF` se convierten en `LF`.

### 6.4 Textos predeterminados

**Autorizada** (`INVOICE_AUTHORIZED`). Asunto: `Factura {{numero_factura}} autorizada para pago`

```text
Recepción de Facturas:

La factura número {{numero_factura}} del proveedor {{proveedor}} por el monto {{monto}} ha sido Autorizada para su pago.

Folio interno: {{folio_interno}}
Fecha de autorización: {{fecha_estatus}}

Este es un mensaje automático del Portal de Proveedores ULTRASIST. No responda a este correo.
```

**Rechazada** (`INVOICE_REJECTED`). Asunto: `Factura {{numero_factura}} rechazada`

```text
{{proveedor}}:

La factura número {{numero_factura}} ha sido “Rechazada” por la siguiente causa:

{{observaciones}}

Folio interno: {{folio_interno}}
Fecha: {{fecha_estatus}}

Puede consultar el detalle en el Portal de Proveedores ULTRASIST. Este es un mensaje automático; no responda a este correo.
```

**Observaciones** (`INVOICE_OBSERVATIONS`). Asunto: `Factura {{numero_factura}} con observaciones`

```text
{{proveedor}}:

La factura número {{numero_factura}} tiene “Observaciones” por la siguiente causa:

{{observaciones}}

Folio interno: {{folio_interno}}
Fecha: {{fecha_estatus}}

Puede consultar el detalle en el Portal de Proveedores ULTRASIST. Este es un mensaje automático; no responda a este correo.
```

**Cancelada** (`INVOICE_CANCELLED`). Asunto: `Cancelación de la factura {{numero_factura}} de {{proveedor}}`

```text
Recepción de Facturas:

La factura número {{numero_factura}} del proveedor {{proveedor}} ha sido cancelada. Por favor acepte la “Cancelación” antes del {{fecha_limite_cancelacion}}.

Folio interno: {{folio_interno}}
Monto: {{monto}}
Fecha de la solicitud: {{fecha_estatus}}

Este es un mensaje automático del Portal de Proveedores ULTRASIST. No responda a este correo.
```

### 6.5 Datos de ejemplo de la vista previa

La vista previa usa la columna "Ejemplo" de la sección 6.2, y `estatus` toma el nombre del evento que se edita. Son datos ficticios fijos: la vista previa nunca lee facturas reales.

## 7. Flujo de uso

1. El Administrador entra a **Administración › Plantillas de correo** (`GET /admin/notification-templates`). La lista muestra las cuatro plantillas con su destinatario, su asunto y su última modificación.
2. Pulsa **Editar** en una plantilla (`GET /admin/notification-templates/{codigo}`). El formulario muestra el asunto, el cuerpo, el destinatario (sólo lectura) y la tabla de variables de esa plantilla, con las obligatorias marcadas.
3. Modifica el texto y pulsa **Vista previa** (`POST /admin/notification-templates/{codigo}/preview`). El sistema valida el borrador:
   - **Sin errores:** muestra, debajo del formulario, el asunto y el cuerpo compuestos con los datos de ejemplo.
   - **Con errores:** muestra la lista "Campo: mensaje" y conserva el texto capturado.

   En ambos casos no se guarda nada.
4. Si quiere volver al texto original, pulsa **Cargar texto predeterminado** (`GET /admin/notification-templates/{codigo}?default=1`). El formulario se llena con el texto predeterminado y muestra el aviso "Se cargó el texto predeterminado. Pulse Guardar para aplicarlo."; la plantilla vigente no cambia.
5. Pulsa **Guardar** (`POST /admin/notification-templates/{codigo}`). El sistema valida de nuevo:
   - **Sin errores:** guarda, aumenta la versión y regresa al listado con el aviso "Plantilla actualizada".
   - **Con errores:** responde 400 con la lista de errores y conserva el texto capturado.
   - **Otro Administrador guardó antes:** responde 409 y no guarda.
6. Desde ese momento, HU-20 y HU-14 componen sus correos con la versión guardada.

## 8. Criterios de aceptación — spec `plantillas-notificacion`

Los requisitos de esta sección siguen el formato de delta de OpenSpec. Se copian tal cual a `openspec/changes/plantillas-estatus-factura/specs/plantillas-notificacion/spec.md`, bajo el encabezado `## ADDED Requirements`.

### Requirement: Una plantilla por evento de estatus de factura
El sistema SHALL mantener exactamente una plantilla de correo por cada evento de notificación de la factura:
- `INVOICE_AUTHORIZED`, que se muestra como "Autorizada";
- `INVOICE_REJECTED`, que se muestra como "Rechazada";
- `INVOICE_OBSERVATIONS`, que se muestra como "Observaciones";
- `INVOICE_CANCELLED`, que se muestra como "Cancelada".

Cada plantilla SHALL tener asunto, cuerpo, número de versión, fecha de la última modificación y el Administrador que la hizo. Las cuatro plantillas SHALL existir desde la instalación con su texto predeterminado, en la versión 1 y sin Administrador asociado. La interfaz MUST NOT permitir crear, eliminar ni desactivar plantillas.

#### Scenario: Instalación nueva
- **WHEN** se ejecuta `alembic upgrade head` sobre una base vacía
- **THEN** existen cuatro plantillas, una por evento, en la versión 1, con el texto predeterminado y sin Administrador de la última modificación

#### Scenario: Evento inexistente
- **WHEN** el Administrador solicita `GET /admin/notification-templates/INVOICE_PAID`
- **THEN** la respuesta es HTTP 404

### Requirement: Configuración exclusiva del Administrador
Las rutas `GET /admin/notification-templates`, `GET /admin/notification-templates/{codigo}`, `POST /admin/notification-templates/{codigo}/preview` y `POST /admin/notification-templates/{codigo}` SHALL estar disponibles únicamente para el rol `ADMIN`. Las peticiones `POST` MUST exigir un token CSRF válido. El menú Administración SHALL mostrar la opción "Plantillas de correo" sólo al rol `ADMIN`.

#### Scenario: PMO sin acceso
- **WHEN** un usuario con rol `INTERNAL` solicita el listado, la edición o la vista previa, o envía un guardado
- **THEN** la respuesta es HTTP 403 y ninguna plantilla cambia

#### Scenario: Proveedor sin acceso
- **WHEN** un usuario con rol `PROVIDER` solicita el listado, la edición o la vista previa, o envía un guardado
- **THEN** la respuesta es HTTP 403 y ninguna plantilla cambia

#### Scenario: Guardado sin token CSRF
- **WHEN** un Administrador envía `POST /admin/notification-templates/INVOICE_REJECTED` sin token CSRF o con uno inválido
- **THEN** la respuesta es HTTP 403 y la plantilla no cambia

#### Scenario: Opción en el menú
- **WHEN** un Administrador y un usuario `INTERNAL` abren el tablero
- **THEN** el menú del Administrador incluye "Plantillas de correo" y el del usuario `INTERNAL` no

### Requirement: Consulta de las plantillas
`GET /admin/notification-templates` SHALL listar las cuatro plantillas en el orden Autorizada, Rechazada, Observaciones y Cancelada. De cada una SHALL mostrar el nombre del evento, el destinatario, el asunto vigente y la fecha y el Administrador de la última modificación, o "Predeterminada" si nunca se ha modificado. El destinatario SHALL ser:
- "Recepción de Facturas" para Autorizada y Cancelada;
- "Proveedor (correo del catálogo)" para Rechazada y Observaciones.

La página de edición SHALL mostrar el destinatario como dato de solo lectura y la lista de variables de la plantilla, con su descripción y la marca de obligatoria. Las páginas MUST NOT usar scripts ni estilos en línea.

#### Scenario: Listado inicial
- **WHEN** el Administrador abre el listado en una instalación nueva
- **THEN** ve cuatro filas en el orden Autorizada, Rechazada, Observaciones y Cancelada, con los destinatarios "Recepción de Facturas", "Proveedor (correo del catálogo)", "Proveedor (correo del catálogo)" y "Recepción de Facturas", y todas con la última modificación "Predeterminada"

#### Scenario: Destinatario de solo lectura
- **WHEN** el Administrador abre la edición de la plantilla Rechazada
- **THEN** la página muestra "Destinatario: Proveedor (correo del catálogo)" y el formulario no tiene ningún campo para cambiarlo

### Requirement: Variables por plantilla
Cada plantilla SHALL admitir únicamente las variables de su evento y SHALL exigir en el cuerpo sus variables obligatorias. Todas las plantillas admiten `folio_interno`, `estatus` y `fecha_estatus`. Además:
- Autorizada: obligatorias `numero_factura`, `proveedor` y `monto`;
- Rechazada: obligatorias `numero_factura` y `observaciones`; disponibles `proveedor` y `monto`;
- Observaciones: obligatorias `numero_factura` y `observaciones`; disponibles `proveedor` y `monto`;
- Cancelada: obligatorias `numero_factura`, `proveedor` y `fecha_limite_cancelacion`; disponible `monto`.

#### Scenario: Variables de la plantilla Cancelada
- **WHEN** el Administrador abre la edición de la plantilla Cancelada
- **THEN** la página lista `numero_factura`, `folio_interno`, `proveedor`, `monto`, `estatus`, `fecha_estatus` y `fecha_limite_cancelacion`; marca como obligatorias `numero_factura`, `proveedor` y `fecha_limite_cancelacion`, y no lista `observaciones`

#### Scenario: Variable de otro evento
- **WHEN** el Administrador guarda la plantilla Rechazada con `{{fecha_limite_cancelacion}}` en el cuerpo
- **THEN** la respuesta es HTTP 400 con el error "Cuerpo: la variable {{fecha_limite_cancelacion}} no existe en esta plantilla" y la plantilla no cambia

### Requirement: Validación de la plantilla
Al guardar y al generar la vista previa, el sistema SHALL normalizar el texto (recortar los espacios de los extremos del asunto y del cuerpo, y convertir `CRLF` en `LF`) y SHALL validarlo con estas reglas:
- el asunto es obligatorio, tiene hasta 200 caracteres y no contiene saltos de línea;
- el cuerpo es obligatorio y tiene hasta 5000 caracteres;
- cada `{{...}}` del asunto o del cuerpo contiene, sin contar los espacios interiores, el nombre de una variable de la plantilla;
- ninguna `{{` queda sin su `}}` en la misma línea;
- el cuerpo incluye al menos una vez cada variable obligatoria de la plantilla.

El sistema SHALL reportar todos los errores juntos, con el formato "Campo: mensaje", responder HTTP 400 y conservar en el formulario el texto capturado. Una plantilla con errores MUST NOT guardarse.

#### Scenario: Variable desconocida
- **WHEN** el Administrador guarda la plantilla Rechazada con `{{rfc_proveedor}}` en el cuerpo
- **THEN** la respuesta es HTTP 400 con el error "Cuerpo: la variable {{rfc_proveedor}} no existe en esta plantilla. Variables disponibles: {{numero_factura}}, {{folio_interno}}, {{proveedor}}, {{monto}}, {{estatus}}, {{fecha_estatus}}, {{observaciones}}", y la plantilla conserva su texto y su versión

#### Scenario: Variable obligatoria ausente
- **WHEN** el Administrador guarda la plantilla Rechazada sin `{{observaciones}}` en el cuerpo
- **THEN** la respuesta es HTTP 400 con el error "Cuerpo: debe incluir la variable obligatoria {{observaciones}}"

#### Scenario: Variable obligatoria sólo en el asunto
- **WHEN** el Administrador guarda la plantilla Autorizada con `{{monto}}` en el asunto pero no en el cuerpo
- **THEN** la respuesta es HTTP 400 con el error "Cuerpo: debe incluir la variable obligatoria {{monto}}"

#### Scenario: Variable sin cerrar
- **WHEN** el cuerpo contiene `{{numero_factura` sin `}}` en la misma línea
- **THEN** la respuesta es HTTP 400 con el error "Cuerpo: hay una variable sin cerrar; falta }}"

#### Scenario: Asunto demasiado largo
- **WHEN** el asunto tiene 201 caracteres
- **THEN** la respuesta es HTTP 400 con el error "Asunto: admite hasta 200 caracteres"

#### Scenario: Espacios interiores y llaves sencillas
- **WHEN** el cuerpo usa `{{ numero_factura }}` y contiene el texto `{nota}`
- **THEN** la plantilla es válida, y la vista previa muestra "A-1024" en lugar de la variable y `{nota}` sin cambios

#### Scenario: Varios errores a la vez
- **WHEN** el Administrador guarda con el asunto vacío y un cuerpo sin `{{numero_factura}}`
- **THEN** la respuesta HTTP 400 incluye "Asunto: es obligatorio" y "Cuerpo: debe incluir la variable obligatoria {{numero_factura}}"

### Requirement: Vista previa con datos de ejemplo
`POST /admin/notification-templates/{codigo}/preview` SHALL validar el borrador con las mismas reglas del guardado. Si es válido, SHALL responder HTTP 200 con el formulario y, debajo, el asunto y el cuerpo compuestos con estos datos de ejemplo:
- `numero_factura` = "A-1024";
- `folio_interno` = "FAC-2026-00042";
- `proveedor` = "Servicios Digitales del Norte SA de CV";
- `monto` = "$116,000.00 MXN";
- `estatus` = el nombre del evento;
- `fecha_estatus` = "25/09/2026 10:30";
- `observaciones` = "El subtotal del XML no coincide con el de la orden de compra.";
- `fecha_limite_cancelacion` = "28/09/2026 10:30".

Si el borrador no es válido, SHALL responder HTTP 400 con los errores y sin vista previa. La vista previa MUST NOT guardar la plantilla, cambiar su versión ni generar registros de auditoría. SHALL funcionar sin JavaScript y mostrar el texto compuesto escapado.

#### Scenario: Vista previa del texto predeterminado
- **WHEN** el Administrador pide la vista previa de la plantilla Autorizada con su texto predeterminado
- **THEN** la respuesta es HTTP 200, el asunto es "Factura A-1024 autorizada para pago" y el cuerpo contiene "La factura número A-1024 del proveedor Servicios Digitales del Norte SA de CV por el monto $116,000.00 MXN ha sido Autorizada para su pago."

#### Scenario: La vista previa no guarda
- **WHEN** el Administrador modifica el cuerpo de la plantilla Rechazada, pide la vista previa y vuelve a abrir la plantilla
- **THEN** la plantilla conserva su texto y su versión anteriores, y no se agregó ningún registro a `audit_logs`

#### Scenario: Texto escapado
- **WHEN** el cuerpo contiene `<b>Urgente</b>` y el Administrador pide la vista previa
- **THEN** la página muestra el texto `<b>Urgente</b>` tal cual, y su HTML contiene `&lt;b&gt;Urgente&lt;/b&gt;`

#### Scenario: Borrador inválido
- **WHEN** el Administrador pide la vista previa de un borrador sin una variable obligatoria
- **THEN** la respuesta es HTTP 400 con el error correspondiente y la página no muestra la vista previa

### Requirement: Guardado con control de edición concurrente
`POST /admin/notification-templates/{codigo}` SHALL recibir `subject`, `body` y `version`, que es la versión que el Administrador tenía al abrir el formulario. Si el texto es válido y `version` coincide con la vigente, el sistema SHALL guardar el asunto y el cuerpo, aumentar la versión en 1 y registrar la fecha y el Administrador de la modificación. Después SHALL redirigir con HTTP 303 al listado, que muestra el aviso "Plantilla actualizada".

Si `version` no coincide con la vigente, el sistema SHALL responder HTTP 409 con el mensaje "Otro administrador modificó esta plantilla mientras usted la editaba. Revise la versión vigente y vuelva a aplicar sus cambios." y MUST NOT guardar. Un guardado cuyo texto normalizado es idéntico al vigente MUST NOT aumentar la versión ni generar auditoría.

#### Scenario: Guardado exitoso
- **WHEN** la plantilla Rechazada está en la versión 1 y el Administrador la guarda con el asunto "Su factura {{numero_factura}} fue rechazada" y `version = 1`
- **THEN** la respuesta es HTTP 303 al listado, la plantilla queda en la versión 2 y el listado muestra el nuevo asunto, el nombre del Administrador y la fecha de la modificación

#### Scenario: Edición concurrente
- **WHEN** dos Administradores abren la plantilla Rechazada en la versión 1, el primero guarda y el segundo guarda después con `version = 1`
- **THEN** el segundo recibe HTTP 409 con el mensaje de edición concurrente, y la plantilla conserva el texto del primero en la versión 2

#### Scenario: Guardado sin cambios
- **WHEN** el Administrador guarda la plantilla sin modificar el texto
- **THEN** la respuesta es HTTP 303 al listado, la versión no cambia y no se agrega ningún registro a `audit_logs`

### Requirement: Carga del texto predeterminado
`GET /admin/notification-templates/{codigo}?default=1` SHALL mostrar el formulario con el asunto y el cuerpo predeterminados del evento, la versión vigente y el aviso "Se cargó el texto predeterminado. Pulse Guardar para aplicarlo.". La plantilla MUST NOT cambiar hasta que el Administrador guarde.

#### Scenario: Cargar y guardar el texto predeterminado
- **WHEN** la plantilla Rechazada está modificada en la versión 3, el Administrador carga el texto predeterminado y después pulsa Guardar
- **THEN** tras la carga la plantilla sigue en la versión 3 con el texto modificado, y tras el guardado queda en la versión 4 con el texto predeterminado

### Requirement: Textos predeterminados conforme a las reglas de negocio
Los textos predeterminados SHALL cumplir las reglas de validación de su plantilla y SHALL reproducir la redacción de las reglas de negocio. Los asuntos SHALL ser:
- Autorizada: "Factura {{numero_factura}} autorizada para pago";
- Rechazada: "Factura {{numero_factura}} rechazada";
- Observaciones: "Factura {{numero_factura}} con observaciones";
- Cancelada: "Cancelación de la factura {{numero_factura}} de {{proveedor}}".

El cuerpo SHALL contener:
- Autorizada (RN-HU20-02): "La factura número {{numero_factura}} del proveedor {{proveedor}} por el monto {{monto}} ha sido Autorizada para su pago.";
- Rechazada (RN-HU20-03): "La factura número {{numero_factura}} ha sido “Rechazada” por la siguiente causa:", seguido de `{{observaciones}}`;
- Observaciones (RN-HU20-03): "La factura número {{numero_factura}} tiene “Observaciones” por la siguiente causa:", seguido de `{{observaciones}}`;
- Cancelada (HU-14): "La factura número {{numero_factura}} del proveedor {{proveedor}} ha sido cancelada. Por favor acepte la “Cancelación” antes del {{fecha_limite_cancelacion}}.".

#### Scenario: Textos predeterminados válidos
- **WHEN** se validan los cuatro textos predeterminados con las reglas de su plantilla
- **THEN** ninguno produce errores

#### Scenario: Texto predeterminado de Cancelada
- **WHEN** se compone un correo `INVOICE_CANCELLED` con la plantilla predeterminada, `numero_factura = "A-1024"`, `proveedor = "Servicios Digitales del Norte SA de CV"` y la fecha límite 2026-09-28 16:30 UTC
- **THEN** el cuerpo contiene "La factura número A-1024 del proveedor Servicios Digitales del Norte SA de CV ha sido cancelada. Por favor acepte la “Cancelación” antes del 28/09/2026 10:30."

### Requirement: Composición del correo de un evento
El sistema SHALL ofrecer un servicio de composición para las HU que envían notificaciones. El servicio recibe el evento y los valores de sus variables, y devuelve el asunto y el cuerpo compuestos con la plantilla vigente. El servicio:
- SHALL formatear los montos con separador de miles, dos decimales y la moneda (`$116,000.00 MXN`), y las fechas en la zona de negocio con el formato `dd/mm/aaaa HH:MM`;
- SHALL tomar `estatus` del nombre del evento;
- SHALL sustituir cada variable por su valor como texto literal: un valor que contiene `{{...}}` no se vuelve a sustituir;
- SHALL convertir los saltos de línea del asunto compuesto en espacios y recortarlo a 255 caracteres;
- MUST fallar con un error explícito, sin componer el correo, si falta el valor de alguna variable del evento o si una variable obligatoria llega vacía;
- si la plantilla guardada no cumple las reglas de validación, SHALL componer el correo con el texto predeterminado del evento y registrar el evento de log `notification.template_fallback`.

El servicio MUST NOT enviar el correo ni escribir en el log el asunto o el cuerpo compuestos.

#### Scenario: Composición con la plantilla vigente
- **WHEN** la plantilla Rechazada se guardó con el asunto "Su factura {{numero_factura}} fue rechazada" y se compone un correo `INVOICE_REJECTED` con `numero_factura = "A-1024"`
- **THEN** el asunto compuesto es "Su factura A-1024 fue rechazada"

#### Scenario: Formato de montos y fechas
- **WHEN** se compone un correo `INVOICE_CANCELLED` con la plantilla predeterminada, un monto de `Decimal("116000.00")` en `MXN`, la fecha de la solicitud 2026-09-25 16:30 UTC y la fecha límite 2026-09-28 16:30 UTC
- **THEN** el cuerpo contiene "antes del 28/09/2026 10:30", "Monto: $116,000.00 MXN" y "Fecha de la solicitud: 25/09/2026 10:30"

#### Scenario: Valor con llaves
- **WHEN** se compone un correo `INVOICE_OBSERVATIONS` con `observaciones = "Corrija el campo {{monto}}"`
- **THEN** el cuerpo contiene el texto literal "Corrija el campo {{monto}}" y no el monto de la factura

#### Scenario: Asunto en una sola línea
- **WHEN** la plantilla Observaciones tiene el asunto "Observaciones: {{observaciones}}" y se compone con `observaciones = "Línea 1\nLínea 2"`
- **THEN** el asunto compuesto es "Observaciones: Línea 1 Línea 2"

#### Scenario: Variable obligatoria vacía
- **WHEN** se compone un correo `INVOICE_REJECTED` con `observaciones = ""`
- **THEN** el servicio falla con un error que nombra la variable `observaciones` y no devuelve ningún correo

#### Scenario: Plantilla guardada inválida
- **WHEN** se ejecuta `UPDATE notification_templates SET body = 'Sin variables' WHERE event = 'INVOICE_REJECTED'` y después se compone un correo `INVOICE_REJECTED`
- **THEN** el correo se compone con el texto predeterminado de Rechazada, y el log contiene un evento `notification.template_fallback` con `event_code = "INVOICE_REJECTED"`, sin el asunto ni el cuerpo compuestos

### Requirement: Auditoría de cambios a plantillas
Cada guardado que cambia una plantilla SHALL generar un registro de auditoría `NOTIFICATION_TEMPLATE_UPDATED` con:
- la entidad `NotificationTemplate` y el código del evento como identificador;
- el Administrador que guardó;
- `old_value` con el asunto, el cuerpo y la versión anteriores;
- `new_value` con el asunto, el cuerpo y la versión nuevos.

La vista previa, la carga del texto predeterminado, los guardados rechazados (HTTP 400 o 409) y los guardados sin cambios MUST NOT generar registros de auditoría.

#### Scenario: Auditoría de un cambio
- **WHEN** el Administrador guarda un cambio en la plantilla Rechazada, que pasa de la versión 1 a la 2
- **THEN** `audit_logs` contiene un registro `NOTIFICATION_TEMPLATE_UPDATED` con el `user_id` del Administrador, `entity_id = "INVOICE_REJECTED"`, `old_value` con el texto de la versión 1 y `version = 1`, y `new_value` con el texto nuevo y `version = 2`

#### Scenario: Acciones sin auditoría
- **WHEN** el Administrador pide una vista previa, carga el texto predeterminado, recibe un HTTP 400 por un error de validación y recibe un HTTP 409 por edición concurrente
- **THEN** no se agrega ningún registro a `audit_logs`

## 9. Deltas sobre capacidades existentes

### 9.1 `integridad-datos`

Destino: `openspec/changes/plantillas-estatus-factura/specs/integridad-datos/spec.md`. El requisito modificado reproduce el bloque completo vigente con los cambios aplicados.

```markdown
## MODIFIED Requirements

### Requirement: Restricciones CHECK sobre estados, montos y vigencias
La base de datos SHALL rechazar:
- valores de estado, rol, tipo de proveedor, origen de proveedor, evento de notificación, severidad, estado de regla, decisión de revisión o estado de procesamiento que no pertenezcan a su enumeración;
- montos negativos en factura;
- `authorized_amount <= 0` en contratos y `new_amount <= 0` en enmiendas;
- `end_date < start_date` en contratos;
- `validation_score` fuera de 0..100;
- `confidence` fuera de 0..1.

`suppliers.status` SHALL ser una enumeración tipada (`REGISTERED`, `ACTIVE`, `INACTIVE`), `suppliers.origin` SHALL ser una enumeración tipada (`NATIONAL`, `INTERNATIONAL`), `notification_templates.event` SHALL ser una enumeración tipada (`INVOICE_AUTHORIZED`, `INVOICE_REJECTED`, `INVOICE_OBSERVATIONS`, `INVOICE_CANCELLED`) y `contracts.status` SHALL ser una enumeración tipada (`ACTIVE`, `INACTIVE`).

#### Scenario: Estado inválido por SQL directo
- **WHEN** se ejecuta `UPDATE invoices SET status = 'APROBADA'`
- **THEN** la base de datos rechaza la operación

#### Scenario: Estatus de proveedor fuera de catálogo
- **WHEN** se ejecuta `UPDATE suppliers SET status = 'PENDIENTE'`
- **THEN** la base de datos rechaza la operación

#### Scenario: Evento de notificación fuera de catálogo
- **WHEN** se ejecuta `UPDATE notification_templates SET event = 'INVOICE_PAID' WHERE event = 'INVOICE_CANCELLED'`
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

### Requirement: Una plantilla por evento de notificación
La base de datos SHALL imponer unicidad sobre `notification_templates.event`. Restricciones `CHECK` SHALL exigir que `subject` tenga de 1 a 200 caracteres, que `body` tenga de 1 a 5000 caracteres y que `version` sea mayor o igual que 1. `notification_templates.updated_by` SHALL referenciar a `users` con `ON DELETE RESTRICT` y admitir `NULL` para las plantillas que nunca se han modificado.

#### Scenario: Segunda plantilla para un evento
- **WHEN** se inserta una plantilla con `event = 'INVOICE_REJECTED'` y ya existe una para ese evento
- **THEN** la base de datos rechaza la operación

#### Scenario: Asunto vacío por SQL directo
- **WHEN** se ejecuta `UPDATE notification_templates SET subject = ''`
- **THEN** la base de datos rechaza la operación
```

### 9.2 `observabilidad`

Destino: `openspec/changes/plantillas-estatus-factura/specs/observabilidad/spec.md`.

```markdown
## MODIFIED Requirements

### Requirement: Registro de eventos técnicos del flujo
El sistema SHALL registrar:
- subida de documento: `invoice_id` o `supplier_id`, tipo documental, extensión y tamaño en bytes;
- inicio y fin de validación, con `invoice_id`, duración en milisegundos, score, número de bloqueos y estado resultante;
- decisión de revisión, con `invoice_id` y decisión;
- todo fallo de parseo de XML o de apertura de PDF, con el tipo y el mensaje técnico de la excepción, registrado **antes** de devolver el mensaje genérico al usuario;
- carga masiva de proveedores: evento `supplier.bulk_import` con `mode` (`strict` o `partial`), `result` (`imported`, `partial`, `rejected` o `conflict`), filas leídas (`rows`), proveedores registrados (`registered`), proveedores omitidos (`skipped`), filas con errores (`invalid`), tamaño del archivo en bytes (`size_bytes`) y duración en milisegundos (`duration_ms`);
- cambio de una plantilla de notificación: evento `notification_template.updated` con el código del evento (`event_code`) y la nueva versión (`version`);
- composición de un correo con el texto predeterminado porque la plantilla guardada no es válida: evento `notification.template_fallback` con `event_code` y el motivo (`reason`).

Los eventos de plantillas y notificaciones MUST NOT incluir el asunto, el cuerpo ni los valores de las variables.

#### Scenario: Validación registrada
- **WHEN** se ejecuta la prevalidación de una factura
- **THEN** el log contiene un evento `validation.started` y un evento `validation.completed` con `duration_ms`, `score` y `blockers`

#### Scenario: PDF dañado
- **WHEN** se sube un PDF que PyMuPDF no puede abrir
- **THEN** el usuario ve "El PDF no puede abrirse o esta danado" y el log contiene un evento `pdf.analysis_failed` con el tipo y el mensaje de la excepción original

#### Scenario: Carga masiva registrada
- **WHEN** el Administrador carga un archivo válido con 3 proveedores nuevos
- **THEN** el log contiene un evento `supplier.bulk_import` con `mode = "strict"`, `result = "imported"`, `rows = 3`, `registered = 3`, `skipped = 0`, `invalid = 0`, `size_bytes` y `duration_ms`

#### Scenario: Carga parcial registrada
- **WHEN** el Administrador agrega las filas válidas de un archivo con 2 filas con errores
- **THEN** el log contiene un evento `supplier.bulk_import` con `mode = "partial"`, `result = "partial"` e `invalid = 2`

#### Scenario: Cambio de plantilla registrado
- **WHEN** el Administrador guarda un cambio en la plantilla Rechazada y esta queda en la versión 2
- **THEN** el log contiene un evento `notification_template.updated` con `event_code = "INVOICE_REJECTED"` y `version = 2`, sin el asunto ni el cuerpo

#### Scenario: Plantilla inválida registrada
- **WHEN** se compone un correo `INVOICE_REJECTED` y la plantilla guardada no es válida
- **THEN** el log contiene un evento `notification.template_fallback` con `event_code = "INVOICE_REJECTED"` y `reason`, sin el asunto, el cuerpo ni los valores de las variables
```

## 10. Notas de diseño (insumo para `design.md`)

| # | Decisión | Alternativas descartadas y motivo |
| --- | --- | --- |
| D1 | Tabla `notification_templates` (`id`, `event` único, `subject`, `body`, `version`, `updated_at`, `updated_by`) con las cuatro filas insertadas por la migración | Archivos de texto en el repositorio: el Administrador no podría editarlos. Una tabla genérica clave-valor de parámetros: sin restricciones por campo ni control de versión. HU-08 decidirá su propio modelo para destinatarios y transporte |
| D2 | Sustitución propia: una expresión regular localiza cada `{{ nombre }}` y lo reemplaza, en una sola pasada, por el valor ya formateado. Las plantillas del Administrador nunca pasan por Jinja2 | Jinja2, incluso en su sandbox: un texto del Administrador podría evaluar expresiones (SSTI) y se hereda una sintaxis que el negocio no necesita. `str.format`: permite acceder a atributos (`{0.__class__}`). `string.Template`: usa `$`, que choca con los montos (`$116,000.00`) |
| D3 | Un catálogo en código (`app/services/notification_templates.py`) define por evento el nombre, el destinatario, las variables disponibles y obligatorias, los datos de ejemplo y el texto predeterminado. Lo usan la validación, la interfaz, la vista previa y la composición | Guardar el catálogo en la base de datos: se podría quitar una variable obligatoria y romper RD-04 |
| D4 | Enumeración `NotificationEvent`, independiente de `InvoiceStatus` (RD-02) | Usar `InvoiceStatus` como llave: no existe "Cancelada", `ACCEPTED` se muestra como "Aceptada" y HU-05 quedaría atada a las decisiones de HU-20 y HU-14 |
| D5 | Vista previa en el servidor. El formulario tiene dos botones de envío y "Vista previa" usa el atributo `formaction` hacia `/preview`. El cuerpo compuesto se muestra con autoescape en un bloque con `white-space: pre-wrap`, definido en `app.css` | Vista previa en vivo con JavaScript: duplica en el navegador la lógica de composición, que podría divergir de la del servidor |
| D6 | Bloqueo optimista con `UPDATE ... WHERE event = :event AND version = :version`; si no afecta ninguna fila, 409. La versión viaja en un campo oculto del formulario | Que gane la última escritura: un Administrador perdería sin aviso el cambio de otro |
| D7 | Correo en texto plano (RD-05). La HU que envíe podrá envolverlo en un diseño HTML fijo sin cambiar las plantillas | HTML escrito por el Administrador: exige sanitizarlo, choca con la CSP en la vista previa (estilos en línea) y facilita enlaces engañosos |
| D8 | La composición valida de nuevo la plantilla guardada y, si no es válida, usa el texto predeterminado y registra `notification.template_fallback` (RD-10) | Fallar la composición: el cambio de estatus de HU-20 fallaría, o se perdería una notificación obligatoria |
| D9 | Revisión `0003_notification_templates`: crea la tabla con sus restricciones e inserta las cuatro plantillas, con los textos copiados en la propia migración. El downgrade lanza `NotImplementedError` si alguna plantilla tiene una versión mayor que 1, porque revertir perdería los cambios del Administrador | Importar los textos desde `app`: la migración cambiaría cada vez que cambie el código. Crear las plantillas al arrancar la aplicación: el esquema y sus datos mínimos quedarían en dos lugares |
| D10 | El servicio de composición recibe valores tipados (`numero_factura`, `folio_interno`, `proveedor`, `monto` y `moneda`, `fecha_estatus`, `observaciones`, `fecha_limite_cancelacion`) y los formatea él mismo | Recibir la factura (`Invoice`): acopla el servicio al modelo y a los campos que agregará HU-14 (la fecha de la solicitud de cancelación) |
| D11 | Las rutas viven en `app/routers/admin.py` (prefijo `/admin`) y la lógica en el servicio; el router sólo traduce HTTP | Un router nuevo: un archivo más para cuatro rutas de la misma sección |

**Riesgos y mitigaciones**

- **El Administrador quita información útil pero no obligatoria**, como el folio interno → sólo se protegen las variables que exigen las RN; el resto es una decisión de redacción, y la auditoría registra quién hizo cada cambio.
- **Texto engañoso o erróneo** → sólo el rol `ADMIN` edita, cada cambio queda auditado con el texto anterior y el nuevo, y la vista previa permite revisarlo antes de guardar.
- **Observaciones largas o de varias líneas en el asunto** → la composición convierte los saltos de línea en espacios y recorta el asunto a 255 caracteres.
- **Acentos y "ñ" en los correos** → las plantillas se guardan en UTF-8; la HU que envíe (HU-08) debe declarar `charset=utf-8`.
- **Base de pruebas compartida por toda la sesión** → las pruebas que modifican plantillas las restauran con un fixture para no afectar a otras.
- **Estatus del PoC distintos a los de la ERS** → los eventos no dependen de la enumeración; HU-20 y HU-14 hacen el mapeo al disparar cada correo.

## 11. Impacto

| Área | Cambio |
| --- | --- |
| `app/core/constants.py` | Enumeración `NotificationEvent` |
| `app/models/__init__.py` | Modelo `NotificationTemplate` con su unicidad y sus restricciones `CHECK` |
| `alembic/versions/` | Nueva revisión `0003_notification_templates`, posterior a `0002_supplier_bulk_import` |
| `app/services/` | Nuevo `notification_templates.py`: catálogo de eventos y variables, textos predeterminados, validación, vista previa, guardado y composición |
| `app/routers/admin.py` | `GET /admin/notification-templates`, `GET` y `POST /admin/notification-templates/{codigo}` y `POST /admin/notification-templates/{codigo}/preview` |
| `app/templates/admin/` | Nuevas `notification_templates.html` (listado) y `notification_template_edit.html` (edición y vista previa) |
| `app/templates/base.html` | Opción "Plantillas de correo" en el menú Administración |
| `app/static/css/app.css` | Estilo del cuerpo de la vista previa (`white-space: pre-wrap`) |
| `tests/` | Nuevo `test_plantillas_notificacion.py`, con un escenario por requisito; ajustes en `test_integridad.py`, `test_migraciones.py` y `test_observabilidad.py` |
| `README.md` | Sección de plantillas de correo con la tabla de variables |
| Dependencias | Ninguna nueva |

## 12. Dependencias

- **Depende de:** ninguna HU (`docs/DEPENDENCIAS_HUs.md`). Técnicamente, la revisión nueva va después de `0002_supplier_bulk_import`.
- **Habilita** (con lo que cada HU recibe de esta):

| HU | Qué recibe de HU-05 | Qué le toca decidir a esa HU |
| --- | --- | --- |
| HU-20 | Las plantillas Autorizada, Rechazada y Observaciones, y el servicio de composición | Mapear sus tres botones a los eventos, hacer obligatorias las observaciones (RN-HU20-01) y enviar el correo |
| HU-14 | La plantilla Cancelada | Crear el estatus "Cancelada", calcular la fecha límite (+72 h) y enviar el correo |
| HU-08 | Correos compuestos, listos para enviarse | El destinatario Recepción de Facturas, el transporte SMTP, el remitente y el correo de prueba |
| HU-03 | Un catálogo de eventos extensible | Agregar su evento de credenciales, cuidando que la contraseña temporal no llegue al log ni a la auditoría (RN-HU03-01) |
| HU-17 | — | Mostrar en el portal las mismas observaciones que el proveedor recibe por correo |

**Nota sobre la ERS:** RF-05 lista como consumidores a RF-09, RF-10 y RF-16. RF-16 (HU-17) es la consulta del estatus por el proveedor y no envía correos, así que se toma como errata. Los consumidores reales son RF-09 (HU-14) y RF-10 (HU-20).

## 13. Definición de terminado

- [ ] Change `plantillas-estatus-factura` creado con proposal, specs, design y tasks; `openspec validate plantillas-estatus-factura --strict` sin errores.
- [ ] Cada escenario de las secciones 8 y 9 tiene al menos una prueba automatizada que pasa sobre la base PostgreSQL temporal de la sesión.
- [ ] Las pruebas que modifican plantillas las devuelven a su texto predeterminado.
- [ ] La cobertura no baja del umbral vigente (`--cov-fail-under=93`).
- [ ] Revisión Alembic `0003_notification_templates`; `alembic check` sin diferencias; downgrade conforme a D9.
- [ ] Sin dependencias nuevas; `pip-audit` sin hallazgos.
- [ ] `scripts/check.py` en verde (ruff, pytest, `alembic check`, `pip-audit`).
- [ ] Páginas nuevas sin scripts ni estilos en línea (CSP de `proteccion-http`) y utilizables sin JavaScript.
- [ ] Los cuatro textos predeterminados revisados y aprobados por el negocio (PMO y Recepción de Facturas).
- [ ] Los puntos de la sección 15 confirmados o ajustados en esta HU.
- [ ] README actualizado con la sección de plantillas y la tabla de variables.
- [ ] Change archivado y specs sincronizadas (`/opsx:archive`).

## 14. Trazabilidad

| Elemento | Referencia |
| --- | --- |
| Alcance del MVP (minuta del 21-sep-2026) | Rol Administrador: "Configurar correos y destinatarios de notificaciones". Resultado de la sesión: se prioriza "la gestión de estatus y las notificaciones automáticas" |
| Documento de HUs | HU-05 (literal); NOTA general sobre las plantillas de correo; RN-02 y RN-03 del rol PMO (hoy RN-HU20-02 y RN-HU20-03); HU-14 |
| Validación de HUs | HU-05 "Dentro del MVP" (sección 2) y sin RN asociada (sección 5); hueco 8 de la sección 4.2 (destinatarios, que cubre HU-08) |
| ERS v1.3 | §2.4 "plantillas de correo configurables (RF-05)"; §3.1 HU-05; §3.2 RF-05, RF-09, RF-10 y RF-13; §3.4 RNF de notificaciones; §3.5 RN-HU20-02 y RN-HU20-03; §3.6 modelo de estados; §4.1 matriz HU-05 ↔ RF-05 |
| OpenSpec | Capacidad nueva `plantillas-notificacion`; deltas en `integridad-datos` y `observabilidad`; sin cambios en `proteccion-http` (CSP y respuestas 409), `migraciones-esquema` (una revisión por cambio de modelo) ni `flujo-facturas` |

## 15. Puntos a confirmar en la revisión

Cada punto tiene una propuesta ya reflejada en este documento, así que no bloquea `/opsx:propose`. Si la revisión la cambia, la columna "Si cambia" indica qué se ajusta.

| # | Punto | Propuesta | Si cambia |
| --- | --- | --- | --- |
| 1 | Idioma de los correos a proveedores internacionales (Rechazada y Observaciones) | Español, como el resto del MVP | Una plantilla por idioma y el idioma del proveedor en el catálogo: cambian RD-01, el modelo y las secciones 6 y 8 |
| 2 | Formato del correo | Texto plano (RD-05) | HTML con un diseño base fijo: cambia D7 y hay que sanitizar el contenido |
| 3 | Destinatarios por evento | Los de las RN: Recepción de Facturas para Autorizada y Cancelada, y el proveedor para Rechazada y Observaciones. El proveedor no recibe correo al autorizarse su factura; ve el estatus en el portal (HU-17) | Un evento o un destinatario en copia adicional: se define en HU-08 y se agrega aquí su plantilla |
| 4 | Plantillas no desactivables | Sí, porque las RN obligan el envío (RD-07) | Un indicador "activa" en el modelo, con su auditoría |
| 5 | Textos predeterminados | Los de la sección 6.4 | Se ajustan la sección 6.4 y el requisito "Textos predeterminados conforme a las reglas de negocio" |
