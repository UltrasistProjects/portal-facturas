## Context

Fix del navegador; el servidor ya rechaza las operaciones repetidas con su error de negocio.

## Decisions

- **Un solo oyente global:** `app.js` escucha `submit` en `document`, en la fase de burbuja. Los oyentes propios de cada formulario corren antes, así que un envío que su script cancela (`preventDefault`, como la carga masiva por `fetch` o los modales de activación de contrato y autorización de proveedores) llega con `defaultPrevented` y no se bloquea; `form.submit()` no dispara `submit`. Sólo aplica a `method="post"`.
- **Botones deshabilitados en la siguiente vuelta:** deshabilitarlos dentro del evento `submit` quitaría de la petición el `name`/`value` del botón pulsado (la decisión del PMO); por eso se deshabilitan con `setTimeout` y, mientras tanto, la marca `data-submitting` ignora los envíos repetidos.
- **Formularios inválidos:** el navegador no dispara `submit` si la validación nativa falla, así que no quedan bloqueados.
- **Atrás (bfcache):** en `pageshow` con `persisted` se quitan la marca y el bloqueo de los botones.

## Risks / Trade-offs

- [Un `POST` que no navega (descarga de archivo o respuesta 204) dejaría el formulario bloqueado] → hoy ninguno: las descargas son `GET` y los `POST` responden con una página o una redirección.
