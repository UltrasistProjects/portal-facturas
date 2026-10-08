## MODIFIED Requirements

### Requirement: Edición de los datos del Invoice
El proveedor SHALL poder editar los datos del Invoice de una factura internacional mientras esté en un estatus editable (Borrador, Cargada u Observaciones), desde la carga documental, con `POST /invoices/{invoice_id}/amounts`. La ruta SHALL ser exclusiva del rol `Proveedor`, exigir CSRF, bloquear la fila de la factura y aplicar las mismas validaciones del registro. SHALL responder:
- HTTP 409 si la factura no está en un estatus editable;
- HTTP 400 si la factura es de un proveedor nacional.

Un guardado con cambios SHALL auditar `INVOICE_AMOUNTS_UPDATED` con los valores anteriores y nuevos de los campos que cambiaron; uno sin cambios MUST NOT auditar.

#### Scenario: Corrección tras Observaciones
- **WHEN** una factura internacional está en "Observaciones" y el proveedor corrige el total a `1160.00` con impuestos `160.00`
- **THEN** la factura guarda los importes nuevos, sigue en "Observaciones" y `audit_logs` contiene `INVOICE_AMOUNTS_UPDATED` con `old_value = {"tax": "0.00", "total": "1000.00"}` y `new_value = {"tax": "160.00", "total": "1160.00"}`

#### Scenario: Factura enviada
- **WHEN** el proveedor envía la edición de los datos de una factura "Enviada"
- **THEN** la respuesta es HTTP 409 y los importes no cambian

#### Scenario: Otro rol
- **WHEN** un usuario `PMO` envía la edición de los datos de una factura internacional
- **THEN** la respuesta es HTTP 403 y los importes no cambian
