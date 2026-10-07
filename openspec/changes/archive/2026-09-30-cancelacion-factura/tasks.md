> Todas las rutas son relativas a la raíz de la PoC (`PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress-V1/PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress/`). Cada grupo termina con `ruff` limpio y sus pruebas en verde sobre PostgreSQL.

## 1. Modelo y esquema

- [x] 1.1 `app/core/constants.py`: `InvoiceStatus.CANCELLED` y su etiqueta, transiciones a "Cancelada", `CANCELLATION_WINDOW`, `DocumentType.CANCELLATION_ACK` con su nivel fijo y motivo (D1, D2, D3).
- [x] 1.2 `app/models/__init__.py`: columnas de la cancelación, `ck_invoices_cancellation` y el acuse en `ck_invoice_document_types_fixed_levels`.
- [x] 1.3 `app/services/invoice_service.py`: `transition_invoice` fecha la cancelación (D2).
- [x] 1.4 Revisión `alembic/versions/0012_invoice_cancellation.py` con el tipo del sistema, el conflicto de nombre y el downgrade (D8); `alembic check` sin diferencias.

## 2. Cancelación y correo

- [x] 2.1 Nuevo `app/services/cancellation_service.py`: `check_request` y `cancel` (D4).
- [x] 2.2 `app/services/review_service.py`: evento de "Cancelada", `send_notification` generalizado y `DECIDED` (D5).
- [x] 2.3 `app/services/foreign_invoice_service.py`: duplicados sin facturas canceladas (D6).
- [x] 2.4 `app/routers/invoices.py`: `POST /invoices/{id}/cancel`, error de la sección y resultado del correo para el proveedor (D4, D5).
- [x] 2.5 `invoices/detail.html` y `app.css`: sección "Cancelar factura", aviso de factura cancelada, resultado del correo, texto del reenvío y `.status-cancelled` (D7).
- [x] 2.6 `scripts/seed_db.py`: `CANCELADA-001` con su acuse (D9).

## 3. Pruebas

- [x] 3.1 `tests/test_cancelacion.py`: sección por rol y estatus, 403 del PMO, 404 de otro proveedor, validaciones en orden sin escribir archivo, contenido inválido, acuse XML no CFDI, cancelación desde Enviada y Autorizada con fechas, repetida 409, cancelada sin carga, envío ni decisión, fuera de la bandeja.
- [x] 3.2 Correo: texto con la fecha límite al buzón, resultado para el proveedor sin direcciones, servidor caído con la cancelación conservada, reenvío del PMO, id de otro evento ignorado.
- [x] 3.3 Catálogo: acuse no ofrecido ni exigido, nivel fijo en la matriz del Administrador; FIN-007 y carga del Invoice con el nombre de una factura cancelada.
- [x] 3.4 `tests/test_migraciones.py` (0012, conflicto de nombre y downgrade) y `tests/test_integridad.py` (`CHECK` de la cancelación y nivel fijo por SQL).
- [x] 3.5 Ajustar las pruebas que cuentan facturas demo o enumeran estatus: `tests/test_respaldos.py` (12 facturas) y `tests/test_registro_envio.py` (etiquetas del filtro). `tests/test_archivos_minimos.py` y `tests/test_demo_workflow.py` no requirieron cambios.

## 4. Documentación y verificación

- [x] 4.1 `README.md`: cancelación, acuse, fecha límite y correo.
- [x] 4.2 `python scripts/check.py` en verde.
- [x] 4.3 Verificación en navegador: proveedor cancela con y sin acuse, `.eml` a Recepción, aviso en el detalle del PMO, falla y reenvío.
- [x] 4.4 `openspec validate cancelacion-factura --strict` sin errores.
