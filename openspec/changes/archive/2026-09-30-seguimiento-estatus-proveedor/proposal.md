## Why

RF-16 (HU-17) pide que el proveedor liste sus facturas con su estatus actual y consulte "el motivo/observaciones cuando la factura esté Rechazada o con Observaciones", para dar seguimiento a su validación y pago. Es la última historia de la ruta crítica de EP-01 (HU-10 → HU-12/13 → HU-18/19 → HU-20 → HU-17) y cierra el alcance "registrar, validar y dar seguimiento a las facturas" de la minuta.

Hoy el proveedor ya tiene su listado con alcance, búsqueda, filtro por los siete estatus y paginación, y recibe los correos de la decisión (HU-20). Le faltan tres cosas:
- el detalle sólo muestra el último `invoices.comments`, en cualquier estatus y sin decir de dónde viene: tras reenviar una factura con observaciones, sigue viendo las de la ronda anterior como si fueran vigentes, y las rondas previas se pierden;
- el historial de envíos y revisiones (HU-19) es sólo para el PMO;
- el tablero cuenta Enviadas, Observaciones y Autorizadas, pero no Rechazadas ni Canceladas, y sus indicadores no llevan al listado filtrado.

## What Changes

- **"Seguimiento" para el proveedor:** el historial de HU-19 (envíos del proveedor y decisiones del PMO) también se muestra al proveedor con el título "Seguimiento", con "PMO" en lugar del nombre del revisor (EP-02 DT-07) y sin los comentarios internos (`COMMENT`) del PoC.
- **Cancelación en el historial:** para todos los roles, la cancelación (auditoría `INVOICE_CANCELLED`) aparece como "Cancelada", con el usuario y la fecha límite de aceptación.
- **Causa destacada:** en "Rechazada" y "Observaciones", el detalle muestra a todos los roles "Motivo del rechazo" u "Observaciones del PMO" con el texto de la última decisión, el mismo del correo. En "Observaciones", el proveedor ve además "Corrija lo indicado y vuelva a enviar la factura" con el acceso a "Gestionar documentos". Se retira el aviso genérico "Observaciones: <comentario>" de los demás estatus.
- **Tablero:** indicadores Enviadas, Observaciones, Autorizadas, Rechazadas y Canceladas, además del total; cada uno abre el listado filtrado por su estatus.

**Fuera de alcance:**
- notificaciones al proveedor dentro del portal (los correos de HU-20 siguen siendo el aviso);
- estatus de pago posterior a "Autorizada" (el portal termina ahí; no hay integración con ClickBalance ni SAP Ariba);
- el nombre del revisor para el proveedor (la HU lo decide: sólo "PMO").

## Capabilities

### New Capabilities
Ninguna.

### Modified Capabilities
- `revision-pmo`: el historial del detalle se muestra también al proveedor como "Seguimiento", sin el nombre del revisor ni los comentarios internos, e incluye la cancelación.
- `flujo-facturas`: causa de la decisión destacada en el detalle e indicadores del tablero por estatus con acceso al listado filtrado.

## Impact

- **Código:** `app/services/invoice_history_service.py` (vista del proveedor, cancelación, última decisión); `app/routers/invoices.py` (contexto del detalle); `app/routers/dashboard.py` (indicadores).
- **Plantillas:** `invoices/detail.html` (Seguimiento y causa), `dashboard.html` (indicadores con enlace); estilos en `app.css`.
- **Esquema:** sin cambios.
- **Demo:** `scripts/seed_db.py` registra la auditoría de envío y cancelación de sus facturas.
- **Pruebas:** nuevo `tests/test_seguimiento_estatus.py`; ajustes en las pruebas del historial (`tests/test_revision_pmo.py`) y del tablero que asumían el comportamiento anterior.
- **Documentación:** `README.md`.
