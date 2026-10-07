> Todas las rutas son relativas a la raíz de la PoC (`PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress-V1/PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress/`). Cada grupo termina con `ruff` limpio y sus pruebas en verde sobre PostgreSQL.

## 1. Modelo y esquema

- [x] 1.1 `app/core/constants.py`: `InvoiceStatus.PAID` ("Pagada"), `ACCEPTED → {PAID, CANCELLED}`, `PAYMENT_COMPLEMENT_WINDOW`, `NotificationEvent.INVOICE_PAID` y `PAYMENT_COMPLEMENT`, niveles fijos y motivo de `PAYMENT_COMPLEMENT_XML`/`PDF` (D1, D5, D9).
- [x] 1.2 `app/models/__init__.py`: `paid_at`, `paid_by`, `payment_complement_due_at`, `payment_complement_received_at`, `ck_invoices_payment`, índice parcial `ix_invoices_pending_complement` y complementos en `ck_invoice_document_types_fixed_levels` (D2, D9).
- [x] 1.3 `app/services/invoice_service.py`: `transition_invoice` registra `paid_at`/`paid_by` al pasar a `PAID` (D2).
- [x] 1.4 Revisión `alembic/versions/0018_invoice_payment.py`: `CHECK` de estatus y de eventos, columnas, FK, `CHECK`, índice, dos plantillas en la versión 1, dos listas de copias vacías, normalización auditada de los niveles del complemento y downgrade protegido (Migration Plan). `alembic check` sin diferencias.

## 2. Plantillas y notificaciones

- [x] 2.1 `app/services/notification_templates.py`: eventos "Pagada" y "Complemento de pago adjuntado" con destinatario, variables, obligatorias y textos predeterminados; variable condicional `aviso_complemento` en la validación y en la composición (eliminar la línea vacía y colapsar las líneas en blanco); dato de ejemplo de la vista previa; orden del listado (D7).
- [x] 2.2 `app/services/notification_service.py` y la pantalla `/admin/notifications`: destinatarios de los eventos nuevos y sus listas de copias (spec `notificaciones-correo`).

## 3. Pago y complemento

- [x] 3.1 `app/services/xml_service.py`: `parse_payment_complement` (tipo `P`, UUID del timbre, `IdDocumento` de `pago20`/`pago10`) con el parser endurecido (D6).
- [x] 3.2 Nuevo `app/services/payment_service.py`: `requires_complement`, `mark_paid`, `complement_notice`, `pending_complements`, `overdue_complements`, `ensure_no_overdue_complements`, `register_complement` y `notify_complement` (D3, D5).
- [x] 3.3 `app/services/review_service.py`: `EVENTS[PAID]`, `send_notification` con `paid_at` y `aviso_complemento`; reenvío de "Pagada" (D5).
- [x] 3.4 `app/services/submission_service.py`: `ensure_no_overdue_complements` después de comprobar que la factura es editable y antes del recálculo (D8).
- [x] 3.5 `app/services/document_requirements_service.py`: tipos ofrecidos y checklist en una factura "Pagada"; verificación del XML del complemento en cualquier estatus (D4).
- [x] 3.6 `app/services/cancellation_service.py`: 409 "Una factura pagada no se puede cancelar" antes de leer el archivo (D1).
- [x] 3.7 `app/services/invoice_history_service.py`: eventos "Pagada" (con la fecha límite del complemento) y "Complemento de pago adjuntado"; "PMO" para el proveedor (D10).

## 4. Rutas y vistas

