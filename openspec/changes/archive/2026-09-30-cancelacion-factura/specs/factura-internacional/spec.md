## MODIFIED Requirements

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
