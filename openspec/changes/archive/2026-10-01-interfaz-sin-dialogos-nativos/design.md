## Context

La interfaz es HTML renderizado en el servidor (Jinja2) con JavaScript vanilla por página y Bootstrap 5.3.3 local (`app/static/vendor`). La CSP no admite scripts ni estilos en línea (`tests/test_cabeceras.py` lo verifica sobre todas las plantillas). Cada script sigue la mejora progresiva: "sin JavaScript el formulario funciona igual".

Inventario de lo existente:

| Sistema | Qué hay hoy |
|---|---|
| Diálogos nativos | Uno: `window.confirm(button.dataset.confirm)` en `review_decision.js` ("Autorizar"). No hay `alert` ni `prompt`. |
| Modales | Bootstrap Modal en dos lugares con el mismo patrón: el marcado vive en la plantilla (`suppliers/list.html`, `suppliers/import.html`) y el script lo abre con `new bootstrap.Modal(...)` y pinta los textos con `textContent` (`supplier_authorize.js`, `supplier_import.js`). |
| Toasts | Ninguno. Bootstrap Toast está en el bundle pero no se usa. |
| Mensajes de operación | Alertas de Bootstrap (`.alert`) pintadas por el servidor (`notice`, `error`, `errors`) o por `supplier_import.js`. No son interfaz nativa. |
| Formularios | `.form-grid` / `.field` (label + control + `small.form-text`), `.form-check` para casillas, `label.dropzone` con `input type=file` oculto (`display:none`) en documentos, y formularios en línea (`.catalog-edit-form` en flex, `.amend-form` en grid). |
| Validación | Sólo los atributos HTML5 (51 `required`, `pattern` del periodo, `minlength`/`maxlength`, `min`, `step`, `type=email/number/date/file`) más la validación del servidor. `supplier_form.js` y `review_decision.js` cambian `required`/`disabled` en vivo. Ninguna plantilla usa `novalidate`, `is-invalid` ni `invalid-feedback`. |

Nota: hoy el campo de archivo de `invoices/documents.html` está oculto dentro de la zona de arrastre, así que el navegador bloquea el envío sin mostrar ningún aviso (Chrome sólo escribe en la consola "An invalid form control … is not focusable").

## Goals / Non-Goals

**Goals:**
- Reemplazar el `window.confirm` por un modal de Bootstrap con el mismo flujo.
- Mostrar los errores de validación del navegador junto a cada campo, en español, de forma reactiva, sin burbuja nativa.
- Mismas reglas, mismos bloqueos de envío, mismos datos enviados.

**Non-Goals:**
- Introducir toasts o convertir las alertas del servidor (ver D5).
- Cambiar la presentación de los errores que sólo valida el servidor.
- Reglas nuevas en el navegador, cambios de backend, rutas, esquema, permisos o autenticación.
- Refactorizar los scripts existentes más allá de la línea del `confirm`.

## Decisions

### D1. Reutilizar Bootstrap; ninguna dependencia nueva
El modal usa `bootstrap.Modal` y los errores usan las clases `is-invalid` / `invalid-feedback` de Bootstrap, que ya pintan el borde, el icono y el texto en rojo (`.is-invalid ~ .invalid-feedback { display: block }`). El icono es un SVG en `data:`, ya admitido por `img-src`.

*Alternativas:* `<dialog>` nativo (otro patrón distinto a los dos modales existentes); librerías como SweetAlert2 o Pristine (dependencia nueva sin necesidad).

### D2. El modal de "Autorizar" vuelve a pulsar el mismo botón
El marcado del modal va en `invoices/detail.html`, dentro de `{% if can_decide %}`, como en `suppliers/list.html`: título "Autorizar factura", cuerpo vacío que el script llena con `textContent` desde `data-confirm`, "Cancelar" (`btn-light`, `data-bs-dismiss`) y "Autorizar" (`btn-success`).

`review_decision.js` cambia sólo la rama del `confirm`: si el botón tiene `data-confirm` y aún no se confirmó, cancela el clic y abre el modal. Al aceptar, marca `confirmed`, cierra el modal y llama `button.click()`; el manejador ve `confirmed`, lo reinicia y deja pasar el clic. Así el envío sigue el mismo camino que cuando `confirm()` devolvía `true`: el navegador incluye el botón emisor (`decision=ACCEPTED`) y aplica la validación de siempre. Al cerrar sin aceptar (`hidden.bs.modal` sin `confirmed`), el foco vuelve al botón "Autorizar".

*Alternativas:* `form.submit()` como en `supplier_authorize.js` (no envía el valor del botón emisor: el servidor no recibiría `decision`); `form.requestSubmit(button)` (correcto, pero salta el manejador de clic y deja dos caminos de envío); un `input hidden` con la decisión (cambia los datos que viajan).

### D3. Suprimir la burbuja cancelando el evento `invalid`, no con `novalidate`
`form_validation.js` escucha `invalid` en fase de captura sobre `document` (el evento no burbujea, pero sí se captura) y llama `preventDefault()`. Según el algoritmo de validación interactiva de HTML, si todos los `invalid` se cancelan el navegador no muestra burbuja ni mueve el foco, **pero sigue abortando el envío**. El script pinta el mensaje y, al terminar la ronda (siguiente tarea), enfoca el primer campo que recibió `invalid`; si no es enfocable (el archivo oculto de la zona de arrastre), desplaza la vista hasta su contenedor.

Ventajas frente a `novalidate` + un `submit` propio:
- el navegador sigue evaluando y bloqueando: las reglas y el bloqueo no se reimplementan;
- un formulario inválido nunca dispara `submit`, igual que hoy, así que los `submit` de `supplier_authorize.js` (modal) y `supplier_import.js` (`fetch`) no corren con datos inválidos, sin depender del orden de los listeners;
- `form.submit()` y `formnovalidate` conservan su semántica nativa;
- sin JavaScript no hay nada que revertir.

