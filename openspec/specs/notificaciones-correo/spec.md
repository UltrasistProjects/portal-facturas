# notificaciones-correo Specification

## Purpose
Destinatarios y envío de las notificaciones por correo (HU-08, RF-13): acceso exclusivo del Administrador, buzón "Recepción de Facturas", copias por evento, validación de las listas, guardado con control de edición concurrente, destinatarios de cada evento, servicio de envío, bitácora de envíos, correo de prueba, datos del transporte en solo lectura y auditoría.
## Requirements
### Requirement: Configuración exclusiva del Administrador
Las rutas `GET /admin/notifications`, `POST /admin/notifications` y `POST /admin/notifications/test` SHALL estar disponibles únicamente para el rol `ADMIN`. Las peticiones `POST` MUST exigir un token CSRF válido. El menú Administración SHALL mostrar la opción "Notificaciones" sólo al rol `ADMIN`. La página MUST NOT usar scripts ni estilos en línea.

#### Scenario: PMO sin acceso
- **WHEN** un usuario con rol `INTERNAL` solicita la pantalla, envía un guardado o pide un correo de prueba
- **THEN** la respuesta es HTTP 403, la configuración no cambia y no se envía ningún correo

#### Scenario: Proveedor sin acceso
- **WHEN** un usuario con rol `PROVIDER` solicita la pantalla, envía un guardado o pide un correo de prueba
- **THEN** la respuesta es HTTP 403, la configuración no cambia y no se envía ningún correo

#### Scenario: Guardado sin token CSRF
- **WHEN** un Administrador envía `POST /admin/notifications` sin token CSRF o con uno inválido
- **THEN** la respuesta es HTTP 403 y la configuración no cambia

#### Scenario: Opción en el menú
- **WHEN** un Administrador y un usuario `INTERNAL` abren el tablero
- **THEN** el menú del Administrador incluye "Notificaciones" y el del usuario `INTERNAL` no

### Requirement: Buzón "Recepción de Facturas"
El sistema SHALL mantener el buzón "Recepción de Facturas" (`INVOICE_RECEPTION`) con una lista de 1 a 10 direcciones de correo. Desde la instalación SHALL contener `recepcionfacturas@ultrasist.com.mx`. El Administrador SHALL poder reemplazar la lista desde `/admin/notifications`. La interfaz MUST NOT permitir crear ni eliminar buzones.

#### Scenario: Instalación nueva
- **WHEN** se ejecuta `alembic upgrade head` sobre una base vacía
- **THEN** el buzón "Recepción de Facturas" existe con la única dirección `recepcionfacturas@ultrasist.com.mx`

#### Scenario: Cambio del buzón
- **WHEN** el Administrador guarda el buzón con "facturas@ultrasist.com.mx" y "cxp@ultrasist.com.mx"
- **THEN** la respuesta redirige a `/admin/notifications` con el aviso "Configuración guardada" y el buzón queda con esas dos direcciones en ese orden

#### Scenario: Buzón vacío
- **WHEN** el Administrador guarda el buzón sin ninguna dirección
- **THEN** la respuesta es HTTP 400 con el error "Recepción de Facturas: indique al menos un correo" y la configuración no cambia

### Requirement: Copias por evento
Cada evento de estatus de factura (Autorizada, Rechazada, Observaciones y Cancelada) SHALL tener una lista de 0 a 10 direcciones que reciben copia (`Cc`) de su correo, además del destinatario principal. Desde la instalación las cuatro listas SHALL estar vacías. La pantalla SHALL mostrar, por cada evento, su destinatario principal en solo lectura y su lista de copias editable.

#### Scenario: Copias iniciales
- **WHEN** el Administrador abre `/admin/notifications` en una instalación nueva
- **THEN** ve los eventos Autorizada, Rechazada, Observaciones y Cancelada, con los destinatarios principales "Recepción de Facturas", "Proveedor (correo del catálogo)", "Proveedor (correo del catálogo)" y "Recepción de Facturas", y sin copias

#### Scenario: Copia agregada
- **WHEN** el Administrador guarda "pmo@ultrasist.com.mx" como copia del evento Rechazada
- **THEN** la lista de copias de Rechazada contiene esa dirección y las de los demás eventos no cambian

### Requirement: Validación de las listas de correos
Al guardar, cada lista SHALL normalizarse: las direcciones se separan por saltos de línea, comas o punto y coma; se recortan los espacios de los extremos; se descartan las vacías; se convierten a minúsculas y se eliminan las repetidas, conservando el orden de la primera aparición. Después, cada dirección SHALL ser un correo válido de hasta 254 caracteres y cada lista SHALL respetar su número de direcciones. Si hay errores, la respuesta SHALL ser HTTP 400 con todos los errores juntos, cada uno con la forma "<Lista>: <mensaje>", y el formulario SHALL conservar lo capturado. Un guardado con errores MUST NOT cambiar ninguna lista.

