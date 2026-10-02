## Context

- **Historial (HU-19):** `invoice_history_service.history(db, invoice)` junta los envíos (auditoría `INVOICE_SUBMITTED`) y las revisiones (`reviews`) en `HistoryEvent(at, title, actor, detail)`. El router sólo lo calcula para `INTERNAL`/`ADMIN` y la plantilla lo pinta en `#history`.
- **Observaciones:** `review_service.decide` guarda el texto en `reviews.comments` y en `invoices.comments`, y el correo usa el de la revisión. `invoices.comments` sobrevive al reenvío, y la demo lo usa para notas de escenario ("Caso por decidir"). El detalle muestra `invoices.comments` en cualquier estatus.
- **Cancelación (HU-14):** auditoría `INVOICE_CANCELLED` con `new_value.deadline` (ISO) y las columnas `cancelled_at`, `cancelled_by`, `cancellation_deadline`.
- **Tablero:** `status_counts` (GROUP BY) y `total_amount` ya respetan el alcance del proveedor; la plantilla muestra cuatro tarjetas sin enlace.

## Goals / Non-Goals

**Goals:** que el proveedor sepa en qué va cada factura, por qué se rechazó o qué debe corregir, y qué pasó antes; sin datos que no le corresponden (el nombre del revisor, los comentarios internos).

**Non-Goals:** notificaciones dentro del portal, estatus de pago, cambios de esquema.

## Decisions

### D1. Un solo historial con dos vistas
`history(db, invoice, for_provider=False)`:
- revisiones: `actor = "PMO"` si `for_provider`, el nombre del revisor si no; `COMMENT` se omite para el proveedor;
- cancelación: un evento "Cancelada" desde la auditoría `INVOICE_CANCELLED` (fecha, usuario), con el detalle "Fecha límite de aceptación: dd/mm/aaaa HH:MM" tomado de `invoice.cancellation_deadline` (la columna, no el JSON: es la fuente que garantiza el `CHECK`).

El router lo calcula para todos los roles; la plantilla titula "Historial" (PMO, junto al bloque "Proveedor") o "Seguimiento" (proveedor, en su propia sección) con el mismo `id="history"`.

*Alternativa:* un servicio aparte para el proveedor. Duplicaría las consultas y el orden; la diferencia es de presentación.

### D2. Causa desde la última decisión
`last_decision(db, invoice) -> Review | None`: la revisión más reciente con `decision <> COMMENT`, con el mismo orden que `prepare_resend` (`created_at DESC, id DESC`); `prepare_resend` pasa a usarla. El texto del aviso es `review.comments` o, sin revisiones, `invoices.comments`: el mismo que el correo y el reenvío.

El aviso sólo aparece en "Rechazada" (`alert-danger`, "Motivo del rechazo") y "Observaciones" (`alert-warning`, "Observaciones del PMO"; al proveedor, "Corrija lo indicado y vuelva a enviar la factura" con el enlace a `/invoices/{id}/documents`). El aviso genérico se retira: en "Enviada" tras un reenvío mostraba observaciones ya atendidas, y en la demo, notas de escenario.

### D3. Tablero
Tarjetas: Total, Enviadas, Observaciones, Autorizadas, Rechazadas, Canceladas, cada una un `<a class="kpi-card">` a `/invoices?status=<clave>` (Total a `/invoices?status=`, "Todos los estados", porque sin `status` el PMO cae en su bandeja). `.kpi-grid` pasa a `repeat(auto-fit, minmax(150px, 1fr))` para seis tarjetas. El monto acumulado conserva su cálculo.

### D4. Demo con historial
La siembra registra la auditoría `INVOICE_SUBMITTED` de las facturas demo enviadas (dos horas antes de la decisión) e `INVOICE_CANCELLED` de `CANCELADA-001`, con la revisión fechada en el mismo instante que `reviewed_at`. Sin ellas, el "Seguimiento" de la demo sólo mostraría las decisiones.

## Risks / Trade-offs

- **[Texto distinto al del correo]** → ambos salen de `reviews.comments` de la misma revisión; una prueba compara el aviso con el cuerpo del `.eml`.
- **[Monto acumulado con monedas mezcladas]** → ya existía: suma MXN y USD. Queda fuera de esta HU; se anota en el README.
