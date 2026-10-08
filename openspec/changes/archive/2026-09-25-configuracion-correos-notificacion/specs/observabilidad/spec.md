## MODIFIED Requirements

### Requirement: Registro de eventos técnicos del flujo
El sistema SHALL registrar:
- subida de documento: `invoice_id` o `supplier_id`, tipo documental, extensión y tamaño en bytes;
- inicio y fin de validación, con `invoice_id`, duración en milisegundos, score, número de bloqueos y estado resultante;
- decisión de revisión, con `invoice_id` y decisión;
- todo fallo de parseo de XML o de apertura de PDF, con el tipo y el mensaje técnico de la excepción, registrado **antes** de devolver el mensaje genérico al usuario;
- carga masiva de proveedores: evento `supplier.bulk_import` con `mode` (`strict` o `partial`), `result` (`imported`, `partial`, `rejected` o `conflict`), filas leídas (`rows`), proveedores registrados (`registered`), proveedores omitidos (`skipped`), filas con errores (`invalid`), tamaño del archivo en bytes (`size_bytes`) y duración en milisegundos (`duration_ms`);
- cambio de una plantilla de notificación: evento `notification_template.updated` con el código del evento (`event_code`) y la nueva versión (`version`);
- composición de un correo con el texto predeterminado porque la plantilla guardada no es válida: evento `notification.template_fallback` con `event_code` y el motivo (`reason`);
- envío de un correo: evento `notification.sent` con el id del envío en la bitácora (`delivery_id`), `event_code` (`TEST` para el correo de prueba), el transporte (`transport`), el número de destinatarios (`recipients`) y la duración en milisegundos (`duration_ms`);
- correo que no se pudo enviar: evento `notification.failed` con los mismos campos y el tipo de la excepción (`error_type`);
- cambio de los destinatarios de notificaciones: evento `notification_recipients.updated` con los códigos de las listas que cambiaron (`lists`).

Los eventos de plantillas y notificaciones MUST NOT incluir el asunto, el cuerpo, los valores de las variables, las direcciones de correo ni el mensaje técnico de un error de envío.

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

#### Scenario: Envío registrado
- **WHEN** se envía el correo de Autorizada de una factura al buzón "Recepción de Facturas"
- **THEN** el log contiene un evento `notification.sent` con `event_code = "INVOICE_AUTHORIZED"`, `delivery_id`, `transport`, `recipients` y `duration_ms`, y no contiene la dirección del buzón, el asunto ni el cuerpo

#### Scenario: Envío fallido registrado
- **WHEN** el servidor SMTP rechaza la conexión al enviar un correo de prueba
- **THEN** el log contiene un evento `notification.failed` con `event_code = "TEST"` y `error_type`, sin la dirección de destino

#### Scenario: Cambio de destinatarios registrado
- **WHEN** el Administrador cambia las copias de Rechazada
- **THEN** el log contiene un evento `notification_recipients.updated` con `lists = ["INVOICE_REJECTED"]` y sin direcciones de correo

### Requirement: Sin datos sensibles en logs
El log MUST NOT contener contraseñas, hashes, identificadores de sesión, tokens CSRF, `SECRET_KEY`, `SMTP_PASSWORD`, RFC, datos bancarios, contenido de archivos, nombres originales de archivo, ni el asunto, el cuerpo o los destinatarios de los correos.

#### Scenario: Revisión del log tras el flujo completo
- **WHEN** se ejecuta el flujo de login fallido, login exitoso, subida de documentos, validación y revisión, y se busca en el log `password`, `csrf`, `Admin123`, el RFC del proveedor y el RFC receptor
- **THEN** no hay coincidencias

#### Scenario: Revisión del log tras enviar correos
- **WHEN** con `SMTP_PASSWORD` definida se guarda el buzón, se envía un correo de prueba y se envía un correo de evento, y se busca en el log la contraseña SMTP, las direcciones del buzón y de la prueba, y el asunto enviado
- **THEN** no hay coincidencias
