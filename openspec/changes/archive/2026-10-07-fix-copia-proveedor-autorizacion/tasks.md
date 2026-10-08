## 1. Destinatarios

- [x] 1.1 `EventSpec.supplier_copy` y `recipient_label`; Autorizada con copia al proveedor
- [x] 1.2 `recipients_for` agrega el correo del proveedor al "Cc" antes de las copias configuradas, sin repetidas
- [x] 1.3 `review_service` entrega siempre el correo del proveedor

## 2. Interfaz

- [x] 2.1 Destinatario "Recepción de Facturas con copia al proveedor" en Plantillas de correo y Notificaciones
- [x] 2.2 Modal de "Autorizar" y resultado de la decisión con las copias

## 3. Pruebas

- [x] 3.1 pytest: destinatarios de Autorizada y Cancelada, correo de la autorización, pantallas y modal
- [x] 3.2 Spec Playwright 17, video del recorrido y `hu-catalogo.json`
