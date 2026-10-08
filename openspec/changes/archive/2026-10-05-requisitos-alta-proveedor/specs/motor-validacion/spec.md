## ADDED Requirements

### Requirement: Expediente mínimo según los requisitos de alta configurados
Al validar una factura, SUP-003 (`ERROR`) SHALL evaluar los requisitos de alta exigibles del proveedor de la factura con la configuración vigente (capacidad `requisitos-alta-proveedor`):
- `PASS` con el mensaje "Expediente mínimo disponible" si cada requisito exigible tiene un documento vigente en el expediente;
- `FAIL` con el mensaje "Expediente del proveedor incompleto. Pendientes: <nombre>, <nombre>" en otro caso, con los nombres en el orden del catálogo;
- `NOT_APPLICABLE` con el mensaje "No aplica a proveedores internacionales" si el proveedor es Internacional y no tiene requisitos de alta exigibles.

La antigüedad de los documentos MUST NOT afectar SUP-003. SUP-004 no cambia.

#### Scenario: Proveedor demo con expediente completo
- **WHEN** se valida la factura demo A-CORRECTA después de la migración y de `reset_demo`
- **THEN** SUP-003 resulta `PASS` con "Expediente mínimo disponible"

#### Scenario: Requisito obligatorio agregado después de la autorización
- **WHEN** el Administrador da de alta "Declaración de ISR por retenciones de salarios", Obligatorio para Persona moral, y se valida una factura de una persona moral "Autorizado" que no tiene ese documento
- **THEN** SUP-003 resulta `FAIL` con "Expediente del proveedor incompleto. Pendientes: Declaración de ISR por retenciones de salarios", el envío no procede y el proveedor sigue "Autorizado"

#### Scenario: Opinión de cumplimiento opcional
- **WHEN** con la configuración inicial se valida una factura de una persona moral con todos sus requisitos obligatorios y sin opinión de cumplimiento
- **THEN** SUP-003 resulta `PASS`

#### Scenario: Proveedor internacional con un requisito configurado
- **WHEN** "Estado de cuenta bancario" es Obligatorio para Internacional y se valida una factura de un proveedor internacional sin ese documento
- **THEN** SUP-003 resulta `FAIL` con "Expediente del proveedor incompleto. Pendientes: Estado de cuenta bancario"

## MODIFIED Requirements

### Requirement: Reglas nacionales que no aplican a la factura internacional
Al validar una factura de un proveedor de origen Internacional, el motor SHALL reportar como `NOT_APPLICABLE`, con el mensaje "No aplica a proveedores internacionales" y conservando la severidad de cada regla:
- las reglas del CFDI, XML-001 a XML-010, sin intentar leer un XML;
- FIN-004 (UUID duplicado);
- SUP-003 (expediente mínimo), cuando el proveedor no tiene requisitos de alta exigibles; si los tiene, SUP-003 se evalúa conforme a "Expediente mínimo según los requisitos de alta configurados";
- SUP-004 (vigencia de los documentos del expediente).

SEM-001 SHALL resultar `NOT_EVALUATED` con "Sin conceptos que comparar: el Invoice no es un CFDI". Las demás reglas (DOC, SUP-001, SUP-002, CON, DAT y FIN-001, FIN-002, FIN-003, FIN-005 y FIN-006) SHALL evaluarse igual que para el proveedor nacional, con los importes y la moneda capturados. La validación de facturas de proveedores nacionales MUST NOT cambiar, salvo SUP-003, que sigue la configuración de requisitos de alta.

#### Scenario: Factura internacional completa
- **WHEN** con la configuración inicial de requisitos de alta se valida una factura internacional con Invoice, orden de compra y Vo.Bo., importes que cuadran y dentro del monto de su contrato vigente
- **THEN** XML-001 a XML-010, FIN-004, SUP-003 y SUP-004 resultan `NOT_APPLICABLE`, ninguna regla resulta `FAIL` y la factura puede enviarse

#### Scenario: Monto excedido
- **WHEN** el subtotal capturado de una factura internacional excede el monto autorizado de su contrato
- **THEN** FIN-001 resulta `FAIL` con severidad `CRITICAL` y el envío no procede

#### Scenario: Factura nacional sin cambios
- **WHEN** se valida la factura demo A-CORRECTA
- **THEN** sus resultados son los mismos que antes de este cambio y no incluyen reglas INT ni FIN-007
