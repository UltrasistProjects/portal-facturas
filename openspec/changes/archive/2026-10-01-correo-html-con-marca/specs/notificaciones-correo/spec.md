## MODIFIED Requirements

### Requirement: Envío de notificaciones
El sistema SHALL ofrecer un servicio de envío para las HU que notifican. El servicio recibe el evento, los valores de las variables de su plantilla, el correo del proveedor si el evento lo requiere, la entidad relacionada y el usuario que origina el envío. El servicio:
- SHALL resolver los destinatarios del evento y componer el correo con la plantilla vigente del evento;
- SHALL enviar un mensaje `multipart/alternative` UTF-8 con `From` (`MAIL_FROM`), `To`, `Cc` si hay copias, `Subject`, `Date`, `Message-ID` y `Auto-Submitted: auto-generated`, que contiene el cuerpo compuesto en texto plano y su versión HTML;
- SHALL registrar el envío en la bitácora y confirmar ese registro;
- ante un error del servidor de correo, o si rechaza a algún destinatario, SHALL registrar el envío como fallido y devolverlo sin propagar la excepción;
- SHALL llamarse después de confirmar la transacción de negocio, de modo que un correo fallido no la revierte.

La versión HTML SHALL derivarse del cuerpo compuesto, sin plantillas HTML editables: una tarjeta centrada con el logo de ULTRASIST, el asunto como título y el cuerpo en párrafos, con los estilos en línea. El logo SHALL viajar dentro del mensaje como parte relacionada referenciada por `cid:`. Cada valor del cuerpo MUST escaparse; las direcciones `http://` y `https://` SHALL mostrarse como enlaces y ningún otro esquema; un párrafo de dos o más líneas `Etiqueta: valor` SHALL mostrarse como bloque de datos.

#### Scenario: Envío al buzón con el transporte de archivo
- **WHEN** con `MAIL_BACKEND=file` se envía el correo de Autorizada de la factura "A-1024" del proveedor "Servicios Digitales del Norte SA de CV" por `$116,000.00 MXN`
- **THEN** el buzón de salida contiene un archivo `.eml` `multipart/alternative` con `To: recepcionfacturas@ultrasist.com.mx`, el asunto "Factura A-1024 autorizada para pago" y una parte `text/plain; charset="utf-8"` con el cuerpo compuesto, y la bitácora registra el envío como `SENT`

#### Scenario: Versión HTML con el logo
- **WHEN** se envía el correo de Autorizada de la factura "A-1024"
- **THEN** el mensaje tiene una parte `multipart/related` con el HTML y el logo PNG `inline`, el HTML referencia el logo por su `Content-ID`, muestra el asunto como título y muestra "Folio interno" y "FAC-2026-00042" en un bloque de datos

#### Scenario: Valores escapados en la versión HTML
- **WHEN** se envía un correo de Rechazada con las observaciones `<b>Urgente</b>`
- **THEN** la parte de texto plano contiene `<b>Urgente</b>` tal cual y el HTML contiene `&lt;b&gt;Urgente&lt;/b&gt;` y ninguna etiqueta `<b>`

#### Scenario: Servidor de correo caído
- **WHEN** el transporte SMTP no puede conectarse al servidor y se envía un correo de Rechazada
- **THEN** el servicio no lanza una excepción, devuelve el envío con resultado `FAILED` y la bitácora guarda el tipo y el mensaje técnico del error

#### Scenario: Transporte SMTP con STARTTLS
- **WHEN** `MAIL_BACKEND=smtp`, `SMTP_SECURITY=starttls` y hay `SMTP_USERNAME`, y se envía un correo
- **THEN** el transporte se conecta a `SMTP_HOST:SMTP_PORT`, ejecuta STARTTLS con verificación del certificado antes de autenticarse, inicia sesión y envía el mensaje