#### Scenario: Normalización
- **WHEN** el Administrador guarda el buzón con " Facturas@Ultrasist.com.mx ; cxp@ultrasist.com.mx,facturas@ultrasist.com.mx "
- **THEN** el buzón queda con "facturas@ultrasist.com.mx" y "cxp@ultrasist.com.mx"

#### Scenario: Dirección inválida
- **WHEN** el Administrador guarda "recepcion@" como copia del evento Autorizada
- **THEN** la respuesta es HTTP 400 con el error "Copias de Autorizada: «recepcion@» no es un correo válido" y ninguna lista cambia

#### Scenario: Demasiadas direcciones
- **WHEN** el Administrador guarda 11 direcciones distintas en el buzón
- **THEN** la respuesta es HTTP 400 con el error "Recepción de Facturas: admite hasta 10 correos"

#### Scenario: Varios errores
- **WHEN** el Administrador guarda el buzón vacío y "x@" como copia de Cancelada
- **THEN** la respuesta es HTTP 400 y muestra los dos errores, y el formulario conserva "x@" en las copias de Cancelada

### Requirement: Guardado con control de edición concurrente
La pantalla SHALL enviar la huella `config_version` de la configuración que muestra: el SHA-256 del buzón y de todas las listas de copias. El guardado SHALL tomar un bloqueo consultivo de transacción y comparar la huella antes de validar. Si la huella no coincide, la respuesta SHALL ser HTTP 409 con el mensaje "La configuración cambió mientras la editaba. Recargue la página." y nada se guarda. Un guardado sin cambios SHALL redirigir con el aviso "Sin cambios" y MUST NOT escribir ni auditar.

#### Scenario: Edición concurrente
- **WHEN** dos Administradores abren la pantalla, el primero guarda un cambio y el segundo guarda después con la huella anterior
- **THEN** el segundo recibe HTTP 409 con el mensaje de edición concurrente y la configuración conserva el cambio del primero

#### Scenario: Sin cambios
- **WHEN** el Administrador guarda la configuración sin modificarla
- **THEN** la respuesta redirige con el aviso "Sin cambios" y no se agrega ningún registro de auditoría

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

### Requirement: Envío de notificaciones
El sistema SHALL ofrecer un servicio de envío para las HU que notifican. El servicio recibe el evento, los valores de las variables de su plantilla, el correo del proveedor si el evento lo requiere, la entidad relacionada y el usuario que origina el envío. El servicio:
- SHALL resolver los destinatarios del evento y componer el correo con la plantilla vigente del evento;
- SHALL enviar un mensaje de texto plano UTF-8 con `From` (`MAIL_FROM`), `To`, `Cc` si hay copias, `Subject`, `Date`, `Message-ID` y `Auto-Submitted: auto-generated`;
- SHALL registrar el envío en la bitácora y confirmar ese registro;
- ante un error del servidor de correo, o si rechaza a algún destinatario, SHALL registrar el envío como fallido y devolverlo sin propagar la excepción;
- SHALL llamarse después de confirmar la transacción de negocio, de modo que un correo fallido no la revierte.

#### Scenario: Envío al buzón con el transporte de archivo
- **WHEN** con `MAIL_BACKEND=file` se envía el correo de Autorizada de la factura "A-1024" del proveedor "Servicios Digitales del Norte SA de CV" por `$116,000.00 MXN`
- **THEN** el buzón de salida contiene un archivo `.eml` con `To: recepcionfacturas@ultrasist.com.mx`, el asunto "Factura A-1024 autorizada para pago", `Content-Type: text/plain; charset="utf-8"` y el cuerpo compuesto, y la bitácora registra el envío como `SENT`

#### Scenario: Servidor de correo caído
- **WHEN** el transporte SMTP no puede conectarse al servidor y se envía un correo de Rechazada
- **THEN** el servicio no lanza una excepción, devuelve el envío con resultado `FAILED` y la bitácora guarda el tipo y el mensaje técnico del error

#### Scenario: Transporte SMTP con STARTTLS
- **WHEN** `MAIL_BACKEND=smtp`, `SMTP_SECURITY=starttls` y hay `SMTP_USERNAME`, y se envía un correo
- **THEN** el transporte se conecta a `SMTP_HOST:SMTP_PORT`, ejecuta STARTTLS con verificación del certificado antes de autenticarse, inicia sesión y envía el mensaje

