## MODIFIED Requirements

### Requirement: Copias por evento
Cada evento de factura (Autorizada, Rechazada, Observaciones, Cancelada, Pagada y Complemento de pago adjuntado) SHALL tener una lista de 0 a 10 direcciones que reciben copia (`Cc`) de su correo, además del destinatario principal. Desde la instalación las seis listas SHALL estar vacías. La pantalla SHALL mostrar, por cada evento, su destinatario principal en solo lectura y su lista de copias editable.

#### Scenario: Copias iniciales
- **WHEN** el Administrador abre `/admin/notifications` en una instalación nueva
- **THEN** ve los eventos Autorizada, Rechazada, Observaciones, Cancelada, Pagada y Complemento de pago adjuntado, con los destinatarios principales "Recepción de Facturas con copia al proveedor", "Proveedor (correo del catálogo)", "Proveedor (correo del catálogo)", "Recepción de Facturas", "Proveedor (correo del catálogo)" y "Recepción de Facturas", y sin copias

#### Scenario: Copia agregada
- **WHEN** el Administrador guarda "pmo@ultrasist.com.mx" como copia del evento Rechazada
- **THEN** la lista de copias de Rechazada contiene esa dirección y las de los demás eventos no cambian

#### Scenario: Copia del aviso de pago
- **WHEN** el Administrador guarda "cxp@ultrasist.com.mx" como copia del evento Pagada y el PMO marca una factura como pagada
- **THEN** el correo "Pagada" va al correo del proveedor con "Cc" a "cxp@ultrasist.com.mx"

### Requirement: Destinatarios de cada evento
El sistema SHALL resolver los destinatarios de un correo de evento así:
- Autorizada, Cancelada y Complemento de pago adjuntado: "Para" es la lista del buzón "Recepción de Facturas";
- Autorizada lleva además en "Cc" el correo del proveedor de la factura, que la HU que envía proporciona, antes de la lista de copias del evento; si falta, el correo sale sólo con el buzón y las copias configuradas;
- Rechazada, Observaciones y Pagada: "Para" es el correo del proveedor de la factura, que la HU que envía proporciona; si falta, el envío MUST fallar con un error explícito, sin enviar nada;
- Credenciales de acceso: "Para" es el correo del proveedor autorizado, con la misma regla si falta; este evento MUST NOT llevar copias, porque su correo contiene una contraseña temporal, y la pantalla de Notificaciones no le ofrece lista de copias;
- "Cc" es la lista de copias del evento (en Autorizada, precedida del correo del proveedor), sin las direcciones que ya están en "Para" y sin repetidas.

La configuración SHALL leerse de la base de datos en cada envío, sin caché.

#### Scenario: Evento dirigido al buzón
- **WHEN** el buzón contiene "facturas@ultrasist.com.mx" y "cxp@ultrasist.com.mx", las copias de Autorizada contienen "cxp@ultrasist.com.mx" y "pmo@ultrasist.com.mx", y se resuelven los destinatarios de Autorizada
- **THEN** "Para" es "facturas@ultrasist.com.mx" y "cxp@ultrasist.com.mx", y "Cc" es sólo "pmo@ultrasist.com.mx"

#### Scenario: Autorizada con copia al proveedor
- **WHEN** las copias de Autorizada contienen "pmo@ultrasist.com.mx" y "contacto@proveedor.mx", y se resuelven los destinatarios de Autorizada con el correo del proveedor "Contacto@Proveedor.mx"
- **THEN** "Para" es la lista del buzón "Recepción de Facturas" y "Cc" es "contacto@proveedor.mx" y "pmo@ultrasist.com.mx", sin repetidas

#### Scenario: Cancelada sin copia al proveedor
- **WHEN** se resuelven los destinatarios de Cancelada con el correo del proveedor "contacto@proveedor.mx" y sin copias configuradas
- **THEN** "Para" es la lista del buzón "Recepción de Facturas" y "Cc" está vacío

#### Scenario: Evento dirigido al proveedor
- **WHEN** se resuelven los destinatarios de Rechazada con el correo del proveedor "contacto@proveedor.mx"
- **THEN** "Para" es "contacto@proveedor.mx" y "Cc" es la lista de copias de Rechazada

#### Scenario: Aviso de pago al proveedor
- **WHEN** se resuelven los destinatarios de Pagada con el correo del proveedor "contacto@proveedor.mx"
- **THEN** "Para" es "contacto@proveedor.mx" y "Cc" es la lista de copias de Pagada

#### Scenario: Complemento adjuntado a Recepción
- **WHEN** se resuelven los destinatarios de Complemento de pago adjuntado
- **THEN** "Para" es la lista del buzón "Recepción de Facturas" y "Cc" es la lista de copias de Complemento de pago adjuntado

#### Scenario: Proveedor sin correo
- **WHEN** se pide enviar el correo de Observaciones sin el correo del proveedor
- **THEN** el servicio falla con un error que nombra el correo del proveedor, no se envía nada y no se registra ningún envío

#### Scenario: Credenciales sin copias
- **WHEN** se resuelven los destinatarios de Credenciales de acceso con el correo "contacto@proveedor.mx"
- **THEN** "Para" es "contacto@proveedor.mx", "Cc" está vacío y la pantalla de Notificaciones no muestra copias para ese evento
