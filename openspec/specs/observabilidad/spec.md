# observabilidad Specification

## Purpose
Log estructurado en JSON con correlación por petición y registro de los eventos técnicos del flujo, sin datos sensibles.
## Requirements
### Requirement: Log estructurado en JSON
Cada línea del log de aplicación SHALL ser un objeto JSON válido con, al menos: `timestamp` (ISO 8601 UTC), `level`, `logger`, `message` y `request_id`. `user_id` SHALL incluirse cuando la petición está autenticada. Los atributos adicionales de cada evento SHALL emitirse como campos del objeto. El log SHALL conservar la rotación existente (2 MB × 3 archivos).

#### Scenario: Línea de log de una petición autenticada
- **WHEN** un usuario autenticado provoca un evento de log
- **THEN** la línea es JSON parseable y contiene `request_id` y `user_id`

#### Scenario: Evento fuera de petición
- **WHEN** se registra el arranque de la aplicación
- **THEN** la línea es JSON parseable y `request_id` es `null`

### Requirement: Correlación por petición
Un middleware SHALL asignar un `request_id` a cada petición y devolverlo en la cabecera `X-Request-ID`. Si la petición trae una cabecera `X-Request-ID` de 8 a 64 caracteres `[A-Za-z0-9-]`, SHALL reutilizarla; en caso contrario SHALL generar uno nuevo.

#### Scenario: Cabecera de respuesta
- **WHEN** se solicita cualquier ruta
- **THEN** la respuesta incluye `X-Request-ID` y todas las líneas de log de esa petición tienen ese mismo `request_id`

#### Scenario: Identificador entrante inválido
- **WHEN** la petición trae `X-Request-ID: <script>`
- **THEN** se ignora y se genera un identificador nuevo

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

### Requirement: Sin datos sensibles en logs
El log MUST NOT contener contraseñas, hashes, identificadores de sesión, tokens CSRF, `SECRET_KEY`, RFC, datos bancarios, contenido de archivos ni nombres originales de archivo.

#### Scenario: Revisión del log tras el flujo completo
- **WHEN** se ejecuta el flujo de login fallido, login exitoso, subida de documentos, validación y revisión, y se busca en el log `password`, `csrf`, `Admin123`, el RFC del proveedor y el RFC receptor
- **THEN** no hay coincidencias

