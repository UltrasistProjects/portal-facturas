## Context

- **Estatus:** `InvoiceStatus` tiene siete estatus. `ALLOWED_TRANSITIONS` define las transiciones. `invoice_service.transition_invoice` valida cada transición, registra las fechas (`submitted_at`, `reviewed_at`, `cancelled_*`) y audita `STATUS_CHANGED`. "Autorizada" y "Rechazada" sólo admiten `CANCELLED`, que es final. `EDITABLE_STATUSES` (Borrador, Cargada, Observaciones) controla la carga, la verificación y el envío (`submission_service.submit_invoice`: bloqueo de fila → editable → recálculo → motor). `invoices.status` es `VARCHAR(19)` con el `CHECK invoicestatus`.
- **CFDI:** `xml_service` extrae `MetodoPago` como `payment_method`. El motor guarda esos datos en `metadata_json` del documento `INVOICE_XML` vigente (`validation_engine`), y el detalle los muestra. El catálogo "Métodos de pago" trae `PUE` y `PPD`. El valor esperado inicial de las Reglas de Validación es `PPD` (0007).
- **Documentos:** `invoice_document_types` ya contiene `PAYMENT_COMPLEMENT_XML` y `PAYMENT_COMPLEMENT_PDF` (Opcional / No aplica), pero el Administrador puede editar sus niveles. `FIXED_REQUIREMENTS` y `ck_invoice_document_types_fixed_levels` fijan los niveles del CFDI, del Invoice y del acuse. La carga documental (`POST /invoices/{id}/documents`) exige estado editable y recalcula Borrador/Cargada.
- **Correos:** `review_service` asocia cada estatus con su evento (`EVENTS`). Compone y envía con `notification_service.notify` después del commit, y ofrece el reenvío cuando el último envío del evento del estatus actual falló. `MAILBOX_EVENTS` distingue los eventos que van al buzón de los que van al proveedor. Las columnas `event` de `notification_templates`, `notification_copies` y `email_deliveries` son `VARCHAR(20)` con el `CHECK notificationevent`, que se reemplazó en 0006.
- **Plazos:** `CANCELLATION_WINDOW = timedelta(hours=72)` ya sienta el precedente de las horas naturales guardadas en UTC.

## Goals / Non-Goals

**Goals:**
- Registrar el pago de una factura autorizada y avisarlo al proveedor por correo.
- Pedir el Complemento de Pago sólo cuando corresponde (nacional + PPD), recibirlo en la factura pagada y avisar a Recepción de Facturas.
- Hacer cumplir el plazo de 72 horas con un bloqueo de envíos que se calcula en el momento, sin tareas programadas.
- Que el "Complemento de pago" quede siempre como Opcional en la configuración de requisitos.

**Non-Goals:**
- Fecha, monto o referencia del pago, pagos parciales y revertir un pago.
- Recordatorios automáticos y tareas en segundo plano.
- Validar el complemento ante el SAT o cuadrar sus importes.
- Reenvío por el PMO del correo "Complemento de pago adjuntado".

## Decisions

### D1. `PAID` en el modelo de estatus
`InvoiceStatus.PAID = "PAID"` con la etiqueta "Pagada". `ALLOWED_TRANSITIONS[ACCEPTED]` pasa a `{PAID, CANCELLED}`, y `PAID` no tiene salidas. Así la cancelación desde "Pagada" responde 409 sin lógica extra en `cancellation_service`. Sólo se agrega una verificación previa para dar el mensaje "Una factura pagada no se puede cancelar" antes de leer el archivo. `PAID` no entra en `EDITABLE_STATUSES`, así que la verificación, el envío y la decisión ya responden 409, y la factura no entra en la bandeja (que filtra "Enviada"). `PAID` mide 4 caracteres: la columna no cambia.

*Alternativa:* un indicador `is_paid` sobre "Autorizada". Se descarta porque la HU habla de "actualizar como Pagada", y el filtro, el tablero y el historial ya trabajan por estatus.

### D2. Datos del pago y del complemento en `invoices`
Cuatro columnas:
- `paid_at` (`UTCDateTime`);
- `paid_by` (FK `users.id` `RESTRICT`, indexada);
- `payment_complement_due_at` (`UTCDateTime`, nulo si no se requiere);
- `payment_complement_received_at` (`UTCDateTime`).

