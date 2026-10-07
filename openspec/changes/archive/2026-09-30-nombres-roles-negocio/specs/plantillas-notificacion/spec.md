## MODIFIED Requirements

### Requirement: Configuración exclusiva del Administrador
Las rutas `GET /admin/notification-templates`, `GET /admin/notification-templates/{codigo}`, `POST /admin/notification-templates/{codigo}/preview` y `POST /admin/notification-templates/{codigo}` SHALL estar disponibles únicamente para el rol `Administrador`. Las peticiones `POST` MUST exigir un token CSRF válido. El menú Administración SHALL mostrar la opción "Plantillas de correo" sólo al rol `Administrador`.

#### Scenario: PMO sin acceso
- **WHEN** un usuario con rol `PMO` solicita el listado, la edición o la vista previa, o envía un guardado
- **THEN** la respuesta es HTTP 403 y ninguna plantilla cambia

#### Scenario: Proveedor sin acceso
- **WHEN** un usuario con rol `Proveedor` solicita el listado, la edición o la vista previa, o envía un guardado
- **THEN** la respuesta es HTTP 403 y ninguna plantilla cambia

#### Scenario: Guardado sin token CSRF
- **WHEN** un Administrador envía `POST /admin/notification-templates/INVOICE_REJECTED` sin token CSRF o con uno inválido
- **THEN** la respuesta es HTTP 403 y la plantilla no cambia

#### Scenario: Opción en el menú
- **WHEN** un Administrador y un usuario `PMO` abren el tablero
- **THEN** el menú del Administrador incluye "Plantillas de correo" y el del usuario `PMO` no
