> Rutas relativas a la raíz de la PoC (`PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress-V1/PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress/`). La suite corre sobre PostgreSQL (`DOCKER_CONTEXT=default docker compose up -d --wait db`). Cada grupo termina con `ruff` limpio.

## 1. Esquema: órdenes de compra, liga de la factura y migración

- [x] 1.1 `app/core/constants.py`: `UNIT_EQUIVALENCES` (sección 6.5 de la HU), `AMOUNT_TOLERANCE`, `PURCHASE_ORDER_ITEM_KEYS` y los textos de las reglas que se comparten.
- [x] 1.2 `app/models/__init__.py`:
  - modelo `PurchaseOrder` con sus `CHECK`, índices y FK (D1);
  - `Invoice.purchase_order_id` y `Invoice.purchase_order`;
  - `Invoice.project_name` nulo;
  - `__all__`.
- [x] 1.3 Revisión `alembic/versions/0023_ferromex_purchase_orders.py` (D14): tabla, FK, `project_name` nulo, niveles de `invoice_document_types`, receptor INTERMODAL MEXICO en las Reglas de Validación (XML-011 activa) y constante `RECEIVER`. Downgrade protegido. Verificar `alembic check` sin diferencias.
- [x] 1.4 `tests/conftest.py`: `restore_validation_rules` aplica `RECEIVER` de `0023` después de `0020`.
- [x] 1.5 `purchase_order_service.validate_items`, `OrderItem` y `OrderView` (D2).

## 2. Extracción de los datos de la factura

- [x] 2.1 `xml_service.parse_cfdi`: serie, folio, régimen del emisor, `unit_key`, `unit`, `identification`, `tax_object` y `kind` de cada impuesto (D3).
- [x] 2.2 `app/services/ai`: `extract_invoice` y `AnalyzerUnavailable` en la interfaz; el mock y los esqueletos de Azure la lanzan; se retira `semantic_compare` y `extract_fields` (D4).
- [x] 2.3 `invoice_extraction_service`: `parse_printed_cfdi`, `extract_pdf`, `extract`, `stored_data`, `UnreadableInvoiceError`, mensaje de PDF y XML distintos, número y periodo derivados, y evento `invoice.extracted` (D3).
- [x] 2.4 `scripts/cfdi_demo.py`: generador de la representación impresa (PyMuPDF) y del XML de un CFDI, con `EXAMPLE_3668`. Generar `data/demo_documents/factura_3668.pdf` y `factura_3668.xml`.
- [x] 2.5 `tests/test_extraccion_factura.py`:
  - `parse_cfdi` ampliado;
  - conceptos, emisor, receptor y totales de la 3668 desde el PDF;
  - PDF sin texto con el analizador no disponible;
  - PDF y XML con UUID distinto;
  - número y periodo derivados.

## 3. Reglas PRV y OC (funciones puras)

- [x] 3.1 `app/rules/text.py` con `normalize_text`, `compact` y `same_name`. `international_rules` y `mock_analyzer` lo importan.
- [x] 3.2 `app/rules/supplier_identity_rules.py` (PRV-001 a PRV-003; D7).
- [x] 3.3 `app/rules/purchase_order_rules.py`: `detect_order_number`, `match_items`, `units_match`, IVA de RD-13 y `purchase_order_rules` nacional e internacional (D7, secciones 6.4 y 6.7 de la HU).
- [x] 3.4 Pruebas unitarias sin base de datos en `tests/test_orden_compra.py`: cada escenario de "Validación de la factura contra la orden de compra" a nivel de reglas, empates y partida más específica, unidades, tolerancia, `NOT_APPLICABLE` en cascada, internacional, y PRV-001 a PRV-003.

## 4. Servicio de órdenes de compra, motor y envío

