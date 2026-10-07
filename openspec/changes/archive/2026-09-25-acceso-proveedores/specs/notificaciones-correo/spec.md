## MODIFIED Requirements

### Requirement: Destinatarios de cada evento
El sistema SHALL resolver los destinatarios de un correo de evento así:
- Autorizada y Cancelada: "Para" es la lista del buzón "Recepción de Facturas";
- Rechazada y Observaciones: "Para" es el correo del proveedor de la factura, que la HU que envía proporciona; si falta, el envío MUST fallar con un error explícito, sin enviar nada;
- Credenciales de acceso: "Para" es el correo del proveedor autorizado, con la misma regla si falta; este evento MUST NOT llevar copias, porque su correo contiene una contraseña temporal, y la pantalla de Notificaciones no le ofrece lista de copias;
- "Cc" es la lista de copias del evento, sin las direcciones que ya están en "Para" y sin repetidas.

La configuración SHALL leerse de la base de datos en cada envío, sin caché.

#### Scenario: Evento dirigido al buzón
- **WHEN** el buzón contiene "facturas@ultrasist.com.mx" y "cxp@ultrasist.com.mx", las copias de Autorizada contienen "cxp@ultrasist.com.mx" y "pmo@ultrasist.com.mx", y se resuelven los destinatarios de Autorizada
- **THEN** "Para" es "facturas@ultrasist.com.mx" y "cxp@ultrasist.com.mx", y "Cc" es sólo "pmo@ultrasist.com.mx"

#### Scenario: Evento dirigido al proveedor
- **WHEN** se resuelven los destinatarios de Rechazada con el correo del proveedor "contacto@proveedor.mx"
- **THEN** "Para" es "contacto@proveedor.mx" y "Cc" es la lista de copias de Rechazada

#### Scenario: Proveedor sin correo
- **WHEN** se pide enviar el correo de Observaciones sin el correo del proveedor
- **THEN** el servicio falla con un error que nombra el correo del proveedor, no se envía nada y no se registra ningún envío

#### Scenario: Credenciales sin copias
- **WHEN** se resuelven los destinatarios de Credenciales de acceso con el correo "contacto@proveedor.mx"
- **THEN** "Para" es "contacto@proveedor.mx", "Cc" está vacío y la pantalla de Notificaciones no muestra copias para ese evento
