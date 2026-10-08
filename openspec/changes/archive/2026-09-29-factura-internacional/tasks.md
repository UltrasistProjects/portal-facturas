> Todas las rutas son relativas a la raíz de la PoC (`PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress-V1/PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress/`). Cada grupo termina con `ruff` limpio y sus pruebas en verde sobre PostgreSQL.

## 1. Datos del Invoice

- [x] 1.1 `app/schemas/__init__.py`: `ForeignInvoiceData` con los validadores de D2 y las etiquetas de sus campos en `FIELD_LABELS`.
- [x] 1.2 Nuevo `app/services/foreign_invoice_service.py`: `parse_data` (esquema más moneda activa), `duplicate_folios`, `lock_supplier` (bloqueo consultivo de D5) e `invoice_text` (texto y legibilidad del Invoice vigente, D7).
- [x] 1.3 `app/routers/invoices.py`: alta con los datos del Invoice para el internacional (D3); `POST /invoices/{id}/amounts` (D4); control de duplicados al cargar un `FOREIGN_INVOICE` (D5).
- [x] 1.4 Plantillas: bloque "Datos del Invoice" en `invoices/new.html` y panel de edición en `invoices/documents.html` (D10).

## 2. Validación internacional

- [x] 2.1 `app/services/validation_settings_service.py`: `receiver_address` en `RuleParameters` (D9).
- [x] 2.2 `app/rules/xml_rules.py`, `supplier_rules.py`, `financial_rules.py` y `semantic_rules.py`: variantes `NOT_APPLICABLE`/`NOT_EVALUATED` para el internacional (D6).
- [x] 2.3 Nuevo `app/rules/international_rules.py`: INT-001 a INT-004 (D8) y FIN-007.
- [x] 2.4 `app/services/validation_engine.py`: rama según el origen, lectura del Invoice y FIN-007 (D6, D7).

## 3. Detalle y reglas

- [x] 3.1 `invoices/detail.html` y su contexto: "Datos del Invoice" y UUID "No aplica (Invoice)" (D10).
- [x] 3.2 `admin/rules.html`: nota sobre INT-002 e INT-003.

## 4. Demo

- [x] 4.1 `app/core/demo.py`: cuenta `proveedor3@poc.local` sin acceso rápido; `tests/conftest.py`: su contraseña en `TEST_PASSWORDS`.
- [x] 4.2 `scripts/seed_db.py`: proveedor, usuario, contrato e Invoice PDF demo; factura "INV-2026-0042" en "Cargada" (D11).

## 5. Pruebas

- [x] 5.1 `tests/test_factura_internacional.py`: registro (éxito, total que no cuadra, moneda inactiva, fecha futura, nacional sin campos), edición (Observaciones con auditoría, enviada 409, otro rol 403, nacional 400, sin cambios sin auditoría).
- [x] 5.2 Duplicados: otra factura (409 sin archivo escrito), mismo nombre con otra capitalización, reemplazo en la misma factura, otro proveedor, FIN-007 al enviar con el folio en la evidencia.
- [x] 5.3 Motor: reglas N/A del internacional, INT con datos presentes y ausentes, PDF sin texto, comparaciones desactivadas, dirección vacía, FIN-001 con el monto capturado, envío exitoso de extremo a extremo y factura nacional sin cambios.
- [x] 5.4 Detalle y carga documental: "Datos del Invoice" para el internacional y "Datos CFDI" para el nacional.
- [x] 5.5 Ajustar `tests/test_archivos_minimos.py` (alta internacional con datos del Invoice) y las pruebas que cuentan usuarios, proveedores o facturas demo.

## 6. Documentación y verificación

- [x] 6.1 `README.md`: sección "Facturas de proveedores internacionales", cuenta demo nueva y retiro de la limitación de las facturas internacionales.
- [x] 6.2 `python scripts/check.py` en verde: ruff, formato, `alembic check`, pytest con cobertura ≥ 93 % y `pip-audit`.
- [x] 6.3 Verificación en la aplicación con navegador: registrar un Invoice como `proveedor3@poc.local`, cargar documentos, intentar un Invoice repetido, verificar, enviar la demo INV-2026-0042 y revisar el detalle como PMO.
- [x] 6.4 `openspec validate factura-internacional --strict` sin errores.
