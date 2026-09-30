## Context

- **Estatus:** `InvoiceStatus` tiene los seis estatus del ERS; `ALLOWED_TRANSITIONS` los enlaza y `invoice_service.transition_invoice` valida, fecha (`submitted_at`, `reviewed_at`) y audita `STATUS_CHANGED`. `EDITABLE_STATUSES` (Borrador, Cargada, Observaciones) gobierna la carga, la verificación y los datos del Invoice; el envío exige Cargada u Observaciones; la decisión, Enviada. La columna es `VARCHAR(19)` con el `CHECK invoicestatus` (0011).
- **Documentos:** el catálogo `invoice_document_types` (HU-04) guarda nombre, formatos y niveles por origen; `ck_invoice_document_types_fixed_levels` y `FIXED_REQUIREMENTS` fijan los niveles del CFDI y del Invoice. `offered_types` sólo ofrece tipos activos que no son "No aplica" para el origen. `LocalFileStorage.save_invoice_file` valida extensión, contenido, tamaño y ruta antes de escribir.
- **Correos (HU-20):** `review_service` asocia cada estatus de decisión con su evento (`EVENTS`), compone y envía con `notification_service.notify` después del commit, y ofrece el reenvío cuando el último envío del evento del estatus actual falló (`last_delivery`, `can_resend`, `prepare_resend`, `POST /invoices/{id}/notification`). La plantilla `INVOICE_CANCELLED` (HU-05) va al buzón "Recepción de Facturas" y exige `numero_factura`, `proveedor` y `fecha_limite_cancelacion`.
- **Duplicados del Invoice (HU-15):** `foreign_invoice_service.duplicate_folios` busca documentos `FOREIGN_INVOICE` vigentes del mismo nombre en las demás facturas del proveedor; lo usan la carga (409) y FIN-007.

## Goals / Non-Goals

**Goals:**
- Que el proveedor cancele su factura dejando el acuse como evidencia.
- Que Recepción de Facturas reciba el aviso con la fecha límite de 72 horas, y que un aviso fallido pueda reenviarse.
- Que una factura cancelada no vuelva a moverse y sea evidente en el detalle.

**Non-Goals:**
- Registrar en el portal la aceptación o el rechazo de la cancelación, el motivo SAT, la consulta del estatus del CFDI ni revertir una cancelación.
- Recordatorios antes del vencimiento de las 72 horas.
- Seguimiento del estatus por el proveedor (HU-17).

## Decisions

### D1. `CANCELLED` en el modelo de estatus
`InvoiceStatus.CANCELLED = "CANCELLED"` con la etiqueta "Cancelada". En `ALLOWED_TRANSITIONS` cada estatus distinto de `CANCELLED` agrega `CANCELLED` (Autorizada y Rechazada ahora tienen una única salida); `CANCELLED` no tiene salidas. `EDITABLE_STATUSES`, `SUBMITTABLE_STATUSES` y la decisión no cambian: al no incluir `CANCELLED`, la carga, la verificación, los datos del Invoice, el envío y la decisión ya responden 409, y la factura sale de la bandeja (que filtra "Enviada").

`CANCELLED` (9) es más corto que `REQUIRES_CORRECTION` (19): la columna no cambia de longitud.

*Alternativa:* un estatus "Cancelación solicitada" hasta que Recepción la acepte. Queda fuera por P-09 (S2): la aceptación ocurre ante el SAT, no en el portal.

### D2. Datos de la cancelación en `invoices`
Tres columnas: `cancelled_at` (`UTCDateTime`), `cancelled_by` (FK `users.id` con `RESTRICT`, indexada, como `reviewed_by`) y `cancellation_deadline` (`UTCDateTime`). `transition_invoice` las llena al pasar a `CANCELLED`, igual que hoy llena `submitted_at` y `reviewed_at`: `cancellation_deadline = cancelled_at + CANCELLATION_WINDOW` con `CANCELLATION_WINDOW = timedelta(hours=72)` en `constants.py` (S5: horas naturales).