- [x] 4.1 `purchase_order_service`: `find` con `FOR UPDATE` (nacional por RFC, internacional por `supplier_id`), `active_invoices`, `search` paginado y `detail` (D8).
- [x] 4.2 `validation_rules_service.rule_set` agrega los regímenes fiscales activos al `RuleSet`.
- [x] 4.3 `validation_engine.run_validation` (D5):
  - fuente de datos XML o PDF;
  - `xml_rules` con `source`;
  - PRV y OC;
  - sin CON, SEM, SUP-002, DOC-005, FIN-001, FIN-003 ni FIN-006;
  - número de O.C. en la factura;
  - `purchase_order` en el resultado;
  - `identity_checks` para la Validación 1 (D6).
- [x] 4.4 Reglas que cambian:
  - `document_rules` sin DOC-005;
  - `financial_rules` sin contrato (FIN-002, FIN-004, FIN-005);
  - `supplier_rules` sin SUP-002;
  - `xml_rules` evalúa sobre datos del PDF.

  Se eliminan `contract_rules.py` y `semantic_rules.py`.
- [x] 4.5 `submission_service.submit_invoice` liga `purchase_order_id` al pasar a "Enviada" (D9).
- [x] 4.6 Pruebas con base de datos en `tests/test_orden_compra.py`:
  - entidad e integridad;
  - envío del ejemplo 3668 con OC-001 a OC-012 en `PASS` y liga;
  - orden de otro proveedor;
  - orden ya facturada y con factura cancelada;
  - "Verificar" no liga;
  - envíos concurrentes de dos facturas contra la misma orden.

## 5. Asistente nacional: Archivos → Revisión → Envío

- [x] 5.1 `file_service.check_upload(filename, content)` factorizado desde `_save` y usado por el Paso 1.
- [x] 5.2 `routers/invoices.py` (D10):
  - `GET/POST /invoices/new` nacional multipart;
  - `GET /invoices/{id}/data`;
  - reemplazo del PDF/XML con nueva extracción y `INVOICE_DATA_EXTRACTED`;
  - `next=data`.
- [x] 5.3 Plantillas:
  - `invoices/new.html` (Archivos, o formulario internacional);
  - `invoices/review.html` (imagen + tarjetas con ✓/✗ + checklist + Verificar/Enviar);
  - pasos de `invoices/documents.html`;
  - `app/static/js/app.js` sin el selector de contrato;
  - estilos de la revisión en `app.css`.
- [x] 5.4 Detalle (D11): datos del comprobante con su fuente, "Orden de compra" en el encabezado y panel de la orden. Se retiran "Proyecto", "Contrato" y "Conciliación contractual"; enlace "Revisión" para el proveedor nacional.
- [x] 5.5 `tests/test_registro_por_archivos.py`: escenarios de "Registro de la factura a partir de sus archivos", "Revisión de los datos junto a la imagen de la factura", "Reemplazo del PDF o del XML" y "Validación de los datos del proveedor".

## 6. Proveedor internacional contra orden de compra

- [x] 6.1 `schemas.ForeignInvoiceData` con `purchase_order_number` y validación del número de factura del registro; `foreign_invoice_service` (`FIELDS`, `form_values`, `apply_data` y la propuesta desde el texto del Invoice) (D12).
- [x] 6.2 Registro internacional en `POST /invoices/new` (sin contrato, periodo, proyecto ni líder; periodo de la fecha) y `components/foreign_invoice_fields.html` con la orden de compra.
- [x] 6.3 Detalle internacional con la orden de compra.
- [x] 6.4 Actualizar `tests/test_factura_internacional.py` a los escenarios de la spec `factura-internacional` y a las reglas OC internacionales.

## 7. Consulta de órdenes de compra y menú

- [x] 7.1 `app/routers/purchase_orders.py` (`GET /purchase-orders`, `GET /purchase-orders/{id}`, PMO y Administrador) registrado en `main.py`.
- [x] 7.2 Plantillas `purchase_orders/list.html` y `purchase_orders/detail.html`.
- [x] 7.3 `base.html`: "Órdenes de compra" en lugar de "Contratos"; "Requisitos mínimos" sin "Alta de contrato".
- [x] 7.4 Pruebas en `tests/test_orden_compra.py` y `tests/test_listados_paginados.py`: listado, búsqueda por convenio y nombre, página fuera de rango, detalle, 403 del proveedor, 404 y menú por rol.

