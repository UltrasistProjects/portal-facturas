## MODIFIED Requirements

### Requirement: Carga masiva exclusiva del Administrador
La página de carga (`GET /suppliers/import`), la descarga de la plantilla (`GET /suppliers/import/template`) y el procesamiento del archivo (`POST /suppliers/import`) SHALL estar disponibles únicamente para el rol `Administrador`. El procesamiento MUST exigir un token CSRF válido.

#### Scenario: PMO sin acceso
- **WHEN** un usuario con rol `PMO` solicita la página de carga, la plantilla o envía un archivo
- **THEN** la respuesta es HTTP 403 y no se registra ningún proveedor

#### Scenario: Proveedor sin acceso
- **WHEN** un usuario con rol `Proveedor` solicita la página de carga, la plantilla o envía un archivo
- **THEN** la respuesta es HTTP 403 y no se registra ningún proveedor

#### Scenario: Envío sin token CSRF
- **WHEN** un Administrador envía `POST /suppliers/import` sin token CSRF o con uno inválido
- **THEN** la respuesta es HTTP 403 y el archivo no se procesa
