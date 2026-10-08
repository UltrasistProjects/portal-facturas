## MODIFIED Requirements

### Requirement: Campos de auditoría en contratos
La tabla `contracts` SHALL registrar `created_at`, `created_by`, `updated_at` y `updated_by`. Los valores se asignan automáticamente en el alta y en cada modificación.

#### Scenario: Alta de contrato
- **WHEN** un ADMIN crea un contrato
- **THEN** el contrato guarda `created_at` en UTC, `created_by` con el id del ADMIN, y `updated_at`/`updated_by` con los mismos valores

#### Scenario: Modificación de contrato
- **WHEN** un ADMIN registra una enmienda del monto autorizado de un contrato
- **THEN** `updated_at` avanza a la fecha de la enmienda y `updated_by` toma el id de ese ADMIN, sin alterar `created_at` ni `created_by`
