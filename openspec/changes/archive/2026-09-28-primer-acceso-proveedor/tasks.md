> Todas las rutas son relativas a la raíz de la PoC (`PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress-V1/PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress/`). Cada grupo termina con `ruff` limpio y sus pruebas en verde sobre PostgreSQL.

## 1. Marca y migración

- [x] 1.1 `app/models/__init__.py`: `User.must_change_password` (`Boolean`, `default=False`, `server_default` falso) (D1).
- [x] 1.2 Revisión `alembic/versions/0008_password_change_required.py` (`down_revision = "0007_validation_rules_catalogs"`): columna, marca para los usuarios con auditoría `USER_CREATED` y downgrade que elimina la columna (D9).
- [x] 1.3 `tests/test_migraciones.py`: instalación nueva con la columna, usuarios auditados marcados y demo sin marcar, y downgrade.

## 2. Bloqueo y cambio de contraseña

- [x] 2.1 `app/core/security.py`: `get_authenticated_user`, excepción `PasswordChangeRequired` y `get_current_user` que la lanza con la marca activa (D2); handler en `app/main.py` (303 a `/account/password`).
- [x] 2.2 `app/routers/auth.py`: el login redirige a `/account/password` con la marca activa (D3).
- [x] 2.3 `app/routers/auth.py`: `GET` y `POST /account/password` con CSRF, limitación de intentos, validación en el orden de D4, hash nuevo, marca apagada, rotación de sesión (D5), auditoría `PASSWORD_CHANGED` con `forced` y redirección a `/?notice=password_changed`.
- [x] 2.4 `app/templates/auth/change_password.html` con los bloques `content` y `anonymous` (D7); enlace "Cambiar contraseña" en `base.html`; aviso en `dashboard.html` y parámetro `notice` en `app/routers/dashboard.py` (D6).

## 3. Contraseñas asignadas por otra persona

- [x] 3.1 `app/services/supplier_access_service.py`: marca activa al crear el usuario en la autorización y al reenviar; `can_resend` y `resend_credentials` según la marca, con el mensaje nuevo (D8).
- [x] 3.2 `app/routers/admin.py`: marca activa en el alta de `/admin/users`; `admin/users.html` con el aviso del alta y "Contraseña temporal" en el listado (D10).
- [x] 3.3 `app/templates/suppliers/detail.html` (y el contexto de `app/routers/suppliers.py` si hace falta): estado de la contraseña en "Acceso al portal" (D10).

## 4. Pruebas

- [x] 4.1 `tests/test_primer_acceso.py`: primer acceso del proveedor autorizado, navegación bloqueada (GET y POST sin efectos), cierre de sesión disponible, usuario creado por el Administrador, usuario demo sin marca.
- [x] 4.2 Cambio de contraseña: éxito con la temporal inválida después, política (sin carácter especial, común), varios errores juntos, igual a la actual, actual incorrecta con intento registrado, 429 tras 5 fallos, CSRF, cambio voluntario, página con y sin menú.
- [x] 4.3 Sesiones y auditoría: otra sesión revocada, identificador nuevo en la sesión actual, `PASSWORD_CHANGED` con `forced` y sin contraseñas, rechazos sin auditoría.
- [x] 4.4 `tests/test_acceso_proveedores.py`: usuario autorizado con la marca, login con la temporal que lleva al cambio, reenvío a quien entró sin cambiar, 409 a quien ya cambió, estado de la contraseña en el expediente.
- [x] 4.5 Ajustar las pruebas existentes que crean usuarios en `/admin/users` e inician sesión con ellos.

## 5. Documentación y verificación

- [x] 5.1 `README.md`: sección "Primer acceso y cambio de contraseña"; retirar "Pendiente de HU-10" y ajustar el reenvío de credenciales y las limitaciones.
- [x] 5.2 `python scripts/check.py` en verde: ruff, formato, `alembic check`, pytest con cobertura ≥ 93 % y `pip-audit`.
- [x] 5.3 Verificación en la aplicación: autorizar un proveedor, entrar con la temporal del `.eml`, intentar navegar, cambiar la contraseña, volver a entrar con la nueva y revisar el expediente. Con el enlace nuevo, el menú lateral del Administrador mide 843 px y el botón de cerrar sesión quedaba fuera de pantalla en ventanas más bajas: `app/static/css/app.css` agrega `overflow-y:auto` a `.sidebar`.
- [x] 5.4 `openspec validate primer-acceso-proveedor --strict` sin errores.
