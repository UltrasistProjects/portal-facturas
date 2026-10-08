## Why

Varios `POST` del portal responden después de enviar su correo; la cancelación de una factura tarda segundos. Un segundo clic en ese lapso repetía la operación, que el servidor ya encontraba hecha, y el usuario veía un error de negocio (HTTP 409) aunque la operación se había hecho bien.

## What Changes

- Con JavaScript, cada formulario `POST` se envía una sola vez: tras el primer envío ignora los siguientes y deshabilita sus botones, conservando el botón pulsado en la petición.
- No se bloquean los formularios inválidos (el navegador no los envía) ni los que su script envía por `fetch` o tras su propio modal de confirmación.
- Al volver con "Atrás" desde la caché del navegador, los botones se rehabilitan.
- Sin JavaScript no cambia nada: el servidor sigue rechazando la operación repetida.

## Capabilities

### New Capabilities

_Ninguna._

### Modified Capabilities

- `interfaz-usuario`: un solo envío por formulario.

## Impact

`app/static/js/app.js`. Sin cambios en el servidor ni migraciones.
