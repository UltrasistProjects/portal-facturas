> Todas las rutas son relativas a la raíz de la PoC (`PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress-V1/PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress/`). Cada grupo termina con `ruff` limpio y sus pruebas en verde sobre PostgreSQL.

## 1. Regla rol–proveedor

- [x] 1.1 `app/routers/admin.py`: proveedor obligatorio y existente para `PROVIDER`, ignorado para otros roles (D1).
- [x] 1.2 `app/routers/admin.py`: formulario conservado al rechazar y 409 al habilitar un `PROVIDER` sin proveedor (D1, D4).
- [x] 1.3 `app/routers/invoices.py`: mensaje para el usuario sin proveedor (D4).
- [x] 1.4 `admin/users.html`: opción vacía "Seleccione un proveedor (sólo Proveedor)" y valores conservados (D5).

## 2. Base de datos

- [x] 2.1 `app/models/__init__.py`: `ck_users_provider_supplier` (D2).
- [x] 2.2 Revisión `alembic/versions/0013_provider_user_supplier.py` con la migración de datos y el downgrade (D3); `alembic check` sin diferencias.

## 3. Pruebas

- [x] 3.1 `tests/test_usuarios_admin.py`: alta sin proveedor, proveedor inexistente, interno con proveedor, alta correcta, formulario conservado, habilitar huérfano 409 y mensaje al registrar factura (con el `CHECK`, un Proveedor activo sin proveedor ya no existe: se prueba la función del router).
- [x] 3.2 `tests/test_migraciones.py` (datos migrados y auditados, downgrade) y `tests/test_integridad.py` (`CHECK` por SQL).

## 4. Documentación y verificación

- [x] 4.1 `README.md`: usuarios Proveedor y su proveedor.
- [x] 4.2 `python scripts/check.py` en verde.
- [x] 4.3 `openspec validate usuario-proveedor-vinculado --strict` sin errores.