## 8. Retiro de contratos sin tocar el esquema

- [x] 8.1 Eliminar el código de contratos (D13):
  - `routers/contracts.py`, `contract_service.py` y `contract_requirements_service.py`;
  - las plantillas `contracts/*` y `admin/contract_requirements.html`, y `contract_activate.js`;
  - las rutas `/admin/contract-requirements*`;
  - `save_contract_file`, los esquemas `Contract*` y las constantes de contratos que ya no se usan.
- [x] 8.2 Modelos de contratos obsoletos, sin relaciones; `Supplier.contracts` e `Invoice.contract` retirados. El listado de proveedores pasa de "Contratos" a "Órdenes de compra" con un conteo en SQL.
- [x] 8.3 `scripts/reporte_monedas.py` sin contratos.
- [x] 8.4 Prueba de aislamiento: ningún módulo fuera de `app/models` y `alembic/` importa `Contract`, `ContractAmendment` ni `ContractDocumentType`. `/contracts` y `/admin/contract-requirements` responden 404. Las tablas y filas de contratos siguen presentes después de `0023`.

## 9. Datos demo

- [x] 9.1 CFDI demo (`cfdi_demo_correcto.xml`, `cfdi_demo_monto_excedido.xml`, `cfdi_demo_rfc_incorrecto.xml`):
  - receptor INTERMODAL MEXICO;
  - emisor con `RegimenFiscal` y nombre del proveedor;
  - concepto con `ClaveUnidad`, `Unidad`, `ObjetoImp` y `(OC/<convenio>)`.
- [x] 9.2 `scripts/seed_db.py` (D15):
  - el proveedor persona física es el del ejemplo (`GOHS60031745A`);
  - órdenes de compra sembradas (ejemplo 25704872, una por factura demo, sin entrega, con dos partidas, recorrido manual e internacional en USD);
  - facturas demo sin contrato y ligadas a su orden si están enviadas;
  - Invoice internacional con INTERMODAL MEXICO y su orden;
  - mensaje final con los conteos.
- [x] 9.3 Pruebas del seed: orden 25704872 con `Docto Material` `5000527117`, orden internacional en USD, ninguna factura demo con contrato y escenarios demo con sus resultados esperados (`test_demo_workflow.py`).

## 10. Suite existente

- [x] 10.1 `tests/cfdi.py` con los helpers comunes:
  - XML y PDF del CFDI con cambios;
  - registro por archivos;
  - fábrica `purchase_orders`;
  - `ready_invoice`;
  - proveedor demo del ejemplo.
- [x] 10.2 Reescribir sobre el registro por archivos y las órdenes de compra las suites que registraban con contrato:
  - `test_registro_envio`, `test_archivos_minimos`, `test_motor`, `test_folio_y_reglas`, `test_financial_rules`, `test_validation_engine`;
  - `test_flujo`, `test_cancelacion`, `test_pago_facturas`, `test_revision_pmo`, `test_moneda_del_catalogo`;
  - `test_reglas_validacion`, `test_observabilidad`, `test_permissions`, `test_altas`, `test_datos_proveedor`;
  - `test_requisitos_alta`, `test_integridad`, `test_migraciones`, `test_listados_paginados`, `test_tema_keycloak`, `test_demo_workflow` y las demás que fallen.
- [x] 10.3 Eliminar `test_contratos.py` y `test_requisitos_contrato.py`.
- [x] 10.4 Pruebas de migración: upgrade de `0022` a `0023` con contratos, enmiendas y facturas ligadas; niveles y reglas actualizados; downgrade protegido.
- [x] 10.5 `scripts/check.py` en verde: ruff, `alembic check`, pytest con cobertura ≥ 93 % y `pip-audit`. Ejecutado con `--skip-audit` (1306 pruebas, cobertura 96.86 %): el cambio no agrega ni actualiza dependencias.

