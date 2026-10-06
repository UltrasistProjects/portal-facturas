## Why

La HU "Complemento de Pagos" pide que, cuando el PMO o el Administrador marquen como "Pagada" una factura, el proveedor (nacional o internacional) reciba un correo que le avise que su factura fue pagada. Si la factura es de un proveedor nacional con método de pago PPD (pago en parcialidades o diferido), el correo debe pedirle además que adjunte su "Complemento de Pago". Cuando lo adjunte, el sistema debe avisar a "Recepción de Facturas". Si no lo adjunta en 72 horas, el portal debe bloquear el envío de sus facturas siguientes. Así ULTRASIST tiene a tiempo el CFDI de pago que el SAT exige para las facturas PPD.

Hoy nada de esto existe. No hay estatus "Pagada": "Autorizada" sólo admite la cancelación. Una factura que ya no es editable no puede recibir documentos. El envío a validación no revisa nada del historial del proveedor. Ya existen la base del catálogo de documentos (HU-04), con "Complemento de pago (XML)" y "Complemento de pago (PDF)" como Opcional para Nacional, las plantillas de correo (HU-05), el buzón y el servicio de envío (HU-08), y la forma de enviar los correos de la decisión después del commit, con reenvío (HU-20).

## What Changes

- **Estatus "Pagada"** (`PAID`), final, al que sólo se llega desde "Autorizada". Una factura "Pagada" no admite cancelación, decisión del PMO, verificación ni envío. Sólo admite la carga de su Complemento de Pago cuando lo requiere.
- **Marcar como pagada:** en el detalle de una factura "Autorizada", el PMO o el Administrador usan "Marcar como pagada" (`POST /invoices/{id}/payment`). El sistema bloquea la fila, registra `paid_at`, `paid_by` y la auditoría, y decide si la factura requiere Complemento de Pago: proveedor nacional y `MetodoPago = PPD` en el XML del CFDI vigente. Si lo requiere, guarda la fecha límite `payment_complement_due_at = paid_at + 72 horas`.
- **Correo "Pagada" al proveedor** (`INVOICE_PAID`), enviado después del commit al correo del proveedor en el catálogo, con el texto "su factura <número> ha sido pagada". Sólo en las facturas nacionales PPD, el correo agrega el aviso "Es importante que adjunte su “Complemento de Pago” a dicha factura pagada", con la fecha límite y la consecuencia de no hacerlo. Si el envío falla, se puede reenviar como los correos de la decisión.
- **Carga del Complemento de Pago en la factura "Pagada":** el proveedor puede cargar el XML y el PDF del complemento por la carga documental, aunque la factura ya no sea editable. El XML debe ser un CFDI de tipo `P` que relacione el UUID de la factura. La factura cuenta como "complemento adjuntado" desde la primera carga válida del XML.
- **Correo a "Recepción de Facturas"** (`PAYMENT_COMPLEMENT`) en cada carga del XML del complemento: "El Complemento de Pago ha sido adjuntado a la factura <número>".
- **Bloqueo por complementos vencidos:** cada envío a validación (`POST /invoices/{id}/submit`) revisa, antes de ejecutar el motor, si el proveedor tiene facturas "Pagada" con un complemento requerido sin adjuntar y con la fecha límite vencida. Si las tiene, responde HTTP 409 con la lista de esas facturas y no ejecuta el motor. El tablero y el listado del proveedor muestran sus complementos pendientes y vencidos.
- **"Complemento de pago" Opcional en la configuración de requisitos:** los tipos `PAYMENT_COMPLEMENT_XML` y `PAYMENT_COMPLEMENT_PDF` pasan a tener niveles fijos: Opcional para Nacional y No aplica para Internacional, con el motivo "Se carga después del pago de la factura". Así se cumple la nota de la HU y se evita que un Administrador los haga Obligatorios. Eso impediría enviar cualquier factura nacional, porque el complemento sólo existe después del pago.
- **Plantillas y destinatarios:** dos plantillas nuevas, "Pagada" y "Complemento de pago adjuntado", y sus listas de copias. La plantilla "Pagada" usa la variable `{{aviso_complemento}}`: es obligatoria en el cuerpo y sólo tiene valor en las facturas PPD.
- **Detalle, historial, tablero y listado:** el estatus "Pagada" aparece en los filtros y en un indicador del tablero. El detalle muestra el bloque "Complemento de pago": No requerido, Pendiente hasta <fecha>, Vencido desde <fecha> o Adjuntado el <fecha>. El historial incluye el pago y cada carga del complemento.
- **Migración** `0018_invoice_payment`: estatus `PAID`, columnas del pago y del complemento con su `CHECK`, eventos y plantillas nuevos, listas de copias vacías y niveles fijos de los complementos.

