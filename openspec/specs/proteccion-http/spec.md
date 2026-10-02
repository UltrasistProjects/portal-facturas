# proteccion-http Specification

## Purpose
Cabeceras de seguridad en todas las respuestas y manejo de errores sin fuga de trazas, con los errores de negocio traducidos a códigos HTTP 4xx.
## Requirements
### Requirement: Cabeceras de seguridad en todas las respuestas
Toda respuesta HTTP, incluidas las de archivos estáticos, las de error y las redirecciones, SHALL incluir:
- `Content-Security-Policy: default-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'self'; form-action 'self' <origen de Keycloak>; frame-ancestors 'none'`. El origen de Keycloak es el esquema, el host y el puerto de `KEYCLOAK_SERVER_URL`, y se necesita porque el navegador aplica `form-action` a la redirección que sigue a `POST /logout`.
- `X-Frame-Options: DENY`
- `X-Content-Type-Options: nosniff`
- `Referrer-Policy: same-origin`

La única excepción a esa CSP es la respuesta de la vista previa de una plantilla de correo (`POST /admin/notification-templates/{codigo}/preview` válida): SHALL agregar `style-src 'self' 'unsafe-hashes'` seguido del hash `sha256` de cada atributo `style` distinto del correo, porque el `iframe` `srcdoc` hereda la CSP de la página. Esa respuesta MUST NOT incluir `'unsafe-inline'` y conserva las demás directivas y cabeceras.

`Strict-Transport-Security: max-age=31536000` SHALL emitirse sólo en respuestas servidas por HTTPS. El sistema MUST NOT registrar `CORSMiddleware`.

#### Scenario: Cabeceras en una redirección
- **WHEN** se solicita `GET /login`
- **THEN** la redirección a Keycloak contiene las cuatro cabeceras con los valores indicados

#### Scenario: Cabeceras en recursos estáticos y errores
- **WHEN** se solicita `GET /static/css/app.css` y una ruta inexistente que devuelve 404
- **THEN** ambas respuestas contienen las mismas cabeceras de seguridad

#### Scenario: HSTS sólo sobre TLS
- **WHEN** la petición llega por HTTP plano
- **THEN** la respuesta no contiene `Strict-Transport-Security`

#### Scenario: Logout permitido por la CSP
- **WHEN** con `KEYCLOAK_SERVER_URL=http://127.0.0.1:58080` se solicita cualquier página
- **THEN** su `form-action` es `'self' http://127.0.0.1:58080` y no incluye otros orígenes

#### Scenario: Interfaz funcional bajo la CSP
- **WHEN** se cargan las páginas principales (dashboard, listado, detalle, documentos, revisión, administración)
- **THEN** ningún recurso propio queda bloqueado por la CSP (no hay scripts ni estilos en línea)

#### Scenario: CSP de la vista previa del correo
- **WHEN** el Administrador pide una vista previa válida y después abre el editor de la misma plantilla
- **THEN** la CSP de la vista previa es la del portal más `style-src 'self' 'unsafe-hashes'` con exactamente los hashes de los atributos `style` del correo, sin `'unsafe-inline'`, y la del editor es la CSP del portal sin cambios

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

#### Scenario: Decisión sobre una factura ya revisada
- **WHEN** un usuario PMO envía una decisión sobre una factura "Autorizada"
- **THEN** la respuesta es HTTP 409 con "La factura ya fue revisada" y el estado no cambia

#### Scenario: Petición JSON
- **WHEN** una violación de regla de negocio ocurre en una petición con `Accept: application/json`
- **THEN** la respuesta es JSON `{"detail": "<mensaje>"}` con HTTP 409

