## Why

Al probar el portal, el Administrador creó un usuario y no lo encontró en la lista: se guardó bien (una sola transacción), pero `/admin/users` muestra a todos los usuarios ordenados por nombre, sin búsqueda ni paginación, y el nuevo quedó a mitad de la lista. Lo mismo ocurre con proveedores, contratos y claves de catálogo: cargan todos los registros en una sola página, crecen sin límite y un alta no se distingue. La bitácora de correos muestra sólo los últimos 20 envíos y los anteriores no se pueden consultar.

Regla de negocio pedida: **todas las listas deben estar paginadas.** Hoy sólo lo están las facturas (25 por página) y el Audit Log (50).

## What Changes

- **Paginación en SQL** (`LIMIT/OFFSET`, 25 por página, con el mismo componente del listado de facturas) en:
  - Proveedores (`/suppliers`), conservando el filtro de estatus y la autorización por lotes sobre la página;
  - Usuarios (`/admin/users`);
  - Contratos (`/contracts`), del más reciente al más antiguo;
  - Claves de cada catálogo (`/admin/catalogs/{catalogo}`); los conteos "activas de N" se calculan en SQL;
  - Bitácora de envíos de correo (`/admin/notifications`): todos los envíos, del más reciente al más antiguo, en lugar de sólo 20.
- **Búsqueda** (`q`, sin distinguir mayúsculas, `%` y `_` literales) en proveedores (razón social, RFC o identificador fiscal, correo), usuarios (nombre, correo), contratos (proyecto, proveedor) y claves de catálogo (clave, descripción).
- **El alta muestra lo creado:** crear un usuario, un contrato o una clave regresa a la lista filtrada por ese registro (correo, proyecto o clave) con el aviso "Usuario creado", "Contrato creado" o "Clave agregada". El alta de proveedor ya lleva a su expediente.
- **Las acciones conservan la página:** habilitar o deshabilitar un usuario, registrar una enmienda de contrato y editar o desactivar una clave regresan a la misma búsqueda y página.

**No se paginan** las pantallas que no son listados de registros sino formularios o resultados que se guardan o leen completos: la matriz de archivos mínimos (se guarda entera con su huella), las reglas de validación, las plantillas de correo y el índice de los seis catálogos (conjuntos fijos), la vista previa de una carga masiva (resultado de un archivo, hasta 1000 filas) y la matriz de evidencia de una factura. Los selectores de proveedor de los formularios de alta tampoco cambian.

**Fuera de alcance:** transacciones distribuidas o SAGA. El alta ya es atómica: el registro y su auditoría se confirman en una sola transacción de PostgreSQL.

## Capabilities

### New Capabilities
- `listados-paginados`: paginación, búsqueda y retorno tras las altas y acciones en los listados de administración.

### Modified Capabilities
- `notificaciones-correo`: la bitácora de envíos se consulta completa y paginada, no sólo los últimos 20.

## Impact

- **Código:** `app/repositories/pagination.py` (búsqueda compartida y cadena de consulta), `app/repositories/invoice_repository.py` (usa la búsqueda compartida); `app/routers/suppliers.py`, `app/routers/admin.py`, `app/routers/contracts.py`; `app/services/catalog_service.py` y `app/services/notification_service.py` (consultas paginadas).
- **Plantillas:** `suppliers/list.html`, `admin/users.html`, `contracts/list.html`, `admin/catalog.html`, `admin/notifications.html`.
- **Esquema:** sin cambios.
- **Pruebas:** nuevo `tests/test_listados_paginados.py`; ajustes en las pruebas que asumían listas completas o los 20 envíos.
- **Documentación:** `README.md`.
