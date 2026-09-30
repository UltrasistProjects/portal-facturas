# revision-pmo Specification

## Purpose
Bandeja y detalle de revisión del PMO (HU-18, HU-19; RF-17, RF-18): bandeja de facturas "Enviada" ordenada por fecha de envío, columnas del listado para el PMO (origen, envío y advertencias), bloque del proveedor e historial de envíos y revisiones en el detalle.
## Requirements
### Requirement: Bandeja del PMO
Para los roles `INTERNAL` y `ADMIN`, `GET /invoices` sin el parámetro `status` SHALL mostrar sólo las facturas "Enviada" (`UNDER_REVIEW`). Siempre que el filtro de estatus de `INTERNAL` o `ADMIN` sea "Enviada", por omisión o elegido, el listado SHALL ordenarse por `submitted_at` ascendente y después por `id`, también en las páginas siguientes. Con cualquier otro estatus o con "Todos los estados" (`status` vacío), SHALL ordenarse por `created_at` descendente, como hoy. El formulario de filtros SHALL enviar siempre `status` y mostrar seleccionado "Enviada" cuando se abre la bandeja. El listado del rol `PROVIDER` MUST NOT cambiar: sin `status` muestra todas sus facturas, ordenadas por `created_at` descendente.

#### Scenario: Bandeja inicial
- **WHEN** hay tres facturas "Enviada" enviadas el 1, 2 y 3 de septiembre y el PMO abre "Facturas"
- **THEN** ve sólo facturas "Enviada", la enviada el 1 de septiembre primero, y el filtro de estatus muestra "Enviada"

#### Scenario: Segunda página de la bandeja
- **WHEN** hay 30 facturas "Enviada" y el PMO pasa a la página 2 de la bandeja
- **THEN** ve las 5 enviadas más recientemente, en orden de envío ascendente

#### Scenario: Todos los estados
- **WHEN** el PMO elige "Todos los estados" y filtra
- **THEN** ve facturas de cualquier estatus, las creadas más recientemente primero

#### Scenario: Proveedor sin bandeja
- **WHEN** un proveedor abre "Facturas" sin filtros
- **THEN** ve todas sus facturas en cualquier estatus, las más recientes primero

### Requirement: Columnas del listado para el PMO
Para `INTERNAL` y `ADMIN`, cada fila del listado SHALL mostrar el proveedor y su identificador fiscal, el folio interno y el número de factura, el origen ("Nacional" o "Internacional"), el proyecto, la fecha de envío (o "—" si no se ha enviado), el monto con su moneda, el score, el número de advertencias (`WARNING`) de la última validación y el estatus. El conteo de advertencias SHALL obtenerse con una sola consulta agregada para toda la página, de modo que el número de consultas no dependa del número de facturas.

#### Scenario: Fila de una factura internacional enviada
- **WHEN** una factura internacional "Enviada" por `$1,000.00 USD` tiene dos resultados `WARNING` y el PMO abre la bandeja
- **THEN** su fila muestra "Internacional", la fecha de envío, "$1,000.00 USD" y "2 advertencias"

#### Scenario: Consultas constantes
- **WHEN** el PMO renderiza una página de 25 facturas con resultados de validación
- **THEN** el número de consultas SQL es el mismo que con una página de 5 facturas

### Requirement: Datos del proveedor en el detalle
El detalle de la factura SHALL mostrar a `INTERNAL` y `ADMIN` un bloque "Proveedor" con la razón social, el origen, el identificador fiscal (RFC, o país e identificador extranjero), el correo y el estatus del proveedor.

#### Scenario: Proveedor internacional
- **WHEN** el PMO abre el detalle de la demo INV-2026-0042
- **THEN** el bloque "Proveedor" muestra "Global Data Services Inc. (DEMO)", "Internacional", "US 98-7654321", "proveedor3@poc.local" y "Autorizado"

### Requirement: Historial de revisión en el detalle
El detalle de la factura SHALL mostrar el historial en orden cronológico: a `INTERNAL` y `ADMIN` en la sección "Historial" y al `PROVIDER` en la sección "Seguimiento" (HU-17), con:
- cada envío a validación del proveedor (auditoría `INVOICE_SUBMITTED`): fecha y usuario;
- cada revisión del PMO (tabla `reviews`): fecha, decisión con la etiqueta de su estatus ("Autorizada", "Rechazada", "Observaciones" o "Comentario") y observaciones;
- la cancelación (auditoría `INVOICE_CANCELLED`): fecha, "Cancelada", usuario y "Fecha límite de aceptación: <fecha límite>" en la zona de negocio.

A `INTERNAL` y `ADMIN` SHALL mostrar el nombre del revisor. Al `PROVIDER` SHALL mostrar "PMO" en lugar del nombre del revisor (EP-02 DT-07) y MUST NOT mostrar las revisiones `COMMENT` (comentarios internos del PoC). Sin eventos, SHALL mostrar "Sin envíos ni revisiones".

