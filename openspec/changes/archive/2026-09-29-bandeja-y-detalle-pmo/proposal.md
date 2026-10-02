## Why

El rol PMO del Alcance del MVP (minuta del 21-sep-2026) debe "consultar las facturas registradas por los proveedores" y "realizar la validación manual de las facturas cargadas". El ERS lo cubre con HU-18 (RF-17: listado con estatus, proveedor, folio, monto y tipo Nacional/Internacional) y HU-19 (RF-18: visualizar la factura y sus documentos soporte junto con el resultado de las validaciones automáticas).

Hoy el PMO (rol `INTERNAL`) usa el mismo listado que el proveedor: abre con todas las facturas por fecha de creación, sin origen ni fecha de envío, así que las pendientes de revisar se mezclan con borradores. En el detalle sólo puede descargar los documentos: no los ve en el navegador, y la descarga siempre es un adjunto (spec `almacenamiento-documentos`). Tampoco ve los datos del proveedor ni el historial de revisiones: sólo el último comentario.

Con HU-13 y HU-16 ya hay facturas nacionales e internacionales "Enviadas". Es la parte PMO de la ola 2 (EP-02).

## What Changes

- **Bandeja del PMO** (HU-18, EP-02 DT-02): para `INTERNAL` y `ADMIN`, `/invoices` sin filtro de estatus abre en "Enviada", ordenada por fecha de envío ascendente (lo que más ha esperado primero). "Todos los estados" u otro estatus vuelven al orden por fecha de creación descendente. Nuevo filtro por origen (Nacional, Internacional).
- **Columnas para el PMO:** origen, fecha de envío y número de advertencias de la validación, además de proveedor, folio, número, proyecto, monto con moneda, score y estatus. Sin consultas por fila.
- **Visualización de documentos en el portal** (HU-19, DT-03): "Ver" en cada documento abre una página del portal:
  - PDF: cada página renderizada en el servidor como imagen PNG (hasta 20 páginas);
  - PNG y JPEG: la imagen;
  - XML y TXT: su texto escapado.

  Misma autorización que la descarga; la descarga sigue siendo un adjunto.
- **Detalle para la revisión:**
  - bloque "Proveedor" con origen, identificador fiscal, correo y estatus;
  - "Historial" con los envíos del proveedor y las revisiones (fecha, decisión, observaciones y revisor), visible para `INTERNAL` y `ADMIN` (DT-07).

**Fuera de alcance:**
- el panel de decisión con tres botones y los correos (HU-20);
- el historial para el proveedor (HU-17);
- exportar el listado y asignar revisores;
- un índice `(status, submitted_at)`: con el volumen del MVP el listado ya responde con los índices actuales (se revisará si el RNF de 3 s lo requiere).

## Supuestos

- **S1.** La bandeja aplica "Enviada" sólo cuando la petición no trae `status`. El formulario de filtros siempre lo envía, vacío para "Todos los estados", así que elegir "Todos" muestra todo.
- **S2.** Renderizar el PDF en el servidor evita depender del visor PDF de cada navegador y de relajar la CSP (`object-src 'none'`, `frame-ancestors 'none'`): el navegador sólo recibe imágenes y HTML del portal. Es la alternativa que EP-02 DT-03 dejó abierta como riesgo.
- **S3.** El historial se arma con la tabla `reviews` (decisiones del PMO) y la auditoría `INVOICE_SUBMITTED` (envíos del proveedor); no se agrega una tabla.
- **S4.** El proveedor también puede usar "Ver" sobre los documentos de sus facturas: la autorización es la misma que la descarga.

## Capabilities

### New Capabilities
- `revision-pmo`: bandeja del PMO (filtro inicial, orden, origen y columnas), bloque del proveedor e historial de revisión en el detalle.

### Modified Capabilities
- `flujo-facturas`: el listado filtra por origen y, para `INTERNAL` y `ADMIN` sin estatus, abre en "Enviada" ordenado por fecha de envío.
- `almacenamiento-documentos`: visualización segura de documentos dentro del portal (páginas del PDF como imágenes, imágenes y texto escapado).

## Impact

- **Código:**
  - `app/repositories/invoice_repository.py`: `origin`, estatus por omisión y orden para `INTERNAL`/`ADMIN`, y conteo de advertencias por página;
  - `app/routers/invoices.py`: parámetros del listado y rutas `GET /invoices/{id}/documents/{doc}/view`, `/pages/{n}` y `/image`;
  - nuevo `app/services/document_view_service.py`: tipo de vista, número de páginas, render de página y texto con límite;
  - `app/services/invoice_history_service.py`: historial (envíos y revisiones).
- **Plantillas:** `invoices/list.html`, `components/invoice_table.html`, `invoices/detail.html` y nueva `invoices/document_view.html`.
- **Esquema:** sin migración.
- **Dependencias:** ninguna nueva (PyMuPDF ya está).
- **Pruebas:** nuevo `tests/test_revision_pmo.py`; ajustes en las pruebas del listado que asumían el orden por creación para `INTERNAL`.
- **Documentación:** `README.md`.
