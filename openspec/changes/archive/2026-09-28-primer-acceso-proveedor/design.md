## Context

HU-03 crea el usuario `PROVIDER` con una contraseña temporal aleatoria y la envía por correo. Hoy nada obliga a cambiarla, y ningún usuario puede cambiar su propia contraseña: la única forma de fijar una es el alta en `/admin/users`, la autorización o el reenvío de credenciales, y en los tres casos la asigna otra persona.

Estado actual relevante:

- **Autenticación:** `get_current_user` (`app/core/security.py`) resuelve la sesión del servidor y es la dependencia de todas las rutas autenticadas; `require_roles` se apoya en ella. `POST /logout` no la usa. Un `401` se traduce en un 303 a `/login` en el handler de `app/main.py`.
- **Política:** `app/core/passwords.py` (`password_problems`) implementa RF-06 y la lista de contraseñas comunes; hoy sólo la usan el alta de usuarios y el seed.
- **Limitación de intentos:** `login_throttle.check/record` por correo e IP.
- **Sesiones:** `session_service.create/revoke/revoke_all_for_user`; el login ya rota el identificador.
- **Interfaz:** `base.html` pinta el menú si hay `user` en el contexto y el bloque `anonymous` si no; el login usa ese bloque. No hay mensajes flash entre redirecciones.

## Goals / Non-Goals

**Goals:**
- Que ninguna contraseña asignada por otra persona siga en uso después del primer acceso.
- Que el bloqueo no dependa de que cada ruta nueva lo recuerde.
- Reutilizar la política, la limitación de intentos y las sesiones que ya existen.

**Non-Goals:**
- Rotación periódica (HU-11), recuperación de contraseña y caducidad de la temporal.
- Purgar la temporal de ClickCloud (adaptador inexistente).

## Decisions

### D1. Marca booleana `users.must_change_password`
Columna `BOOLEAN NOT NULL DEFAULT false`. La activan la autorización, el reenvío de credenciales y el alta en `/admin/users`; la apaga el cambio de contraseña. El seed crea con el valor por defecto.

*Alternativas:* derivarla de `last_login_at` (lo que hacía el reenvío) no distingue "entró" de "cambió la contraseña". Una fecha `password_changed_at` serviría también para HU-11, pero ninguna HU del MVP la necesita y la marca expresa exactamente la regla.

### D2. El bloqueo vive en la dependencia de autenticación
`get_current_user` pasa a ser `get_authenticated_user` (resuelve la sesión, sin exigir nada) más la verificación de la marca: si está activa, lanza `PasswordChangeRequired`. Un handler en `app/main.py` la traduce a `RedirectResponse("/account/password", 303)`. Sólo las rutas de `/account/password` usan `get_authenticated_user`.

Como toda ruta autenticada ya depende de `get_current_user` (directamente o por `require_roles`), una ruta nueva queda bloqueada sin hacer nada. `POST /logout` no depende de ella y sigue disponible. Los archivos estáticos y `/health` no se autentican.

*Alternativa:* un middleware que lea la sesión y redirija. Resolvería la sesión dos veces por petición y tendría que mantener una lista de rutas permitidas separada de los routers.

### D3. El login lleva directo al cambio
Si el usuario tiene la marca, `POST /login` redirige a `/account/password` en lugar de `/`. Ahorra un salto; sin esto, D2 igual lo llevaría ahí desde `/`.

### D4. Orden de la validación del cambio
1. `login_throttle.check(email, ip)`: si hay bloqueo, 429 sin verificar Argon2, igual que el login.
2. Contraseña actual: si falla, `record(FAILURE)` y 400 con ese único error; no tiene sentido validar la nueva si quien escribe no conoce la actual.
3. Nueva contraseña: `password_problems`, confirmación y "distinta de la actual", todos juntos.

Un cambio exitoso registra `record(SUCCESS)`, que reinicia el contador de fallos como lo hace un login exitoso.

Los intentos fallidos del formulario cuentan para el bloqueo del login porque verifican el mismo secreto: sin esto, alguien con una sesión robada podría adivinar la contraseña actual sin límite.

### D5. Rotación de sesión al cambiar
`revoke_all_for_user` seguido de `create`: se revocan todas las sesiones del usuario, incluida la actual, y se emite un identificador nuevo; `request.session.clear()` descarta el token CSRF anterior. Quien hubiera entrado con la temporal interceptada del correo queda fuera.

### D6. Aviso "Contraseña actualizada" por parámetro
El portal no tiene mensajes flash. El cambio redirige a `/?notice=password_changed` y el tablero muestra el texto sólo para claves conocidas; cualquier otro valor se ignora. Es el mismo enfoque de `?authorization=` en HU-02.

### D7. Página con y sin menú
`auth/change_password.html` define el bloque `content` (dentro del menú) y el bloque `anonymous` (pantalla aislada, como el login). La ruta pasa `user` al contexto sólo si la marca está apagada; con la marca activa se muestra aislada, con la política de contraseñas y el botón de cerrar sesión, porque los enlaces del menú sólo devolverían a la misma página. El menú lateral de todos los roles agrega "Cambiar contraseña".

### D8. Reenvío de credenciales según la marca
`can_resend` y `resend_credentials` cambian `last_login_at is None` por `must_change_password`. El reenvío deja la marca activa. Así el Administrador puede reenviar a un proveedor que entró, no cambió la temporal y perdió el correo; una vez cambiada, el reenvío responde 409 con "El proveedor ya cambió su contraseña temporal; no se generan credenciales nuevas.".

### D9. Migración `0008_password_change_required`
- Agrega la columna con `server_default false`.
- `UPDATE users SET must_change_password = true WHERE id IN (SELECT entity_id::int FROM audit_logs WHERE action = 'USER_CREATED' AND entity = 'User')`: los creados desde la aplicación (supuesto S2).
- Downgrade: elimina la columna. No se pierde información que la versión anterior pueda usar.

### D10. Estado visible para el Administrador
El expediente del proveedor muestra "Temporal, pendiente de cambio" o "Cambiada por el proveedor"; el listado de usuarios agrega "Contraseña temporal" junto al estado. El formulario de alta de usuarios avisa que el usuario deberá cambiar la contraseña en su primer acceso.

## Risks / Trade-offs

- **[Pruebas que crean usuarios en `/admin/users` e inician sesión con ellos]** → quedarían redirigidas al cambio. Se ajustan para cambiar la contraseña o se crean los usuarios de prueba con la marca apagada.
- **[Un usuario marcado por la migración que ya trabajaba en el portal]** → en su siguiente acceso debe cambiar la contraseña. Es el comportamiento buscado: su contraseña la asignó otra persona. El README lo avisa.
- **[Bloqueo del login por fallos en el formulario de cambio]** → es intencional (D4) y usa los mismos tiempos que el login; el Administrador ve el evento `LOGIN_LOCKED` en la auditoría.
- **[Un proveedor olvida su contraseña ya cambiada]** → no hay recuperación en el MVP. El Administrador puede deshabilitar el usuario; la recuperación es una HU fuera del MVP.

## Migration Plan

1. `alembic upgrade head` aplica `0008_password_change_required`.
2. Los usuarios creados desde la aplicación deben cambiar su contraseña en su siguiente acceso; los usuarios demo no.
3. Rollback: `alembic downgrade 0007_validation_rules_catalogs` elimina la columna y la aplicación anterior vuelve a funcionar sin el cambio obligatorio.

## Open Questions

- P-02 de EP-01 (¿los usuarios internos también cambian la contraseña asignada?): se aplica el valor por defecto, sí. Si negocio responde que no, basta con no activar la marca en el alta de `/admin/users`.
