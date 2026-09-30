> Todas las rutas son relativas a la raíz de la PoC (`PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress-V1/PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress/`). Cada grupo termina con `ruff` limpio y sus pruebas en verde sobre PostgreSQL.

## 1. Utilidades

- [x] 1.1 `app/repositories/pagination.py`: `PER_PAGE`, `escape_like`, `search`, `list_query` y `back_to` (D1, D4); `invoice_repository` usa `escape_like` compartido.

## 2. Listados

- [x] 2.1 Proveedores: búsqueda, filtro y paginación; autorización sobre la página (D5).
- [x] 2.2 Usuarios: búsqueda, paginación, alta visible y retorno tras habilitar/deshabilitar (D3, D4).
- [x] 2.3 Contratos: búsqueda, paginación (más recientes primero), alta visible y retorno tras la enmienda.
- [x] 2.4 Claves de catálogo: `page_entries` y `counts`, búsqueda, paginación, alta visible y retorno tras editar o cambiar el estado (D6).
- [x] 2.5 Bitácora de envíos paginada (D7).
- [x] 2.6 Plantillas y estilos: barra de búsqueda y componente de paginación en las cinco pantallas.

## 3. Pruebas

- [x] 3.1 `tests/test_listados_paginados.py`: segunda página, página fuera de rango, búsqueda (mayúsculas, comodines literales), filtro + búsqueda, conteos del catálogo en SQL, alta visible, retorno tras acciones, `back_to` sin otras claves, bitácora de 30 envíos, consultas constantes por página.
- [x] 3.2 Ajustar las pruebas que asumían listas completas o los 20 envíos.

## 4. Documentación y verificación

- [x] 4.1 `README.md`: listados paginados y búsqueda.
- [x] 4.2 `python scripts/check.py` en verde.
- [x] 4.3 Verificación en navegador: alta de usuario visible, paginación y búsqueda en las cinco pantallas.
- [x] 4.4 `openspec validate paginacion-listados --strict` sin errores.
