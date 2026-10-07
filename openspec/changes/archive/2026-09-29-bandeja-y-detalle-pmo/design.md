## Context

- **Listado** (`invoice_repository.search_invoices`): una consulta con `JOIN` al proveedor (`contains_eager`), búsqueda, filtro por estatus (uno desconocido deja el listado vacío), alcance por proveedor, orden `created_at DESC` y paginación de 25. El mismo componente `components/invoice_table.html` pinta el listado y las facturas recientes del tablero.
- **Detalle** (`invoices/detail.html`): documentos vigentes con descarga, datos del CFDI o del Invoice (HU-15), conciliación con el contrato y matriz de evidencia. `invoices.comments` guarda sólo el último comentario del PMO.
- **Descarga:** siempre `attachment` y `application/octet-stream`. La CSP global es `default-src 'self'; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'` y hay `X-Frame-Options: DENY` y `nosniff`.
- **Revisión:** la tabla `reviews` guarda cada decisión (`ACCEPTED`, `REJECTED`, `REQUIRES_CORRECTION`, `COMMENT`) con revisor y fecha. Cada envío del proveedor audita `INVOICE_SUBMITTED` (HU-13).
- **PDF:** PyMuPDF (`fitz`) ya se usa para extraer texto al cargar y en el seed.

## Goals / Non-Goals

**Goals:**
- Que el PMO abra "Facturas" y vea primero lo que tiene pendiente, en el orden en que llegó.
- Ver cualquier documento de la factura sin descargarlo, sin relajar la CSP y sin depender del visor PDF del navegador.
- Que el detalle tenga lo necesario para decidir: proveedor, documentos, validaciones e historial.

**Non-Goals:**
- Decisión con tres botones y correos (HU-20); historial para el proveedor (HU-17).
- Índices nuevos, exportación y asignación de revisores.

## Decisions

### D1. Bandeja: filtro por omisión y orden según el estatus efectivo
`search_invoices` recibe `status: str | None`. Para `INTERNAL`/`ADMIN`, `None` se convierte en `UNDER_REVIEW`; `""` significa "todos". El orden depende del estatus efectivo y no de cómo llegó: con `UNDER_REVIEW` es `submitted_at ASC, id ASC`; con cualquier otro valor, `created_at DESC, id DESC`. Así la página 2 de la bandeja, cuyo enlace ya lleva `status=UNDER_REVIEW`, conserva el orden. El resultado incluye el estatus efectivo para que el formulario lo muestre seleccionado. El proveedor no cambia.

*Alternativa:* una ruta `/pmo/inbox` aparte. Duplicaría listado, filtros y paginación para cambiar sólo el filtro inicial y el orden.

### D2. Filtro por origen
Parámetro `origin` (`NATIONAL` o `INTERNATIONAL`) sobre `Supplier.origin`, ya unido en la consulta. Un valor desconocido se ignora. Se ofrece a todos los roles, aunque para el proveedor no cambia nada.

### D3. Advertencias con una consulta agregada por página
`warning_counts(db, ids)` ejecuta `SELECT invoice_id, count(*) ... WHERE status = 'WARNING' AND invoice_id IN (...) GROUP BY invoice_id` sobre los ids de la página. El número de consultas es constante (listado, conteo de la paginación y advertencias). El tablero no lo usa: la plantilla trata `warnings` ausente como vacío.

*Alternativa:* subconsulta correlacionada en el `SELECT` del listado. `paginate` trabaja con entidades y habría que cambiar su contrato.

### D4. Columnas para el PMO
`invoice_table.html`, para `INTERNAL`/`ADMIN`: Proveedor, Folio / factura, Origen, Proyecto, Envío (`submitted_at` o "—"), Monto, Score (con "N advertencias" debajo si hay), Estado. El proveedor conserva sus columnas.

### D5. Documentos como imágenes y texto dentro del portal
Nuevo `document_view_service`:
- `kind(document)`: `PDF` para `.pdf`, `IMAGE` para `.png`/`.jpg`/`.jpeg`, `TEXT` para `.xml`/`.txt`, según la extensión de `documents.path`, que se verificó por contenido al cargar;
- `pdf_page_count(path)` y `render_page(path, n)`: PNG con zoom 1.5, reducido si el ancho pasaría de 1600 px, para acotar memoria y tamaño;
- `read_text(path)`: UTF-8 con reemplazo de bytes inválidos, hasta 200 000 caracteres.

Rutas, todas con la autorización de la descarga (`_invoice_or_404` y el documento de esa factura) y `Cache-Control: private, max-age=300`:
- `GET .../view`: página del portal con las imágenes de las primeras 20 páginas, la imagen o el texto en `<pre>`;
- `GET .../pages/{n}`: `image/png` de la página `n`; 404 fuera de rango o si no es PDF;
- `GET .../image`: la imagen con su MIME y `inline`; 404 si no es imagen.

El navegador nunca recibe el PDF, el XML ni el texto como documento: sólo HTML del portal (con la CSP de siempre) e imágenes. "Ver" abre en una pestaña nueva (`target="_blank" rel="noopener"`).

*Alternativas:* servir el PDF `inline` (el visor integrado depende del navegador y la CSP con `object-src 'none'` puede impedirlo; habría que relajarla para esa ruta) o incluir pdf.js (un vendor grande con su propio JavaScript y sus propias actualizaciones de seguridad).

### D6. Proveedor e historial en el detalle
- `SUPPLIER_ORIGIN_LABELS` ("Nacional", "Internacional") en `constants.py`, global de plantillas.
- `invoice_history_service.history(db, invoice)` une los envíos (`AuditLog` `INVOICE_SUBMITTED` de esa factura, con el usuario) y las revisiones (`Review` con el revisor), los ordena por fecha y etiqueta la decisión con `STATUS_LABELS` ("Autorizada", "Rechazada", "Observaciones") o "Comentario". Dos consultas, sin tablas nuevas.
- El bloque "Proveedor" y la sección "Historial" se pintan sólo para `INTERNAL`/`ADMIN`.

## Risks / Trade-offs

- **[Render de PDF en el servidor]** → MuPDF procesa archivos del proveedor (ya lo hace al cargar). Se acota a 20 páginas y 1600 px de ancho; las respuestas se pueden cachear 5 minutos en el navegador.
- **[Pruebas del listado que asumían el orden por creación para `INTERNAL`]** → Se ajustan para pedir `status=` explícito o para esperar la bandeja.
- **[El PMO no ve borradores al entrar]** → Es la intención de la bandeja; "Todos los estados" los muestra.

## Migration Plan

Sin migración ni configuración nueva.

## Open Questions

- ¿El PMO debe ver los resultados de "Verificar" de una factura que aún no se envía? Se conserva el comportamiento actual (los ve quien ve la factura); HU-20 puede restringirlo.