`ck_invoices_cancellation`:
```
(status = 'CANCELLED' AND cancelled_at IS NOT NULL AND cancelled_by IS NOT NULL
   AND cancellation_deadline IS NOT NULL AND cancellation_deadline > cancelled_at)
OR (status <> 'CANCELLED' AND cancelled_at IS NULL AND cancelled_by IS NULL AND cancellation_deadline IS NULL)
```
Todos los `IS NOT NULL` son explícitos: una comparación con `NULL` daría `NULL` y el `CHECK` la aceptaría.

*Alternativa:* leer la fecha de la auditoría. Obligaría a consultar `audit_logs` para pintar el detalle y no se podría garantizar por `CHECK`.

### D3. El acuse es un tipo del sistema "No aplica"
`DocumentType.CANCELLATION_ACK` se siembra en `invoice_document_types` como tipo del sistema: "Acuse de cancelación", "Acuse de cancelación del CFDI emitido por el SAT o documento que acredita la cancelación", formatos PDF y XML, "No aplica" para ambos orígenes. Se agrega a `FIXED_REQUIREMENTS` (motivo "Se carga al cancelar la factura") y a `ck_invoice_document_types_fixed_levels`, de modo que el Administrador ve los niveles bloqueados y no puede hacerlo exigible: nunca aparece en la carga documental ni en la prevalidación.

El nombre y los formatos se leen del catálogo: el mensaje de formato es el mismo `requirements.ensure_format` de la carga ("Formato no admitido para Acuse de cancelación. Formatos admitidos: PDF, XML") y el detalle muestra el nombre con `type_names`, como cualquier documento.

*Alternativa:* guardar el acuse fuera del catálogo. El detalle mostraría la clave y el Administrador no sabría que el tipo existe.

### D4. `cancellation_service`
Nuevo `app/services/cancellation_service.py`, sin commit:
- `check_request(db, invoice, confirmed, filename) -> None`: en orden, "Confirme la cancelación", "Cargue el Acuse de cancelación" y el formato (D3). No toca la factura ni el disco. Antes, un formulario viejo sobre una factura ya cancelada recibe 409 "La factura ya está cancelada": el detalle de una cancelada no tiene sección donde mostrar un 400.
- `async cancel(db, invoice, upload, user_id) -> Document`: `lock_invoice`; 409 "La factura ya está cancelada" si ya lo está; guarda el archivo (`save_invoice_file`: un contenido que no corresponde a la extensión es `ValueError` → 400); crea el `Document` vigente `CANCELLATION_ACK` (`metadata_json` vacío: el XML no se procesa como CFDI, S3/HU-14); transiciona (D1, D2); audita `INVOICE_CANCELLED` con `{"status": <anterior>}` → `{"document_id", "deadline"}`.

El router valida CSRF, rol (`provider_only`: 403 a `INTERNAL`/`ADMIN`) y visibilidad (404), llama a `check_request` antes de leer el archivo, después a `cancel`, confirma y envía el correo (D5). Un 400 vuelve a pintar el detalle con el error en la sección.

`FOREIGN_INVOICE_LOCK_KEY` no se toma: cancelar sólo libera nombres de archivo del Invoice (D6), nunca provoca un duplicado.

### D5. Correo y reenvío con el mecanismo de HU-20
`review_service.EVENTS` agrega `CANCELLED → INVOICE_CANCELLED`, y `send_notification` se generaliza:
- los eventos del buzón (`INVOICE_AUTHORIZED`, `INVOICE_CANCELLED`) no llevan `supplier_email`;
- `fecha_estatus` es `cancelled_at` para "Cancelada" y `reviewed_at` para las decisiones;
- "Cancelada" agrega `fecha_limite_cancelacion = cancellation_deadline`.

Así `last_delivery`, `can_resend`, `prepare_resend` y `POST /invoices/{id}/notification` cubren el aviso de cancelación sin cambios: el PMO ve "Reenviar notificación" si el último envío falló. El mensaje "La factura ya fue revisada" de `decide` pasa a depender de `DECIDED` (los tres estatus de decisión) en lugar de `EVENTS`: sobre una factura cancelada responde "La factura no está en revisión".

