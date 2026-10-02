## Context

- **Decisión actual:** `GET /invoices/{id}/review` pinta `invoices/review.html` con cuatro botones y comentarios opcionales. `POST /invoices/{id}/review` llama a `invoice_service.review_invoice`, que para `COMMENT` sólo registra la revisión y para las demás decisiones transiciona con `transition_invoice` (valida `ALLOWED_TRANSITIONS`, asigna `reviewed_at`/`reviewed_by` y audita `STATUS_CHANGED`). No bloquea la fila: dos decisiones simultáneas pasan ambas la validación de la transición.
- **ClickBalance:** `ACCEPTED → READY_FOR_CLICKBALANCE → UPLOADED_TO_CLICKBALANCE` por `POST /invoices/{id}/clickbalance`, con dos botones en el detalle. El seed tiene `CLICK-READY` y `CLICK-DONE`.
- **Correo:** `notification_service.notify(db, event, supplier_email=..., entity=..., entity_id=..., user_id=..., **values)` resuelve destinatarios (HU-08), compone con la plantilla vigente (HU-05), envía, registra en `email_deliveries` y confirma ese registro; un error de transporte queda `FAILED` sin excepción. `compose` exige todas las variables del evento. HU-03 muestra el resultado del envío con el id del envío en la URL (`?credentials=`).
- **Bloqueo:** `invoice_service.lock_invoice` (`refresh(..., with_for_update=True)`) ya lo usan la carga, la verificación y el envío.
- **Detalle (HU-19):** bloque "Proveedor" e "Historial" para `INTERNAL`/`ADMIN`; el historial ya etiqueta las decisiones.

## Goals / Non-Goals

**Goals:**
- Los tres botones del ERS en el detalle, con las observaciones que exige RN-HU20-01.
- Que Recepción de Facturas se entere de cada autorización y el proveedor de cada rechazo u observación, y que un correo fallido no se pierda en silencio.
- Una sola decisión por envío.
- Un modelo de estatus sin pasos fuera del alcance.

**Non-Goals:**
- Revertir decisiones, motivos de rechazo en catálogo, seguimiento del proveedor (HU-17), cancelación (HU-14).

## Decisions

### D1. `review_service` concentra la decisión
Nuevo `app/services/review_service.py`:
- `decide(db, invoice, decision, observations, reviewer_id) -> Review`: bloquea (`lock_invoice`), exige `UNDER_REVIEW` (409 "La factura ya fue revisada" o "La factura no está en revisión"), valida la decisión (400 "Decisión inválida", `COMMENT` incluida) y las observaciones (D3), aplica `ensure_can_accept` al autorizar, transiciona, guarda `invoices.comments`, registra la revisión y audita la decisión. No hace commit.
- `notify_decision(db, invoice, review)` y `send_notification(db, invoice, observations, user_id)`, que devuelven el `EmailDelivery` o `None` (D4), y `prepare_resend(db, invoice, user_id)` (D5). Ninguna hace commit: el endpoint confirma la decisión o el reenvío y después envía.

`invoice_service.review_invoice` y `next_clickbalance_status` se retiran; `ensure_can_accept` se queda en `invoice_service` porque es la regla de control del flujo.

*Alternativa:* extender `review_invoice`. Quedaría con la lógica de correo mezclada en el servicio de reglas de estado, que no conoce las notificaciones.

### D2. Panel en el detalle y la ruta de siempre
El panel "Decisión" (`id="decision"`) es un `<form method="post" action="/invoices/{id}/review">` con el `<textarea name="comments">` "Observaciones" (máx. 2 000) y tres `<button name="decision">`. Se conserva el nombre `comments` del formulario: es el que ya usan la ruta y las pruebas. `GET /review` redirige a `#decision` y `invoices/review.html` se elimina. En el encabezado, "Revisar expediente" pasa a "Decidir" y apunta a `#decision`.

`app/static/js/review_decision.js` (archivo externo por la CSP) oculta el campo hasta elegir "Rechazar" u "Observaciones" (el primer clic lo muestra y enfoca sin enviar), marca el campo como requerido para esas decisiones y pide `confirm()` antes de "Autorizar". Sin JavaScript el campo está visible con la nota y el servidor valida igual.

