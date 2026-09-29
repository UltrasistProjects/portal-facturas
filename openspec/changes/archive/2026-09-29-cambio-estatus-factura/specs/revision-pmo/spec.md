## ADDED Requirements

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
Para `INTERNAL` y `ADMIN`, cuando la factura está "Autorizada", "Rechazada" u "Observaciones" y el último envío del evento de ese estatus para la factura falló, el detalle SHALL ofrecer "Reenviar notificación". `POST /invoices/{invoice_id}/notification` SHALL exigir CSRF y esos roles, verificar las mismas condiciones (HTTP 409 "No hay una notificación fallida que reenviar" si no se cumplen), enviar de nuevo el correo con las observaciones de la última revisión, auditar `INVOICE_NOTIFICATION_RESENT` y redirigir al detalle con el resultado del nuevo envío.

#### Scenario: Reenvío tras una falla
- **WHEN** el correo de una autorización falló y el PMO pulsa "Reenviar notificación" con el transporte funcionando
- **THEN** sale el correo a Recepción de Facturas, el detalle muestra "Correo enviado a …" y el botón deja de mostrarse

#### Scenario: Notificación ya enviada
- **WHEN** el PMO envía `POST /invoices/{id}/notification` sobre una factura cuya notificación se envió bien
- **THEN** la respuesta es HTTP 409 con "No hay una notificación fallida que reenviar" y no sale ningún correo
