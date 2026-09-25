> Todas las rutas son relativas a la raíz de la PoC (`PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress-V1/PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress/`). Cada grupo termina con `ruff` limpio y sus pruebas en verde sobre PostgreSQL.

## 1. Plantilla de credenciales y migración

- [x] 1.1 `app/core/constants.py`: `NotificationEvent.SUPPLIER_CREDENTIALS` y la etiqueta "Autorizado" para `SupplierStatus.ACTIVE` (D1).
- [x] 1.2 `app/services/notification_templates.py` (D7):
  - variables `usuario`, `contrasena_temporal` y `url_portal` con descripción y ejemplo;
  - evento "Credenciales de acceso" con destinatario `Recipient.SUPPLIER`, sus variables y obligatorias, y el texto predeterminado;
  - argumentos nuevos de `compose()`.
- [x] 1.3 Revisión `alembic/versions/0006_supplier_credentials.py` (`down_revision = "0005_notification_recipients"`):
  - `CHECK notificationevent` de `notification_templates`, `notification_copies` y `email_deliveries` con el evento nuevo;
  - plantilla de credenciales en la versión 1, con el texto copiado en la migración;
  - downgrade que restaura las restricciones y borra la plantilla, o que lanza `NotImplementedError` si la plantilla se modificó o hay envíos de credenciales.
- [x] 1.4 Pruebas en `tests/test_plantillas_notificacion.py` (cinco plantillas, variables y vista previa de credenciales, texto predeterminado válido, composición), `tests/test_migraciones.py` (instalación nueva, downgrade sin cambios y bloqueado) y `tests/test_integridad.py` (evento de credenciales aceptado en las tres tablas).

## 2. Servicio de acceso de proveedores

- [x] 2.1 `app/services/secret_vault.py`: protocolo `SecretVault`, `NullSecretVault` y `get_vault()` (D6).
- [x] 2.2 `app/services/supplier_access_service.py`, `authorize()` (D3, D8):
  - validación de la selección (400/404);
  - bloqueo `FOR UPDATE` y clasificación (autorizado, con usuario previo, omitido, conflicto);
  - usuario `PROVIDER` con contraseña temporal, resguardo antes del commit y auditoría;
  - 409 ante una carrera por el correo;
  - credenciales con `notify(SUPPLIER_CREDENTIALS)` después del commit;
  - evento `supplier.bulk_authorize`.
- [x] 2.3 `provider_user()`, `credentials_status()` (último envío de credenciales del proveedor), `failed_credentials()` (para el listado) y `authorization_summary()` (D5).
- [x] 2.4 `resend_credentials()` (D9) con sus cuatro condiciones, contraseña nueva, resguardo, auditoría `SUPPLIER_CREDENTIALS_RESENT` y envío.

## 3. Rutas e interfaz

- [x] 3.1 `app/routers/suppliers.py`:
  - `GET /suppliers` con `?status=` y `?authorization=`;
  - `POST /suppliers/authorize` y `POST /suppliers/{supplier_id}/credentials` (sólo `ADMIN`, CSRF);
  - `GET /suppliers/{id}` con `?credentials=`;
  - alta individual en `REGISTERED` con el correo único (D10).
- [x] 3.2 `app/templates/suppliers/list.html`: filtro por estatus, formulario de autorización con casillas sólo en "Registrado", "seleccionar todos", contador, botón, modal de confirmación, marca "Credenciales no enviadas" y resumen de la autorización.
- [x] 3.3 `app/static/js/supplier_authorize.js`: seleccionar todos, contador, botón deshabilitado sin selección y confirmación con el modal de Bootstrap.
- [x] 3.4 `app/templates/suppliers/detail.html`: sección "Acceso al portal" (sólo `ADMIN`) con usuario, último acceso, último envío, botón "Reenviar credenciales" y resultado del reenvío.

## 4. Pruebas de la capacidad

- [x] 4.1 `tests/test_acceso_proveedores.py`: fixtures que crean proveedores "Registrado" y limpian usuarios, envíos y buzón de salida; utilidades para autorizar y leer credenciales de los `.eml`.
- [x] 4.2 Estatus y alta individual: etiqueta "Autorizado", alta en "Registrado", correo en uso (`tests/test_altas.py`).
- [x] 4.3 Acceso: INTERNAL y PROVIDER, CSRF, casillas y botón sólo para `ADMIN`, filtro por estatus.
- [x] 4.4 Reglas: autorización de registrados, omitidos, conflicto de correo, selección vacía, más de 100, id inexistente y atomicidad.
- [x] 4.5 Credenciales: usuario creado, inicio de sesión con la contraseña del correo, contraseña fuera de `users`, `audit_logs`, `email_deliveries` y log, proveedor con usuario propio, resguardo con un `SecretVault` de prueba y fallo del resguardo que revierte.
- [x] 4.6 Correo: `.eml` sin `Cc` con asunto, usuario, contraseña y `/login`; servidor caído que conserva la autorización.
- [x] 4.7 Resumen: enviado, fallido y "Ya tenía usuario"; omitidos y no autorizados; parámetro que no es una autorización.
- [x] 4.8 Expediente y reenvío: datos de acceso, marca en el listado, reenvío exitoso con contraseña nueva, las cuatro condiciones con 409 y resultado del reenvío.
- [x] 4.9 Auditoría de la autorización y del reenvío, sin contraseñas; operaciones rechazadas sin auditoría.
- [x] 4.10 `tests/test_observabilidad.py`: `supplier.bulk_authorize` con sus contadores, sin correos ni contraseñas.

## 5. Documentación y verificación

- [x] 5.1 `README.md`: sección "Autorización y acceso de proveedores" (estatus, autorización masiva, correo de credenciales, reenvío, ClickCloud pendiente) y la plantilla de credenciales en la tabla de plantillas.
- [x] 5.2 `python scripts/check.py` en verde: ruff, formato, `alembic check`, pytest con cobertura ≥ 93 % y `pip-audit`. *(552 pruebas, cobertura 96.69 %, sin vulnerabilidades conocidas.)*
- [x] 5.3 Verificación en la aplicación con navegador: carga masiva, filtro, selección, confirmación, resumen, `.eml` de credenciales, inicio de sesión del proveedor y reenvío. *(Chromium headless (Playwright) sobre uvicorn y una base temporal: 22/22 verificaciones, con la carga masiva real de `carga_masiva_proveedores_demo.xlsx`, 10 proveedores autorizados, cancelación del modal, un `.eml` por proveedor, inicio de sesión con la contraseña temporal, reenvío y consola sin errores ni violaciones de CSP.)*
- [x] 5.4 `openspec validate acceso-proveedores --strict` sin errores.