`transition_invoice` llena `paid_at`/`paid_by` al pasar a `PAID`, igual que con la cancelación. `payment_service` llena la fecha límite (D3).

`ck_invoices_payment`:
```
(status = 'PAID' AND paid_at IS NOT NULL AND paid_by IS NOT NULL
   AND (payment_complement_due_at IS NULL OR payment_complement_due_at > paid_at)
   AND (payment_complement_received_at IS NULL OR payment_complement_due_at IS NOT NULL))
OR (status <> 'PAID' AND paid_at IS NULL AND paid_by IS NULL
   AND payment_complement_due_at IS NULL AND payment_complement_received_at IS NULL)
```
"Requiere complemento" equivale a `payment_complement_due_at IS NOT NULL`, y "pendiente" a `received_at IS NULL`. No hace falta una columna booleana adicional. El requisito queda fijo al pagar (spec `pago-facturas`).

Índice parcial `ix_invoices_pending_complement (supplier_id, payment_complement_due_at) WHERE status = 'PAID' AND payment_complement_due_at IS NOT NULL AND payment_complement_received_at IS NULL`. Hace barata la consulta del bloqueo en cada envío y la del aviso en el tablero.

*Alternativa:* una tabla `payments`. Es innecesaria mientras haya un único pago por factura (Non-Goals). Puede introducirse si llegan los pagos parciales.

### D3. `payment_service`
Nuevo `app/services/payment_service.py`, sin commit:
- `requires_complement(db, invoice) -> bool`: el proveedor es `NATIONAL` y `metadata_json["payment_method"]` del `INVOICE_XML` vigente es `"PPD"`. Se lee el dato que ya extrajo el motor, sin volver a leer el XML: la factura se autorizó con esos resultados.
- `mark_paid(db, invoice, user_id)`: `lock_invoice`; 409 "La factura ya fue pagada" si ya lo está; 409 "Sólo una factura autorizada se puede marcar como pagada" si no está "Autorizada"; `transition_invoice(PAID)`; si `requires_complement`, `payment_complement_due_at = paid_at + PAYMENT_COMPLEMENT_WINDOW`, y si ya existe un XML del complemento vigente y válido, `received_at` es la fecha de esa carga; audita `INVOICE_PAID`.
- `complement_notice(invoice) -> str`: el texto de `aviso_complemento`, o `""` si la factura no requiere complemento. Lo usan el envío y el reenvío, de modo que el reenvío reproduce la misma fecha límite.
- `pending_complements(db, supplier_id) -> list[Invoice]`: complementos pendientes ordenados por fecha límite. `overdue_complements` filtra `due_at <= now`.
- `ensure_no_overdue_complements(db, supplier_id)`: lanza `BusinessRuleError` con el mensaje de la spec y los números de factura.
- `register_complement(db, invoice, document, user_id)`: primera carga → `received_at`; audita `PAYMENT_COMPLEMENT_UPLOADED`.

`PAYMENT_COMPLEMENT_WINDOW = timedelta(hours=72)` va en `constants.py`, junto a `CANCELLATION_WINDOW`.

El router `POST /invoices/{id}/payment` exige CSRF y `PMO`/`Administrador` (el mismo guard que la decisión), llama a `mark_paid`, confirma, envía el correo (D5) y redirige con el id del envío, como `POST /invoices/{id}/review`.

### D4. Carga del complemento en una factura "Pagada"
La carga documental es la misma ruta. Hoy el router hace `ensure_editable` y después recalcula. Con el cambio:
- `document_requirements_service.offered_types(db, invoice)` devuelve sólo los dos tipos del complemento si la factura está `PAID` y requiere complemento. La página reutiliza la plantilla con el checklist sin contador de obligatorios.
- En la ruta `POST`, antes de `ensure_editable`, si `invoice.status == PAID` se delega a `payment_service`. El servicio responde 409 si no requiere complemento o si el tipo no es de complemento. No hay `sync_upload_status` ni se ejecuta el motor. Las demás verificaciones de archivo (`save_invoice_file`, formato del tipo) se mantienen.
- La verificación del CFDI de pago (D6) se aplica a todo `PAYMENT_COMPLEMENT_XML`, en cualquier estatus, antes de escribir el archivo.