### D3. Validación de las observaciones
`strip()`; obligatorias para `REJECTED` y `REQUIRES_CORRECTION`; máximo 2 000 caracteres para cualquier decisión. Al autorizar sin texto, `invoices.comments` queda `NULL`: así el aviso de observaciones de una ronda anterior no sigue apareciendo.

### D4. Correo después del commit y resultado por id
El router confirma la decisión y luego llama a `notify_decision`:

| Estatus | Evento | `supplier_email` |
| --- | --- | --- |
| `ACCEPTED` | `INVOICE_AUTHORIZED` | — (buzón) |
| `REJECTED` | `INVOICE_REJECTED` | `invoice.supplier.email` |
| `REQUIRES_CORRECTION` | `INVOICE_OBSERVATIONS` | `invoice.supplier.email` |

Valores: `numero_factura`, `folio_interno`, `proveedor`, `monto`/`moneda` (`total`, `currency`), `fecha_estatus` (`reviewed_at`) y `observaciones` para las dos últimas. `notify` registra `FAILED` ante un error de transporte; un `NotificationDataError` (datos incompletos) se registra en el log (`review.notification_error`) y se muestra como falla genérica.

La redirección es `/invoices/{id}?notification=<delivery_id>`. El detalle sólo usa el envío si su entidad es `Invoice` con ese id: un id ajeno no muestra nada (como `?credentials=` de HU-03). Mensajes: "Correo enviado a <Para>" o "No se pudo enviar el correo: <error>".

### D5. Reenvío sólo de una notificación fallida
`last_delivery(db, invoice, event)`: el envío más reciente con `entity = 'Invoice'`, ese id y el evento del estatus actual. "Reenviar notificación" se ofrece y `POST /invoices/{id}/notification` procede sólo si la factura está en un estatus con evento y ese último envío es `FAILED`; si no, 409 "No hay una notificación fallida que reenviar". Usa las observaciones de la última revisión con decisión y audita `INVOICE_NOTIFICATION_RESENT`. El bloqueo de fila evita dos reenvíos simultáneos.

*Alternativa:* reenviar siempre que se pida. Duplicaría avisos de pago a Recepción de Facturas.

### D6. Retiro de ClickBalance
- `InvoiceStatus` pierde `READY_FOR_CLICKBALANCE` y `UPLOADED_TO_CLICKBALANCE`; `ALLOWED_TRANSITIONS` pierde `ACCEPTED → …`; se retira la ruta, los botones y las clases CSS de esos estatus.
- Migración `0011_retire_clickbalance`: primero los datos (`UPDATE` a `ACCEPTED` con `RETURNING` y un `STATUS_MIGRATED` por factura, como `0010`), después el `CHECK invoicestatus` con los seis estatus y la columna de `VARCHAR(24)` a `VARCHAR(19)`: `enum_column` toma la longitud del valor más largo, que deja de ser `UPLOADED_TO_CLICKBALANCE` (sin este paso, `alembic check` detecta la diferencia). El downgrade restaura la longitud y el `CHECK` de ocho; los estatus migrados no se revierten (son válidos antes).
- Seed: `CLICK-READY` → `OBSERVACIONES-001` en `REQUIRES_CORRECTION` con su revisión del PMO ("Falta el Vo.Bo. firmado"); `CLICK-DONE` → `ENVIADA-002` en `UNDER_REVIEW`. Se conservan once facturas y sus folios.

## Risks / Trade-offs

- **[Datos de ClickBalance en una base existente]** → se migran a "Autorizada" con auditoría; el paso manual de ClickBalance ya no se registra en el portal (P-01 de EP-02).
- **[Correos de decisión en pruebas]** → el transporte `file` de la suite escribe en un directorio temporal; las pruebas que cuentan envíos usan `restore_notification_recipients`.
- **[Pruebas que decidían `COMMENT`]** → se ajustan a decisiones reales sobre facturas propias.
- **[Decisión con la fila bloqueada durante el envío]** → el correo se envía después del commit, fuera del bloqueo.

## Migration Plan

`alembic upgrade head` aplica `0011`. Rollback: `alembic downgrade 0010_invoice_status_model` restaura el `CHECK`; el código anterior acepta "Autorizada".

## Open Questions

- P-01, P-02, P-03, P-05 y P-06 de EP-02 siguen abiertas; se aplican sus valores por defecto.
