> Todas las rutas son relativas a la raíz de la PoC (`PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress-V1/PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress/`). Sólo se tocan archivos estáticos, plantillas, pruebas y documentación: ningún archivo de `app/routers`, `app/services`, `app/models`, `app/schemas`, `app/core` ni `alembic`.

## 1. Confirmación de "Autorizar" en modal

- [x] 1.1 `app/templates/invoices/detail.html`: marcado del modal `#decision-confirm` dentro de `{% if can_decide %}`, con el patrón de `suppliers/list.html`: título "Autorizar factura", párrafo vacío para el texto, "Cancelar" (`btn-light`, `data-bs-dismiss`) y "Autorizar" (`btn-success`) (D2).
- [x] 1.2 `app/static/js/review_decision.js`: cambiar sólo la rama del `window.confirm`. Abrir el modal con el texto de `data-confirm` (`textContent`); al aceptar, `confirmed = true`, cerrar el modal y `button.click()`; el manejador reinicia `confirmed` y deja pasar el clic; al cerrar sin aceptar, foco de vuelta en "Autorizar" (D2). Actualizar el comentario de cabecera.

## 2. Validación junto al campo

- [x] 2.1 Nuevo `app/static/js/form_validation.js`:
  - `invalid` en captura sobre `document` con `preventDefault()`, pinta el mensaje y enfoca el primer inválido de la ronda, o desplaza la vista hasta su contenedor si no es enfocable (D3);
  - `change` / `input` reactivos leyendo `validity`, con refresco de los campos del formulario que ya muestran error (D4);
  - `window.portalValidation.refresh(form)` (D4).
- [x] 2.2 En el mismo script:
  - ubicación del `invalid-feedback` (control, `.form-check`, `label` contenedor);
  - `aria-invalid` y `aria-describedby` agregados y quitados sin perder los ids previos;
  - mensajes en español por propiedad de `ValidityState` según la tabla de la spec, con `data-error-required` / `data-error-pattern`, decimales del `step`, fecha mínima `dd/mm/aaaa` y caída a `validationMessage` (D6).
- [x] 2.3 `app/templates/base.html`: cargar `form_validation.js` después de `bootstrap.bundle.min.js` y antes de `app.js` (D7).
- [x] 2.4 Atributos de presentación:
  - `data-error-pattern="Use el formato MM/AAAA, por ejemplo 08/2026."` en el periodo de servicio (`invoices/new.html`);
  - `data-error-required="Capture las observaciones."` en las observaciones (`invoices/detail.html`).
- [x] 2.5 `app/static/js/review_decision.js`: llamar `window.portalValidation?.refresh(form)` después de ajustar `observations.required` (D4).
- [x] 2.6 `app/static/css/app.css`:
  - `label.dropzone.is-invalid` con el borde de error de Bootstrap;
  - el mensaje en su propia fila en `.catalog-edit-form`;
  - revisar en el navegador los demás formularios en línea (`.amend-form`, tablas de `required_documents.html`) y ajustar sólo si el mensaje desacomoda la fila.

## 3. Pruebas

- [x] 3.1 Nuevo `tests/test_interfaz_usuario.py`:
  - ningún archivo de `app/static/js` ni de `app/templates` (sin `vendor`) contiene `alert(`, `confirm(` ni `prompt(`;
  - `base.html` carga `form_validation.js` y el archivo se sirve;
  - el detalle de una factura "Enviada" para el PMO incluye `#decision-confirm` y el botón con `data-confirm`; para el proveedor no;
  - el periodo de servicio y las observaciones llevan su `data-error-*`.
- [x] 3.2 `node --check` de `form_validation.js` y `review_decision.js`.
- [x] 3.3 Confirmar que `tests/test_cabeceras.py` (sin scripts en línea) y `tests/test_revision_pmo.py` siguen en verde sin cambios.

## 4. Documentación y verificación

- [x] 4.1 `README.md`:
  - en la decisión del PMO, "Autorizar pide confirmación en un modal";
  - nota breve de la validación de formularios junto al campo, con la validación nativa como respaldo sin JavaScript.
- [x] 4.2 Búsqueda final en `app/` (sin `vendor`) de `alert(`, `confirm(`, `prompt(`, `reportValidity`, `novalidate` y `setCustomValidity`: no queda ninguna interfaz nativa que debiera reemplazarse.
- [x] 4.3 `python scripts/check.py --skip-audit` en verde (ruff, formato, alembic check, pytest con el umbral de cobertura).
- [x] 4.4 Verificación en navegador (Chrome y Firefox, con y sin JavaScript). Hecha en Chromium (Playwright, 50/50, con y sin JavaScript) sobre una instancia desechable igual a la de la suite: base temporal, Keycloak simulado, correo a archivo y todo POST abortado en el navegador. En Firefox 155, el bloqueo del envío y los mensajes de cada regla, con una página de prueba; el modal en Firefox queda para revisión manual:
  - "Autorizar": cancelar, Esc y aceptar;
  - "Rechazar" sin observaciones;
  - alta de usuario con nombre vacío y correo inválido, y el error desaparece al corregir;
  - periodo `8/2026`;
  - "Cargar documento" sin archivo;
  - alta de proveedor cambiando el origen con un error visible;
  - enmienda con 3 decimales;
  - carga masiva sin archivo (no se hace la petición);
  - autorización masiva (su modal sigue igual).
- [x] 4.5 `openspec validate interfaz-sin-dialogos-nativos --strict` sin errores.
