> Todas las rutas son relativas a la raíz de la PoC (`PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress-V1/PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress/`). Cada grupo termina con `ruff` limpio y sus pruebas en verde sobre PostgreSQL.

## 1. Retiro de ClickBalance

- [x] 1.1 `app/core/constants.py`: `InvoiceStatus`, etiquetas y `ALLOWED_TRANSITIONS` sin ClickBalance; `app/services/invoice_service.py` sin `next_clickbalance_status` (D6).
- [x] 1.2 Revisión `alembic/versions/0011_retire_clickbalance.py` (datos con `STATUS_MIGRATED`, `CHECK` de seis estatus, columna `VARCHAR(19)` y downgrade).
- [x] 1.3 `scripts/seed_db.py`: `OBSERVACIONES-001` y `ENVIADA-002` en lugar de `CLICK-READY` y `CLICK-DONE`.

## 2. Decisión y correos

- [x] 2.1 Nuevo `app/services/review_service.py`: `decide`, `notify_decision`, `send_notification`, `last_delivery`, `can_resend` y `prepare_resend` (D1, D3, D4, D5); se retira `invoice_service.review_invoice`.
- [x] 2.2 `app/routers/invoices.py`: `GET /review` redirige, `POST /review` decide y notifica, `POST /notification` reenvía, contexto del resultado del envío; se retira `POST /clickbalance`.
- [x] 2.3 `invoices/detail.html`: panel "Decisión", resultado del correo, "Reenviar notificación", "Decidir" en el encabezado; sin botones de ClickBalance. Se elimina `invoices/review.html`.
- [x] 2.4 `app/static/js/review_decision.js` y estilos del panel.

## 3. Pruebas

- [x] 3.1 `tests/test_cambio_estatus.py`: panel por rol y estatus, tres decisiones, `COMMENT` 400, proveedor 403, redirección de `/review`, observaciones obligatorias y longitud, factura no enviada 409, decisión repetida 409, bloqueo crítico.
- [x] 3.2 Correos: autorización a Recepción con el texto de RN-HU20-02, rechazo y observaciones al proveedor, resultado en el detalle, id ajeno sin mensaje, servidor caído con la decisión conservada.
- [x] 3.3 Reenvío: botón sólo con envío fallido, reenvío exitoso con auditoría, 409 sin falla previa.
- [x] 3.4 `tests/test_migraciones.py`: `0011` migra ClickBalance a Autorizada con auditoría y el downgrade; `tests/test_integridad.py`: estatus retirado rechazado.
- [x] 3.5 Ajustar `tests/test_errores.py`, `tests/test_observabilidad.py`, `tests/test_demo_workflow.py` y las pruebas que deciden con `POST /review`.

## 4. Documentación y verificación

- [x] 4.1 `README.md`: decisión del PMO, correos, reenvío y retiro de ClickBalance.
- [x] 4.2 `python scripts/check.py` en verde.
- [x] 4.3 Verificación en navegador como PMO: decidir las tres opciones, observaciones obligatorias, `.eml` de cada correo, falla y reenvío.
- [x] 4.4 `openspec validate cambio-estatus-factura --strict` sin errores.
