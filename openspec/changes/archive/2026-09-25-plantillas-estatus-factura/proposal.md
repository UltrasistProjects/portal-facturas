## Why

La HU-05 (RF-05) pide que el Administrador defina, desde la configuración del sistema, los correos que se envían cuando una factura pasa a "Autorizada", "Rechazada", "Observaciones" o "Cancelada". La NOTA general del documento de HUs exige lo mismo para todos los correos: plantillas en la configuración "para que sea flexible".

Las reglas de las HU que disparan esos correos (RN-HU20-02 y RN-HU20-03 en HU-20, y HU-14) dictan qué debe decir cada uno: número de factura, proveedor, monto, causa o fecha límite. Si el texto quedara fijo en el código, cualquier ajuste de redacción exigiría un despliegue. Esta HU hace editable la redacción sin permitir que se pierda un dato que exige una regla de negocio.

Hoy el PoC no envía correos y sus estatus no coinciden con los de la ERS, así que este cambio entrega las plantillas y el servicio que compone cada correo, pero no el envío. La historia completa, sus reglas derivadas (RD-01 a RD-10) y los puntos a confirmar están en `docs/stories/new/HU-05 Configuracion de plantillas de estatus de factura.md`.

## What Changes

- **Cuatro plantillas de correo, una por evento:** `INVOICE_AUTHORIZED` (Autorizada), `INVOICE_REJECTED` (Rechazada), `INVOICE_OBSERVATIONS` (Observaciones) e `INVOICE_CANCELLED` (Cancelada).
  - Se crean con la migración, con un texto predeterminado que reproduce la redacción de las reglas de negocio.
  - No se crean, eliminan ni desactivan desde la interfaz.
  - Los eventos no dependen de la enumeración de estatus de factura del PoC.
- **Pantalla Administración › Plantillas de correo** (`/admin/notification-templates`), exclusiva del rol `ADMIN`:
  - listado con destinatario, asunto vigente y última modificación;
  - edición del asunto y del cuerpo en texto plano, con variables `{{variable}}` y la tabla de variables de cada plantilla;
  - destinatario de solo lectura, fijado por la regla de negocio de cada evento;
  - vista previa con datos de ejemplo, resuelta en el servidor y sin guardar;
  - carga del texto predeterminado en el formulario, que no se aplica hasta guardar.
- **Validación al guardar y en la vista previa:** normalización, longitudes, una sola línea en el asunto, variables sin cerrar, variables que no son de la plantilla y variables obligatorias ausentes en el cuerpo. Todos los errores se reportan juntos con HTTP 400.
- **Control de edición concurrente** con número de versión: un guardado sobre una versión vieja responde 409 y no guarda. Un guardado sin cambios no aumenta la versión.
- **Servicio de composición** para HU-20 y HU-14: recibe el evento y valores tipados, formatea montos y fechas y devuelve el asunto y el cuerpo. Sustituye las variables en una sola pasada y sin Jinja2. Si la plantilla guardada no es válida, compone con el texto predeterminado y lo registra en el log. No envía correos.
- **Auditoría** `NOTIFICATION_TEMPLATE_UPDATED` con el texto y la versión anteriores y nuevos, y eventos de log `notification_template.updated` y `notification.template_fallback`, sin el texto de los correos.
- **Migración** `0004_notification_templates`, posterior a `0003_invoice_document_types` (HU-04): tabla `notification_templates` con sus restricciones y las cuatro plantillas predeterminadas.

**Fuera de alcance** (detalle en la sección 3 de la HU):
- envío de correos, transporte SMTP, remitente, cola y reintentos (HU-08, HU-20 y HU-14);
- destinatarios configurables, incluido el buzón "Recepción de Facturas" (HU-08);
- disparar la notificación al cambiar el estatus y alinear los estatus del PoC con la ERS (HU-20 y HU-14);
- plantillas de otros correos, como credenciales (HU-03);
- correo de prueba, HTML, adjuntos, otros idiomas e historial con opción de volver a una versión anterior.

## Capabilities

### New Capabilities
- `plantillas-notificacion`: plantillas de correo de los eventos de estatus de factura. Cubre:
  - una plantilla por evento y acceso exclusivo del Administrador;
  - consulta, variables por plantilla y validación;
  - vista previa y carga del texto predeterminado;
  - guardado con control de edición concurrente;
  - textos predeterminados conforme a las reglas de negocio;
  - servicio de composición y auditoría.

### Modified Capabilities
- `integridad-datos`:
  - la restricción de enumeraciones incluye el evento de notificación (`notification_templates.event`);
  - nuevo requisito: una plantilla por evento, con longitudes de asunto y cuerpo, versión positiva y `updated_by` con `ON DELETE RESTRICT`.
- `observabilidad`: el registro de eventos técnicos incluye el cambio de una plantilla y la composición con el texto predeterminado, sin el texto de los correos ni los valores de las variables.

## Impact

- **Código:**
  - `app/core/constants.py`: enumeración `NotificationEvent`;
  - `app/models/__init__.py`: modelo `NotificationTemplate`;
  - nuevo `app/services/notification_templates.py`: catálogo de eventos y variables, textos predeterminados, validación, vista previa, guardado y composición;
  - `app/routers/admin.py`: rutas `/admin/notification-templates*`;
  - plantillas: nuevas `admin/notification_templates.html` y `admin/notification_template_edit.html`; opción de menú en `base.html`;
  - `app/static/css/app.css`: estilo del cuerpo de la vista previa.
- **Esquema:** nueva revisión Alembic `0004_notification_templates`.
- **Rutas nuevas:**
  - `GET /admin/notification-templates`;
  - `GET /admin/notification-templates/{codigo}` (con `?default=1` para cargar el texto predeterminado);
  - `POST /admin/notification-templates/{codigo}/preview`;
  - `POST /admin/notification-templates/{codigo}`.
- **Pruebas:** nuevo `tests/test_plantillas_notificacion.py`; ajustes en `tests/test_integridad.py`, `tests/test_migraciones.py` y `tests/test_observabilidad.py`.
- **Documentación:** `README.md`, con la sección de plantillas de correo y la tabla de variables.
- **Dependencias:** ninguna nueva.
- **Orden respecto a HU-04:** la migración va después de la de `archivos-minimos-por-tipo-proveedor`, y el delta de `integridad-datos` parte del texto que deja esa HU. Este change se archiva después de aquel.
- **Sin cambios:** estatus y flujo de facturas (`flujo-facturas`), CSP y cabeceras (`proteccion-http`), datos demo (`scripts/seed_db.py`).
