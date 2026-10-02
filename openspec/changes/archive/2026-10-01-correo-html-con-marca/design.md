## Context

`mail_transport.build_message` arma un `EmailMessage` de texto plano (D7 de HU-08) que usan `notification_service.deliver` para todos los eventos y el correo de prueba. Las plantillas de HU-05 son texto con `{{variables}}` que el Administrador edita; sus valores incluyen texto capturado por usuarios (razón social, observaciones del PMO).

## Goals / Non-Goals

**Goals:** correos con identidad visual de ULTRASIST que se vean bien en Gmail, Outlook y móviles, sin cambiar las plantillas ni su edición.

**Non-Goals:** HTML editable, seguimiento de aperturas, imágenes remotas.

## Decisions

### D1. HTML derivado del texto, con el texto plano como alternativa
`build_message` agrega una alternativa HTML generada a partir del cuerpo ya compuesto. Los clientes sin HTML, y las pruebas que leen el cuerpo, siguen usando la parte `text/plain`.
*Alternativa:* plantillas HTML por evento. Se descarta: duplicaría HU-05 y obligaría al Administrador a editar HTML.

### D2. Logo incrustado por `cid:`
La parte HTML es `multipart/related` con el PNG del logo (`Content-Disposition: inline`). Una URL remota no se vería en desarrollo (`127.0.0.1`) y los clientes bloquean imágenes remotas por omisión; `data:` no lo muestra Gmail.

### D3. Estilos en línea y plantilla fuera de `app/templates`
Los clientes de correo descartan `<style>`, así que la plantilla usa tablas y atributos `style`. Vive en `app/email_templates/` porque `app/templates` son páginas servidas con la CSP del portal, que prohíbe estilos en línea (`test_plantillas_sin_scripts_ni_estilos_en_linea`).

### D4. Escape y estructura mínima
Jinja2 con `autoescape` escapa cada valor. Sólo se reconocen dos estructuras: direcciones `http(s)://` (otro esquema queda como texto) y párrafos de dos o más líneas `Etiqueta: valor` (etiqueta de hasta 40 caracteres), que se muestran apilados, etiqueta arriba y valor abajo, para que una contraseña no se parta en pantallas angostas.

### D5. Vista previa: el mismo HTML en un iframe `srcdoc`
El editor muestra exactamente el HTML que se envía, con el logo como `data:` URI (la vista previa no tiene partes `cid:`). Va en un `iframe` `srcdoc` con `sandbox="allow-same-origin"`: sin `allow-scripts` nada se ejecuta en el correo, y `allow-same-origin` sólo deja que `app.js` ajuste la altura del marco. Sin JavaScript el marco conserva una altura fija con desplazamiento, así que se cumple "funciona sin JavaScript". El texto plano queda debajo en un `<details>`.

Un documento `srcdoc` hereda la CSP de la página, y `default-src 'self'` bloquea sus atributos `style` (comprobado en Chromium: el correo sale sin estilos). La respuesta de la vista previa agrega `style-src 'self' 'unsafe-hashes'` con el `sha256` de cada atributo `style` distinto del correo, calculados sobre el HTML que se envía (`mail_layout.style_hashes`). El middleware respeta una CSP que la respuesta ya trae y la construye la misma `content_security_policy()`, así que las demás directivas no cambian. La página del portal no tiene atributos `style` (lo verifica `test_plantillas_sin_scripts_ni_estilos_en_linea`), por lo que los hashes no le habilitan nada más.

*Alternativas descartadas:* `'unsafe-inline'` (abre cualquier estilo en línea de la página); un endpoint GET aparte con su propia CSP (el borrador sin guardar no cabe con seguridad en la URL y obligaría a relajar `frame-ancestors` y `X-Frame-Options`); reproducir el correo con clases de `app.css` (dos diseños que se desalinean).
