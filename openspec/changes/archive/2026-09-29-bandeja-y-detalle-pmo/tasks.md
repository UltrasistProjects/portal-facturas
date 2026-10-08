> Todas las rutas son relativas a la raíz de la PoC (`PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress-V1/PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress/`). Cada grupo termina con `ruff` limpio y sus pruebas en verde sobre PostgreSQL.

## 1. Bandeja del PMO

- [x] 1.1 `app/repositories/invoice_repository.py`: `status` opcional con "Enviada" por omisión para `INTERNAL`/`ADMIN`, orden según el estatus efectivo (D1), filtro `origin` (D2) y `warning_counts` (D3).
- [x] 1.2 `app/routers/invoices.py` (listado): parámetros `status` opcional y `origin`, estatus efectivo y advertencias en el contexto.
- [x] 1.3 `invoices/list.html` (filtro de origen, estatus efectivo seleccionado) y `components/invoice_table.html` (columnas de D4).

## 2. Visualización de documentos

- [x] 2.1 Nuevo `app/services/document_view_service.py`: `kind`, `pdf_page_count`, `render_page` y `read_text` (D5).
- [x] 2.2 `app/routers/invoices.py`: `GET .../view`, `.../pages/{n}` y `.../image` con la autorización de la descarga.
- [x] 2.3 Nueva `invoices/document_view.html` y enlace "Ver" en el detalle.

## 3. Detalle para la revisión

- [x] 3.1 `SUPPLIER_ORIGIN_LABELS` en `app/core/constants.py` y global de plantillas.
- [x] 3.2 Nuevo `app/services/invoice_history_service.py` (D6).
- [x] 3.3 `invoices/detail.html`: bloque "Proveedor" e "Historial" para `INTERNAL`/`ADMIN`.

## 4. Pruebas

- [x] 4.1 `tests/test_revision_pmo.py`, bandeja: filtro inicial y orden, segunda página, todos los estados, proveedor sin cambios, filtro por origen, columnas y advertencias, consultas constantes.
- [x] 4.2 Visualización: PDF (páginas `image/png`), página fuera de rango, imagen `inline`, XML escapado, texto truncado, documento ajeno 404, documento de otra factura 404, PDF dañado.
- [x] 4.3 Detalle: bloque del proveedor, historial con envío, observaciones y reenvío, "Sin envíos ni revisiones", proveedor sin historial.
- [x] 4.4 Ajustar las pruebas del listado que asumían el orden por creación para `INTERNAL`/`ADMIN`.

## 5. Documentación y verificación

- [x] 5.1 `README.md`: bandeja del PMO y visualización de documentos.
- [x] 5.2 `python scripts/check.py` en verde.
- [x] 5.3 Verificación en navegador como PMO: bandeja, filtros, "Ver" un PDF, un XML y una imagen, historial.
- [x] 5.4 `openspec validate bandeja-y-detalle-pmo --strict` sin errores.
