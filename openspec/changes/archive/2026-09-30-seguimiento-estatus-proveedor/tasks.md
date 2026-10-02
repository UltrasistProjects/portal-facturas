> Todas las rutas son relativas a la raíz de la PoC (`PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress-V1/PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress/`). Cada grupo termina con `ruff` limpio y sus pruebas en verde sobre PostgreSQL.

## 1. Seguimiento y causa

- [x] 1.1 `app/services/invoice_history_service.py`: vista del proveedor ("PMO", sin `COMMENT`), evento de cancelación y `last_decision` (D1, D2); `review_service.prepare_resend` usa `last_decision`.
- [x] 1.2 `app/routers/invoices.py`: historial para todos los roles y texto de la causa.
- [x] 1.3 `invoices/detail.html`: sección "Seguimiento" del proveedor, aviso de la causa en "Rechazada" y "Observaciones", retiro del aviso genérico.

## 2. Tablero

- [x] 2.1 `app/routers/dashboard.py` y `dashboard.html`: seis indicadores con enlace al listado filtrado; estilos en `app.css` (D3).
- [x] 2.2 `scripts/seed_db.py`: auditoría de envío y cancelación de la demo para que su "Seguimiento" no quede vacío (D4).

## 3. Pruebas

- [x] 3.1 `tests/test_seguimiento_estatus.py`: seguimiento del proveedor sin revisor ni `COMMENT`, cancelación en el historial, causa igual al correo en "Rechazada" y "Observaciones", sin aviso tras reenviar, filtro "Observaciones" con alcance, 404 de otro proveedor, indicadores y sus enlaces.
- [x] 3.2 Ajustar las pruebas del historial y del tablero que asumían el comportamiento anterior.

## 4. Documentación y verificación

- [x] 4.1 `README.md`: seguimiento del proveedor, causa y tablero.
- [x] 4.2 `python scripts/check.py` en verde.
- [x] 4.3 Verificación en navegador como proveedor: tablero, filtro, rechazada, observaciones con reenvío y cancelada.
- [x] 4.4 `openspec validate seguimiento-estatus-proveedor --strict` sin errores.
