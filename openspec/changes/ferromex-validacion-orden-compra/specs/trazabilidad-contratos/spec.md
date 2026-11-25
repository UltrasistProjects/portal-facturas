## REMOVED Requirements

### Requirement: Campos de auditoría en contratos
**Reason**: Se retira el módulo de contratos en la rama `ferromex`; la factura se controla contra su orden de compra (HU-24).
**Migration**: Las tablas `contracts`, `contract_amendments` y `contract_document_types` se conservan con sus datos sin uso (P-02); la factura apunta a `purchase_orders` (spec `orden-compra`).

### Requirement: Modificación versionada del monto autorizado
**Reason**: Se retira el módulo de contratos en la rama `ferromex`; la factura se controla contra su orden de compra (HU-24).
**Migration**: Las tablas `contracts`, `contract_amendments` y `contract_document_types` se conservan con sus datos sin uso (P-02); la factura apunta a `purchase_orders` (spec `orden-compra`).

### Requirement: Validación auditable contra el monto vigente
**Reason**: Se retira el módulo de contratos en la rama `ferromex`; la factura se controla contra su orden de compra (HU-24).
**Migration**: Las tablas `contracts`, `contract_amendments` y `contract_document_types` se conservan con sus datos sin uso (P-02); la factura apunta a `purchase_orders` (spec `orden-compra`).
