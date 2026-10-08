## MODIFIED Requirements

### Requirement: Historial de revisión en el detalle
El detalle de la factura SHALL mostrar el historial en orden cronológico: a `PMO` y `Administrador` en la sección "Historial" y al `Proveedor` en la sección "Seguimiento" (HU-17), con:
- cada envío a validación del proveedor (auditoría `INVOICE_SUBMITTED`): fecha y usuario;
- cada revisión del PMO (tabla `reviews`): fecha, decisión con la etiqueta de su estatus ("Autorizada", "Rechazada", "Observaciones" o "Comentario") y observaciones;
- la cancelación (auditoría `INVOICE_CANCELLED`): fecha, "Cancelada", usuario y "Fecha límite de aceptación: <fecha límite>" en la zona de negocio;
- el pago (auditoría `INVOICE_PAID`): fecha, "Pagada", usuario y, si la factura requiere Complemento de Pago, "Fecha límite del complemento: <fecha límite>" en la zona de negocio;
- cada carga del XML del Complemento de Pago (auditoría `PAYMENT_COMPLEMENT_UPLOADED`): fecha, "Complemento de pago adjuntado" y usuario.

A `PMO` y `Administrador` SHALL mostrar el nombre del revisor y el de quien marcó el pago. Al `Proveedor` SHALL mostrar "PMO" en lugar del nombre del revisor y de quien marcó el pago (EP-02 DT-07), y MUST NOT mostrar las revisiones `COMMENT` (comentarios internos del PoC). Sin eventos, SHALL mostrar "Sin envíos ni revisiones".

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

#### Scenario: Pago y complemento en el historial
- **WHEN** el PMO marcó como pagada una factura nacional PPD el 01/10/2026 a las 10:00 y el proveedor adjuntó el complemento el 02/10/2026 a las 09:00
- **THEN** el historial termina con "Pagada", el nombre del PMO y "Fecha límite del complemento: 04/10/2026 10:00", seguido de "Complemento de pago adjuntado" con el usuario del proveedor; el proveedor ve el pago atribuido a "PMO"

### Requirement: Reenvío de la notificación de la decisión
Para `PMO` y `Administrador`, cuando la factura está "Autorizada", "Rechazada", "Observaciones", "Cancelada" o "Pagada" y el último envío del evento de ese estatus para la factura falló, el detalle SHALL ofrecer "Reenviar notificación". `POST /invoices/{invoice_id}/notification` SHALL exigir CSRF y esos roles, y verificar las mismas condiciones; si no se cumplen, SHALL responder HTTP 409 "No hay una notificación fallida que reenviar". SHALL enviar de nuevo el correo con las observaciones de la última revisión; para "Cancelada", con la fecha límite de la cancelación, y para "Pagada", con el aviso del complemento calculado con la fecha límite registrada. Después SHALL auditar `INVOICE_NOTIFICATION_RESENT` y redirigir al detalle con el resultado del nuevo envío.

#### Scenario: Reenvío tras una falla
- **WHEN** el correo de una autorización falló y el PMO pulsa "Reenviar notificación" con el transporte funcionando
- **THEN** sale el correo a Recepción de Facturas, el detalle muestra "Correo enviado a …" y el botón deja de mostrarse

#### Scenario: Notificación ya enviada
- **WHEN** el PMO envía `POST /invoices/{id}/notification` sobre una factura cuya notificación se envió bien
- **THEN** la respuesta es HTTP 409 con "No hay una notificación fallida que reenviar" y no sale ningún correo

#### Scenario: Reenvío del aviso de cancelación
- **WHEN** el correo de cancelación falló y el PMO pulsa "Reenviar notificación" con el transporte funcionando
- **THEN** sale el correo de cancelación a Recepción de Facturas con la misma fecha límite

#### Scenario: Reenvío del aviso de pago
- **WHEN** el correo "Pagada" de una factura nacional PPD falló y el PMO pulsa "Reenviar notificación" con el transporte funcionando
- **THEN** sale el correo "Pagada" al correo del proveedor con el aviso del Complemento de Pago y la misma fecha límite
