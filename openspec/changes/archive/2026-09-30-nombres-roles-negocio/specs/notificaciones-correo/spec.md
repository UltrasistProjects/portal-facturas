## MODIFIED Requirements

### Requirement: Configuración exclusiva del Administrador
Las rutas `GET /admin/notifications`, `POST /admin/notifications` y `POST /admin/notifications/test` SHALL estar disponibles únicamente para el rol `Administrador`. Las peticiones `POST` MUST exigir un token CSRF válido. El menú Administración SHALL mostrar la opción "Notificaciones" sólo al rol `Administrador`. La página MUST NOT usar scripts ni estilos en línea.

#### Scenario: PMO sin acceso
- **WHEN** un usuario con rol `PMO` solicita la pantalla, envía un guardado o pide un correo de prueba
- **THEN** la respuesta es HTTP 403, la configuración no cambia y no se envía ningún correo

#### Scenario: Proveedor sin acceso
- **WHEN** un usuario con rol `Proveedor` solicita la pantalla, envía un guardado o pide un correo de prueba
- **THEN** la respuesta es HTTP 403, la configuración no cambia y no se envía ningún correo

#### Scenario: Guardado sin token CSRF
- **WHEN** un Administrador envía `POST /admin/notifications` sin token CSRF o con uno inválido
- **THEN** la respuesta es HTTP 403 y la configuración no cambia

#### Scenario: Opción en el menú
- **WHEN** un Administrador y un usuario `PMO` abren el tablero
- **THEN** el menú del Administrador incluye "Notificaciones" y el del usuario `PMO` no
