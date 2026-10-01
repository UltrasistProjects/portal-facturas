## MODIFIED Requirements

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
