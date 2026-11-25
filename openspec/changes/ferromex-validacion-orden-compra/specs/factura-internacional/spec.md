## MODIFIED Requirements

### Requirement: Datos del Invoice en el registro de la factura internacional
Cuando el proveedor del usuario es de origen Internacional, el formulario de alta SHALL pedir el número de factura (1 a 100 caracteres) y los datos del Invoice:
- número de orden de compra, obligatorio, de 6 a 10 dígitos; si falta o no tiene ese formato, el error SHALL ser "Capture el número de orden de compra";
- fecha de la factura, no posterior a hoy en la zona horaria de negocio;
- subtotal mayor que cero;
- impuestos mayores o iguales a cero;
- moneda, elegida de las claves activas del catálogo de monedas.

El formulario MUST NOT pedir contrato, periodo, proyecto ni líder de proyecto. El periodo de la factura SHALL tomarse del mes de la fecha de la factura (`MM/AAAA`).

El total SHALL mostrarse en un campo de solo lectura que la página recalcula al cambiar el subtotal o los impuestos. El servidor SHALL calcular `total = subtotal + impuestos` con `Decimal`, redondeado a 2 decimales con `ROUND_HALF_UP`, e ignorar cualquier total que envíe el cliente.

Los importes SHALL tener a lo sumo dos decimales y caber en `NUMERIC(16, 2)`; el sistema SHALL aceptar el separador de miles `,` y el símbolo `$`. Los datos SHALL guardarse en `invoices.invoice_date`, `subtotal`, `tax`, `total`, `currency` y `purchase_order_number`. Un error SHALL rechazar el alta con HTTP 400, mostrar todos los errores juntos y conservar lo capturado. Para un proveedor nacional el formulario MUST NOT mostrar estos campos: su registro es por archivos (spec `registro-factura-extraccion`).

#### Scenario: Registro de un Invoice
- **WHEN** un proveedor internacional registra la factura "INV-2026-001" con orden de compra `45009001`, fecha 15/09/2026, subtotal `1,000.00`, impuestos `0.00` y moneda `USD`
- **THEN** la factura queda en "Borrador" con `invoice_date = 2026-09-15`, `service_period = 09/2026`, `subtotal = 1000.00`, `tax = 0.00`, `total = 1000.00`, `currency = USD`, `purchase_order_number = 45009001` y `contract_id` nulo, y el proveedor pasa a la carga documental

#### Scenario: Sin número de orden de compra
- **WHEN** un proveedor internacional registra un Invoice sin número de orden de compra
- **THEN** la respuesta es HTTP 400 con "Capture el número de orden de compra" y no se crea la factura

#### Scenario: Total manipulado por el cliente
- **WHEN** una petición directa registra subtotal `1000.00`, impuestos `160.00` y total `1.00`
- **THEN** la factura se crea con `total = 1160.00`

#### Scenario: Total recalculado en la página
- **WHEN** el proveedor captura subtotal `1,000.50` e impuestos `160.08` en el formulario
- **THEN** el campo Total muestra `1,160.58` y no se puede editar

#### Scenario: Moneda inactiva
- **WHEN** un proveedor internacional registra la moneda `JPY`, que no está activa en el catálogo
- **THEN** la respuesta es HTTP 400 con "Moneda: la clave no está activa en el catálogo" y no se crea la factura

#### Scenario: Moneda inexistente por petición directa
- **WHEN** una petición directa registra la moneda `XYZ`
- **THEN** la respuesta es HTTP 400 con "Moneda: la clave no está activa en el catálogo" y no se crea la factura

#### Scenario: Fecha futura
- **WHEN** un proveedor internacional registra una fecha posterior a hoy
- **THEN** la respuesta es HTTP 400 con "Fecha de la factura: no puede ser posterior a hoy"

#### Scenario: Proveedor nacional
- **WHEN** un proveedor nacional abre el formulario de alta
- **THEN** el formulario pide el PDF y el XML de la factura y no muestra los campos del Invoice

### Requirement: Edición de los datos del Invoice
El proveedor SHALL poder editar los datos del Invoice de una factura internacional, incluido el número de orden de compra, mientras esté en un estatus editable (Borrador, Cargada u Observaciones), desde la carga documental, con `POST /invoices/{invoice_id}/amounts`. La ruta SHALL ser exclusiva del rol `Proveedor`, exigir CSRF, bloquear la fila de la factura y aplicar las mismas validaciones y el mismo cálculo del total que el registro. SHALL responder:
- HTTP 409 si la factura no está en un estatus editable;
- HTTP 400 si la factura es de un proveedor nacional.

Si la factura no tiene número de orden de compra y el texto del Invoice vigente cita `OC/<número>`, el formulario SHALL proponer ese número. Un guardado con cambios SHALL auditar `INVOICE_AMOUNTS_UPDATED` con los valores anteriores y nuevos de los campos que cambiaron; uno sin cambios MUST NOT auditar.

#### Scenario: Corrección tras Observaciones
- **WHEN** una factura internacional de subtotal `1000.00` está en "Observaciones" y el proveedor corrige los impuestos a `160.00`
- **THEN** la factura guarda `tax = 160.00` y `total = 1160.00`, sigue en "Observaciones" y `audit_logs` contiene `INVOICE_AMOUNTS_UPDATED` con `old_value = {"tax": "0.00", "total": "1000.00"}` y `new_value = {"tax": "160.00", "total": "1160.00"}`

#### Scenario: Corrección de la orden de compra
- **WHEN** el proveedor cambia la orden de compra de una factura internacional en "Borrador" de `45009001` a `45009002`
- **THEN** la factura guarda `purchase_order_number = 45009002` y `INVOICE_AMOUNTS_UPDATED` registra el cambio

#### Scenario: Orden propuesta desde el Invoice
- **WHEN** una factura internacional sin número de orden tiene un Invoice cuyo texto dice "PO: OC/45009001"
- **THEN** el formulario de los datos del Invoice muestra `45009001` en el campo de la orden de compra

#### Scenario: Total manipulado en la edición
- **WHEN** una petición directa edita los datos con subtotal `500.00`, impuestos `80.00` y total `999.99`
- **THEN** la factura guarda `total = 580.00`

#### Scenario: Factura enviada
- **WHEN** el proveedor envía la edición de los datos de una factura "Enviada"
- **THEN** la respuesta es HTTP 409 y los importes no cambian

#### Scenario: Otro rol
- **WHEN** un usuario `PMO` envía la edición de los datos de una factura internacional
- **THEN** la respuesta es HTTP 403 y los importes no cambian

### Requirement: Datos del Invoice en el detalle y la carga documental
El detalle de una factura internacional SHALL mostrar la sección "Datos del Invoice" en lugar de "Datos CFDI", con la fecha, el subtotal, los impuestos, el total, la moneda, el número de orden de compra, el identificador fiscal y el país del proveedor, y si el texto del Invoice vigente es legible. El UUID SHALL mostrarse como "No aplica (Invoice)". La carga documental de una factura internacional editable SHALL mostrar el formulario para editar los datos del Invoice.

#### Scenario: Detalle de una factura internacional
- **WHEN** el PMO abre el detalle de una factura internacional con total `1000.00 USD` y orden de compra `45009001`
- **THEN** ve "Datos del Invoice" con el total `$1,000.00 USD` y la orden `45009001`, "No aplica (Invoice)" como UUID y no ve la sección "Datos CFDI"

#### Scenario: Formulario en la carga documental
- **WHEN** el proveedor internacional abre la carga documental de su factura en "Borrador"
- **THEN** ve el formulario "Datos del Invoice" con los valores capturados en el registro, incluida la orden de compra
