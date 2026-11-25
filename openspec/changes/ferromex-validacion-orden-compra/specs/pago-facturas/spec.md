## MODIFIED Requirements

### Requirement: Factura que requiere Complemento de Pago
Una factura SHALL requerir Complemento de Pago si y sólo si su proveedor es nacional (`NATIONAL`), el método de pago (`MetodoPago`) de su CFDI vigente es `PPD` y el tipo "Complemento de pago (XML)" (`PAYMENT_COMPLEMENT_XML`) está activo en Archivos mínimos. El método de pago SHALL leerse de los datos extraídos del CFDI (`payment_method`, spec `registro-factura-extraccion`): los del XML vigente o, si la factura no tiene XML, los que se leyeron de su PDF. Si no hay datos extraídos o no traen método de pago, la factura no lo requiere. El requisito SHALL determinarse una sola vez, al marcar la factura como pagada, y SHALL quedar fijo en `payment_complement_due_at`. Un cambio posterior en el catálogo o en las Reglas de Validación MUST NOT cambiarlo.

Si al marcar la factura como pagada ya tiene un XML del Complemento de Pago vigente y válido, el sistema SHALL registrar también `payment_complement_received_at` con la fecha de esa carga, y el complemento no queda pendiente.

#### Scenario: Nacional PPD
- **WHEN** el PMO marca como pagada el 01/10/2026 a las 10:00 (hora de negocio) la factura nacional "A-1024", cuyo XML trae `MetodoPago="PPD"`
- **THEN** la factura requiere Complemento de Pago con fecha límite 04/10/2026 10:00

#### Scenario: Nacional PPD registrada sólo con el PDF
- **WHEN** el Administrador marca como pagada la factura 3668, registrada sin XML y cuyo PDF dice "MÉTODO DE PAGO PPD - Pago en parcialidades o diferido"
- **THEN** la factura requiere Complemento de Pago con fecha límite 72 horas después del pago

#### Scenario: Nacional PUE
- **WHEN** el PMO marca como pagada una factura nacional cuyo XML trae `MetodoPago="PUE"`
- **THEN** la factura no requiere Complemento de Pago y `payment_complement_due_at` es nulo

#### Scenario: Internacional
- **WHEN** el PMO marca como pagada una factura de un proveedor internacional
- **THEN** la factura no requiere Complemento de Pago

#### Scenario: Tipo del complemento eliminado
- **WHEN** el Administrador eliminó "Complemento de pago (XML)" y el PMO marca como pagada una factura nacional PPD
- **THEN** la factura no requiere Complemento de Pago y `payment_complement_due_at` es nulo
