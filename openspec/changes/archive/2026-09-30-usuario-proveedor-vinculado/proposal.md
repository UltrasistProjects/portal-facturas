## Why

El Administrador creó en `/admin/users` el usuario `jobhdev@gmail.com` con rol Proveedor y dejó el selector de proveedor en "Ninguno". Se guardó con `users.supplier_id = NULL` y, al intentar registrar una factura, recibió 409 "Su proveedor no está autorizado para registrar facturas": un mensaje que sugiere un proveedor por autorizar cuando en realidad no hay ninguno.

`supplier_id` no se genera: es una llave foránea que apunta a un proveedor existente, y para ese correo no existía ninguno. Ninguna de las tres capas lo impidió:
- **formulario:** el selector ofrece "Ninguno" como primera opción, también para Proveedor;
- **esquema:** `UserCreate.supplier_id` es opcional y no se valida junto con el rol;
- **base de datos:** la columna admite `NULL` (los usuarios internos no tienen proveedor) y sólo existe el `CHECK` de valores del rol; nada liga el rol con el proveedor.

La vía normal para dar acceso a un proveedor es autorizarlo en `/suppliers` (HU-03), que crea el usuario con el `supplier_id` del proveedor. El alta manual debe cumplir la misma regla.

## What Changes

- **Alta de usuario:** con rol Proveedor, el proveedor es obligatorio y debe existir (HTTP 400 "Seleccione el proveedor del usuario" / "Proveedor inexistente"). Para Interno y Administrador se ignora. El formulario reemplaza "Ninguno" por "Seleccione un proveedor (sólo Proveedor)" y conserva lo capturado cuando el alta se rechaza.
- **Base de datos:** `CHECK ck_users_provider_supplier`: un usuario Proveedor activo tiene proveedor y un usuario Interno o Administrador no lo tiene.
- **Datos existentes** (migración `0013_provider_user_supplier`): cada usuario Proveedor sin proveedor se deshabilita, se revocan sus sesiones y se audita `USER_DEACTIVATED_WITHOUT_SUPPLIER`; un usuario Interno o Administrador con proveedor pierde el vínculo (`USER_SUPPLIER_CLEARED`). Así se valida el `CHECK` sin borrar a nadie.
- **Reactivación:** habilitar un usuario Proveedor sin proveedor responde 409 "El usuario no está vinculado a un proveedor: dé de alta uno nuevo con su proveedor".
- **Mensaje al registrar factura:** un usuario Proveedor sin proveedor recibe 409 "Su usuario no está vinculado a un proveedor. Contacte al Administrador" en lugar del mensaje de proveedor no autorizado.

**Fuera de alcance:** editar el proveedor de un usuario existente (no hay edición de usuarios; se da de alta uno nuevo) y crear el proveedor desde la pantalla de usuarios (el proveedor se registra y autoriza en `/suppliers`).

## Capabilities

### New Capabilities
- `administracion-usuarios`: alta y habilitación de usuarios por el Administrador con la regla rol–proveedor.

### Modified Capabilities
- `integridad-datos`: `CHECK` que liga el rol del usuario con su proveedor y migración de los datos existentes.
- `flujo-facturas`: mensaje específico para un usuario Proveedor sin proveedor al registrar una factura.

## Impact

- **Código:** `app/routers/admin.py` (alta y habilitación), `app/routers/invoices.py` (mensaje), `app/models/__init__.py` (`CHECK`).
- **Plantillas:** `admin/users.html`.
- **Esquema:** revisión `0013_provider_user_supplier`.
- **Pruebas:** nuevo `tests/test_usuarios_admin.py`; `tests/test_migraciones.py`, `tests/test_integridad.py`.
- **Documentación:** `README.md`.
