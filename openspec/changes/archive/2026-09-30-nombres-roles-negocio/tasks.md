> Todas las rutas son relativas a la raíz de la PoC (`PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress-V1/PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress/`). Cada grupo termina con `ruff` limpio y sus pruebas en verde sobre PostgreSQL.

## 1. Enumeración y código

- [x] 1.1 `app/core/constants.py`: `Role.ADMINISTRADOR`, `Role.PROVEEDOR`, `Role.PMO` con los nombres del negocio como valor (D1).
- [x] 1.2 `app/models/__init__.py`: `enum_column` guarda el valor (`values_callable`) y `ck_users_provider_supplier` compara con `'Proveedor'` (D2).
- [x] 1.3 Routers, `invoice_repository.py`, `supplier_access_service.py` y `scripts/seed_db.py` con los miembros nuevos.

## 2. Plantillas

- [x] 2.1 Comparaciones de rol en `base.html`, `dashboard.html`, `components/invoice_table.html`, `contracts/list.html`, `invoices/list.html`, `suppliers/detail.html` y `suppliers/list.html`.
- [x] 2.2 `admin/users.html`: selector Proveedor, PMO y Administrador (D4); "—" en lugar de "Interno" para usuarios sin proveedor.

## 3. Base de datos

- [x] 3.1 Revisión `alembic/versions/0014_business_role_names.py` con la migración de datos y el downgrade (D3); `alembic check` sin diferencias.

## 4. Pruebas

- [x] 4.1 `tests/test_migraciones.py`: roles renombrados, `CHECK role` y `ck_users_provider_supplier` con los nombres nuevos, y downgrade.
- [x] 4.2 Pruebas que usaban `PROVIDER`, `INTERNAL` o `ADMIN` en datos a la cabeza de la cadena (`test_usuarios_admin.py`, `test_altas.py`, `test_primer_acceso.py`, `test_listados_paginados.py`, `test_acceso_proveedores.py`, `test_carga_masiva_proveedores.py`, `test_respaldos.py`, entre otras).

## 5. Documentación y verificación

- [x] 5.1 `README.md`: nombres de los roles y migración `0014`.
- [x] 5.2 `pytest` en verde (891 pruebas, cobertura 97%) y `ruff check` / `ruff format --check` limpios.
- [x] 5.3 `openspec validate nombres-roles-negocio --strict` sin errores.