**Fuera de alcance:**
- capturar la fecha, el monto o la referencia bancaria del pago, o registrar pagos parciales. El pago se marca una vez y su fecha es la del registro en el portal;
- revertir una factura "Pagada";
- recordatorios automáticos antes de que venza el plazo (no hay tareas programadas en el PoC);
- validar el complemento ante el SAT o cuadrar sus importes (`ImpPagado`, `ImpSaldoInsoluto`) contra la factura;
- el reenvío por el PMO del correo "Complemento de pago adjuntado": su resultado queda en la bitácora y lo ve el proveedor.

## Supuestos

- **S1.** La "forma de pago PDD" de la HU es el método de pago **PPD** del CFDI (atributo `MetodoPago`, catálogo "Métodos de pago": PUE / PPD). El valor se toma del XML del CFDI vigente de la factura, ya extraído por el motor de validación.
- **S2.** El "correo del contacto del proveedor" es el correo del proveedor en el catálogo (`suppliers.email`). Es el mismo destinatario de los correos de Rechazada y Observaciones.
- **S3.** Las 72 horas son naturales y se cuentan desde que la factura se marca "Pagada" en el portal, igual que el plazo de la cancelación (HU-14).
- **S4.** El complemento cuenta como adjuntado con su XML, que es el CFDI de pago. El PDF es opcional y su carga no envía correo.
- **S5.** El bloqueo aplica a todos los envíos a validación del proveedor, incluidos los reenvíos desde "Observaciones". No impide dar de alta facturas ni cargar sus documentos. Se levanta en cuanto se adjuntan los complementos vencidos.
- **S6.** Una factura "Pagada" no se cancela en el portal.

## Capabilities

### New Capabilities
- `pago-facturas`: marcar una factura como "Pagada", correo al proveedor con el aviso condicional del complemento, carga y validación del Complemento de Pago en la factura pagada, correo a Recepción de Facturas, plazo de 72 horas y bloqueo de envíos por complementos vencidos.

### Modified Capabilities
- `flujo-facturas`: el modelo de estatus agrega "Pagada" y la transición `ACCEPTED → PAID`. El envío a validación revisa primero los complementos vencidos. El tablero y el filtro de estatus incluyen "Pagada".
- `archivos-minimos-factura`: niveles fijos del Complemento de pago (XML y PDF). La carga documental admite el complemento en una factura "Pagada" que lo requiere.
- `plantillas-notificacion`: plantillas "Pagada" (con `{{aviso_complemento}}`) y "Complemento de pago adjuntado", sus variables, textos predeterminados, orden del listado y datos de ejemplo.
- `notificaciones-correo`: destinatarios y listas de copias de los dos eventos nuevos.
- `revision-pmo`: el historial muestra el pago y el complemento. El reenvío de la notificación también aplica al correo "Pagada".
- `cancelacion-facturas`: una factura "Pagada" no se puede cancelar.
- `integridad-datos`: enumeraciones con `PAID` y los dos eventos nuevos, `CHECK` de los datos del pago y niveles fijos de los complementos.

## Impact

- **Código:**
  - `app/core/constants.py`: `InvoiceStatus.PAID` y su etiqueta, transiciones, `NotificationEvent.INVOICE_PAID` y `PAYMENT_COMPLEMENT`, `PAYMENT_COMPLEMENT_WINDOW`, niveles fijos de los complementos;
  - `app/models/__init__.py`: columnas `paid_at`, `paid_by`, `payment_complement_due_at`, `payment_complement_received_at` y su `CHECK`;
  - nuevo `app/services/payment_service.py` (marcar pagada, complemento requerido, carga del complemento, complementos pendientes y vencidos);
  - `app/services/submission_service.py` (bloqueo), `app/services/review_service.py` (correo y reenvío de "Pagada"), `app/services/notification_templates.py`, `app/services/notification_service.py`, `app/services/xml_service.py` (lectura del CFDI de pago), `app/services/invoice_history_service.py`, `app/services/document_requirements_service.py`;
  - `app/routers/invoices.py` (`POST /invoices/{id}/payment`, carga del complemento, contexto del detalle) y `app/routers/dashboard.py`.
- **Plantillas:** `invoices/detail.html` (panel "Pago", bloque "Complemento de pago"), `invoices/documents.html`, `dashboard.html`, listado de facturas y páginas de administración de plantillas y notificaciones.
- **Esquema:** revisión Alembic `0018_invoice_payment`.
- **Demo:** `scripts/seed_db.py` con una factura nacional PPD "Pagada" (`PAGADA-001`) y su complemento ya adjuntado: uno pendiente vencería a las 72 horas y bloquearía los envíos del proveedor demo.
- **Pruebas:** nuevo `tests/test_pago_facturas.py`. Ajustes en `tests/test_migraciones.py`, `tests/test_integridad.py`, `tests/test_archivos_minimos.py`, `tests/test_plantillas_notificacion.py`, `tests/test_notificaciones_correo.py`, `tests/test_cambio_estatus.py`, `tests/test_seguimiento_estatus.py`, `tests/test_cancelacion.py` y las pruebas que enumeran estatus, eventos o tipos con nivel fijo. Escenario nuevo en la suite Playwright de HUs (`tests/hu`).
- **Documentación:** `README.md`.