#### Scenario: Factura devuelta y reenviada
- **WHEN** una factura se envió, el PMO la marcó con observaciones "Falta el Vo.Bo." y el proveedor la reenvió
- **THEN** el historial muestra, en ese orden, el primer envío, la revisión "Observaciones" con "Falta el Vo.Bo." y el nombre del revisor, y el segundo envío

#### Scenario: Seguimiento del proveedor
- **WHEN** el proveedor abre el detalle de esa misma factura
- **THEN** ve la sección "Seguimiento" con los mismos tres eventos, la revisión atribuida a "PMO" y sin el nombre del revisor

#### Scenario: Comentario interno
- **WHEN** la factura tiene una revisión `COMMENT` del PoC
- **THEN** el PMO la ve como "Comentario" y el proveedor no la ve

#### Scenario: Cancelación en el historial
- **WHEN** el proveedor canceló la factura el 25/09/2026 a las 10:30 (hora de negocio)
- **THEN** el historial termina con "Cancelada", el usuario del proveedor y "Fecha límite de aceptación: 28/09/2026 10:30"

### Requirement: Decisión del PMO con tres botones
Para los roles `INTERNAL` y `ADMIN`, el detalle de una factura "Enviada" (`UNDER_REVIEW`) SHALL mostrar el panel "Decisión" con el campo "Observaciones" y tres botones: "Autorizar" (`ACCEPTED`), "Observaciones" (`REQUIRES_CORRECTION`) y "Rechazar" (`REJECTED`). En otro estatus, o para el rol `PROVIDER`, el panel MUST NOT mostrarse. `GET /invoices/{invoice_id}/review` SHALL redirigir (303) a `/invoices/{invoice_id}#decision`.

`POST /invoices/{invoice_id}/review` SHALL exigir CSRF y los roles `INTERNAL` o `ADMIN` (403 para `PROVIDER`). Una decisión distinta de las tres, incluida `COMMENT`, SHALL rechazarse con HTTP 400 "Decisión inválida" sin cambios. Una decisión válida SHALL, en una sola transacción:
- pasar la factura al estatus de la decisión, con `reviewed_at` y `reviewed_by`, auditando `STATUS_CHANGED` y la decisión con sus observaciones;
- registrar la revisión en `reviews` y guardar las observaciones en `invoices.comments` (vacías al autorizar sin observaciones);
- rechazar "Autorizar" con HTTP 409 "No se puede aceptar con bloqueos criticos" si la factura tiene un `FAIL` crítico.

Después SHALL redirigir (303) al detalle con el resultado del correo de la decisión.

#### Scenario: Autorizar
- **WHEN** el PMO pulsa "Autorizar" en una factura "Enviada" sin bloqueos
- **THEN** la factura queda "Autorizada", `reviewed_by` es el PMO, `reviews` tiene la decisión `ACCEPTED` y el detalle ya no muestra el panel "Decisión"

#### Scenario: Observaciones
- **WHEN** el PMO pulsa "Observaciones" con "Falta el Vo.Bo. firmado"
- **THEN** la factura queda en "Observaciones", el detalle muestra esas observaciones y el proveedor puede corregir y reenviar la factura

#### Scenario: Decisión de comentario
- **WHEN** se envía `decision = COMMENT`
- **THEN** la respuesta es HTTP 400 con "Decisión inválida" y la factura sigue "Enviada"

#### Scenario: Proveedor
- **WHEN** un usuario `PROVIDER` envía una decisión sobre su propia factura
- **THEN** la respuesta es HTTP 403 y la factura no cambia

#### Scenario: Página de revisión anterior
- **WHEN** el PMO abre `/invoices/{id}/review`
- **THEN** la respuesta redirige a `/invoices/{id}#decision`

### Requirement: Observaciones obligatorias para rechazar u observar
Las observaciones SHALL recortarse en sus extremos. Para "Rechazar" y "Observaciones" SHALL ser obligatorias: vacías, la respuesta SHALL ser HTTP 400 "Capture las observaciones". Con cualquier decisión SHALL admitir a lo sumo 2 000 caracteres: más, HTTP 400 "Las observaciones admiten hasta 2,000 caracteres". Un rechazo por observaciones MUST NOT cambiar la factura, registrar revisión ni enviar correo. Con JavaScript, el panel SHALL mostrar el campo al elegir "Rechazar" u "Observaciones" y pedir confirmación antes de "Autorizar"; sin JavaScript, el campo SHALL estar visible con la nota "Obligatorias para Rechazar u Observaciones".

#### Scenario: Rechazo sin observaciones
- **WHEN** el PMO pulsa "Rechazar" con el campo vacío o sólo con espacios
- **THEN** la respuesta es HTTP 400 con "Capture las observaciones", la factura sigue "Enviada" y no se envía correo

