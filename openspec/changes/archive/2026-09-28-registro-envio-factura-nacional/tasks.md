> Todas las rutas son relativas a la raíz de la PoC (`PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress-V1/PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress/`). Cada grupo termina con `ruff` limpio y sus pruebas en verde sobre PostgreSQL.

## 1. Modelo de estatus y migración

- [x] 1.1 `app/core/constants.py`: `InvoiceStatus` sin `VALIDATING`, `VALIDATION_FAILED` ni `PREVALIDATED`; `STATUS_LABELS` y `ALLOWED_TRANSITIONS` de D1.
- [x] 1.2 Revisión `alembic/versions/0010_invoice_status_model.py` (`down_revision = "0009_supplier_profile"`): reasignación de D8 con el checklist en SQL, `STATUS_MIGRATED` por factura cambiada, `CHECK` `invoicestatus` de 8 valores y downgrade que restaura el de 11.
- [x] 1.3 `tests/test_migraciones.py`: `PREVALIDATED` completa → `UPLOADED` con su auditoría; `REQUIRES_CORRECTION` sin revisión y sin Vo.Bo. → `DRAFT`; devuelta por el PMO → `REQUIRES_CORRECTION`; `ACCEPTED` intacta y sin auditoría; `CHECK` que rechaza `PREVALIDATED`; downgrade.

## 2. Servicios

- [x] 2.1 `app/services/invoice_service.py`: `EDITABLE_STATUSES` de D1, `sync_upload_status(db, invoice, complete, user_id)` (D2) y retiro de `PREVALIDATABLE_STATUSES` y `ensure_prevalidatable`.
- [x] 2.2 `app/services/validation_engine.py`: `run_validation` sin transiciones; `validation.completed` con `failures` en lugar de `status` (D4).
- [x] 2.3 Nuevo `app/services/submission_service.py`: `submit_invoice` con el orden de D3 (bloqueo de fila, estatus, recálculo, motor, transición y `INVOICE_SUBMITTED`); devuelve si procedió y los resultados en `FAIL`.

## 3. Rutas e interfaz

- [x] 3.1 `app/routers/invoices.py`: `require_roles(Role.PROVIDER)` en alta, carga documental, "Verificar" y envío (D6); alta con el proveedor del usuario, estatus del proveedor y contrato propio y activo, en el orden de D7; contratos filtrados en el servidor.
- [x] 3.2 `app/routers/invoices.py`: la carga de documentos bloquea la fila (D5), expira `invoice.documents` tras el `flush` y llama a `sync_upload_status`; "Verificar" exige estatus editable y no cambia el estatus.
- [x] 3.3 `app/routers/invoices.py`: envío con `submission_service`; 303 con `?notice=submitted` o 409 con el detalle y las reglas en `FAIL` (D3). El detalle se arma en una función compartida por `GET /invoices/{id}` y el envío.
- [x] 3.4 `app/templates/invoices/new.html` y `app/static/js/app.js`: sin selector de proveedor, aviso sin contratos activos y copia de proyecto y líder al elegir contrato (D7).
- [x] 3.5 `app/templates/invoices/documents.html`: pasos "Información · Documentos · Envío", aviso "Factura cargada. Ya puede enviarla a validación", botones "Verificar" y "Enviar a validación" (D10).
- [x] 3.6 `app/templates/invoices/detail.html`: botones por estatus y rol, avisos "Factura enviada a validación" y "El envío no procedió", panel "Reglas que impiden el envío" (D10).
- [x] 3.7 `app/routers/dashboard.py`, `dashboard.html` y `invoices/list.html`: indicadores sin `PREVALIDATED`, etiquetas "Enviadas", "Observaciones" y "Autorizadas", y "Nueva factura" sólo para el proveedor; `app.css`: clases de estatus de D10.

## 4. Datos demo

- [x] 4.1 `scripts/seed_db.py`: estatus finales de D9 y `submitted_at` en las facturas enviadas o posteriores.
- [x] 4.2 `tests/test_demo_workflow.py`: el seed contiene los estatus de D9 y las páginas principales renderizan.

## 5. Pruebas

- [x] 5.1 Nuevo `tests/test_registro_envio.py`, registro: alta en "Borrador"; "Borrador" → "Cargada" al cargar el Vo.Bo. con `STATUS_CHANGED`; aviso de obligatorios completos; "Observaciones" no se recalcula; reemplazo en "Cargada".
- [x] 5.2 Envío: exitoso con `submitted_at` e `INVOICE_SUBMITTED`; XML-010 con esperado y detectado (409, sigue "Cargada"); reglas cambiadas después de verificar; desde "Borrador" sin ejecutar el motor; desde "Enviada"; reenvío desde "Observaciones"; `WARNING` no bloquea.
- [x] 5.3 Duplicados: UUID de otro proveedor sin revelar sus datos; UUID de una factura "Rechazada".
- [x] 5.4 Roles y contratos: 403 para INTERNAL y ADMIN en alta, carga, "Verificar" y envío; detalle del PMO sin botones; 404 sobre la factura de otro proveedor; HTML del alta sin contratos ajenos; `supplier_id` manipulado; contrato ajeno e inactivo (400); proveedor inactivo (409).
- [x] 5.5 "Verificar": no cambia el estatus y lista FIN-001 en "Reglas que impiden el envío"; 409 sobre una factura "Enviada".
- [x] 5.6 Ajustar las pruebas existentes al modelo nuevo: `test_flujo.py`, `test_motor.py`, `test_archivos_minimos.py`, `test_reglas_validacion.py`, `test_observabilidad.py` (`failures`), `test_errores.py` (envío con proveedor), `test_aislamiento.py` y `test_integridad.py` (`CHECK` de estatus). `test_flujo.py` y `test_aislamiento.py` no requirieron cambios; el aislamiento de contratos quedó en `test_registro_envio.py`.

## 6. Documentación y verificación

- [x] 6.1 `README.md`: flujo del proveedor (registro, "Borrador"/"Cargada", "Verificar", envío) y modelo de estatus.
- [x] 6.2 `python scripts/check.py` en verde: ruff, formato, `alembic check`, pytest con cobertura ≥ 93 % y `pip-audit`.
- [x] 6.3 Verificación en la aplicación: registrar una factura como proveedor, verla en "Borrador", completar los obligatorios, enviar con un XML que falla XML-010, corregir y enviar con éxito; como PMO, verla "Enviada" sin botones del proveedor. La barra de pasos pasó a 3 columnas y los botones de `.next-action` ya no parten su texto (`app.css`).
- [x] 6.4 `openspec validate registro-envio-factura-nacional --strict` sin errores.
