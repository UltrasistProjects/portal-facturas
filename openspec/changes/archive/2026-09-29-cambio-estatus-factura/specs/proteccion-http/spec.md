## MODIFIED Requirements

### Requirement: Errores de negocio como respuestas 4xx
Las violaciones de reglas de negocio (transición de estado no permitida, restricción de unicidad violada por una acción del usuario) SHALL traducirse a HTTP 409 con un mensaje comprensible, y MUST NOT producir HTTP 500. El estado persistido SHALL quedar sin cambios.

#### Scenario: Enviar a revisión una factura en borrador
- **WHEN** un usuario autenticado envía `POST /invoices/{id}/submit` con CSRF válido sobre una factura en `DRAFT`
- **THEN** la respuesta es HTTP 409 con el mensaje de transición no permitida y la factura sigue en `DRAFT`

#### Scenario: Decisión sobre una factura ya revisada
- **WHEN** un usuario INTERNAL envía una decisión sobre una factura "Autorizada"
- **THEN** la respuesta es HTTP 409 con "La factura ya fue revisada" y el estado no cambia

#### Scenario: Petición JSON
- **WHEN** una violación de regla de negocio ocurre en una petición con `Accept: application/json`
- **THEN** la respuesta es JSON `{"detail": "<mensaje>"}` con HTTP 409