- [x] 4.1 `app/routers/invoices.py`: `POST /invoices/{id}/payment` (CSRF, PMO/Administrador, redirección con el id del envío); carga del complemento en "Pagada" con su correo a Recepción y su resultado para el proveedor; contexto del detalle (D3, D4, D5).
- [x] 4.2 `invoices/detail.html`: panel "Pago" con confirmación, aviso "Pagada el …", bloque "Complemento de pago", enlace "Adjuntar Complemento de Pago", sin "Cancelar factura" en "Pagada"; `app.css`: `.status-paid` y estilos del bloque, sin estilos en línea (D10).
- [x] 4.3 `invoices/documents.html`: modo "Pagada" con sólo los complementos y sin contador de obligatorios.
- [x] 4.4 `app/routers/dashboard.py`, `dashboard.html` e `invoices/list.html`: indicador "Pagadas", filtro "Pagada" y aviso "Tiene complementos de pago pendientes" para el proveedor (D10).
- [x] 4.5 `scripts/seed_db.py`: factura demo nacional PPD "Pagada" con el complemento ya adjuntado (uno pendiente venceria a las 72 h y bloquearia los envios del proveedor demo) y `data/demo_documents/complemento_pago_demo.xml`.

## 5. Pruebas

- [x] 5.1 Nuevo `tests/test_pago_facturas.py`: marcar como pagada (roles, CSRF, estatus, simultaneidad), complemento requerido (nacional PPD / PUE / internacional / sin XML), correo "Pagada" con y sin aviso y sin líneas en blanco repetidas, servidor caído y reenvío.
- [x] 5.2 Complemento: carga en "Pagada" (tipos admitidos, 409 de otros tipos y de facturas sin requisito), XML no tipo `P`, otro UUID, factura sin UUID, PDF sin correo, reemplazo con un segundo correo y `received_at` conservado, correo a Recepción y resultado para el proveedor.
- [x] 5.3 Bloqueo: vencido a las 73 h, no vencido a las 71 h, reenvío desde "Observaciones", otro proveedor, levantado al adjuntar, alta y carga permitidas; aviso en el tablero y en el listado con el orden vencidos → pendientes.
- [x] 5.4 Transiciones de "Pagada", cancelación rechazada, historial y reenvío: cubiertos en `tests/test_pago_facturas.py` junto con 5.1–5.3 (reutiliza los helpers de `tests/test_cancelacion.py`); `tests/test_registro_envio.py` agrega "Pagada" al filtro.
- [x] 5.5 `tests/test_plantillas_notificacion.py` y `tests/test_notificaciones_correo.py`: siete plantillas, variables, `aviso_complemento` obligatoria y vacía, vista previa, destinatarios y copias de los eventos nuevos.
- [x] 5.6 `tests/test_archivos_minimos.py`, `tests/test_migraciones.py` y `tests/test_integridad.py`: niveles fijos del complemento (pantalla, 409, SQL), migración 0018 con niveles modificados y downgrade protegido, `CHECK` del pago, enumeraciones.
- [x] 5.7 Ajustar las pruebas que enumeran estatus, eventos, plantillas o facturas demo (`tests/test_registro_envio.py`, `tests/test_respaldos.py`, `tests/test_demo_workflow.py`).
- [x] 5.8 Suite Playwright de HUs: nuevo `tests/hu/specs/21-HU-23-complemento-pagos.spec.ts` (requisitos con el complemento Opcional, factura PPD autorizada, marcar como pagada, correo al proveedor con el aviso, complemento pendiente en el tablero, complemento inválido rechazado, complemento adjuntado con correo a Recepción e historial), CFDI PPD y complemento en `tests/hu/fixtures/herramientas.py`, HU-23 en `hu-catalogo.json`, `INDICE_HUs.md` y `DEPENDENCIAS_HUs.md`. Corrida RMUVVE30F: 21/21 PASS; evidencias en `evidencias/HU-23/` y `EVIDENCIA-PRUEBAS-HUs.pdf` regenerado. El bloqueo de 72 h queda en pytest (la suite no modifica la base).

## 6. Documentación y verificación

- [x] 6.1 `README.md`: estatus "Pagada", Complemento de Pago, plazo de 72 horas, bloqueo y correos nuevos.
- [x] 6.2 `python scripts/check.py` en verde.