*Alternativa descartada:* `form.noValidate = true` y validar en un `submit` en captura con `stopImmediatePropagation()`: reimplementa el bloqueo y depende de que ningún otro script envíe antes.

### D4. Validación reactiva sin disparar eventos
Fuera del envío, el script lee `control.validity` (no llama `checkValidity()`, que dispararía `invalid` y movería el foco):
- `change` (burbujea a `document`): valida el campo cambiado. Cubre "al salir con un valor cambiado" en textos y la elección inmediata en listas, casillas y archivos; recorrer con Tab sin escribir no dispara `change`.
- `input`: sólo actualiza campos que ya muestran error, para que el mensaje cambie o desaparezca mientras se escribe.
- En ambos, también refresca los demás campos del mismo formulario que muestran error: así un campo que `supplier_form.js` deshabilita (ya no `willValidate`) pierde su mensaje. El listener de `document` corre después del de la lista dependiente, que está en el propio `select`.
- Expone `window.portalValidation.refresh(form)` para scripts que cambian `required` sin un `change`; `review_decision.js` lo llama tras ajustar `observations.required`, de modo que el error de observaciones no quede a la vista al elegir "Autorizar".

Sólo se marca lo inválido: no se usa `is-valid` ni `was-validated`, para no pintar de verde los campos correctos.

### D5. Sin toasts
No hay `alert()` que reemplazar, y las alertas del servidor no son interfaz nativa. Llevarlas a toasts que se cierran solos ocultaría información que debe quedar a la vista: la contraseña temporal que se muestra una sola vez, los errores con enlace "Recargar", el resultado del envío de correos con sus destinatarios. Si en el futuro se quiere, Bootstrap Toast ya está en el bundle.

### D6. Ubicación y mensajes
- **Ubicación del mensaje** (`div.invalid-feedback`, creado una vez por campo con id `<id del campo>-error`):
  - por omisión, justo después del control;
  - casilla dentro de `.form-check`: al final de `.form-check`;
  - control dentro de un `label` (zona de arrastre): después del `label`, que recibe `is-invalid`.
- **Accesibilidad:** el id se agrega a `aria-describedby` sin borrar lo que ya tenga (p. ej. `supplier-origin-help`) y se quita al corregir; `aria-invalid="true"` mientras haya error.
- **Mensajes:** según la tabla de la spec, elegidos por la propiedad de `ValidityState` que falla, en el orden entrada incompleta → obligatorio → tipo → formato → longitud → rango → paso. La entrada incompleta va primero porque un número o una fecha a medias también dejan el valor vacío (`valueMissing`), y "Este campo es obligatorio." confundiría a quien sí escribió algo. `data-error-required` y `data-error-pattern` permiten un texto propio por campo:
  - el periodo de servicio de `invoices/new.html`: "Use el formato MM/AAAA, por ejemplo 08/2026.";
  - las observaciones de `invoices/detail.html`: "Capture las observaciones.", el mismo texto que da el servidor.

  Sin mensaje definido, se usa `control.validationMessage`, pintado igual junto al campo.
- **Decimales:** para un `step` de la forma `0.0…1` se calcula el número de decimales; otro `step` usa el mensaje del navegador.
- **Fechas mínimas:** `min` se muestra como `dd/mm/aaaa`.
- **Formularios en línea:** en `.catalog-edit-form` (flex) el mensaje ocupa su propia fila (`flex-wrap` y `flex-basis: 100%`). La zona de arrastre inválida usa el color de borde de error de Bootstrap (`--bs-form-invalid-border-color`).

### D7. Carga y alcance del script
`form_validation.js` se carga en `base.html` después de `bootstrap.bundle.min.js`, para todas las páginas con o sin sesión; los listeners son delegados en `document`, así que cubre todos los formularios sin registrarlos uno a uno. No toca formularios sin campos con reglas (búsquedas, botones de una acción).

## Risks / Trade-offs

- **[Navegadores que no respeten la cancelación de `invalid`]** → Es el comportamiento estándar desde HTML5 en Chrome, Firefox, Safari y Edge. Si alguno mostrara la burbuja de todos modos, el mensaje del portal sigue apareciendo y el envío sigue bloqueado: no hay pérdida de función.
- **[Mensaje que no corresponde con el del navegador para un caso raro]** → El orden de reglas y la caída a `validationMessage` cubren cualquier propiedad no mapeada.
- **[Estado visual obsoleto cuando otro script cambia `required`/`disabled`]** → D4: refresco en cada `input`/`change` del formulario y `portalValidation.refresh` para `review_decision.js`, el único que cambia `required` sin un `change`.
- **[Sin pruebas automáticas de navegador]** → El proyecto no tiene runner de JavaScript y agregar Playwright sería una dependencia nueva. Se cubre con pruebas de pytest sobre el HTML (sin diálogos nativos, script cargado, modal presente, atributos `data-error-*`), `node --check` de los scripts y una verificación manual en Chrome y Firefox con la lista de las tareas.
- **[Pruebas que comparan HTML]** → El cambio sólo agrega marcado (modal, `data-error-*`, `<script>`); las pruebas que buscan textos o atributos existentes no se afectan.

## Migration Plan

Sólo archivos estáticos y plantillas: se despliega con la aplicación y se revierte con el commit. No hay datos ni configuración que migrar.

## Open Questions

Ninguna bloqueante. Queda a decisión del negocio si más adelante los avisos de éxito del servidor (`notice`) se quieren como toasts (D5).
