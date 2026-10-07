## MODIFIED Requirements

### Requirement: Cancelación exclusiva del proveedor
El detalle de una factura que no está "Cancelada" SHALL ofrecer al rol `Proveedor` la sección "Cancelar factura" con el campo del "Acuse de cancelación" (PDF o XML) y la confirmación "Confirmo que la factura se canceló y adjunto su acuse". `POST /invoices/{invoice_id}/cancel` SHALL exigir CSRF y el rol `Proveedor` (HTTP 403 para `PMO` y `Administrador`); una factura de otro proveedor SHALL responder HTTP 404. Los demás roles MUST NOT ver la sección.

#### Scenario: Sección para el proveedor
- **WHEN** el proveedor abre el detalle de su factura "Enviada"
- **THEN** ve "Cancelar factura" con el campo del acuse y la confirmación

#### Scenario: PMO sin cancelación
- **WHEN** el PMO abre el detalle de una factura o envía `POST /invoices/{id}/cancel`
- **THEN** no ve la sección y la petición responde HTTP 403 sin cambios

#### Scenario: Factura de otro proveedor
- **WHEN** un proveedor envía la cancelación de una factura de otro proveedor
- **THEN** la respuesta es HTTP 404 y la factura no cambia
