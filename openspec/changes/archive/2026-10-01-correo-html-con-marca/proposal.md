## Why

Los correos del portal (credenciales de HU-03, estatus de factura de HU-14 y HU-20, cancelación y el correo de prueba de HU-08) llegan como texto plano: se leen bien pero no llevan la identidad de ULTRASIST y los datos importantes (usuario, contraseña temporal, folio, fecha) se pierden entre los párrafos. El SMTP ya funciona; falta la presentación.

## What Changes

- Cada correo se envía como `multipart/alternative`: el texto plano de siempre y una versión HTML con el logo de ULTRASIST en una tarjeta centrada con estilos en línea.
- La versión HTML se **deriva** del texto ya compuesto: las plantillas de HU-05 siguen siendo de texto plano y el Administrador no edita HTML.
- El logo (`app/static/img/Ultrasistlogo.png`) viaja dentro del mensaje como parte relacionada (`cid:`), para verse sin descargar imágenes remotas.
- Cada valor se escapa; las direcciones `http(s)` se vuelven enlaces; un párrafo de dos o más líneas `Etiqueta: valor` se muestra como bloque de datos.
- La **vista previa** del editor de plantillas (HU-05) muestra el correo tal como se envía, en un `iframe` aislado, con el texto plano plegado debajo. Su respuesta admite en la CSP sólo los hashes de los atributos `style` del correo.

**Fuera de alcance:** plantillas HTML editables por el Administrador, imágenes remotas, modo oscuro y botones de acción por evento.

## Capabilities

### New Capabilities
<!-- Ninguna. -->

### Modified Capabilities
- `notificaciones-correo`: el requirement "Envío de notificaciones" cambia el mensaje de texto plano por `multipart/alternative` con versión HTML de marca, y agrega sus escenarios.
- `plantillas-notificacion`: el requirement "Vista previa con datos de ejemplo" muestra el correo HTML en un `iframe` `srcdoc` y el texto plano plegado.
- `proteccion-http`: el requirement "Cabeceras de seguridad en todas las respuestas" admite, sólo en la vista previa del correo, `style-src 'self' 'unsafe-hashes'` con los hashes de sus atributos `style`.

## Impact

- **PoC** (rutas relativas a `PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress-V1/PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress/`): `app/services/mail_transport.py` (`build_message`), nuevo `app/services/mail_layout.py`, nueva plantilla `app/email_templates/layout.html`, `app/core/middleware.py` (CSP con hashes de estilo), `app/routers/admin.py` y `app/templates/admin/notification_template_edit.html` (vista previa), `app/static/css/app.css`, `app/static/js/app.js` (altura del iframe), `README.md` y las pruebas que leen el cuerpo del correo.
- **Specs:** `notificaciones-correo`, `plantillas-notificacion` y `proteccion-http` al archivar.
- **Esquema y dependencias:** sin cambios (Jinja2 ya es dependencia directa).
