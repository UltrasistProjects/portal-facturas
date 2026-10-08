## Why

El portal todavía usa la interfaz nativa del navegador en dos puntos: el `window.confirm` de "Autorizar" en el panel de decisión del PMO (`review_decision.js`) y las burbujas de validación de HTML5 en unos 50 campos de 14 plantillas. Ambas se ven distintas en cada navegador, no siguen el estilo del portal y, en el caso de la carga de documentos, fallan en silencio: el `input type=file` obligatorio está oculto dentro de la zona de arrastre, así que el navegador bloquea el envío sin mostrar ningún mensaje. El resto del portal ya resuelve las confirmaciones con modales de Bootstrap (autorización masiva y carga masiva de proveedores); falta llevar el mismo patrón a estos dos puntos.

Es sólo una mejora de presentación: las reglas, los flujos, las rutas y el backend no cambian.

## What Changes

- **Confirmación de "Autorizar" en un modal del portal.** El `window.confirm` del panel de decisión se reemplaza por un modal de Bootstrap con el mismo texto (`data-confirm`), siguiendo el patrón de `supplier_authorize.js`. El flujo es el mismo: "Cancelar", cerrar o Esc no envían nada; "Autorizar" envía la decisión `ACCEPTED` igual que antes.
- **Errores de validación junto al campo.** Un script común toma la presentación de la validación de los formularios con JavaScript: el navegador sigue evaluando las mismas reglas (los atributos `required`, `pattern`, `minlength`, `maxlength`, `min`, `step` y `type` que ya tienen los campos), pero el mensaje se pinta en español debajo del campo con los estilos de Bootstrap (`is-invalid` / `invalid-feedback`), en lugar de la burbuja nativa:
  - al enviar, se marcan todos los campos inválidos y el foco va al primero; el envío no procede, como hoy;
  - el campo se valida cuando el usuario lo deja con un valor cambiado; desde que muestra un error, el mensaje se actualiza con cada tecla y desaparece cuando el valor es válido;
  - la zona de arrastre de documentos muestra su error, que hoy no aparece.
- **Sin JavaScript nada cambia:** los formularios conservan la validación nativa, como en el resto del portal ("sin JavaScript el formulario funciona igual").

**Fuera de alcance:**
- **Toasts:** no hay `alert()` ni `prompt()` en el proyecto, así que no hay mensajes nativos que llevar a un toast. Los avisos del servidor (`notice`, `error`, resultado de correos) ya son alertas de Bootstrap dentro de la página, no interfaz nativa, y algunos no deben desaparecer solos (la contraseña temporal que se muestra una sola vez, los errores con enlace "Recargar"). No se cambian.
- Los errores que valida el servidor (p. ej. "Capture las observaciones", montos del Invoice, reglas) siguen mostrándose como hoy, en la alerta de la página: llevarlos junto a cada campo exigiría cambiar las respuestas del backend.
- Reglas nuevas o distintas en el navegador, cambios de textos de negocio, y el formulario de inicio de sesión (lo pinta Keycloak).

## Capabilities

### New Capabilities
- `interfaz-usuario`: confirmaciones en modales del portal en lugar de diálogos nativos, y presentación de los errores de validación de los formularios junto a cada campo, con las mismas reglas que ya declaran.

### Modified Capabilities
<!-- Ninguna: "pedir confirmación antes de Autorizar" (revision-pmo) sigue igual; sólo cambia cómo se pide. -->

## Impact

- **JavaScript:**
  - nuevo `app/static/js/form_validation.js` (cargado en `base.html` para todas las páginas);
  - `app/static/js/review_decision.js`: modal en lugar de `window.confirm`.
- **Plantillas:**
  - `base.html`: carga del script común;
  - `invoices/detail.html`: marcado del modal de confirmación de "Autorizar";
  - atributos de presentación (`data-error-*`) sólo donde el mensaje genérico no basta, p. ej. el formato `MM/AAAA` del periodo de servicio en `invoices/new.html`.
- **CSS:** `app/static/css/app.css`: estado inválido de la zona de arrastre y acomodo del mensaje en los formularios en línea.
- **Backend, rutas, esquema, permisos y autenticación:** sin cambios.
- **Dependencias:** ninguna nueva; se reutilizan Modal y los estilos de validación de Bootstrap 5.3.3, ya incluidos en `app/static/vendor`.
- **CSP:** sin cambios; todo el código va en archivos estáticos propios (la CSP no admite scripts en línea).
- **Pruebas:** nueva prueba que verifica que no quedan `alert`, `confirm` ni `prompt` nativos en el código del portal y que el detalle del PMO incluye el modal; la suite actual debe seguir pasando.
- **Documentación:** `README.md`, la nota de "Autorizar pide confirmación" y la validación de formularios.
