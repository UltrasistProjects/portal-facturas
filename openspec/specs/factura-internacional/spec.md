# factura-internacional Specification

## Purpose
Factura del proveedor internacional (HU-15, HU-16; RF-14, RF-15): datos del Invoice capturados en el registro y editables mientras la factura es editable, duplicado del Invoice por nombre de archivo (al cargar y FIN-007), reglas INT sobre el texto del Invoice y datos del Invoice en el detalle y la carga documental.
## Requirements
### Requirement: Datos del Invoice en el registro de la factura internacional
Cuando el proveedor del usuario es de origen Internacional, el formulario de alta SHALL pedir, además de los datos generales, los datos del Invoice:
- fecha de la factura, no posterior a hoy en la zona horaria de negocio;
- subtotal mayor que cero;
- impuestos mayores o iguales a cero;
- moneda, elegida de las claves activas del catálogo de monedas.

El total SHALL mostrarse en un campo de solo lectura que la página recalcula al cambiar el subtotal o los impuestos. El servidor SHALL calcular `total = subtotal + impuestos` con `Decimal`, redondeado a 2 decimales con `ROUND_HALF_UP`, e ignorar cualquier total que envíe el cliente.

Los importes SHALL tener a lo sumo dos decimales y caber en `NUMERIC(16, 2)`; el sistema SHALL aceptar el separador de miles `,` y el símbolo `$`. Los datos SHALL guardarse en `invoices.invoice_date`, `subtotal`, `tax`, `total` y `currency`. Un error SHALL rechazar el alta con HTTP 400, mostrar todos los errores juntos y conservar lo capturado. Para un proveedor nacional el formulario MUST NOT mostrar estos campos y el sistema SHALL ignorarlos si se envían: sus importes salen del XML.

#### Scenario: Registro de un Invoice
- **WHEN** un proveedor internacional registra la factura "INV-2026-001" con fecha 15/09/2026, subtotal `1,000.00`, impuestos `0.00` y moneda `USD`
- **THEN** la factura queda en "Borrador" con `invoice_date = 2026-09-15`, `subtotal = 1000.00`, `tax = 0.00`, `total = 1000.00` y `currency = USD`, y el proveedor pasa a la carga documental

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
- **THEN** el formulario no muestra los campos del Invoice, y si la petición los incluye, la factura se crea con importes en cero hasta que el XML los aporte

### Requirement: Edición de los datos del Invoice
El proveedor SHALL poder editar los datos del Invoice de una factura internacional mientras esté en un estatus editable (Borrador, Cargada u Observaciones), desde la carga documental, con `POST /invoices/{invoice_id}/amounts`. La ruta SHALL ser exclusiva del rol `Proveedor`, exigir CSRF, bloquear la fila de la factura y aplicar las mismas validaciones y el mismo cálculo del total que el registro. SHALL responder:
- HTTP 409 si la factura no está en un estatus editable;
- HTTP 400 si la factura es de un proveedor nacional.

Un guardado con cambios SHALL auditar `INVOICE_AMOUNTS_UPDATED` con los valores anteriores y nuevos de los campos que cambiaron; uno sin cambios MUST NOT auditar.

#### Scenario: Corrección tras Observaciones
- **WHEN** una factura internacional de subtotal `1000.00` está en "Observaciones" y el proveedor corrige los impuestos a `160.00`
- **THEN** la factura guarda `tax = 160.00` y `total = 1160.00`, sigue en "Observaciones" y `audit_logs` contiene `INVOICE_AMOUNTS_UPDATED` con `old_value = {"tax": "0.00", "total": "1000.00"}` y `new_value = {"tax": "160.00", "total": "1160.00"}`

#### Scenario: Total manipulado en la edición
- **WHEN** una petición directa edita los datos con subtotal `500.00`, impuestos `80.00` y total `999.99`
- **THEN** la factura guarda `total = 580.00`

#### Scenario: Factura enviada
- **WHEN** el proveedor envía la edición de los datos de una factura "Enviada"
- **THEN** la respuesta es HTTP 409 y los importes no cambian

#### Scenario: Otro rol
- **WHEN** un usuario `PMO` envía la edición de los datos de una factura internacional
- **THEN** la respuesta es HTTP 403 y los importes no cambian

### Requirement: Invoice duplicado por nombre de archivo
Al cargar un documento de tipo `FOREIGN_INVOICE`, el sistema SHALL tomar un bloqueo consultivo de transacción por proveedor y buscar, entre los documentos `FOREIGN_INVOICE` vigentes de las demás facturas no canceladas del mismo proveedor, uno con el mismo nombre de archivo, sin distinguir mayúsculas y sin los espacios de los extremos. Si existe, SHALL responder HTTP 409 con "Ya existe una factura con un Invoice llamado «<nombre>»: <folio>" antes de escribir el archivo. Reemplazar el Invoice de la misma factura con un archivo del mismo nombre SHALL permitirse.

