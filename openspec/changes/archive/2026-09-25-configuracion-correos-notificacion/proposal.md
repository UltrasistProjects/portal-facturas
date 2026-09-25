## Why

La HU-08 (RF-13) pide que el Administrador configure los correos y destinatarios de las notificaciones, en particular el buzón "Recepción de Facturas", "para que cada aviso del sistema llegue a la persona o área correcta". La minuta del 21-sep-2026 fija ese buzón en `recepcionfacturas@ultrasist.com.mx` y la ERS exige que RF-09 (HU-14) y RF-10 (HU-20) lo tomen de esta configuración.

Hoy el PoC no envía ningún correo: no hay transporte, remitente ni registro de envíos. HU-05 dejó compuestos los textos de los cuatro eventos de factura y dejó a esta HU el transporte SMTP, el remitente, los destinatarios y el correo de prueba. HU-03 (envío de credenciales, módulo siguiente) necesita este transporte para funcionar.

## What Changes

- **Transporte de correo configurable por entorno** (`.env`):
  - `MAIL_BACKEND=smtp` envía por SMTP con STARTTLS, SSL o sin cifrar, usuario y contraseña opcionales y tiempo de espera;
  - `MAIL_BACKEND=file` escribe cada correo como archivo `.eml` en `MAIL_OUTBOX_DIR`, sin enviarlo; es el valor por omisión fuera de producción;
  - remitente `MAIL_FROM`, obligatorio con SMTP;
  - en producción el arranque se aborta con `MAIL_BACKEND=file` o con `SMTP_SECURITY=none`.
- **Pantalla Administración › Notificaciones** (`/admin/notifications`), exclusiva del rol `ADMIN`:
  - buzón **"Recepción de Facturas"**: de 1 a 10 correos, sembrado con `recepcionfacturas@ultrasist.com.mx`;
  - **copias por evento**: de 0 a 10 correos adicionales para Autorizada, Rechazada, Observaciones y Cancelada;
  - validación de todas las direcciones con los errores juntos (HTTP 400), control de edición concurrente con huella (HTTP 409) y auditoría `NOTIFICATION_RECIPIENTS_UPDATED`;
  - **correo de prueba** a una dirección que indica el Administrador;
  - datos del transporte en solo lectura, sin la contraseña;
  - los últimos 20 envíos con su resultado.
- **Servicio de notificaciones** para las HU que envían correos (HU-03, HU-14 y HU-20):
  - resuelve los destinatarios de cada evento: el buzón para Autorizada y Cancelada, el correo del proveedor para Rechazada y Observaciones, más las copias del evento;
  - compone el correo con la plantilla vigente de HU-05 y lo envía en texto plano UTF-8;
  - un fallo del transporte nunca revierte la operación de negocio: queda registrado como envío fallido.
- **Bitácora de envíos** (`email_deliveries`): evento, destinatarios, resultado, error técnico, entidad relacionada y usuario que lo originó, sin asunto ni cuerpo.
- **Migración** `0005_notification_recipients`: tablas `notification_mailboxes`, `notification_copies` y `email_deliveries`, con el buzón sembrado y las copias vacías.

**Fuera de alcance:**
- disparar los correos de factura al cambiar el estatus (HU-20) o al cancelar (HU-14);
- el correo de credenciales (HU-03, módulo siguiente);
- cola, reintentos automáticos y envío asíncrono;
- HTML, adjuntos y seguimiento de lectura;
- otros buzones además de "Recepción de Facturas".

## Supuestos

Decisiones tomadas ante ambigüedades de la HU, consistentes con el código existente y confirmadas en el plan de módulos:

- **S1.** "Configurar los correos" se interpreta como las direcciones de destino (buzón y copias) y el correo de prueba. Las credenciales del servidor SMTP y el remitente viven en `.env`, como el resto de secretos del PoC (`SECRET_KEY`, `DATABASE_URL`), y no en la base de datos.
- **S2.** El tipo de destinatario de cada evento lo fija su regla de negocio (RD-03 de HU-05: RN-HU20-02, RN-HU20-03 y HU-14). El Administrador configura las direcciones del buzón y agrega copias, pero no cambia quién es el destinatario principal.
- **S3.** El envío es síncrono y ocurre después de confirmar la transacción de negocio. El resultado se registra en la bitácora; un correo fallido no se reintenta solo.
- **S4.** El correo de prueba tiene un texto fijo y no es una plantilla configurable: verifica el transporte, no la redacción de los avisos.
- **S5.** Fuera de producción el transporte por omisión es `file`, para que el desarrollo y las pruebas nunca envíen correos reales.
- **S6.** Las copias no se ofrecen para eventos cuyo correo contenga secretos. Esto aplica al evento de credenciales de HU-03, que se agregará sin copias.

## Capabilities

### New Capabilities
- `notificaciones-correo`: transporte de correo, buzón "Recepción de Facturas" y copias por evento configurables por el Administrador, resolución de destinatarios por evento, servicio de envío de notificaciones, bitácora de envíos, correo de prueba y auditoría.

### Modified Capabilities
- `configuracion-entorno`:
  - nuevo requisito de transporte de correo configurable por entorno;
  - las verificaciones de arranque en producción incluyen el transporte `file` y SMTP sin cifrar.
- `observabilidad`:
  - el registro de eventos técnicos incluye `notification.sent`, `notification.failed` y `notification_recipients.updated`;
  - los logs no contienen la contraseña SMTP, las direcciones de los destinatarios ni el texto de los correos.
- `integridad-datos`:
  - la restricción de enumeraciones incluye el buzón de notificación y el resultado del envío;
  - nuevo requisito de integridad de la configuración de notificaciones y de la bitácora de envíos.

## Impact

- **Código:**
  - `app/core/config.py`: variables `MAIL_*` y `SMTP_*`;
  - `app/core/startup.py`: verificaciones de producción;
  - `app/core/constants.py`: enumeraciones `Mailbox` y `DeliveryStatus`;
  - `app/models/__init__.py`: modelos `NotificationMailbox`, `NotificationCopy` y `EmailDelivery`;
  - `app/services/notification_templates.py`: el destinatario de cada evento pasa a ser una enumeración (`Recipient`), sin cambio visible;
  - nuevos `app/services/mail_transport.py` y `app/services/notification_service.py`;
  - `app/routers/admin.py`: rutas `/admin/notifications*`;
  - nueva plantilla `admin/notifications.html`; opción "Notificaciones" en `base.html`.
- **Esquema:** nueva revisión Alembic `0005_notification_recipients`, posterior a `0004_notification_templates`.
- **Rutas nuevas:**
  - `GET /admin/notifications`;
  - `POST /admin/notifications`;
  - `POST /admin/notifications/test`.
- **Configuración:** `.env.example` documenta las variables nuevas; `.gitignore` excluye `outbox/`.
- **Dependencias:** ninguna nueva (`smtplib` y `email` de la biblioteca estándar).
- **Pruebas:** nuevo `tests/test_notificaciones_correo.py`; ajustes en `tests/test_configuracion.py`, `tests/test_integridad.py`, `tests/test_migraciones.py`, `tests/test_observabilidad.py` y `tests/conftest.py`, que dirige el buzón de salida a un directorio temporal.
- **Documentación:** `README.md`, con la sección de correo y notificaciones.
- **Sin cambios:** plantillas de correo y su pantalla (HU-05), estatus y flujo de facturas, datos demo.
