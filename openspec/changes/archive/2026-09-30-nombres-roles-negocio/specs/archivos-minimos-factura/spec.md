## MODIFIED Requirements

### Requirement: Configuración exclusiva del Administrador
La página `GET /admin/required-documents` y las operaciones `POST /admin/required-documents`, `POST /admin/required-documents/types`, `POST /admin/required-documents/types/{type_id}` y `POST /admin/required-documents/types/{type_id}/status` SHALL estar disponibles únicamente para el rol `Administrador`. Toda operación `POST` MUST exigir un token CSRF válido.

#### Scenario: PMO sin acceso
- **WHEN** un usuario con rol `PMO` solicita la página de configuración o envía cualquiera de sus operaciones
- **THEN** la respuesta es HTTP 403 y la configuración no cambia

#### Scenario: Proveedor sin acceso
- **WHEN** un usuario con rol `Proveedor` solicita la página de configuración o envía cualquiera de sus operaciones
- **THEN** la respuesta es HTTP 403 y la configuración no cambia

#### Scenario: Envío sin token CSRF
- **WHEN** un Administrador envía `POST /admin/required-documents` sin token CSRF o con uno inválido
- **THEN** la respuesta es HTTP 403 y la configuración no cambia