Al validar una factura internacional, la regla FIN-007 (`CRITICAL`) SHALL resultar `FAIL` con el mensaje "Invoice duplicado por nombre de archivo" y los folios de las otras facturas en su evidencia si existe esa coincidencia, `PASS` si no, y `NOT_EVALUATED` si la factura no tiene Invoice. Las facturas de proveedores nacionales MUST NOT generar FIN-007.

#### Scenario: Invoice repetido en otra factura
- **WHEN** el proveedor internacional ya cargó `INV-2026-001.pdf` en la factura FAC-2026-00012 y carga `inv-2026-001.PDF` como Invoice de otra factura
- **THEN** la respuesta es HTTP 409 con "Ya existe una factura con un Invoice llamado «inv-2026-001.PDF»: FAC-2026-00012" y no se escribe ningún archivo en `storage/`

#### Scenario: Reemplazo en la misma factura
- **WHEN** el proveedor vuelve a cargar `INV-2026-001.pdf` como Invoice de la misma factura
- **THEN** la carga se acepta y el documento anterior deja de estar vigente

#### Scenario: Mismo nombre en otro proveedor
- **WHEN** otro proveedor internacional carga un Invoice llamado `INV-2026-001.pdf`
- **THEN** la carga se acepta

#### Scenario: Duplicado detectado al enviar
- **WHEN** dos facturas del mismo proveedor tienen vigente un Invoice con el mismo nombre y se envía una de ellas
- **THEN** FIN-007 resulta `FAIL` con severidad `CRITICAL`, el envío no procede y la evidencia lista el folio de la otra factura

#### Scenario: Nombre de una factura cancelada
- **WHEN** la factura que tenía el Invoice `INV-2026-001.pdf` se canceló y el proveedor carga ese nombre en otra factura
- **THEN** la carga se acepta y FIN-007 resulta `PASS`

### Requirement: Reglas sobre el texto del Invoice
Al validar una factura internacional, el motor SHALL extraer el texto del PDF del Invoice vigente y evaluar estas reglas de categoría `INT`, todas de severidad `WARNING`, que resultan `PASS` o `WARNING` y nunca `FAIL`. Cada una SHALL usar el valor esperado de su regla internacional activa:
- INT-001: el identificador fiscal del proveedor (`foreign_tax_id`) aparece en el texto;
- INT-002: la Razón Social de INT-002 aparece en el texto;
- INT-003: el Código Postal de INT-003 aparece en el texto como número de 5 dígitos;
- INT-004: la Dirección de INT-004 aparece en el texto.

INT-001, INT-002 e INT-004 SHALL comparar sin acentos, sin distinguir mayúsculas e ignorando espacios y signos de puntuación. Una regla INT eliminada SHALL resultar `NOT_APPLICABLE` con "Regla inactiva en Reglas de Validación". Si la factura no tiene Invoice o su PDF no tiene texto legible, las reglas activas SHALL resultar `NOT_EVALUATED` con "No se pudo leer el texto del Invoice". Las facturas de proveedores nacionales MUST NOT generar reglas INT.

#### Scenario: Invoice con los datos esperados
- **WHEN** el texto del Invoice contiene "Tax ID: 98-7654321", "Bill to: ULTRASIST, S.A. de C.V." y "C.P. 03930", el proveedor tiene `foreign_tax_id = 987654321`, INT-002 espera "ULTRASIST SA DE CV" e INT-003 espera `03930`
- **THEN** INT-001, INT-002 e INT-003 resultan `PASS`

#### Scenario: Razón social ausente
- **WHEN** el texto del Invoice no contiene la Razón Social de INT-002
- **THEN** INT-002 resulta `WARNING` con "No se encontró la razón social de ULTRASIST en el Invoice" y el envío procede si no hay ningún `FAIL`

#### Scenario: Invoice escaneado
- **WHEN** el PDF del Invoice no tiene capa de texto
- **THEN** las reglas INT activas resultan `NOT_EVALUATED` con "No se pudo leer el texto del Invoice" y no afectan el score

#### Scenario: Regla eliminada
- **WHEN** INT-003 está eliminada en las Reglas de Validación — Internacionales
- **THEN** INT-003 resulta `NOT_APPLICABLE` con "Regla inactiva en Reglas de Validación"

### Requirement: Datos del Invoice en el detalle y la carga documental
El detalle de una factura internacional SHALL mostrar la sección "Datos del Invoice" en lugar de "Datos CFDI", con la fecha, el subtotal, los impuestos, el total, la moneda, el identificador fiscal y el país del proveedor, y si el texto del Invoice vigente es legible. El UUID SHALL mostrarse como "No aplica (Invoice)". La carga documental de una factura internacional editable SHALL mostrar el formulario para editar los datos del Invoice.

#### Scenario: Detalle de una factura internacional
- **WHEN** el PMO abre el detalle de una factura internacional con total `1000.00 USD`
- **THEN** ve "Datos del Invoice" con el total `$1,000.00 USD`, "No aplica (Invoice)" como UUID y no ve la sección "Datos CFDI"

#### Scenario: Formulario en la carga documental
- **WHEN** el proveedor internacional abre la carga documental de su factura en "Borrador"
- **THEN** ve el formulario "Datos del Invoice" con los valores capturados en el registro