#### Scenario: Observaciones demasiado largas
- **WHEN** el PMO envía "Observaciones" con 2 001 caracteres
- **THEN** la respuesta es HTTP 400 con "Las observaciones admiten hasta 2,000 caracteres"

### Requirement: Una decisión por envío
La decisión SHALL bloquear la fila de la factura antes de comprobar su estatus. Si la factura ya no está "Enviada", la respuesta SHALL ser HTTP 409 con "La factura ya fue revisada" (si está "Autorizada", "Rechazada" u "Observaciones") o "La factura no está en revisión" (en otro estatus), sin registrar revisión ni enviar correo.

#### Scenario: Dos decisiones simultáneas
- **WHEN** dos PMO deciden sobre la misma factura "Enviada" al mismo tiempo
- **THEN** una decisión se aplica, la otra recibe HTTP 409 con "La factura ya fue revisada", `reviews` tiene una sola revisión nueva y sale un solo correo

#### Scenario: Factura cargada
- **WHEN** el PMO envía una decisión sobre una factura "Cargada"
- **THEN** la respuesta es HTTP 409 con "La factura no está en revisión"

### Requirement: Correos de la decisión
Después de confirmar la decisión, el sistema SHALL enviar con el servicio de notificaciones el correo del evento de la decisión, registrado en la bitácora con la entidad `Invoice` y el id de la factura:

| Decisión | Evento | Para |
| --- | --- | --- |
| Autorizada | `INVOICE_AUTHORIZED` | Buzón "Recepción de Facturas" y las copias del evento |
| Rechazada | `INVOICE_REJECTED` | Correo del proveedor de la factura y las copias del evento |
| Observaciones | `INVOICE_OBSERVATIONS` | Correo del proveedor de la factura y las copias del evento |

con `numero_factura` (número de factura), `folio_interno`, `proveedor` (razón social), `monto` (total con su moneda), `fecha_estatus` (`reviewed_at`) y, para Rechazada y Observaciones, `observaciones`. Un envío fallido MUST NOT revertir la decisión. La redirección SHALL llevar el id del envío y el detalle SHALL mostrar "Correo enviado a <destinatarios>" o "No se pudo enviar el correo: <error>"; un id que no es un envío de esa factura MUST NOT mostrar nada.

#### Scenario: Autorización notificada a Recepción
- **WHEN** con `MAIL_BACKEND=file` el PMO autoriza la factura "A-1024" del proveedor "Servicios Digitales del Norte SA de CV" por `$116,000.00 MXN`
- **THEN** el buzón de salida tiene un correo para `recepcionfacturas@ultrasist.com.mx` con el asunto "Factura A-1024 autorizada para pago" y el texto "La factura número A-1024 del proveedor Servicios Digitales del Norte SA de CV por el monto $116,000.00 MXN ha sido Autorizada para su pago.", y el detalle muestra "Correo enviado a recepcionfacturas@ultrasist.com.mx"

#### Scenario: Rechazo notificado al proveedor
- **WHEN** el PMO rechaza una factura con "El RFC del receptor no corresponde"
- **THEN** el proveedor recibe en su correo del catálogo el correo de Rechazada con esa causa

#### Scenario: Servidor de correo caído
- **WHEN** el servidor SMTP rechaza la conexión y el PMO autoriza una factura
- **THEN** la factura queda "Autorizada", la bitácora registra el envío como `FAILED` y el detalle muestra "No se pudo enviar el correo" con el error

### Requirement: Reenvío de la notificación de la decisión
Para `INTERNAL` y `ADMIN`, cuando la factura está "Autorizada", "Rechazada", "Observaciones" o "Cancelada" y el último envío del evento de ese estatus para la factura falló, el detalle SHALL ofrecer "Reenviar notificación". `POST /invoices/{invoice_id}/notification` SHALL exigir CSRF y esos roles, verificar las mismas condiciones (HTTP 409 "No hay una notificación fallida que reenviar" si no se cumplen), enviar de nuevo el correo (con las observaciones de la última revisión o, para "Cancelada", con la fecha límite de la cancelación), auditar `INVOICE_NOTIFICATION_RESENT` y redirigir al detalle con el resultado del nuevo envío.

#### Scenario: Reenvío tras una falla
- **WHEN** el correo de una autorización falló y el PMO pulsa "Reenviar notificación" con el transporte funcionando
- **THEN** sale el correo a Recepción de Facturas, el detalle muestra "Correo enviado a …" y el botón deja de mostrarse

#### Scenario: Notificación ya enviada
- **WHEN** el PMO envía `POST /invoices/{id}/notification` sobre una factura cuya notificación se envió bien
- **THEN** la respuesta es HTTP 409 con "No hay una notificación fallida que reenviar" y no sale ningún correo

#### Scenario: Reenvío del aviso de cancelación
- **WHEN** el correo de cancelación falló y el PMO pulsa "Reenviar notificación" con el transporte funcionando
- **THEN** sale el correo de cancelación a Recepción de Facturas con la misma fecha límite