El bloqueo de fila (`lock_invoice`) se toma como en cualquier carga, así que una carga y un pago simultáneos se ejecutan en orden.

*Alternativa:* una ruta propia `POST /invoices/{id}/payment-complement`. Duplicaría la validación de archivos y el reemplazo con historial (`replaced_document_id`). Reutilizar la carga mantiene un solo camino de escritura en `storage/`.

### D5. Correos con el mecanismo de HU-20
- `NotificationEvent` agrega `INVOICE_PAID` (12 caracteres) y `PAYMENT_COMPLEMENT` (18). Ambos caben en `VARCHAR(20)`. El nombre `PAYMENT_COMPLEMENT_UPLOADED` se reserva para la acción de auditoría (`String(80)`), porque como evento obligaría a ampliar tres columnas.
- `review_service.EVENTS[PAID] = INVOICE_PAID` (va al proveedor: no entra en `MAILBOX_EVENTS`). `send_notification` toma `fecha_estatus = paid_at` y `aviso_complemento = payment_service.complement_notice(invoice)` cuando el estatus es `PAID`. Con eso, `last_delivery`, `can_resend` y `prepare_resend` cubren "Pagada" sin cambios de forma.
- El correo del complemento lo envía `payment_service.notify_complement(db, invoice, user_id)` después del commit de la carga, con `fecha_estatus = uploaded_at`. No entra en `EVENTS`: no es el correo de un estatus y no tiene reenvío (Non-Goals).

### D6. Lectura del CFDI de pago
`xml_service.parse_payment_complement(content) -> {"uuid", "related_uuids"}` usa el mismo parser endurecido de `xml_service` (sin entidades externas). Verifica que el comprobante sea `cfdi:Comprobante` con `TipoDeComprobante="P"`. Extrae el UUID del `tfd:TimbreFiscalDigital` y los `IdDocumento` de cada `pago20:DoctoRelacionado`, también de `pago10` por compatibilidad. La comparación con `invoice.uuid` ignora mayúsculas y espacios. `invoice.uuid` lo asigna el motor desde el timbre del XML de la factura. Si una factura PPD pagada no lo tiene, ningún complemento puede relacionarla: se rechaza con el mensaje de "no relaciona la factura", y el caso queda cubierto por una prueba.

*Alternativa:* aceptar cualquier XML. Bastaría con subir un archivo cualquiera para levantar el bloqueo, y el aviso a Recepción no serviría de nada.

### D7. Plantillas: variable condicional `aviso_complemento`
`notification_templates.VARIABLES` agrega `aviso_complemento` y un conjunto `CONDITIONAL_VARIABLES = {"aviso_complemento"}`. En la validación de la plantilla es obligatoria: el Administrador no puede quitar el aviso del cuerpo. En la composición, una variable condicional puede llegar vacía. Si llega vacía, se elimina la línea que sólo la contenía y las líneas en blanco consecutivas se reducen a una.

*Alternativas:*
- Dos plantillas, "Pagada" y "Pagada con complemento". El Administrador tendría que mantener dos textos casi iguales, y existirían dos eventos con dos listas de copias.
- Un párrafo fijo agregado por el código. No sería editable, a diferencia del resto de los correos (HU-05).

### D8. Bloqueo del envío calculado en el momento
`submit_invoice` llama a `payment_service.ensure_no_overdue_complements(db, invoice.supplier_id)` justo después de verificar que la factura es editable y antes de `sync_upload_status`. Se reutiliza el mismo `BusinessRuleError` (409) que ya pinta el router. El vencimiento se evalúa con la hora actual en cada envío, así que no se necesita un proceso que "active" el bloqueo a las 72 horas. Adjuntar el complemento lo levanta de inmediato. "Verificar", el alta y la carga no llaman a esta función (S5).

La consulta de complementos vencidos no bloquea las filas de las otras facturas. Si la carga del complemento ocurre al mismo tiempo que un envío, el resultado depende del orden de llegada, lo que es aceptable: en el peor caso el proveedor vuelve a enviar.

