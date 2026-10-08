## Context

HU-08 (RF-13) cierra el hueco 8 de la validación de HUs: la configuración de correos y destinatarios de las notificaciones. Estado actual del PoC:

- **Correo:** no hay dependencia, configuración ni servicio de envío. `notification_templates.compose()` (HU-05) devuelve asunto y cuerpo, sin enviarlos.
- **Destinatarios:** HU-05 muestra en cada plantilla una etiqueta fija ("Recepción de Facturas" o "Proveedor (correo del catálogo)"), sin direcciones.
- **Configuración persistente:** HU-04 estableció el patrón: tabla propia, pantalla de administración que guarda en una sola transacción, huella `config_version` con bloqueo consultivo para detectar ediciones concurrentes y auditoría del cambio.
- **Arranque:** `startup_problems()` aborta en producción ante una configuración insegura.
- **Configuración de entorno:** `Settings` (pydantic-settings) valida `.env` y ancla las rutas a la raíz del proyecto.
- **Pruebas:** comparten una base PostgreSQL por sesión y un almacenamiento temporal; `APP_ENV=test`.

## Goals / Non-Goals

**Goals:**
- Que el Administrador defina a qué direcciones llegan los avisos sin despliegues.
- Un servicio de envío único para HU-03, HU-14 y HU-20: destinatarios resueltos por evento, correo compuesto con la plantilla vigente y resultado registrado.
- Que ningún correo real salga del desarrollo ni de las pruebas.
- Que un fallo del servidor de correo nunca deshaga una operación de negocio ni se pierda en silencio.

**Non-Goals:**
- Disparar los correos de factura (HU-20 y HU-14) y el de credenciales (HU-03).
- Cola, reintentos automáticos, envío asíncrono, HTML y adjuntos.
- Buzones adicionales o destinatarios principales editables.

## Decisions

### D1. Transporte con la biblioteca estándar y dos implementaciones
`app/services/mail_transport.py` define `build_message()` y dos transportes con la misma interfaz `send(message)`:
- `SmtpTransport`: `smtplib.SMTP` con `starttls()` o `smtplib.SMTP_SSL`, contexto `ssl.create_default_context()`, `login()` sólo si hay usuario y `timeout` configurable.
- `FileTransport`: escribe `message.as_bytes()` en `MAIL_OUTBOX_DIR/<fecha UTC>_<uuid>.eml` con permisos `0600`.

`transport_from_settings()` elige según `MAIL_BACKEND`.

*Alternativas:*
- Una dependencia como `fastapi-mail` o `aiosmtplib`: agrega superficie para un envío síncrono y simple.
- Un transporte en memoria sólo para pruebas: las pruebas usan `FileTransport` sobre un directorio temporal, que es el mismo código que se usa en desarrollo.

### D2. Configuración del transporte en `.env`
Variables:
- `MAIL_BACKEND` (`smtp` | `file`): sin definir, `smtp` en producción y `file` en los demás entornos;
- `MAIL_FROM`: obligatoria con `smtp`; con `file` toma "Portal de Proveedores ULTRASIST <no-reply@portal.local>";
- `MAIL_OUTBOX_DIR`: `./outbox`, anclada a la raíz del proyecto;
- `SMTP_HOST`, obligatoria con `smtp`;
- `SMTP_PORT` (587), `SMTP_SECURITY` (`starttls` | `ssl` | `none`, por omisión `starttls`), `SMTP_USERNAME`, `SMTP_PASSWORD` (`SecretStr`) y `SMTP_TIMEOUT` (10 s, de 1 a 120).

`startup_problems()` agrega en producción `MAIL_BACKEND=file` y `SMTP_SECURITY=none`.

*Alternativa:* guardar el servidor y la contraseña SMTP en la base de datos, editables desde la pantalla. Es un secreto: quedaría en los respaldos (`pg_dump`) y el PoC no cifra columnas. Supuesto S1.

### D3. Dos tablas de configuración y una huella común
- `notification_mailboxes`: `code` (enumeración `Mailbox`, única; hoy sólo `INVOICE_RECEPTION`), `name`, `addresses` (`VARCHAR(254)[]`, de 1 a 10), `updated_at` y `updated_by`.
- `notification_copies`: `event` (`NotificationEvent`, única), `addresses` (`VARCHAR(254)[]`, de 0 a 10), `updated_at` y `updated_by`.

La migración siembra el buzón con `recepcionfacturas@ultrasist.com.mx` y una fila de copias vacía por cada evento que las admite.

La pantalla guarda buzón y copias en una sola transacción con `pg_advisory_xact_lock` y una huella `config_version`: el SHA-256 de todas las listas. Una huella distinta responde 409 "La configuración cambió mientras la editaba. Recargue la página.", igual que HU-04.

*Alternativas:*
- Una columna de copias en `notification_templates`: mezclaría la versión de la redacción (HU-05) con la de los destinatarios.
- Una tabla genérica clave-valor: sin restricciones por campo, ya descartada en HU-05.
- Una tabla de filas (lista, dirección): más uniones y más escrituras para listas de hasta 10 elementos. `ARRAY` ya se usa en `invoice_document_types.formats`.

### D4. Destinatario principal fijado por el evento
`EventSpec.recipient` pasa de texto a la enumeración `Recipient` (`RECEPTION` = "Recepción de Facturas" y `SUPPLIER` = "Proveedor (correo del catálogo)"). Su valor es el mismo texto, así que la pantalla de HU-05 no cambia.

