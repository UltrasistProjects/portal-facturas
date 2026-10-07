## Why

Al autorizar una factura, el PMO sólo notificaba al buzón "Recepción de Facturas": el proveedor no se enteraba de que su factura quedó autorizada para pago hasta consultar el portal. Se pidió que el correo de la autorización le llegue también al proveedor, con copia.

## What Changes

- El correo "Autorizada" sigue dirigido ("Para") al buzón "Recepción de Facturas" y lleva en "Cc" el correo del proveedor de la factura, antes de las copias configuradas del evento y sin repetidas. El reenvío de la notificación lleva la misma copia.
- Cancelada y Complemento de pago adjuntado siguen yendo sólo al buzón y a sus copias.
- El destinatario de Autorizada se muestra como "Recepción de Facturas con copia al proveedor" en Plantillas de correo y en Notificaciones.
- El modal de "Autorizar" avisa "Se notificará a Recepción de Facturas con copia al proveedor." y el resultado de la decisión muestra "Correo enviado a <destinatarios> con copia a <copias>" cuando el envío lleva copias.

## Capabilities

### New Capabilities

_Ninguna._

### Modified Capabilities

- `notificaciones-correo`: Autorizada con copia al proveedor; destinatario principal mostrado en Notificaciones.
- `revision-pmo`: correo y reenvío de la autorización con copia al proveedor; resultado con las copias.
- `plantillas-notificacion`: destinatario de Autorizada en el listado y la edición de plantillas.
- `interfaz-usuario`: texto del modal de "Autorizar".

## Impact

`app/services/notification_templates.py` (`EventSpec.supplier_copy` y `recipient_label`), `app/services/notification_service.py` (`recipients_for`), `app/services/review_service.py`, plantillas de notificaciones y el detalle de la factura; pruebas en `test_notificaciones_correo.py`, `test_cambio_estatus.py`, `test_plantillas_notificacion.py` y `test_interfaz_usuario.py`, la spec Playwright 17, el video del recorrido y `hu-catalogo.json`. Sin migraciones: el texto de la plantilla no cambia.