### D9. Niveles fijos del complemento
`FIXED_REQUIREMENTS` agrega `PAYMENT_COMPLEMENT_XML` y `PAYMENT_COMPLEMENT_PDF` (Nacional `OPTIONAL`, Internacional `NOT_APPLICABLE`) con el motivo "Se carga después del pago de la factura". El mismo cambio va en `ck_invoice_document_types_fixed_levels`. La migración primero normaliza los niveles de esos dos tipos, auditando el cambio si había otro valor, y después reemplaza el `CHECK`. La pantalla de configuración ya pinta los niveles fijos con candado.

### D10. Vistas
- Detalle: panel "Pago" (PMO/Admin en "Autorizada"); aviso "Pagada el …"; bloque "Complemento de pago" (spec `pago-facturas`); enlace "Adjuntar Complemento de Pago" para el proveedor; el resultado del correo, igual que en la decisión.
- Tablero y listado del proveedor: aviso "Tiene complementos de pago pendientes", a partir de `pending_complements` (una consulta por página, sobre el índice de D2).
- Historial (`invoice_history_service`): lee las auditorías `INVOICE_PAID` y `PAYMENT_COMPLEMENT_UPLOADED` con el `_audited` que ya existe. Al proveedor le muestra "PMO" como autor del pago.
- Filtro de estatus y tablero: sale de `STATUS_LABELS`; se agrega el indicador "Pagadas".

## Risks / Trade-offs

- [El XML vigente no trae `MetodoPago`, o el proveedor lo reemplazó después de la autorización] → La factura "Autorizada" ya no es editable, así que el XML no cambia después de la validación. Sin dato, la factura no requiere complemento (spec). Queda registrado en la auditoría `INVOICE_PAID` (`requires_complement: false`).
- [Un proveedor queda bloqueado por un complemento que Recepción recibió por otro medio] → El bloqueo sólo se levanta adjuntando el complemento. El proveedor puede adjuntarlo en cualquier momento. No se agrega una dispensa manual (posible HU futura).
- [El correo "Pagada" falla y el proveedor no se entera del plazo] → El envío fallido queda en la bitácora y el detalle ofrece "Reenviar notificación" al PMO. El aviso en el tablero del proveedor muestra el plazo aunque no llegue el correo.
- [Complementos que relacionan varias facturas (un pago de varias PPD)] → La verificación sólo exige que el complemento relacione el UUID de la factura donde se carga. El mismo XML puede cargarse en cada factura que relaciona.
- [Zona horaria] → Las fechas se guardan en UTC y se muestran en la zona de negocio, como la cancelación.

## Migration Plan

`0018_invoice_payment`:
1. Reemplazar el `CHECK invoicestatus` con `PAID`.
2. Agregar las cuatro columnas, la FK `paid_by`, `ck_invoices_payment` y el índice parcial.
3. Reemplazar el `CHECK notificationevent` de las tres tablas con `INVOICE_PAID` y `PAYMENT_COMPLEMENT`. Insertar las dos plantillas en la versión 1 y sus dos listas de copias vacías.
4. Normalizar los niveles de `PAYMENT_COMPLEMENT_XML`/`PDF` (auditando si cambian) y reemplazar `ck_invoice_document_types_fixed_levels`.

`downgrade` falla con un mensaje explícito si existen facturas `PAID` o envíos de los eventos nuevos (son evidencia). Si no existen, revierte en orden inverso. Hay que respaldar la base antes de actualizar (`scripts/backup.py`), como en las demás revisiones.

## Open Questions

- ¿La HU quiere decir "PPD" (método de pago del CFDI) cuando dice "PDD"? Se asume que sí (S1). Si se refiere a otra cosa, por ejemplo la forma de pago `99` "Por definir", sólo cambia `requires_complement`.
- ¿El bloqueo debe aplicar también a los reenvíos desde "Observaciones"? Se asume que sí (S5).
- ¿Se necesita capturar la fecha real del pago en lugar de usar la fecha del registro? Hoy queda fuera de alcance. Si se captura, el plazo de 72 horas debería contarse desde el registro en el portal y no desde una fecha pasada.
