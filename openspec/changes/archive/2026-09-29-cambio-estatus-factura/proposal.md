## Why

El rol PMO del Alcance del MVP (minuta del 21-sep-2026) debe "modificar el estatus de la factura: Aceptada, Rechazada o Con observaciones" y "registrar observaciones asociadas a la revisión"; la sección "Notificaciones" pide avisar automáticamente a `recepcionfacturas@ultrasist.com.mx`. HU-20 (RF-10) lo precisa: tres botones ("Autorizada", "Rechazada" y "Observaciones") y tres reglas de negocio:

- **RN-HU20-01:** al rechazar o marcar observaciones, el sistema despliega un campo "Observaciones" para las notas del PMO;
- **RN-HU20-02:** al autorizar, correo a Recepción de Facturas ("la factura número X del proveedor Y por el monto Z ha sido autorizada para su pago"), con el destinatario de la configuración;
- **RN-HU20-03:** al rechazar u observar, correo al proveedor con la causa capturada.

Hoy la decisión está en una página aparte con cuatro botones ("Aceptar", "Solicitar corrección", "Rechazar" y "Solo agregar comentario"), los comentarios son opcionales, ningún cambio de estatus envía correo y dos decisiones simultáneas se aplican ambas. Además sobreviven los pasos de ClickBalance del PoC, que no están en el ERS ni en la minuta. HU-05 y HU-08 ya dejaron las plantillas, los destinatarios y el servicio de envío que esta HU sólo invoca. Es la parte PMO de la ola 3 (EP-02).

## What Changes

- **Decisión en el detalle** (EP-02 DT-04): para `INTERNAL` y `ADMIN`, con la factura "Enviada", un panel "Decisión" con los botones "Autorizar", "Observaciones" y "Rechazar" y el campo "Observaciones". `GET /invoices/{id}/review` redirige al panel; `POST /invoices/{id}/review` sigue siendo la acción.
- **Observaciones obligatorias** para "Rechazar" y "Observaciones", de hasta 2 000 caracteres (RN-HU20-01). Con JavaScript, el campo aparece al elegir esas decisiones y "Autorizar" pide confirmación; sin JavaScript el formulario funciona igual.
- **Sólo tres decisiones:** "Solo agregar comentario" se retira; `COMMENT` se rechaza con HTTP 400 y se conserva en la enumeración para las revisiones históricas.
- **Una sola decisión por envío:** la factura se bloquea al decidir; decidir sobre una factura que ya no está "Enviada" responde HTTP 409 "La factura ya fue revisada", sin revisión ni correo.
- **Correos de la decisión** (RN-HU20-02, RN-HU20-03; DT-05), después de confirmar la decisión:
  - Autorizada → `INVOICE_AUTHORIZED` al buzón Recepción de Facturas con número, proveedor y monto total con moneda;
  - Rechazada y Observaciones → `INVOICE_REJECTED` / `INVOICE_OBSERVATIONS` al correo del proveedor con las observaciones.

  El detalle muestra el resultado del envío. Si falló, la decisión se mantiene y el PMO puede **reenviar la notificación**.
- **ClickBalance fuera del MVP** (P-01 de EP-02, DT-06): se retiran sus botones y la ruta `POST /invoices/{id}/clickbalance`. **BREAKING:** la migración `0011_retire_clickbalance` pasa las facturas "Lista para ClickBalance" y "Cargada a ClickBalance" a "Autorizada" (auditoría `STATUS_MIGRATED`) y el catálogo de estatus queda con seis valores.
- **Demo:** los escenarios `CLICK-READY` y `CLICK-DONE` se reemplazan por `OBSERVACIONES-001` (devuelta por el PMO con su revisión) y `ENVIADA-002` (una segunda factura por decidir).

**Fuera de alcance:**
- revertir una decisión (P-05 de EP-02);
- catálogo de motivos de rechazo (P-06);
- el seguimiento del proveedor con su historial (HU-17);
- la cancelación (HU-14).

## Supuestos

Valores por defecto de las preguntas abiertas de EP-02:

- **S1 (P-01).** ClickBalance no forma parte del MVP.
- **S2 (P-02).** El Administrador conserva la facultad de decidir, como hoy.
- **S3 (P-03).** El "monto" del correo es el total de la factura con su moneda.
- **S4 (P-04, P-05).** "Rechazada" y "Autorizada" son definitivas; sólo "Observaciones" permite reenviar.
- **S5 (P-06).** Las observaciones son texto libre, obligatorio para rechazar u observar.
- **S6.** El reenvío de la notificación sólo procede si el último envío de esa decisión falló y la factura sigue en el estatus de la decisión.

## Capabilities

### New Capabilities
<!-- Ninguna: la revisión del PMO ya es la capacidad revision-pmo. -->

### Modified Capabilities
- `revision-pmo`: decisión con tres botones, observaciones obligatorias, una decisión por envío, correos de la decisión y reenvío de la notificación.
- `flujo-facturas`: el modelo de estatus queda con seis valores (sin ClickBalance) y las reglas centralizadas ya no incluyen el siguiente estado de ClickBalance.
- `integridad-datos`: el `CHECK` de `invoices.status` admite los seis estatus.
- `proteccion-http`: el escenario de error de negocio de ClickBalance se reemplaza por una decisión sobre una factura ya revisada.

## Impact

- **Código:**
  - nuevo `app/services/review_service.py`: decisión (bloqueo, validación y transición), correo de la decisión, último envío y reenvío;
  - `app/services/invoice_service.py`: se retiran `review_invoice` y `next_clickbalance_status`;
  - `app/core/constants.py`: `InvoiceStatus` y `ALLOWED_TRANSITIONS` sin ClickBalance;
  - `app/routers/invoices.py`: `GET /review` redirige, `POST /review` con la decisión y el correo, `POST /invoices/{id}/notification` (reenvío); se retira `POST /clickbalance`;
  - nuevo `app/static/js/review_decision.js`.
- **Plantillas:** `invoices/detail.html` (panel de decisión, resultado del correo, reenvío); se elimina `invoices/review.html`.
- **Esquema:** revisión Alembic `0011_retire_clickbalance`.
- **Demo:** `scripts/seed_db.py`.
- **Pruebas:** nuevo `tests/test_cambio_estatus.py`; ajustes en `tests/test_errores.py`, `tests/test_observabilidad.py`, `tests/test_demo_workflow.py`, `tests/test_migraciones.py` y las que deciden con `POST /review`.
- **Documentación:** `README.md`.
