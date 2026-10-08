## MODIFIED Requirements

### Requirement: Correos de la decisión
Después de confirmar la decisión, el sistema SHALL enviar con el servicio de notificaciones el correo del evento de la decisión, registrado en la bitácora con la entidad `Invoice` y el id de la factura:

| Decisión | Evento | Para |
| --- | --- | --- |
| Autorizada | `INVOICE_AUTHORIZED` | Buzón "Recepción de Facturas", con copia al correo del proveedor de la factura y las copias del evento |
| Rechazada | `INVOICE_REJECTED` | Correo del proveedor de la factura y las copias del evento |
| Observaciones | `INVOICE_OBSERVATIONS` | Correo del proveedor de la factura y las copias del evento |

con `numero_factura` (número de factura), `folio_interno`, `proveedor` (razón social), `monto` (total con su moneda), `fecha_estatus` (`reviewed_at`) y, para Rechazada y Observaciones, `observaciones`. Un envío fallido MUST NOT revertir la decisión. La redirección SHALL llevar el id del envío y el detalle SHALL mostrar "Correo enviado a <destinatarios>", seguido de "con copia a <copias>" si el envío llevó copias, o "No se pudo enviar el correo: <error>"; un id que no es un envío de esa factura MUST NOT mostrar nada.

#### Scenario: Autorización notificada a Recepción con copia al proveedor
- **WHEN** con `MAIL_BACKEND=file` el PMO autoriza la factura "A-1024" del proveedor "Servicios Digitales del Norte SA de CV" (correo `proveedor1@poc.local`) por `$116,000.00 MXN`
- **THEN** el buzón de salida tiene un correo para `recepcionfacturas@ultrasist.com.mx` con copia (`Cc`) a `proveedor1@poc.local`, el asunto "Factura A-1024 autorizada para pago" y el texto "La factura número A-1024 del proveedor Servicios Digitales del Norte SA de CV por el monto $116,000.00 MXN ha sido Autorizada para su pago.", y el detalle muestra "Correo enviado a recepcionfacturas@ultrasist.com.mx con copia a proveedor1@poc.local"

#### Scenario: Rechazo notificado al proveedor
- **WHEN** el PMO rechaza una factura con "El RFC del receptor no corresponde"
- **THEN** el proveedor recibe en su correo del catálogo el correo de Rechazada con esa causa

#### Scenario: Servidor de correo caído
- **WHEN** el servidor SMTP rechaza la conexión y el PMO autoriza una factura
- **THEN** la factura queda "Autorizada", la bitácora registra el envío como `FAILED` y el detalle muestra "No se pudo enviar el correo" con el error

### Requirement: Reenvío de la notificación de la decisión
Para `PMO` y `Administrador`, cuando la factura está "Autorizada", "Rechazada", "Observaciones", "Cancelada" o "Pagada" y el último envío del evento de ese estatus para la factura falló, el detalle SHALL ofrecer "Reenviar notificación". `POST /invoices/{invoice_id}/notification` SHALL exigir CSRF y esos roles, y verificar las mismas condiciones; si no se cumplen, SHALL responder HTTP 409 "No hay una notificación fallida que reenviar". SHALL enviar de nuevo el correo con las observaciones de la última revisión; para "Cancelada", con la fecha límite de la cancelación, y para "Pagada", con el aviso del complemento calculado con la fecha límite registrada. Después SHALL auditar `INVOICE_NOTIFICATION_RESENT` y redirigir al detalle con el resultado del nuevo envío.

#### Scenario: Reenvío tras una falla
- **WHEN** el correo de una autorización falló y el PMO pulsa "Reenviar notificación" con el transporte funcionando
- **THEN** sale el correo a Recepción de Facturas con copia al proveedor, el detalle muestra "Correo enviado a …" y el botón deja de mostrarse

#### Scenario: Notificación ya enviada
- **WHEN** el PMO envía `POST /invoices/{id}/notification` sobre una factura cuya notificación se envió bien
- **THEN** la respuesta es HTTP 409 con "No hay una notificación fallida que reenviar" y no sale ningún correo

#### Scenario: Reenvío del aviso de cancelación
- **WHEN** el correo de cancelación falló y el PMO pulsa "Reenviar notificación" con el transporte funcionando
- **THEN** sale el correo de cancelación a Recepción de Facturas con la misma fecha límite

#### Scenario: Reenvío del aviso de pago
- **WHEN** el correo "Pagada" de una factura nacional PPD falló y el PMO pulsa "Reenviar notificación" con el transporte funcionando
- **THEN** sale el correo "Pagada" al correo del proveedor con el aviso del Complemento de Pago y la misma fecha límite
