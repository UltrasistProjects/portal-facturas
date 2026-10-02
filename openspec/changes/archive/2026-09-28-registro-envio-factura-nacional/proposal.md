## Why

HU-12 (RF-07, RN-HU12-01) pide que el proveedor nacional registre su factura con los archivos mínimos y que ésta quede "Cargada". HU-13 (RF-08, RN-HU13-01, RN-HU13-02) pide que la envíe al PMO "previo la validación" del XML contra las Reglas de Validación y el control de duplicados. La minuta del 21-sep-2026 prioriza justo esto: "la recepción y validación de facturas, el control de duplicados, la gestión de estatus".

El PoC tiene el flujo, pero con otro modelo: 11 estatus en lugar de los 6 del ERS (§3.6), prevalidar y enviar como dos acciones separadas por `PREVALIDATED`, y una validación fallida que deja la factura en `REQUIRES_CORRECTION`, el mismo estatus que asigna el PMO al pedir correcciones (brechas B-01 y B-05 de EP-01). Además, el formulario de alta manda al navegador los contratos activos de **todos** los proveedores, con proyecto y monto (B-03), y los usuarios internos pueden registrar facturas a nombre de cualquier proveedor (B-04). EP-01 fija el modelo de estatus en este change (DT-01) porque EP-02 y las demás HU del proveedor lo usan.

## What Changes

- **Modelo de estatus del ERS (DT-01).** Se conservan las claves que ya significan lo mismo y cambia su etiqueta:
  - `DRAFT` "Borrador": faltan archivos obligatorios (P-01 de EP-01, valor por defecto: sí);
  - `UPLOADED` "Cargada": obligatorios completos;
  - `UNDER_REVIEW` "Enviada" (antes "En revisión");
  - `ACCEPTED` "Autorizada" (antes "Aceptada");
  - `REJECTED` "Rechazada";
  - `REQUIRES_CORRECTION` "Observaciones" (antes "Requiere corrección"), que ahora sólo asigna el PMO.
- **BREAKING:** se retiran `VALIDATING`, `VALIDATION_FAILED` y `PREVALIDATED`. `READY_FOR_CLICKBALANCE` y `UPLOADED_TO_CLICKBALANCE` no cambian; los resuelve HU-20 (EP-02).
- **"Borrador" ⇄ "Cargada" automático:** cada carga o reemplazo de documento recalcula el estatus con el checklist de archivos mínimos de HU-04. La carga documental avisa "Factura cargada. Ya puede enviarla a validación".
- **Estatus editables:** "Borrador", "Cargada" y "Observaciones". **BREAKING:** una validación fallida ya no deja la factura editable por sí misma; nunca sale de estos estatus.
- **Enviar = validar + "Enviada" (DT-02).** `POST /invoices/{id}/submit` ejecuta el motor con la configuración vigente, desde "Cargada" u "Observaciones":
  - sin ningún `FAIL`: la factura pasa a "Enviada", con `submitted_at` y auditoría `INVOICE_SUBMITTED`;
  - con algún `FAIL`: el estatus no cambia, los resultados se guardan y el detalle muestra las reglas que lo impiden, con el valor esperado y el detectado.
- **"Verificar":** el botón "Procesar y prevalidar" pasa a "Verificar". Guarda los resultados sin cambiar el estatus, para corregir antes de enviar.
- **Duplicados por UUID (DT-03, P-03 de EP-01):** RN-HU13-01 se cumple con el UUID (folio fiscal), contra facturas en cualquier estatus. El mensaje no revela datos de la otra factura.
- **Sólo el proveedor registra y envía (DT-04).** **BREAKING:** el alta, la carga documental, "Verificar" y el envío responden 403 a `INTERNAL` y `ADMIN`, que conservan la consulta.
- **Contratos filtrados en el servidor (DT-05):** el formulario de alta sólo recibe los contratos activos del proveedor del usuario. El proveedor ya no se elige: es el del usuario.
- **Proveedor no autorizado:** el alta responde 409 si el proveedor no está "Autorizado".
- **Migración `0010_invoice_status_model`:** reasigna los estatus retirados según el checklist, conserva "Observaciones" cuando la última decisión del PMO la pidió, audita `STATUS_MIGRATED` y reconstruye el `CHECK` de estatus.

