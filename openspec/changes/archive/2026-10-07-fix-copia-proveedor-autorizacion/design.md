## Context

Fix acotado sobre la resolución de destinatarios de HU-08; no cambia el esquema ni las plantillas guardadas.

## Decisions

- **Dónde vive la regla:** `EventSpec.supplier_copy` en `notification_templates.EVENTS`, junto al destinatario principal (RD-03), y no en la HU que envía. `recipients_for` agrega el correo del proveedor al "Cc" cuando el evento lo pide; `review_service` entrega siempre el correo del proveedor y la regla decide si se usa.
- **Copia y no destinatario principal:** el correo sigue siendo el aviso a Recepción de Facturas (su texto se dirige a ese buzón); el proveedor lo recibe en "Cc".
- **Proveedor sin correo:** el correo sale sólo con el buzón y las copias configuradas; la copia no debe impedir el aviso a Recepción. En la práctica no ocurre: el correo es obligatorio en el catálogo.
- **Pantallas:** `EventSpec.recipient_label` da el texto "Recepción de Facturas con copia al proveedor" para el listado de plantillas, su edición y la columna "Destinatario principal" de Notificaciones.

## Risks / Trade-offs

- [El proveedor recibe un correo que comienza con "Recepción de Facturas:"] → es una copia del aviso al buzón; si se quisiera un texto propio para el proveedor haría falta un evento y una plantilla nuevos.