`notification_service.recipients_for(db, event, supplier_email)`:
- `RECEPTION`: las direcciones de `INVOICE_RECEPTION`;
- `SUPPLIER`: el correo del proveedor, que es obligatorio; sin él, `NotificationDataError`;
- copias: las del evento, sin las que ya están en "Para" y sin duplicados.

Supuesto S2.

### D5. Envío después del commit y sin excepciones de transporte
`notification_service.notify(db, event, *, supplier_email=None, entity, entity_id, user_id, **valores)`:
1. resuelve los destinatarios;
2. compone el correo con `notification_templates.compose()`;
3. lo envía;
4. registra la fila de `email_deliveries` y confirma la transacción.

Los errores de transporte (`smtplib.SMTPException`, `OSError`, `ssl.SSLError`) se capturan: la fila queda `FAILED` con el error técnico recortado a 300 caracteres. Si el servidor rechaza a algún destinatario, el envío también queda `FAILED`.

Los errores de programación (`NotificationDataError`) sí se propagan. La función se llama después de confirmar la transacción de negocio, así que un correo fallido no la revierte. Supuesto S3.

*Alternativas:*
- Una cola con reintentos: exige un proceso de trabajo que el PoC no tiene. La bitácora permite detectar el fallo y la HU que envía decide cómo reintentar (HU-03 ofrecerá "Reenviar credenciales").
- Enviar antes del commit: un correo podría salir para una operación que después se revierte.

### D6. Bitácora sin contenido
`email_deliveries` guarda:
- `event`: `NotificationEvent`, o `NULL` para el correo de prueba;
- `status` (`SENT` | `FAILED`) y `error`, obligatorio si falló;
- `to_addresses` y `cc_addresses`;
- `transport` (`smtp` | `file`) y `message_id`;
- `entity` y `entity_id`, por ejemplo "Invoice" 42 o "Supplier" 7;
- `requested_by` (FK a `users`) y `created_at`.

No guarda asunto ni cuerpo: el correo de credenciales de HU-03 contendrá una contraseña temporal (RN-HU03-01). La pantalla muestra los últimos 20 envíos.

### D7. Mensaje en texto plano UTF-8
`build_message()` crea un `email.message.EmailMessage` con:
- `From`, `To`, `Cc` si hay copias, y `Subject`;
- `Date` y `Message-ID` (`make_msgid`);
- `Auto-Submitted: auto-generated`;
- cuerpo `text/plain; charset=utf-8`.

El asunto compuesto ya viene en una sola línea (HU-05) y las direcciones están validadas, así que no hay inyección de cabeceras. `EmailMessage` rechaza de todos modos los saltos de línea en las cabeceras.

### D8. Validación de listas de correos
Cada lista llega en un `textarea`, con direcciones separadas por saltos de línea, comas o punto y coma. El servicio:
1. separa y recorta cada dirección, descarta las vacías y convierte a minúsculas;
2. elimina los duplicados conservando el orden;
3. valida cada dirección con `EmailStr` de pydantic, igual que las altas de usuario y proveedor, y con un máximo de 254 caracteres;
4. verifica la cardinalidad.

Todos los errores se reportan juntos con HTTP 400 y el formulario conserva lo capturado. Los mensajes llevan la forma "<Lista>: …".

### D9. Correo de prueba de texto fijo
`POST /admin/notifications/test` valida la dirección, envía el asunto "Correo de prueba del Portal de Proveedores ULTRASIST" y un cuerpo fijo con el nombre del Administrador y la fecha. Registra el envío con `event = NULL` y redirige a la pantalla con el resultado (`?test=sent` o `?test=failed`). Supuesto S4.

### D10. Eventos de log
- `notification.sent`: `delivery_id`, `event_code` (`TEST` para la prueba), `transport`, `recipients` (número de destinatarios) y `duration_ms`;
- `notification.failed`: los mismos campos y `error_type`;
- `notification_recipients.updated`: `lists`, los códigos de las listas que cambiaron.

Ninguno lleva direcciones, asunto, cuerpo ni el mensaje del error, que puede citar direcciones; ese mensaje queda en la bitácora.

## Risks / Trade-offs

- **[Servidor SMTP lento]** El envío síncrono retrasa la respuesta hasta `SMTP_TIMEOUT`. → Tiempo de espera configurable de 10 s por omisión; los avisos del MVP son unitarios.
- **[Correo fallido sin reintento]** → La bitácora lo muestra en la pantalla de Notificaciones y cada HU consumidora decide su reintento.
- **[Archivos `.eml` con contraseñas temporales en desarrollo]** (HU-03). → Permisos `0600`, `outbox/` en `.gitignore` y fuera de `storage/` (no entra en los respaldos), y el transporte `file` está prohibido en producción.
- **[Buzón mal configurado]** Una dirección válida pero inexistente produce rebotes que el portal no ve. → Correo de prueba antes de operar.

## Migration Plan

1. `alembic upgrade head` aplica `0005_notification_recipients`: crea las tablas, siembra el buzón y las copias vacías.
2. En producción, definir `MAIL_BACKEND=smtp`, `SMTP_HOST`, `MAIL_FROM` y, si aplica, las credenciales antes de arrancar; si no, el arranque se aborta con el motivo.
3. Enviar un correo de prueba desde Administración › Notificaciones.

Rollback: el downgrade borra las tres tablas. Si el Administrador ya cambió la configuración o hay envíos registrados, lanza `NotImplementedError` ("… Restaure un respaldo."), igual que 0004.

## Open Questions

- Dirección de remitente definitiva de ULTRASIST y datos del servidor SMTP: se definen en `.env` al desplegar.
- Si se quiere un reintento manual de cualquier envío fallido desde la bitácora: hoy sólo HU-03 lo ofrecerá, para las credenciales.
