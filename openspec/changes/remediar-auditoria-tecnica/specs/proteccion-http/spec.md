## ADDED Requirements

### Requirement: Cabeceras de seguridad en todas las respuestas
Toda respuesta HTTP, incluidas las de archivos estáticos y las de error, SHALL incluir:
- `Content-Security-Policy: default-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'`
- `X-Frame-Options: DENY`
- `X-Content-Type-Options: nosniff`
- `Referrer-Policy: same-origin`

`Strict-Transport-Security: max-age=31536000` SHALL emitirse sólo en respuestas servidas por HTTPS. El sistema MUST NOT registrar `CORSMiddleware`.

#### Scenario: Cabeceras en una página
- **WHEN** se solicita `GET /login`
- **THEN** la respuesta contiene las cuatro cabeceras con los valores indicados

#### Scenario: Cabeceras en recursos estáticos y errores
- **WHEN** se solicita `GET /static/css/app.css` y una ruta inexistente que devuelve 404
- **THEN** ambas respuestas contienen las mismas cabeceras de seguridad

#### Scenario: HSTS sólo sobre TLS
- **WHEN** la petición llega por HTTP plano
- **THEN** la respuesta no contiene `Strict-Transport-Security`

#### Scenario: Interfaz funcional bajo la CSP
- **WHEN** se cargan las páginas principales (login, dashboard, listado, detalle, documentos, revisión, administración)
- **THEN** ningún recurso propio queda bloqueado por la CSP (no hay scripts ni estilos en línea)

### Requirement: Errores sin fuga de información técnica
Ante una excepción no manejada, el sistema SHALL responder con la página de error genérica y HTTP 500, que incluye el identificador de la petición para soporte, y MUST NOT incluir traceback, rutas del servidor, versiones de librerías ni valores de variables.

#### Scenario: Excepción inesperada
- **WHEN** un endpoint lanza una excepción no prevista
- **THEN** el usuario recibe HTTP 500 con un mensaje genérico y el `request_id`, y el log contiene la traza completa asociada a ese `request_id`

### Requirement: Errores de negocio como respuestas 4xx
Las violaciones de reglas de negocio (transición de estado no permitida, restricción de unicidad violada por una acción del usuario) SHALL traducirse a HTTP 409 con un mensaje comprensible, y MUST NOT producir HTTP 500. El estado persistido SHALL quedar sin cambios.

#### Scenario: Enviar a revisión una factura en borrador
- **WHEN** un usuario autenticado envía `POST /invoices/{id}/submit` con CSRF válido sobre una factura en `DRAFT`
- **THEN** la respuesta es HTTP 409 con el mensaje de transición no permitida y la factura sigue en `DRAFT`

#### Scenario: ClickBalance desde un estado inválido
- **WHEN** un usuario INTERNAL envía `POST /invoices/{id}/clickbalance` sobre una factura en `UNDER_REVIEW`
- **THEN** la respuesta es HTTP 409 y el estado no cambia

#### Scenario: Petición JSON
- **WHEN** una violación de regla de negocio ocurre en una petición con `Accept: application/json`
- **THEN** la respuesta es JSON `{"detail": "<mensaje>"}` con HTTP 409
