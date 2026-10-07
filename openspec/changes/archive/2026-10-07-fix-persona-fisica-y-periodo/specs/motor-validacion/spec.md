## ADDED Requirements

### Requirement: Periodo del servicio dentro de la vigencia del contrato
CON-003 (`ERROR`) SHALL comparar el periodo de la factura (`MM/AAAA`) por mes contra la vigencia del contrato: resulta `PASS` si el mes del periodo está entre el mes de inicio y el mes de fin del contrato, inclusive, aunque el contrato empiece o termine a mitad de mes. El valor esperado SHALL mostrarse en el mismo formato del periodo: "MM/AAAA a MM/AAAA".

#### Scenario: Contrato que empieza a mitad de mes
- **WHEN** el contrato va del 15/08/2026 al 10/12/2026 y la factura es del periodo `08/2026`
- **THEN** CON-003 es `PASS` con valor esperado "08/2026 a 12/2026"

#### Scenario: Periodo fuera de la vigencia
- **WHEN** el mismo contrato y una factura del periodo `07/2026`
- **THEN** CON-003 es `FAIL` con valor esperado "08/2026 a 12/2026" y detectado `07/2026`
