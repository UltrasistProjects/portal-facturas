## MODIFIED Requirements

### Requirement: Confirmaciones en modales del portal
El código propio del portal (`app/static/js` y `app/templates`, sin `app/static/vendor`) MUST NOT usar `alert`, `confirm` ni `prompt`. Una acción que pide confirmación SHALL mostrar un modal de Bootstrap con la pregunta, un botón para aceptar y otro para cancelar. Cancelar, cerrar el modal o pulsar Esc MUST NOT ejecutar la acción. Aceptar SHALL ejecutar exactamente la misma acción que el botón ejecutaba antes de la confirmación, con los mismos datos.

#### Scenario: Autorizar con confirmación
- **WHEN** el PMO pulsa "Autorizar" en el panel de decisión de una factura "Enviada"
- **THEN** ve un modal con "¿Autorizar la factura {número} para su pago? Se notificará a Recepción de Facturas con copia al proveedor." y no se envía nada hasta que elige

#### Scenario: Aceptar la autorización
- **WHEN** el PMO acepta en el modal
- **THEN** se envía el formulario con `decision=ACCEPTED` y las observaciones capturadas, igual que antes, y la factura queda "Autorizada"

#### Scenario: Cancelar la autorización
- **WHEN** el PMO pulsa "Cancelar", cierra el modal o pulsa Esc
- **THEN** no se envía el formulario, la factura sigue "Enviada" y el foco vuelve al botón "Autorizar"

#### Scenario: Sin diálogos nativos en el código
- **WHEN** se revisan los archivos de `app/static/js` y `app/templates`, sin `app/static/vendor`
- **THEN** no contienen llamadas a `alert(`, `confirm(` ni `prompt(`
