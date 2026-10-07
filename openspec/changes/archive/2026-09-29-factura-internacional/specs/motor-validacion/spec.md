## ADDED Requirements

### Requirement: Reglas nacionales que no aplican a la factura internacional
Al validar una factura de un proveedor de origen Internacional, el motor SHALL reportar como `NOT_APPLICABLE`, con el mensaje "No aplica a proveedores internacionales" y conservando la severidad de cada regla:
- las reglas del CFDI, XML-001 a XML-010, sin intentar leer un XML;
- FIN-004 (UUID duplicado);
- SUP-003 y SUP-004 (expediente del Anexo A), mientras no se defina el expediente del proveedor internacional.

SEM-001 SHALL resultar `NOT_EVALUATED` con "Sin conceptos que comparar: el Invoice no es un CFDI". Las demás reglas (DOC, SUP-001, SUP-002, CON, DAT y FIN-001, FIN-002, FIN-003, FIN-005 y FIN-006) SHALL evaluarse igual que para el proveedor nacional, con los importes y la moneda capturados. La validación de facturas de proveedores nacionales MUST NOT cambiar.

#### Scenario: Factura internacional completa
- **WHEN** se valida una factura internacional con Invoice, orden de compra y Vo.Bo., importes que cuadran y dentro del monto de su contrato vigente
- **THEN** XML-001 a XML-010, FIN-004, SUP-003 y SUP-004 resultan `NOT_APPLICABLE`, ninguna regla resulta `FAIL` y la factura puede enviarse

#### Scenario: Monto excedido
- **WHEN** el subtotal capturado de una factura internacional excede el monto autorizado de su contrato
- **THEN** FIN-001 resulta `FAIL` con severidad `CRITICAL` y el envío no procede

#### Scenario: Factura nacional sin cambios
- **WHEN** se valida la factura demo A-CORRECTA
- **THEN** sus resultados son los mismos que antes de este cambio y no incluyen reglas INT ni FIN-007
