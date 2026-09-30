## Why

Los roles del sistema son **Administrador**, **Proveedor** y **PMO** (ERS ULTRASIST). El portal los llamaba con nombres en inglés que no existen en el negocio: `ADMIN`, `PROVIDER` e `INTERNAL`. Esos nombres aparecían en el selector de rol de `/admin/users`, en la tabla de usuarios, en la base de datos (`users.role`), en el README y en las specs, y obligaban a traducir: el README documentaba "`INTERNAL` (PMO)". Se reemplazan por los nombres del negocio en todas las capas.

## What Changes

- **Enumeración:** `Role.ADMINISTRADOR = "Administrador"`, `Role.PROVEEDOR = "Proveedor"`, `Role.PMO = "PMO"`. El antiguo `INTERNAL` es el PMO.
- **Persistencia:** `users.role` guarda el valor de la enumeración (`Administrador`), no el nombre del miembro (`ADMINISTRADOR`), que es lo que SQLAlchemy guarda por defecto.
- **Datos existentes** (migración `0014_business_role_names`): renombra los roles de los usuarios, amplía la columna a `VARCHAR(13)` y rehace los `CHECK role` y `ck_users_provider_supplier`. Tiene downgrade.
- **Interfaz:** el selector de rol ofrece "Proveedor", "PMO" y "Administrador" (Proveedor sigue siendo la opción por defecto). La tabla de usuarios muestra el rol con su nombre del negocio y "—" en lugar de "Interno" cuando el usuario no tiene proveedor.
- **Specs y README:** los requisitos y escenarios usan los nombres del negocio.

**Fuera de alcance:** los registros de auditoría previos conservan el nombre que tenía el rol al registrarse (son evidencia). No se renombran los identificadores internos del código que no son nombres de rol (`is_admin`, `provider_only`, `reviewers_only`) ni las rutas `/admin/...`.

## Capabilities

### New Capabilities

Ninguna.

### Modified Capabilities

- `integridad-datos`: nuevo requisito "Nombres de los roles" (`CHECK role` y migración `0014`); la regla rol–proveedor usa los nombres nuevos.
- `acceso-proveedores`, `administracion-usuarios`, `almacenamiento-documentos`, `archivos-minimos-factura`, `autenticacion-sesiones`, `cancelacion-facturas`, `catalogo-proveedores`, `catalogos-referencia`, `factura-internacional`, `flujo-facturas`, `motor-validacion`, `notificaciones-correo`, `plantillas-notificacion`, `proteccion-http`, `reglas-validacion`, `revision-pmo`, `trazabilidad-contratos`: los requisitos que nombraban un rol usan `Administrador`, `Proveedor` y `PMO`. El comportamiento no cambia.

## Impact

- **Código:** `app/core/constants.py` (`Role`), `app/models/__init__.py` (`enum_column` y `CHECK`), `app/routers/admin.py`, `contracts.py`, `invoices.py`, `suppliers.py`, `app/repositories/invoice_repository.py`, `app/services/supplier_access_service.py`, `scripts/seed_db.py`.
- **Plantillas:** `base.html`, `dashboard.html`, `admin/users.html`, `components/invoice_table.html`, `contracts/list.html`, `invoices/list.html`, `suppliers/detail.html`, `suppliers/list.html`.
- **Esquema:** revisión `0014_business_role_names`. Las bases existentes deben ejecutar `alembic upgrade head` antes de iniciar la aplicación.
- **Pruebas:** `tests/test_migraciones.py` (nueva prueba de la migración) y las pruebas que usaban los nombres anteriores.
- **Documentación:** `README.md`.