Tras cancelar, el router redirige a `/invoices/{id}?notification=<id del envío|error>#cancellation-result`. Para el proveedor, el detalle sólo acepta un envío `INVOICE_CANCELLED` de esa factura (`invoice_delivery` ya descarta ids ajenos) y muestra "Se notificó a Recepción de Facturas" o "No se pudo notificar a Recepción de Facturas", sin direcciones; el PMO conserva el mensaje de HU-20 con direcciones y error.

*Alternativa:* un servicio de notificaciones de factura aparte. Duplicaría `last_delivery`/`can_resend` o obligaría a mover el código de HU-20 sin necesidad; se deja para cuando HU-17 agregue avisos al proveedor.

### D6. Duplicados del Invoice sin facturas canceladas
`duplicate_folios` agrega `Invoice.status != CANCELLED`: el proveedor internacional puede volver a cargar el mismo Invoice en una factura nueva tras cancelar la anterior (P-08). El UUID del CFDI sigue único en cualquier estatus (`uq_invoices_uuid`, DT-03): un CFDI cancelado ante el SAT no se reutiliza.

### D7. Detalle
- Proveedor, factura no cancelada: `<details class="panel" id="cancellation">` "Cancelar factura", abierto cuando trae un error, con el `<input type="file" name="upload" accept=".pdf,.xml">` del acuse, la casilla `name="confirm"` "Confirmo que la factura se canceló y adjunto su acuse" y el botón "Cancelar factura" (`multipart/form-data`, CSRF). Sin JavaScript: la casilla es la confirmación.
- Factura cancelada, todos los roles: aviso `id="cancelled"` "Cancelada el <cancelled_at>. Recepción de Facturas debe aceptar la cancelación antes del <cancellation_deadline>." con `business_datetime`. Sin sección de cancelación, panel "Decisión", "Gestionar documentos", "Verificar" ni "Enviar a validación" (ya dependen del estatus).
- El reenvío del PMO dice "El último correo de la cancelación no se envió." para una factura cancelada.
- `.status-cancelled` gris oscuro, distinto de "Rechazada".

### D8. Migración `0012_invoice_cancellation`
1. Columnas, FK `fk_invoices_cancelled_by_users` e índice `ix_invoices_cancelled_by` (nombres de la convención del modelo).
2. `invoicestatus` con los siete estatus y `ck_invoices_cancellation`.
3. `ck_invoice_document_types_fixed_levels` con el acuse, y la fila del sistema. Si un tipo del Administrador ya se llama "Acuse de cancelación" (índice único sin mayúsculas), la migración se detiene con un mensaje que pide renombrarlo: no cambia datos del Administrador por su cuenta.

El downgrade se niega si hay facturas canceladas (su estatus no existe antes); si no las hay, borra la fila del acuse y restaura los `CHECK` y las columnas.

### D9. Demo
`CANCELADA-001` del proveedor 1, enviada y cancelada durante la siembra con un acuse PDF generado (PyMuPDF, como el Invoice de `INV-2026-0042`), `cancelled_by` del proveedor y su fecha límite. Se agrega al final de los escenarios: los folios de los anteriores no cambian y el de `INV-2026-0042` pasa a `FAC-2026-00012`. La siembra no envía correos.

## Risks / Trade-offs

- **[Cancelar una factura Autorizada ya pagada]** → S1 lo permite porque el SAT exige a ULTRASIST responder en 72 horas en cualquier caso; el aviso llega al mismo buzón que la autorización. Si el negocio decide otra cosa (P-05), basta con quitar `CANCELLED` de las salidas de `ACCEPTED`.
- **[El correo falla y nadie lo reenvía]** → el proveedor ve que no se notificó y el PMO ve "Reenviar notificación"; la bitácora de correos (HU-08) lo registra como `FAILED`.
- **[Archivo escrito y commit fallido]** → queda un archivo huérfano en el almacenamiento, como en la carga documental; no hay registro que apunte a él.
- **[Hora del servidor]** → las 72 horas se cuentan en UTC y se muestran en la zona de negocio; un cambio de horario no altera la fecha límite guardada.
