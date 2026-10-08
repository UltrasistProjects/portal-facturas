## Context

- `users.supplier_id`: FK nullable a `suppliers.id` (`RESTRICT`). Los `INTERNAL`/`ADMIN` no tienen proveedor; el `PROVIDER` debe tenerlo, pero hoy nada lo garantiza.
- La autorización de proveedores (HU-03, `supplier_access_service`) crea el usuario con `supplier_id=supplier.id`: esa vía ya es correcta.
- `POST /admin/users` valida con `UserCreate` (rol, correo, contraseña) y asigna `supplier_id` sólo si el rol es `PROVIDER`, sin exigirlo ni comprobar que exista (la FK sólo protege contra un id inexistente con un 500).
- `invoices._ensure_supplier_active` trata igual "sin proveedor" y "proveedor no autorizado".

## Decisions

### D1. Validación en el router
`POST /admin/users` valida primero `UserCreate` (datos de cada campo) y después la regla rol–proveedor: con `PROVIDER` y sin `supplier_id`, 400 "Seleccione el proveedor del usuario"; con un id inexistente (`db.get(Supplier, id)`), 400 "Proveedor inexistente" en lugar de un error de FK; con otro rol, el proveedor se ignora. El rechazo vuelve a pintar la pantalla con el formulario abierto y los valores capturados (sin contraseña).

*Alternativa:* un `model_validator` en `UserCreate`. Sus errores no tienen campo y `validation_message` los etiquetaría mal; además la existencia del proveedor necesita la base de datos.

### D2. `CHECK` en la base de datos
```
(role = 'PROVIDER' AND (supplier_id IS NOT NULL OR NOT is_active))
OR (role <> 'PROVIDER' AND supplier_id IS NULL)
```
Es la última barrera: cualquier otra vía (SQL, una ruta futura) queda cubierta. El `OR NOT is_active` admite a los usuarios huérfanos que deja la migración sin borrarlos: son evidencia de auditoría (inicios de sesión, cambios de contraseña) y el borrado físico de usuarios no existe en el portal.

*Alternativa:* `CHECK ... NOT VALID` sin tocar los datos. Cualquier `UPDATE` posterior de esa fila (p. ej. registrar su último acceso o deshabilitarlo) fallaría con un 500.

### D3. Migración de datos
Antes del `CHECK`, en SQL con `RETURNING` → `audit_logs`, como `0010` y `0011`:
- `PROVIDER` activos sin proveedor → `is_active = false`, `user_sessions.revoked_at = now()`, auditoría `USER_DEACTIVATED_WITHOUT_SUPPLIER`;
- `INTERNAL`/`ADMIN` con proveedor → `supplier_id = NULL`, auditoría `USER_SUPPLIER_CLEARED` con el id anterior.

El downgrade sólo retira el `CHECK`.

### D4. Habilitar y mensaje al registrar
`toggle_user` responde 409 al habilitar un `PROVIDER` sin proveedor (antes del `UPDATE`, así el `CHECK` nunca se viola desde la aplicación). `_ensure_supplier_active` distingue "Su usuario no está vinculado a un proveedor. Contacte al Administrador".

### D5. Formulario
La opción vacía del selector pasa a "Seleccione un proveedor (sólo Proveedor)" y los proveedores se ordenan por razón social. Sin JavaScript: el servidor valida.

## Risks / Trade-offs

- **[Usuario huérfano deshabilitado]** → no puede reactivarse ni editarse: se da de alta uno nuevo con su proveedor (el correo del huérfano queda ocupado; el Administrador puede usar otro correo o, si el proveedor aún está "Registrado", autorizarlo en `/suppliers` con otro correo). Se documenta en el README.
