## MODIFIED Requirements

### Requirement: Configuración exclusiva del Administrador
`GET /admin/rules` y `POST /admin/rules` SHALL estar disponibles únicamente para el rol `Administrador`; el `POST` MUST exigir un token CSRF válido. El menú Administración SHALL mostrar la opción "Reglas de validación" sólo al rol `Administrador`. La página MUST NOT usar scripts ni estilos en línea.

#### Scenario: PMO sin acceso
- **WHEN** un usuario `PMO` solicita `/admin/rules` o envía un guardado
- **THEN** la respuesta es HTTP 403 y la configuración no cambia

#### Scenario: Proveedor sin acceso
- **WHEN** un usuario `Proveedor` solicita `/admin/rules` o envía un guardado
- **THEN** la respuesta es HTTP 403 y la configuración no cambia

#### Scenario: Guardado sin token CSRF
- **WHEN** un Administrador envía `POST /admin/rules` sin token CSRF o con uno inválido
- **THEN** la respuesta es HTTP 403 y la configuración no cambia