## 11. Recorrido manual y Playwright

- [x] 11.1 `data/pruebas-ferromex/_generador/generar.mjs`:
  - receptor INTERMODAL MEXICO;
  - representación impresa con las etiquetas de la sección 6.3 de la HU;
  - conceptos con `(OC/<convenio>)`;
  - A-1001 contra una orden que cuadra y A-1002 con importe distinto;
  - sin carpeta de contrato.

  Regenerar los documentos (con `HU_DIR` si hace falta).
- [x] 11.2 Probar el parser contra los PDF regenerados del recorrido (`test_extraccion_factura.py`).
- [x] 11.3 `GUIA-PRUEBAS.md` y `DATOS-A-CAPTURAR.txt`: sin contrato; registro por archivos; factura 3668 del ejemplo con el proveedor físico demo; resultados esperados por regla.
- [ ] 11.4 Playwright (`tests/hu`):
  - retirar `20-HU-22-requisitos-contrato.spec.ts`;
  - ajustar HU-12, HU-13, HU-15, HU-16 y el recorrido del video al nuevo asistente.

  No se ejecuta en esta tarea: requiere el portal y Keycloak arriba.

  Avance 2026-11-24:
  - `20-HU-22-requisitos-contrato.spec.ts` retirado.
  - Recorrido en video nuevo, `video/recorrido-orden-compra.spec.ts` (utilidades en `video/comun.ts`). Pasa sobre una demo recién reiniciada y deja `evidencias/video/recorrido-orden-compra.webm`, de 9 min.
  - Pendiente: HU-12, HU-13, HU-15 y HU-16, y `video/recorrido.spec.ts`, que todavía registra la factura con contrato.

  Hecho: se retiró la spec de HU-22 y su entrada de `hu-catalogo.json`, y los fixtures usan el receptor INTERMODAL MEXICO. Pendiente: reescribir sobre el registro por archivos las specs que registran facturas (05 HU-04, 06 HU-05, 09 HU-08, 10 HU-12, 11 HU-13, 12 HU-15, 17 HU-20, 21 HU-23 y `video/recorrido.spec.ts`), y sembrar por ejecución las órdenes de compra que citan sus CFDI (OC-012).

- [x] 11.5 Set de prueba `data/pruebas-factura-3668` (2026-11-24). Contiene la factura 3668 como PDF con texto y la maqueta del documento de negocio, dos Vo.Bo. y el complemento de pago, con su `INSTRUCTIVO.md`. El flujo de la proveedora demo `proveedor2@poc.local` pasa por Observaciones, Autorizada, Pagada y complemento adjuntado. `tests/test_set_factura_3668.py` lo recorre. El set sacó a la luz dos ajustes:
  - el parser lee RFC sin etiqueta (sin tomar el del PAC) y el objeto de impuesto con su nombre ("02 - Sí objeto de impuesto.");
  - una factura PPD registrada sólo con el PDF requiere Complemento de Pago (delta `pago-facturas`).

  `EXAMPLE_3668` toma la fecha (2026-01-03T14:24:46) y el lugar de expedición (36100) del documento.

## 12. Documentación y cierre

- [x] 12.1 `README.md`: asistente por archivos, órdenes de compra, reglas nuevas y retiradas, datos demo y migración `0023`.
- [x] 12.2 `docs/source-of-truth/INDICE_HUs.md`: HU-24 y HU-22 retirada en la rama `ferromex`.
- [x] 12.3 Criterio de terminado: `grep -ril contract app/` sólo encuentra `app/models`, `app/core/constants.py` y el CSS de terceros de iconos. `openspec validate ferromex-validacion-orden-compra --strict` en verde.
