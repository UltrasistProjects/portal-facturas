## Why

El Alcance del MVP (minuta del 21-sep-2026) pide "permitir solicitar la cancelación y enviar una notificación automática al área de Facturas Electrónicas". HU-14 (RF-09) lo precisa: el proveedor cancela su factura, el sistema lo obliga a cargar el "Acuse de Cancelación" y envía a "Recepción de Facturas" un correo con el número de factura y el nombre del proveedor, pidiendo aceptar la cancelación antes de la fecha actual + 72 horas. En México, al cancelar un CFDI el receptor tiene 72 horas para aceptar la cancelación en el buzón del SAT; el correo es el aviso para que ULTRASIST lo haga a tiempo.

Hoy no existe: no hay estatus "Cancelada" ni forma de registrar el acuse. HU-05 dejó la plantilla "Cancelada" (con `fecha_limite_cancelacion`), HU-08 el buzón y el servicio de envío, y HU-20 el patrón de correo después del commit con reenvío. Es la parte de EP-01 de la ola 3.

## What Changes

- **Estatus "Cancelada"** (`CANCELLED`), final, desde cualquier estatus excepto "Cancelada" (P-05 de EP-01). La factura cancelada sale de la bandeja del PMO y ya no admite cambios.
- **Cancelación por el proveedor:** en el detalle de su factura, "Cancelar factura" con el acuse (PDF o XML) y una confirmación. `POST /invoices/{id}/cancel`, exclusivo del proveedor, con bloqueo de la fila. Sin acuse o sin confirmación, nada cambia.
- **"Acuse de cancelación"** (`CANCELLATION_ACK`) como tipo de documento del sistema con nivel fijo "No aplica" para ambos orígenes (EP-01 DT-10): no se ofrece en la carga documental ni se exige al enviar; sólo se carga al cancelar.
- **Fecha límite:** `cancellation_deadline = cancelled_at + 72 horas`, guardada en UTC y mostrada en la zona de negocio, junto con `cancelled_at` y `cancelled_by`.
- **Correo a Recepción de Facturas** (`INVOICE_CANCELLED`) después de confirmar la cancelación, con número, proveedor, monto, folio y fecha límite. El proveedor ve si se notificó; si el envío falló, el PMO puede reenviarlo como los correos de la decisión (HU-20).
- **Duplicados del Invoice por nombre:** una factura cancelada deja de contar (P-08 de EP-01); el UUID del CFDI sigue siendo único en cualquier estatus (DT-03).
- **Migración** `0012_invoice_cancellation`: columnas de la cancelación con su `CHECK`, estatus `CANCELLED` en el `CHECK` de estatus y el tipo del sistema con su nivel fijo.
- **Demo:** factura `CANCELADA-001` del proveedor 1 con su acuse.

**Fuera de alcance:**
- que Recepción de Facturas registre en el portal la aceptación o el rechazo de la cancelación (P-09 de EP-01): la aceptación ocurre ante el SAT;
- motivo SAT de cancelación (01 a 04) y consulta del estatus del CFDI ante el SAT;
- revertir una cancelación.

## Supuestos

Valores por defecto de las preguntas abiertas de EP-01:

- **S1 (P-05).** Se cancela desde cualquier estatus excepto "Cancelada", también "Autorizada" y "Rechazada": el SAT pedirá a ULTRASIST aceptar la cancelación en todos los casos.
- **S2 (P-09).** La cancelación es inmediata ("Cancelada", ERS §3.6); no hay estatus "Cancelación solicitada".
- **S3 (P-10).** El proveedor internacional, que no cancela ante el SAT, carga como acuse cualquier PDF que documente la cancelación.
- **S4 (P-11).** "Facturas Electrónicas" de la minuta es el buzón "Recepción de Facturas" de HU-08.
- **S5.** Las 72 horas son naturales, contadas desde la cancelación en el portal.

## Capabilities

### New Capabilities
- `cancelacion-facturas`: cancelación por el proveedor con acuse obligatorio, fecha límite, correo a Recepción de Facturas y su visualización.

### Modified Capabilities
- `flujo-facturas`: el modelo de estatus agrega "Cancelada" y sus transiciones.
- `archivos-minimos-factura`: el catálogo incluye el tipo del sistema "Acuse de cancelación" con nivel fijo "No aplica".
- `integridad-datos`: `CHECK` de estatus con `CANCELLED`, `CHECK` de los datos de la cancelación y nivel fijo del acuse.
- `revision-pmo`: el reenvío de la notificación también aplica al correo de cancelación.
- `factura-internacional`: el duplicado del Invoice por nombre de archivo no cuenta facturas canceladas.

## Impact

- **Código:**
  - `app/core/constants.py`: `InvoiceStatus.CANCELLED`, transiciones, `DocumentType.CANCELLATION_ACK` y su nivel fijo;
  - `app/models/__init__.py`: columnas y `CHECK` de la cancelación, `CHECK` de niveles fijos;
  - nuevo `app/services/cancellation_service.py`; `app/services/review_service.py` (correo y reenvío de la cancelación); `app/services/foreign_invoice_service.py` (duplicados sin canceladas);
  - `app/routers/invoices.py`: `POST /invoices/{id}/cancel` y contexto del detalle.
- **Plantillas:** `invoices/detail.html` (formulario de cancelación, aviso de factura cancelada y resultado del correo para el proveedor).
- **Esquema:** revisión Alembic `0012_invoice_cancellation`.
- **Demo:** `scripts/seed_db.py`.
- **Pruebas:** nuevo `tests/test_cancelacion.py`; ajustes en `tests/test_migraciones.py`, `tests/test_integridad.py`, `tests/test_archivos_minimos.py`, `tests/test_demo_workflow.py`, `tests/test_respaldos.py` y las que enumeran estatus o tipos del sistema.
- **Documentación:** `README.md`.
