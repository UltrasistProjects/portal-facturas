## MODIFIED Requirements

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
