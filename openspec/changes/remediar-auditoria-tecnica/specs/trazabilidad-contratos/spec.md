## ADDED Requirements

### Requirement: Campos de auditoría en contratos
La tabla `contracts` SHALL registrar `created_at`, `created_by`, `updated_at` y `updated_by`. Los valores se asignan automáticamente en el alta y en cada modificación.

#### Scenario: Alta de contrato
- **WHEN** un ADMIN crea un contrato
- **THEN** el contrato guarda `created_at` en UTC, `created_by` con el id del ADMIN, y `updated_at`/`updated_by` con los mismos valores

#### Scenario: Contratos preexistentes
- **WHEN** se migra una base con contratos sin campos de auditoría
- **THEN** `created_at` y `updated_at` toman la marca temporal de la migración, y `created_by`/`updated_by` quedan en `NULL`

### Requirement: Modificación versionada del monto autorizado
El monto autorizado de un contrato SHALL modificarse únicamente mediante una enmienda registrada por un ADMIN. Cada enmienda guarda el contrato, el monto anterior, el monto nuevo, el motivo (obligatorio), el usuario y la marca temporal. Cada enmienda SHALL auditarse como `CONTRACT_AMOUNT_CHANGED`, con `old_value`/`new_value`. El historial de enmiendas SHALL ser visible para INTERNAL y ADMIN.

#### Scenario: Enmienda válida
- **WHEN** un ADMIN cambia el monto de un contrato de 100,000.00 a 120,000.00 con motivo "Ampliación de alcance"
- **THEN** se crea una enmienda con ambos montos, el motivo, el usuario y la fecha; `contracts.authorized_amount` queda en 120,000.00; se registra `CONTRACT_AMOUNT_CHANGED` con `old_value={"authorized_amount": "100000.00"}` y `new_value={"authorized_amount": "120000.00"}`

#### Scenario: Usuario sin permiso
- **WHEN** un usuario INTERNAL o PROVIDER envía una enmienda de monto
- **THEN** la respuesta es HTTP 403 y el monto no cambia

#### Scenario: Motivo ausente
- **WHEN** un ADMIN envía una enmienda sin motivo
- **THEN** la respuesta es HTTP 400 y no se crea la enmienda

#### Scenario: Monto no positivo
- **WHEN** un ADMIN envía una enmienda con monto 0
- **THEN** la respuesta es HTTP 400 y no se crea la enmienda

#### Scenario: Historial visible
- **WHEN** un usuario INTERNAL consulta los contratos
- **THEN** ve, por contrato, las enmiendas en orden cronológico con monto anterior, monto nuevo, motivo, autor y fecha

### Requirement: Validación auditable contra el monto vigente
La regla FIN-001 SHALL registrar en su evidencia el monto autorizado usado y el identificador de la enmienda vigente al momento de validar (o `null` si se usó el monto original).

#### Scenario: Validación tras una enmienda
- **WHEN** se valida una factura después de una enmienda que elevó el monto a 120,000.00
- **THEN** la evidencia de FIN-001 contiene `authorized_amount = "120000.00"` y el id de esa enmienda

#### Scenario: Evidencia histórica preservada
- **WHEN** una factura validada contra 100,000.00 no se revalida y luego el contrato se enmienda
- **THEN** su resultado FIN-001 conserva la evidencia con `authorized_amount = "100000.00"`
