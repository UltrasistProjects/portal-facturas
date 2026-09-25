> Todas las rutas son relativas a la raíz de la PoC (`PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress-V1/PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress/`). Cada grupo termina con `ruff` limpio y sus pruebas en verde sobre PostgreSQL (`docker compose up -d --wait db`).

## 1. Configuración del transporte

- [x] 1.1 `app/core/config.py`: `mail_backend`, `mail_from`, `mail_outbox_dir` (anclada), `smtp_host`, `smtp_port`, `smtp_security`, `smtp_username`, `smtp_password` (`SecretStr`) y `smtp_timeout`, con los valores por omisión derivados de `app_env` y la validación de `SMTP_HOST` y `MAIL_FROM` con `smtp` (D2).
- [x] 1.2 `app/core/startup.py`: en producción, problemas por `MAIL_BACKEND=file` y por `SMTP_SECURITY=none`.
- [x] 1.3 `.env.example` con las variables de correo comentadas; `.gitignore` con `outbox/`; `tests/conftest.py` fija `MAIL_BACKEND=file` y `MAIL_OUTBOX_DIR` en el directorio temporal de la sesión.
- [x] 1.4 Pruebas en `tests/test_configuracion.py`: valores por omisión en desarrollo y en producción, SMTP sin servidor, SMTP sin remitente, cifrado desconocido y las dos verificaciones nuevas de arranque en producción.

## 2. Modelo y migración

- [x] 2.1 `app/core/constants.py`: enumeraciones `Mailbox` (`INVOICE_RECEPTION`) y `DeliveryStatus` (`SENT`, `FAILED`), y la etiqueta "Recepción de Facturas" del buzón.
- [x] 2.2 `app/models/__init__.py`: `NotificationMailbox`, `NotificationCopy` y `EmailDelivery` (D3, D6), con sus restricciones `UNIQUE` y `CHECK`, las FK con `restrict` y los índices de `email_deliveries` por `created_at` y por entidad. Añadirlos a `__all__`.
- [x] 2.3 Revisión `alembic/versions/0005_notification_recipients.py` (`down_revision = "0004_notification_templates"`):
  - tablas y restricciones;
  - buzón `INVOICE_RECEPTION` con `recepcionfacturas@ultrasist.com.mx`;
  - una fila de copias vacía por cada evento de factura;
  - downgrade que borra las tablas, o que lanza `NotImplementedError` ("… Restaure un respaldo.") si hay configuración modificada o envíos registrados.

  Verificar `alembic check` sin diferencias.
- [x] 2.4 Pruebas en `tests/test_integridad.py`: estatus de envío fuera de catálogo, buzón sin direcciones, segunda lista de copias para un evento y envío fallido sin error.
- [x] 2.5 Pruebas en `tests/test_migraciones.py`: nuevas tablas en `DOMAIN_TABLES`; instalación nueva con el buzón sembrado y cuatro listas de copias vacías; downgrade de `0005` sin cambios y regreso a `head`; downgrade bloqueado con un envío registrado.

## 3. Transporte y servicio de notificaciones

- [x] 3.1 `app/services/notification_templates.py`: enumeración `Recipient` (`RECEPTION`, `SUPPLIER`) con los textos actuales como valor, usada en `EventSpec.recipient` (D4); sin cambios visibles en HU-05.
- [x] 3.2 `app/services/mail_transport.py` (D1, D7): `build_message()`, `SmtpTransport`, `FileTransport` y `transport_from_settings()`.
- [x] 3.3 `app/services/notification_service.py`:
  - lectura de la configuración y `config_version()`;
  - `parse_addresses()` con normalización y validación (D8);
  - `save_recipients()` con bloqueo consultivo, huella (409), errores juntos (400), sin escritura ni auditoría si no hay cambios, auditoría `NOTIFICATION_RECIPIENTS_UPDATED` y evento `notification_recipients.updated` tras el commit.
- [x] 3.4 `notification_service.recipients_for()` (D4) y `notification_service.notify()` (D5): composición con la plantilla vigente, envío, registro en `email_deliveries`, eventos `notification.sent` y `notification.failed`, sin propagar errores de transporte.
- [x] 3.5 `notification_service.send_test()` (D9) y `recent_deliveries()` (últimos 20).

## 4. Rutas e interfaz

- [x] 4.1 `app/routers/admin.py`: `GET /admin/notifications` (avisos `?ok=` y `?test=`), `POST /admin/notifications` y `POST /admin/notifications/test`; sólo `ADMIN`, CSRF en los `POST`, y errores 400 o 409 en la misma página con lo capturado.
- [x] 4.2 `app/templates/admin/notifications.html`: buzón, copias por evento con el destinatario principal, huella oculta, correo de prueba, transporte en solo lectura y últimos envíos; sin scripts ni estilos en línea.
- [x] 4.3 `app/templates/base.html`: opción "Notificaciones" en el menú Administración, sólo para `ADMIN`.

## 5. Pruebas de la capacidad

- [x] 5.1 `tests/test_notificaciones_correo.py`: fixture que restaura la configuración sembrada y vacía la bitácora y el buzón de salida; utilidades para guardar y leer los `.eml`.
- [x] 5.2 Acceso: INTERNAL y PROVIDER en las tres rutas, CSRF y opción en el menú.
- [x] 5.3 Buzón y copias: instalación nueva, cambio del buzón, buzón vacío, copias iniciales y copia agregada.
- [x] 5.4 Validación: normalización, dirección inválida, demasiadas direcciones y varios errores conservando lo capturado.
- [x] 5.5 Concurrencia y sin cambios.
- [x] 5.6 Destinatarios: evento al buzón (con copia repetida), evento al proveedor y proveedor sin correo.
- [x] 5.7 Envío: archivo `.eml` con cabeceras y cuerpo UTF-8; servidor caído sin excepción; STARTTLS y autenticación con un `smtplib.SMTP` simulado; SSL; destinatario rechazado.
- [x] 5.8 Bitácora sin contenido y últimos 20 envíos en la pantalla.
- [x] 5.9 Correo de prueba: exitoso, fallido y dirección inválida.
- [x] 5.10 Transporte en solo lectura sin la contraseña, y auditoría (cambio y acciones sin auditoría).
- [x] 5.11 `tests/test_observabilidad.py`: `notification.sent`, `notification.failed` y `notification_recipients.updated`, y revisión del log sin contraseña SMTP, direcciones ni asunto.

## 6. Documentación y verificación

- [x] 6.1 `README.md`: sección "Correo y notificaciones" con las variables, el transporte `file`, la pantalla de Notificaciones, el servicio `notify()` para HU-03, HU-14 y HU-20, y la bitácora.
- [x] 6.2 `python scripts/check.py` en verde: ruff, formato, `alembic check`, pytest con cobertura ≥ 93 % y `pip-audit`. *(504 pruebas, cobertura 96.46 %, sin vulnerabilidades conocidas.)*
- [x] 6.3 Verificación manual en la aplicación: guardar el buzón, enviar un correo de prueba con el transporte `file` y revisar el `.eml`. *(Automatizada con Chromium headless (Playwright) sobre uvicorn y una base temporal: 17/17 verificaciones, incluidos errores de validación que conservan lo capturado, normalización, correo de prueba con su `.eml` en UTF-8, auditoría, 403 para el PMO y consola sin errores ni violaciones de CSP.)*
- [x] 6.4 `openspec validate configuracion-correos-notificacion --strict` sin errores.
