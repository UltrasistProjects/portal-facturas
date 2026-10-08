> Las rutas de la PoC son relativas a `PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress-V1/PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress/`.

## 1. Correo HTML

- [x] 1.1 `app/services/mail_layout.py`: bloques del cuerpo (párrafos, enlaces y datos `Etiqueta: valor`) y render con Jinja2 `autoescape` (D1, D4).
- [x] 1.2 `app/email_templates/layout.html`: tarjeta centrada de 600 px con franja de marca, logo, asunto como título y estilos en línea (D3).
- [x] 1.3 `mail_transport.build_message`: alternativa HTML y logo como parte relacionada `cid:` (D2).
- [x] 1.4 `README.md`: el envío ya no es sólo texto plano.

## 2. Vista previa del editor de plantillas

- [x] 2.1 `mail_layout.render_preview` (logo como `data:` URI) y `style_hashes` (D5).
- [x] 2.2 `content_security_policy()` con `style_hashes` opcionales y `content_security_policy_with_styles()`; el middleware respeta la CSP que trae la respuesta.
- [x] 2.3 `POST /admin/notification-templates/{codigo}/preview`: `iframe` `srcdoc` con `sandbox="allow-same-origin"`, texto plano en `<details>` y CSP con los hashes.
- [x] 2.4 `app.css` (marco) y `app.js` (altura del marco); `README.md` (vista previa y excepción de la CSP).
- [x] 2.5 Verificación en Chromium con la respuesta real: el correo se ve con estilos y la página no cambia frente a la CSP base.

## 3. Pruebas

- [x] 3.1 Las pruebas que leen el cuerpo usan la parte `text/plain` (`get_body(("plain",))`).
- [x] 3.2 `tests/test_notificaciones_correo.py`: estructura `multipart`, logo referenciado por su `Content-ID`, valores escapados, enlaces y bloque de datos.
- [x] 3.3 `tests/test_plantillas_notificacion.py` y `tests/test_cabeceras.py`: `srcdoc` igual al correo, valores escapados, CSP con exactamente los hashes del correo y sin `'unsafe-inline'`, editor con la CSP base, hashes conocidos.
- [x] 3.4 `pytest`, `ruff check` y `ruff format --check` en verde.
- [x] 3.5 `openspec validate correo-html-con-marca --strict` sin errores.