**Fuera de alcance:**
- factura internacional (HU-15, HU-16), cancelación (HU-14) y el estatus `CANCELLED`;
- bandeja, detalle y decisión del PMO (HU-18 a HU-20) y los estatus de ClickBalance;
- historial de estatus y observaciones por ronda para el proveedor (HU-17);
- Serie y Folio del CFDI (sólo si negocio responde otra cosa a P-03).

## Supuestos

- **S1.** P-01, P-03 y P-04 de EP-01 se aplican con su valor por defecto: existe "Borrador", el duplicado nacional es el UUID y "Rechazada" es definitiva.
- **S2.** Bloquea el envío cualquier `FAIL`, sea `CRITICAL` o `ERROR`, igual que hoy para llegar a `PREVALIDATED`. Un `WARNING` no bloquea y el PMO lo ve en la revisión.
- **S3.** "Observaciones" no se recalcula con el checklist: la factura sigue en "Observaciones" mientras el proveedor corrige, hasta que el envío procede.
- **S4.** La revisión `0010` sigue a `0009_supplier_profile`, que aún no está confirmada en la rama. Si ese trabajo no se integra antes, hay que ajustar `down_revision`.

## Capabilities

### New Capabilities
<!-- Ninguna: el registro y el envío pertenecen al flujo de facturas. -->

### Modified Capabilities
- `flujo-facturas`: modelo de estatus del ERS y sus etiquetas, estatus editables, "Borrador"/"Cargada" según los archivos obligatorios, envío con validación, "Verificar", acciones exclusivas del proveedor, contratos del proveedor en el alta, rechazo del alta para un proveedor no autorizado y migración de los estatus.
- `motor-validacion`: la validación deja de cambiar el estatus; el duplicado por UUID, las reglas documentales y las comparaciones del XML impiden el envío en lugar de dejar la factura en "Requiere corrección"; el mensaje de duplicado no revela la otra factura.
- `integridad-datos`: el `CHECK` de `invoices.status` admite sólo los estatus vigentes.

## Impact

- **Código:**
  - `app/core/constants.py`: `InvoiceStatus` sin los tres estatus retirados, `STATUS_LABELS` y `ALLOWED_TRANSITIONS`;
  - `app/services/invoice_service.py`: estatus editables, recálculo "Borrador"/"Cargada" y envío;
  - `app/services/validation_engine.py`: `run_validation` sin transiciones de estatus;
  - `app/routers/invoices.py`: roles, contratos del proveedor, recálculo tras la carga, "Verificar" y envío;
  - `app/routers/dashboard.py`: indicadores sin `PREVALIDATED`;
  - `app/static/js/app.js`: sin el filtro de contratos por proveedor.
- **Plantillas:** `invoices/new.html`, `invoices/documents.html`, `invoices/detail.html`, `invoices/list.html`, `dashboard.html`; estilos de estatus en `app.css`.
- **Esquema:** revisión Alembic `0010_invoice_status_model`, posterior a `0009_supplier_profile`.
- **Datos demo:** `scripts/seed_db.py` siembra las 10 facturas con el modelo nuevo.
- **Rutas:** sin rutas nuevas; `POST /invoices/{id}/submit` y `POST /invoices/{id}/validation` cambian de comportamiento.
- **Dependencias:** ninguna nueva.
- **Pruebas:** nuevo `tests/test_registro_envio.py`; ajustes en `test_flujo.py`, `test_motor.py`, `test_archivos_minimos.py`, `test_reglas_validacion.py`, `test_observabilidad.py`, `test_errores.py`, `test_demo_workflow.py`, `test_aislamiento.py`, `test_integridad.py` y `test_migraciones.py`.
- **Documentación:** `README.md` (flujo del proveedor y modelo de estatus).
