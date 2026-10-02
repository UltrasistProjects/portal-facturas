## MODIFIED Requirements

### Requirement: Bandeja del PMO
Para los roles `PMO` y `Administrador`, `GET /invoices` sin el parámetro `status` SHALL mostrar sólo las facturas "Enviada" (`UNDER_REVIEW`). Siempre que el filtro de estatus de `PMO` o `Administrador` sea "Enviada", por omisión o elegido, el listado SHALL ordenarse por `submitted_at` ascendente y después por `id`, también en las páginas siguientes. Con cualquier otro estatus o con "Todos los estados" (`status` vacío), SHALL ordenarse por `created_at` descendente, como hoy. El formulario de filtros SHALL enviar siempre `status` y mostrar seleccionado "Enviada" cuando se abre la bandeja. El listado del rol `Proveedor` MUST NOT cambiar: sin `status` muestra todas sus facturas, ordenadas por `created_at` descendente.

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
Para `PMO` y `Administrador`, cada fila del listado SHALL mostrar el proveedor y su identificador fiscal, el folio interno y el número de factura, el origen ("Nacional" o "Internacional"), el proyecto, la fecha de envío (o "—" si no se ha enviado), el monto con su moneda, el score, el número de advertencias (`WARNING`) de la última validación y el estatus. El conteo de advertencias SHALL obtenerse con una sola consulta agregada para toda la página, de modo que el número de consultas no dependa del número de facturas.

#### Scenario: Fila de una factura internacional enviada
- **WHEN** una factura internacional "Enviada" por `$1,000.00 USD` tiene dos resultados `WARNING` y el PMO abre la bandeja
- **THEN** su fila muestra "Internacional", la fecha de envío, "$1,000.00 USD" y "2 advertencias"

#### Scenario: Consultas constantes
- **WHEN** el PMO renderiza una página de 25 facturas con resultados de validación
- **THEN** el número de consultas SQL es el mismo que con una página de 5 facturas

### Requirement: Datos del proveedor en el detalle
El detalle de la factura SHALL mostrar a `PMO` y `Administrador` un bloque "Proveedor" con la razón social, el origen, el identificador fiscal (RFC, o país e identificador extranjero), el correo y el estatus del proveedor.

#### Scenario: Proveedor internacional
- **WHEN** el PMO abre el detalle de la demo INV-2026-0042
- **THEN** el bloque "Proveedor" muestra "Global Data Services Inc. (DEMO)", "Internacional", "US 98-7654321", "proveedor3@poc.local" y "Autorizado"

### Requirement: Historial de revisión en el detalle
El detalle de la factura SHALL mostrar el historial en orden cronológico: a `PMO` y `Administrador` en la sección "Historial" y al `Proveedor` en la sección "Seguimiento" (HU-17), con:
- cada envío a validación del proveedor (auditoría `INVOICE_SUBMITTED`): fecha y usuario;
- cada revisión del PMO (tabla `reviews`): fecha, decisión con la etiqueta de su estatus ("Autorizada", "Rechazada", "Observaciones" o "Comentario") y observaciones;
- la cancelación (auditoría `INVOICE_CANCELLED`): fecha, "Cancelada", usuario y "Fecha límite de aceptación: <fecha límite>" en la zona de negocio.

A `PMO` y `Administrador` SHALL mostrar el nombre del revisor. Al `Proveedor` SHALL mostrar "PMO" en lugar del nombre del revisor (EP-02 DT-07) y MUST NOT mostrar las revisiones `COMMENT` (comentarios internos del PoC). Sin eventos, SHALL mostrar "Sin envíos ni revisiones".

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
Para los roles `PMO` y `Administrador`, el detalle de una factura "Enviada" (`UNDER_REVIEW`) SHALL mostrar el panel "Decisión" con el campo "Observaciones" y tres botones: "Autorizar" (`ACCEPTED`), "Observaciones" (`REQUIRES_CORRECTION`) y "Rechazar" (`REJECTED`). En otro estatus, o para el rol `Proveedor`, el panel MUST NOT mostrarse. `GET /invoices/{invoice_id}/review` SHALL redirigir (303) a `/invoices/{invoice_id}#decision`.

`POST /invoices/{invoice_id}/review` SHALL exigir CSRF y los roles `PMO` o `Administrador` (403 para `Proveedor`). Una decisión distinta de las tres, incluida `COMMENT`, SHALL rechazarse con HTTP 400 "Decisión inválida" sin cambios. Una decisión válida SHALL, en una sola transacción:
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
- **WHEN** un usuario `Proveedor` envía una decisión sobre su propia factura
- **THEN** la respuesta es HTTP 403 y la factura no cambia

#### Scenario: Página de revisión anterior
- **WHEN** el PMO abre `/invoices/{id}/review`
- **THEN** la respuesta redirige a `/invoices/{id}#decision`

### Requirement: Reenvío de la notificación de la decisión
Para `PMO` y `Administrador`, cuando la factura está "Autorizada", "Rechazada", "Observaciones" o "Cancelada" y el último envío del evento de ese estatus para la factura falló, el detalle SHALL ofrecer "Reenviar notificación". `POST /invoices/{invoice_id}/notification` SHALL exigir CSRF y esos roles, verificar las mismas condiciones (HTTP 409 "No hay una notificación fallida que reenviar" si no se cumplen), enviar de nuevo el correo (con las observaciones de la última revisión o, para "Cancelada", con la fecha límite de la cancelación), auditar `INVOICE_NOTIFICATION_RESENT` y redirigir al detalle con el resultado del nuevo envío.

#### Scenario: Reenvío tras una falla
- **WHEN** el correo de una autorización falló y el PMO pulsa "Reenviar notificación" con el transporte funcionando
- **THEN** sale el correo a Recepción de Facturas, el detalle muestra "Correo enviado a …" y el botón deja de mostrarse

#### Scenario: Notificación ya enviada
- **WHEN** el PMO envía `POST /invoices/{id}/notification` sobre una factura cuya notificación se envió bien
- **THEN** la respuesta es HTTP 409 con "No hay una notificación fallida que reenviar" y no sale ningún correo

#### Scenario: Reenvío del aviso de cancelación
- **WHEN** el correo de cancelación falló y el PMO pulsa "Reenviar notificación" con el transporte funcionando
- **THEN** sale el correo de cancelación a Recepción de Facturas con la misma fecha límite
