## MODIFIED Requirements

### Requirement: Administración exclusiva del Administrador
Las rutas `/admin/catalogs*` SHALL estar disponibles únicamente para el rol `Administrador`, y sus `POST` MUST exigir un token CSRF válido. El menú Administración SHALL mostrar la opción "Catálogos" sólo al rol `Administrador`. Un catálogo desconocido en la ruta SHALL responder HTTP 404. Las páginas MUST NOT usar scripts ni estilos en línea.

#### Scenario: PMO sin acceso
- **WHEN** un usuario `PMO` solicita `/admin/catalogs`, la página de un catálogo, la plantilla, o envía un alta, una edición, un cambio de estado o una carga
- **THEN** la respuesta es HTTP 403 y ningún catálogo cambia

#### Scenario: Catálogo inexistente
- **WHEN** el Administrador solicita `/admin/catalogs/COUNTRY`
- **THEN** la respuesta es HTTP 404
