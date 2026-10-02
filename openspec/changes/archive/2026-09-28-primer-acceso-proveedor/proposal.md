## Why

La minuta del 21-sep-2026 (sección "Acceso de proveedores") dice: "En el primer inicio de sesión, el proveedor deberá cambiar la contraseña antes de continuar". HU-10 (RF-06) lo pide con la política de complejidad: al menos 8 caracteres, una letra, un número y un carácter especial. El texto literal de HU-10 dice "cambiar mi correo"; es una errata de "contraseña", como la interpreta RF-06.

HU-03 ya entrega al proveedor autorizado una contraseña temporal por correo, pero nada lo obliga a cambiarla: puede operar indefinidamente con una contraseña que viajó en claro por correo (README, "Pendiente de HU-10"). Es la primera HU de EP-01 y precede al registro de facturas (HU-12, HU-15).

## What Changes

- **Marca de contraseña asignada** en cada usuario (`users.must_change_password`). Se activa cuando la contraseña la asignó otra persona:
  - al crear el usuario `PROVIDER` en la autorización (HU-03);
  - al reenviar credenciales (HU-03);
  - al dar de alta un usuario en `/admin/users` (P-02 de EP-01, valor por defecto: sí).
- **Cambio obligatorio:** mientras la marca esté activa, cualquier página o acción del portal redirige a **Cambiar contraseña** (`/account/password`). Sólo quedan disponibles esa página y el cierre de sesión. El inicio de sesión lleva directamente a ella.
- **Página "Cambiar contraseña":** pide la contraseña actual, la nueva y su confirmación.
  - La nueva debe cumplir la política vigente (RF-06), coincidir con su confirmación y ser distinta de la actual.
  - Los errores se reportan juntos.
  - Una contraseña actual incorrecta cuenta como intento fallido en la limitación de intentos del correo.
- **Al guardar:**
  - el portal guarda el nuevo hash y apaga la marca;
  - revoca todas las sesiones del usuario y abre una nueva;
  - audita `PASSWORD_CHANGED` sin la contraseña;
  - lleva al tablero con el aviso "Contraseña actualizada".
- **Cambio voluntario:** la misma página queda disponible para cualquier usuario desde el menú lateral ("Cambiar contraseña").
- **Reenvío de credenciales (HU-03):** procede mientras el proveedor conserve la contraseña temporal (marca activa), en lugar de "mientras nunca haya iniciado sesión". **BREAKING (comportamiento):** un proveedor que entró con la temporal pero no la cambió ahora sí puede recibir credenciales nuevas.
- **Expediente del proveedor y listado de usuarios:** indican si la contraseña sigue siendo la temporal.
- **Migración** `0008_password_change_required`: agrega la columna y activa la marca en los usuarios que se crearon desde la aplicación (S2).

**Fuera de alcance:**
- rotación periódica (HU-11) y recuperación de contraseña: fuera del MVP;
- caducidad de la contraseña temporal;
- purgar la contraseña temporal de ClickCloud, cuyo adaptador aún no existe (RN-HU03-01).

## Supuestos

- **S1.** La marca aplica a toda contraseña que asignó otra persona, no sólo a la del proveedor (P-02 de EP-01, valor por defecto). Los usuarios demo del seed no la tienen: sus contraseñas están documentadas y la demo debe entrar directo.
- **S2.** La migración marca a todo usuario que tenga un registro de auditoría `USER_CREATED`, es decir, los creados por la autorización de proveedores o por `/admin/users`. Hasta hoy nadie puede cambiar su propia contraseña, así que todos conservan la que les asignó otra persona, aunque ya hayan iniciado sesión. El seed no audita sus altas, de modo que los usuarios demo no se marcan.
- **S3.** No se agrega fecha de caducidad ni historial de contraseñas: basta con que la nueva sea distinta de la actual.
- **S4.** Revocar las demás sesiones al cambiar la contraseña expulsa a quien hubiera usado la contraseña temporal interceptada del correo.

## Capabilities

### New Capabilities
<!-- Ninguna: el cambio de contraseña pertenece a la autenticación. -->

### Modified Capabilities
- `autenticacion-sesiones`: requisitos nuevos de cambio obligatorio de la contraseña asignada, cambio de contraseña (validación, limitación de intentos, rotación de sesión) y su auditoría. La política de contraseñas también aplica al cambio.
- `acceso-proveedores`: el usuario creado al autorizar nace con la marca; el reenvío de credenciales depende de la marca y no del último acceso; el expediente muestra el estado de la contraseña.

## Impact

- **Código:**
  - `app/models/__init__.py`: `User.must_change_password`;
  - `app/core/security.py`: dependencia que exige el cambio y excepción `PasswordChangeRequired`; `app/main.py`: su handler (303 a `/account/password`);
  - `app/routers/auth.py`: login que lleva al cambio y rutas `GET`/`POST /account/password`;
  - `app/services/supplier_access_service.py`: marca al crear el usuario y al reenviar, y nueva condición de reenvío;
  - `app/routers/admin.py`: marca en el alta de usuarios;
  - `app/routers/dashboard.py`: aviso "Contraseña actualizada".
- **Plantillas:** nueva `auth/change_password.html`; `base.html` (enlace en el menú), `dashboard.html`, `admin/users.html`, `suppliers/detail.html`.
- **Esquema:** revisión Alembic `0008_password_change_required`, posterior a `0007_validation_rules_catalogs`.
- **Rutas nuevas:** `GET /account/password` y `POST /account/password`.
- **Dependencias:** ninguna nueva.
- **Pruebas:** nuevo `tests/test_primer_acceso.py`; ajustes en `tests/test_acceso_proveedores.py` (reenvío), `tests/test_migraciones.py` y las pruebas que crean usuarios desde `/admin/users` e inician sesión con ellos.
- **Documentación:** `README.md` (retira "Pendiente de HU-10").