### Requirement: Bitácora de envíos
Cada intento de envío SHALL quedar registrado con:
- el evento, o ninguno si es el correo de prueba;
- el resultado (`SENT` o `FAILED`) y, si falló, el error técnico de hasta 300 caracteres;
- las direcciones de "Para" y de "Cc";
- el transporte (`smtp` o `file`) y el `Message-ID`;
- la entidad relacionada y su identificador, si los hay;
- el usuario que lo originó y la fecha.

La bitácora MUST NOT guardar el asunto ni el cuerpo del correo. `/admin/notifications` SHALL mostrar todos los envíos, paginados de 25 en 25 (spec `listados-paginados`), del más reciente al más antiguo, con fecha, evento ("Prueba" para el correo de prueba), destinatarios, resultado y error.

#### Scenario: Envío registrado sin contenido
- **WHEN** se envía el correo de Rechazada de una factura
- **THEN** existe un registro en la bitácora con el evento `INVOICE_REJECTED`, la entidad "Invoice" y su id, y ninguna columna contiene el asunto ni el cuerpo

#### Scenario: Envíos en la pantalla
- **WHEN** hay 30 envíos registrados y el Administrador abre `/admin/notifications`
- **THEN** la bitácora muestra los 25 más recientes, empezando por el último, y en la página 2 los 5 restantes

### Requirement: Correo de prueba
El Administrador SHALL poder enviar un correo de prueba a una dirección que indica, desde `POST /admin/notifications/test`. La dirección SHALL validarse como las de las listas. El correo SHALL tener el asunto "Correo de prueba del Portal de Proveedores ULTRASIST" y un cuerpo fijo con el nombre del Administrador y la fecha y hora en la zona de negocio. El envío SHALL registrarse en la bitácora sin evento. La pantalla SHALL indicar si el correo se envió o si falló.

#### Scenario: Prueba exitosa
- **WHEN** con `MAIL_BACKEND=file` el Administrador envía un correo de prueba a "admin@ultrasist.com.mx"
- **THEN** la pantalla muestra "Correo de prueba enviado a admin@ultrasist.com.mx", el buzón de salida contiene el correo y la bitácora registra un envío `SENT` sin evento

#### Scenario: Prueba fallida
- **WHEN** el servidor SMTP rechaza la conexión y el Administrador envía un correo de prueba
- **THEN** la pantalla muestra "No se pudo enviar el correo de prueba" con el error técnico, y la bitácora registra un envío `FAILED`

#### Scenario: Dirección de prueba inválida
- **WHEN** el Administrador pide un correo de prueba a "admin@"
- **THEN** la respuesta es HTTP 400 con el error "Correo de prueba: «admin@» no es un correo válido" y no se envía nada

### Requirement: Datos del transporte en solo lectura
`/admin/notifications` SHALL mostrar el transporte vigente: "SMTP" con el servidor, el puerto y el cifrado, o "Archivo (no se envían correos)" con el directorio de salida, y el remitente. La página MUST NOT mostrar el usuario ni la contraseña SMTP.

#### Scenario: Transporte de archivo en desarrollo
- **WHEN** con `MAIL_BACKEND=file` el Administrador abre la pantalla
- **THEN** ve "Archivo (no se envían correos)" y el remitente, y la página no contiene la contraseña SMTP

### Requirement: Auditoría de cambios de destinatarios
Cada guardado que cambia la configuración SHALL generar un registro de auditoría `NOTIFICATION_RECIPIENTS_UPDATED` con el Administrador que guardó, la entidad `NotificationRecipients`, y en `old_value` y `new_value` sólo las listas que cambiaron, identificadas por `INVOICE_RECEPTION` o por el código del evento. Los guardados rechazados (HTTP 400 o 409), los guardados sin cambios y los correos de prueba MUST NOT generar registros de auditoría.

#### Scenario: Auditoría de un cambio
- **WHEN** el Administrador cambia sólo las copias de Cancelada de ninguna a "cxp@ultrasist.com.mx"
- **THEN** `audit_logs` contiene un registro `NOTIFICATION_RECIPIENTS_UPDATED` con su `user_id`, `old_value = {"INVOICE_CANCELLED": []}` y `new_value = {"INVOICE_CANCELLED": ["cxp@ultrasist.com.mx"]}`

#### Scenario: Acciones sin auditoría
- **WHEN** el Administrador recibe un HTTP 400, recibe un HTTP 409, guarda sin cambios y envía un correo de prueba
- **THEN** no se agrega ningún registro a `audit_logs`

