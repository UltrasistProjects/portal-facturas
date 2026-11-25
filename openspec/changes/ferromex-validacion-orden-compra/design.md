## Context

La HU-24 (`docs/stories/new/HU-24 Validacion de factura contra orden de compra.md`) cambia el control de la factura en la rama `ferromex`: el contrato sale y la orden de compra de SAP entra. P-01 a P-04 están respondidas. El resto de las preguntas sólo cambia valores iniciales, una severidad o una tolerancia.

Estado actual del PoC (rutas relativas a `PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress-V1/PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress/`):

- **Alta de factura:** `POST /invoices/new` (`routers/invoices.py::create_invoice`) recibe por formulario `contract_id`, `invoice_number`, `service_period`, `project_name`, líder y O.C. opcional. Valida con `InvoiceCreate`, exige un contrato propio `ACTIVE` y crea la factura en "Borrador" con la moneda del contrato. Después redirige a `/invoices/{id}/documents`, donde cada archivo se carga con `POST /invoices/{id}/documents`. Esa carga analiza el PDF con `analyze_pdf` (texto y páginas) y el XML con `parse_cfdi`, y guarda el resultado en `metadata_json`.
- **Motor** (`services/validation_engine.py::run_validation`): parsea de nuevo el XML vigente. Copia UUID, fecha, importes y moneda a la factura (el UUID sólo si no lo tiene otra factura). Ejecuta `document_rules` (DOC-005 con `contract_requirements_service`), `xml_rules`, `supplier_rules` (SUP-002), `contract_rules` (CON-001 a CON-004), `date_rules`, `financial_rules` (FIN-001, FIN-003 y FIN-006 contra el contrato) y `semantic_outcomes` (SEM-001, con `LocalMockAnalyzer.semantic_compare`). No cambia el estatus.
- **Envío** (`submission_service.submit_invoice`): bloquea la fila, recalcula "Borrador"/"Cargada", ejecuta el motor y, sin `FAIL`, pasa a "Enviada".
- **Reglas de Validación** (`validation_rules`, por origen): XML-002 a XML-011 nacionales e INT-002 a INT-004 internacionales, sembradas por `0007`/`0020` con `ULT940623AG0`, "FERROMEX" y 03930. `validation_rules_service.rule_set` devuelve un `RuleSet` con las reglas y las monedas activas. La fixture `restore_validation_rules` de `conftest.py` las devuelve a los valores de `0007` + `0020`.
- **Archivos de la factura** (`invoice_document_types`, HU-04): XML, PDF, orden de compra y Vo.Bo. son Obligatorios para el nacional; contrato y anexo, Opcionales.
- **Visor:** `document_view_service.render_page` y `GET /invoices/{id}/documents/{doc}/pages/{n}` ya sirven páginas del PDF como PNG.
- **Ruta ocupada:** `GET /invoices/{id}/review` ya existe (redirige al panel `#decision` del PMO) y `POST /invoices/{id}/review` es la decisión del PMO (HU-20).
- **Contratos:** `routers/contracts.py` (listado, alta, enmiendas, expediente, documentos, activación), `contract_service.py`, `contract_requirements_service.py`, `rules/contract_rules.py` (que además define `normalize_text`, usado por `mock_analyzer`), pantallas de admin, `contract_activate.js`, `file_service.save_contract_file`, columna "Contratos" del listado de proveedores (`Supplier.contracts`), y `Invoice.contract` en el detalle ("Conciliación contractual").
- **Datos demo** (`scripts/seed_db.py`): 3 proveedores (moral `TIC210101ABC`, física `HELC900101XX1` y uno internacional), 3 contratos y 13 facturas. Los XML demo están emitidos a `ULT940623AG0`. La suite crea una base por sesión con ese seed.
- **Pruebas:** unas 20 de las 52 suites crean contratos o registran facturas con el formulario anterior (`create()` de `test_registro_envio.py` y equivalentes).

## Goals / Non-Goals

**Goals:**
- Registrar la factura nacional desde su PDF, con XML opcional, sin captura manual.
- Validar que la factura es del proveedor del usuario, está emitida a INTERMODAL MEXICO y corresponde, en encabezado y partida por partida, a una orden de compra entregada de ese proveedor.
- Una sola fuente de datos de la factura para el motor, la revisión y el detalle, sea XML, texto del PDF u OCR.
- Retirar los contratos de todo el código de la aplicación, conservando sus tablas y datos.
- Suite verde y `scripts/check.py` en verde en cada grupo de tareas.

**Non-Goals:**
- Integración con SAP, o alta y edición de órdenes de compra (se siembran y se consultan).
- Facturas parciales o con varias órdenes (P-06, P-07).
- Partidas del Invoice internacional (P-15).
- Corrección manual de los datos extraídos (P-08).
- OCR local. El analizador de Azure sigue como esqueleto (P-09).
- Borrar tablas o columnas de contratos (P-02).

## Decisions

### D1. Tabla `purchase_orders` y liga desde la factura
Modelo `PurchaseOrder` con las columnas de la sección 6.1 de la HU:
- `convenio` `BigInteger`, único (`uq_purchase_orders_convenio`);
- `rfc` `String(13)`, con índice;
- `supplier_name` `String(150)`;
- `order_date` `Date`;
- `total` y `taxes` `Money()`;
- `data` `JSONB`;
- `supplier_id` (`restrict("suppliers.id")`, nulo, con índice);
- `created_at` y `updated_at`.

`CHECK`:
- `ck_purchase_orders_convenio_positive` (`convenio > 0`);
- `ck_purchase_orders_total_positive` (`total > 0`);
- `ck_purchase_orders_taxes_non_negative` (`taxes >= 0`);
- `ck_purchase_orders_rfc_length` (`char_length(rfc) BETWEEN 12 AND 13`);
- `ck_purchase_orders_items` (`jsonb_typeof(data->'items') = 'array' AND jsonb_array_length(data->'items') >= 1`).

`Invoice.purchase_order_id` (`restrict("purchase_orders.id")`, nulo, índice) y `Invoice.purchase_order` (relación sin cascada). `Money()` es `NUMERIC(16,2)` en este proyecto: se usa el tipo del proyecto en lugar del `NUMERIC(18,2)` de la HU, por consistencia con los demás montos.

Alternativa descartada: tabla hija de partidas. La HU pide `DATA` en JSON con las etiquetas de SAP para la integración futura, y ninguna consulta filtra por partida.

### D2. Partidas: validación al sembrar y lectura tipada
`purchase_order_service.validate_items(data)` exige `items` como lista no vacía. Cada partida debe traer `Txt.brv`, `Ctd.Pedido`, `Unidad.Pedido`, `Prc.Neto` y `Moneda` no vacíos; `Ctd.Pedido` y `Prc.Neto` deben ser decimales positivos y `Moneda` tres letras. Si no, lanza `ValueError`. Lo usan el seed y las fixtures. `OrderItem` es una dataclass con propiedades `Decimal` (`quantity`, `net_price`) y `delivered` (`Docto Material` y `Fecha Conta` no vacíos). Las reglas reciben `OrderView` (encabezado + `OrderItem`), no el modelo ORM, para seguir siendo funciones puras.

### D3. Extracción en `invoice_extraction_service`
- `parse_cfdi` (en `xml_service`) agrega `series`, `folio`, `issuer_regime` y, por concepto, `unit_key` (`ClaveUnidad`), `unit`, `identification` (`NoIdentificacion`) y `tax_object` (`ObjetoImp`). Cada impuesto agrega `kind` (`Traslado` o `Retencion`). Sólo se agregan claves: los llamadores no cambian.
- `parse_printed_cfdi(text) -> dict | None` lee la representación impresa con expresiones por etiqueta (sección 6.3 de la HU) y devuelve las mismas claves que `parse_cfdi`:
  - el bloque del emisor va del inicio a "CLIENTE"/"RECEPTOR"; el del receptor, hasta "CONCEPTOS";
  - el nombre de cada parte es la línea anterior a su `RFC` (emisor) o la primera línea del bloque (receptor);
  - los conceptos se leen sobre el texto de la tabla con los espacios colapsados: cantidad, `clave - unidad`, identificación (primer token, si tiene un dígito), descripción, precio, objeto de impuesto (`0[1-8]`), importe y sus traslados ("002 IVA Base - … Tasa - … Importe - …");
  - los importes admiten `$` y separador de miles;
  - el total distingue `SUBTOTAL` de `TOTAL`.
- `extract_pdf(path)` devuelve el análisis de `analyze_pdf` y los datos:
  - con texto (`has_extractable_text`), `parse_printed_cfdi`, fuente `pdf_text`;
  - sin texto, `get_document_analyzer().extract_invoice(path)`, fuente `ocr`;
  - si el analizador lanza `AnalyzerUnavailable`, no hay datos.
- `extract(pdf_path, xml_path)` arma el resultado del Paso 1 y del reemplazo:
  - con XML, sus datos (fuente `xml`);
  - sin XML, los del PDF; si faltan los esenciales de RD-03, lanza `UnreadableInvoiceError` (HTTP 422, "No pudimos leer los datos de la factura en el PDF. Adjunte el XML.");
  - si los dos traen UUID y difieren, lanza `BusinessRuleError` (409, "El PDF y el XML no corresponden a la misma factura").
  - El PDF de demo sin datos legibles (`factura_demo.pdf`) acompañado de XML es válido: sólo se compara el UUID cuando ambos lo traen.
- Cada extracción registra el evento `invoice.extracted` con `invoice_id`, `source` y `complete`, sin datos fiscales (spec `observabilidad`).
- `stored_data(invoice)` devuelve los datos ya guardados de la factura: los del XML vigente o, sin XML, el `invoice` del `metadata_json` del PDF vigente. Los usan la revisión y el detalle.

Formato de `metadata_json`:
- **XML:** el diccionario de `parse_cfdi` con `"source": "xml"`, plano como hoy, así las filas anteriores siguen leyéndose igual;
- **PDF:** el análisis de hoy (`page_count`, `has_extractable_text`, `requires_ocr`, `metadata`, `text_preview`) más `"invoice": {…, "source": "pdf_text" | "ocr"}`, o `"invoice": null` si no se pudo leer.

### D4. El analizador documental extrae la factura; SEM-001 se retira
`DocumentAnalyzer.extract_fields` (genérico y sin llamadores) se sustituye por `extract_invoice(path) -> dict`, que devuelve las claves de `parse_cfdi` o lanza `AnalyzerUnavailable` (subclase de `RuntimeError`):
- `LocalMockAnalyzer` la lanza siempre: es el "no disponible" de la HU;
- los esqueletos de Azure la lanzan mientras no estén configurados.

`semantic_compare` sale de la interfaz y de los cuatro analizadores, porque SEM-001 se retira con la tecnología autorizada del contrato. Alternativa descartada: conservar `extract_fields` con el mock devolviendo `DEMO_<campo>`, que fabricaría datos falsos de una factura.

### D5. El motor evalúa sobre los datos extraídos
`run_validation` obtiene los datos así:
- **nacional con XML vigente:** `parse_cfdi`, como hoy;
- **nacional sin XML:** el `invoice` del `metadata_json` del PDF vigente; si falta (un PDF cargado antes de este cambio), lo extrae y lo guarda;
- **internacional:** como hoy, sin CFDI.

Con datos, copia UUID (si no es de otra factura), fecha, importes, moneda activa y el número de O.C. detectado a la factura. `xml_rules` recibe `source`:
- con datos del PDF, XML-001 resulta `NOT_APPLICABLE` "Sin XML: datos tomados del PDF" y las demás se evalúan con `source_document = "CFDI.pdf"`;
- sin datos de ninguna fuente, XML-001 resulta `FAIL` con el motivo;
- con el XML fuera de los obligatorios y sin PDF legible, se conserva el comportamiento `NOT_APPLICABLE` de hoy.

Orden de las familias: DOC, XML, PRV, SUP, DAT, FIN, OC (el internacional agrega INT y FIN-007). El resultado del motor agrega `purchase_order` (la orden resuelta o `None`) para el envío.

### D6. Validación 1 calculada al mostrar el Paso 2, no guardada
`validation_engine.identity_checks(db, invoice, data)` devuelve `PRV-001` a `PRV-003` y `xml_rules` sobre los datos guardados, con las Reglas de Validación y el catálogo vigentes. La revisión la calcula en cada `GET`, así que siempre corresponde a los archivos vigentes (RD-04) sin tocar `validation_results`. Esa tabla conserva el resultado de la última verificación o envío, que es lo que lee el PMO. Las mismas reglas se evalúan otra vez en el motor al verificar y al enviar.

### D7. Reglas `PRV-*` y `OC-*` como funciones puras
- `app/rules/text.py` reúne la normalización:
  - `normalize_text`, movida desde `contract_rules`;
  - `compact` (sin acentos, minúsculas, sólo letras y dígitos), movida desde `international_rules`, que la reimporta;
  - `same_name(a, b)`, la igualdad por `compact`. Así "S.A. de C.V." y "SA DE CV" coinciden, como pide RD-05.
- `app/rules/supplier_identity_rules.py::supplier_identity_rules(data, supplier, tax_regimes)`:
  - PRV-001 compara el RFC en mayúsculas y sin espacios; SUP-001 ya cubre "Autorizado";
  - PRV-002 usa `same_name`;
  - PRV-003 exige el régimen y que esté en las claves activas de `TAX_REGIME`;
  - para el internacional, las tres resultan `NOT_APPLICABLE`;
  - sin datos, `NOT_EVALUATED`.
- `app/rules/purchase_order_rules.py`:
  - `detect_order_number(descriptions) -> OrderReference` (RD-06): `(?<![A-Z0-9])OC(?:\s*[/:\-]\s*|\s+)(\d{6,10})(?!\d)` sin distinguir mayúsculas; reporta conflicto si hay números distintos;
  - `match_items(concepts, items) -> list[ItemMatch]` (RD-08, RD-09): la descripción compactada debe contener el `Txt.brv` compactado. Entre las partidas libres gana la de `Txt.brv` más largo; si empatan, es ambiguo. La partida usada se reserva en orden de concepto;
  - `units_match(unit_key, unit, sap_unit)` con `UNIT_EQUIVALENCES` de `constants.py` (RD-10, sección 6.5);
  - `purchase_order_rules(...)`: las doce reglas de la sección 6.4 (nacional) y de la 6.7 (internacional), con la tolerancia `AMOUNT_TOLERANCE = Decimal("0.01")` (RD-12) y el IVA de RD-13 (traslados `002` con tasa `0.160000`, o `tax` del comprobante si ningún concepto trae impuestos).

Detalle de las reglas:
- **Por concepto:** OC-007, OC-008, OC-009 y OC-011 generan un resultado por concepto con `source_reference = "Concepto <n>"`.
- **Cantidades en los mensajes:** sin ceros sobrantes ("cantidad 2 vs 1"); los importes, con dos decimales ("importe 3600.00 vs 3559.05").
- **Evidencia:** cada resultado guarda el encabezado de la orden (convenio, RFC, nombre, total, impuestos) y, en las reglas por concepto, la partida usada (RD-15).
- **Sin orden de compra:** sin OC-001 u OC-002, las demás resultan `NOT_APPLICABLE` "Sin orden de compra", un resultado por código.
- **OC-010:** compara contra las partidas usadas; si no se usó ninguna, contra todas.

### D8. `purchase_order_service`: consulta, bloqueo y orden ya facturada
- `find(db, number, supplier)`: `SELECT … FOR UPDATE` por `convenio` y `rfc = supplier.rfc` (nacional) o `supplier_id = supplier.id` (internacional) (RD-07). El bloqueo vive hasta el `commit` del endpoint: dos envíos que citan la misma orden se ejecutan uno después del otro, y el segundo ve la liga del primero (RD-16). Al verificar, el bloqueo dura sólo la petición.
- `active_invoices(db, order, invoice)`: folios internos de las otras facturas ligadas a la orden cuyo estatus no es "Rechazada" ni "Cancelada".
- `search(db, q, page)` para el listado: si `q` son sólo dígitos, busca por convenio exacto o por texto en RFC y nombre; si no, por texto en RFC y nombre. Del más reciente al más antiguo, 25 por página. Las partidas y las facturas ligadas de la página se cuentan en una consulta agrupada.
- `detail(db, order_id)`: la orden con sus facturas ligadas.

RD-16 menciona "Enviada", "En revisión", "Autorizada" o "Pagada", pero el modelo no tiene el estatus "En revisión". Por eso se toma como vigente toda factura ligada que no esté "Rechazada" ni "Cancelada". También cuenta "Observaciones": la factura sigue viva y el proveedor la va a reenviar. Sólo el envío liga la factura, así que un borrador nunca ocupa una orden.

### D9. Envío: liga la orden
`submit_invoice`, sin `FAIL`, hace la transición a "Enviada" y asigna `invoice.purchase_order_id` con la orden que resolvió el motor. Si una factura en "Observaciones" se reenvía, conserva o actualiza su liga. "Verificar" nunca liga la orden.

### D10. Asistente nacional: Archivos → Revisión → Envío
- **`GET /invoices/new`.** El nacional ve dos campos de archivo: PDF obligatorio (`accept=".pdf"`) y XML opcional (`accept=".xml"`). El internacional ve el formulario de la D12.
- **`POST /invoices/new` (multipart, `pdf` y `xml`):**
  1. CSRF, proveedor autorizado y usuario vinculado;
  2. 400 "Adjunte el PDF de la factura" si no hay PDF;
  3. lee los dos archivos con el límite de tamaño y verifica extensión y contenido, con las mismas reglas de `LocalFileStorage`, factorizadas en `check_upload(filename, content)`;
  4. escribe los archivos en un directorio temporal y llama a `extract`;
  5. número de factura `Serie`+`Folio` (o el número impreso, D3) y periodo `MM/AAAA` de la fecha de emisión; sin número, 422 con el mensaje de RD-03;
  6. 409 si el número ya existe para el proveedor, por la restricción `uq_invoices_supplier_number` como hoy;
  7. crea la factura en "Borrador" con `contract_id`, `project_name` y `project_leader` nulos, guarda los documentos con `save_invoice_file` y sus `metadata_json` (D3), y llama a `sync_upload_status`;
  8. audita `INVOICE_CREATED` y redirige a `/invoices/{id}/data`.

  Un UUID que ya tiene otra factura no impide el alta: no se asigna y FIN-004 lo reporta, como hoy (spec `motor-validacion`, "Detección de UUID duplicado coherente con la unicidad en BD").
- **`GET /invoices/{id}/data` (Paso 2, "Revisión").** Sólo el proveedor, sobre una factura nacional editable; una no editable redirige al detalle. La ruta no es `/review`, porque `GET/POST /invoices/{id}/review` ya son del PMO.
  - A la izquierda, las páginas del PDF (hasta `MAX_PAGES`) con `/documents/{doc}/pages/{n}`.
  - A la derecha, las tarjetas Factura, Proveedor, Cliente, Conceptos (con la O.C. detectada) y Totales. Cada dato validado lleva ✓ o ✗ con el valor esperado (D6).
  - Debajo, el checklist de archivos con la carga (`POST /invoices/{id}/documents` con `next=data`) y los botones "Verificar" y "Enviar a validación".
- **Reemplazo del PDF o del XML** (`POST /invoices/{id}/documents` de un nacional con `INVOICE_PDF` o `INVOICE_XML`): vuelve a extraer con el archivo nuevo y el otro vigente, con las mismas reglas del Paso 1 (409 de UUID distinto, 422 sin datos, 409 de número repetido).
  - Si procede, actualiza número, periodo, UUID, fecha, importes, moneda y O.C. detectada, y audita `INVOICE_DATA_EXTRACTED` con los valores anteriores y los nuevos.
  - `next=data` regresa al Paso 2; si no, a `/documents`, como hoy.
- **Envío:** "Enviar a validación" sigue en `POST /invoices/{id}/submit`. El detalle y la página `/documents` de un nacional enlazan a "Revisión".

### D11. Datos de la factura en el detalle
El detalle cambia así:
- **Datos del comprobante:** `stored_data`, con la fuente ("XML", "Texto del PDF" u "OCR"), sustituye a "Datos CFDI".
- **Encabezado:** "Proyecto" y "Contrato" se cambian por "Orden de compra":
  - convenio ligado, con enlace para PMO y Administrador;
  - o el número detectado y "sin ligar".
- **Orden de compra:** el panel sustituye a "Conciliación contractual" y muestra el encabezado y la tabla de partidas con todas las etiquetas de `DATA`. Se ve si la factura tiene orden ligada o, para el proveedor, una orden encontrada con su número.

La matriz de validación existente ya muestra cada diferencia por regla y concepto.

### D12. Proveedor internacional
- **Paso 1:** número de factura, número de orden de compra (`purchase_order_number`, `^\d{6,10}$`, obligatorio, "Capture el número de orden de compra"), fecha, moneda, subtotal e impuestos. Ya no pide contrato, periodo, proyecto ni líder; el periodo se toma de la fecha (RD-01). `ForeignInvoiceData` agrega `purchase_order_number`; la edición de "Datos del Invoice" (`POST /invoices/{id}/amounts`) también lo valida y lo audita.
- **Propuesta de la O.C.:** si la factura no tiene número de O.C. y el texto del Invoice cargado trae `OC/<número>`, el formulario de la carga documental lo propone (D7, `detect_order_number`).
- **Reglas:** las de la sección 6.7 de la HU. OC-004 es `WARNING` y compara la razón social del proveedor. OC-011 da un solo resultado sobre todas las partidas. PRV-001 a PRV-003, OC-003 y OC-007 a OC-009 resultan `NOT_APPLICABLE`.

### D13. Retiro de contratos sin tocar el esquema
- **Se eliminan:**
  - `routers/contracts.py`, `services/contract_service.py`, `services/contract_requirements_service.py`, `rules/contract_rules.py` y `rules/semantic_rules.py`;
  - las plantillas `contracts/*` y `admin/contract_requirements.html`, y `static/js/contract_activate.js`;
  - las rutas `/admin/contract-requirements*` de `admin.py`;
  - `file_service.save_contract_file`, `ContractCreate`, `ContractAmendmentCreate`, `ContractDocumentType*` de `schemas`, `CONTRACT_STATUS_LABELS` y `SIGNED_CONTRACT_DOCUMENT`;
  - los estilos `.status-contract-*` y `.contract-*`;
  - la columna "Contratos" del listado de proveedores, que pasa a "Órdenes de compra" con un conteo agrupado por RFC o `supplier_id`;
  - el bloque de contratos de `scripts/reporte_monedas.py`.
- **Se conservan:**
  - `Contract`, `ContractAmendment` y `ContractDocumentType`, con docstring "Obsoleto en la rama ferromex (HU-24)" y sin relaciones (se quitan `Supplier.contracts`, `Invoice.contract`, `Contract.supplier`, `Contract.amendments` y `ContractAmendment.contract`/`author`);
  - `ContractStatus`, por su `CHECK`;
  - `DocumentType.CONTRACT` y `CONTRACT_ANNEX` salen del enum si nada los usa; sus filas del catálogo quedan en No aplica.
- **Prueba de aislamiento:** ningún módulo de `app/`, `scripts/` ni `tests/`, fuera de `app/models` y `alembic/`, importa los tres modelos.
- **Criterio de terminado:** `grep -ril contract app/` sólo encuentra `app/models`, `app/core/constants.py` y el CSS de terceros `app/static/vendor/bootstrap-icons.min.css`, por iconos como `arrows-angle-contract`. El vendor no se modifica.

### D14. Migración `0023_ferromex_purchase_orders`
Upgrade:
1. crea `purchase_orders` con sus `CHECK`, índices y FK;
2. agrega `invoices.purchase_order_id` con FK `RESTRICT` e índice;
3. `invoices.project_name` admite nulo (`project_leader` ya lo admite);
4. niveles de `invoice_document_types`: `INVOICE_XML` (`OPTIONAL`, `NOT_APPLICABLE`); `PURCHASE_ORDER`, `CONTRACT` y `CONTRACT_ANNEX` (`NOT_APPLICABLE`, `NOT_APPLICABLE`), con `updated_at`;
5. Reglas de Validación (P-01): XML-002 → `IME010718PU3`, XML-009 → `INTERMODAL MEXICO`, XML-010 → `11700`, XML-011 → `601` y activa (hoy nace eliminada, `0020`); INT-002 → `INTERMODAL MEXICO`, INT-003 → `11700`. Fija `updated_at` y no cambia `version`: la migración corre con la aplicación detenida. Los valores quedan en la constante `RECEIVER` del módulo, que la fixture `restore_validation_rules` aplica después de `0020`.

No borra ni modifica tablas ni filas de contratos. El downgrade lanza `NotImplementedError` si hay órdenes de compra o facturas con `purchase_order_id`; si no, revierte los pasos 1 a 5 a los valores de `0020`/`0003`. `project_name` vuelve a `NOT NULL` sólo si no hay nulos.

### D15. Datos demo
- **Proveedor del ejemplo:** el proveedor persona física demo (`proveedor2@poc.local`) pasa a ser el de la factura 3668: "SOCORRO PATRICIA GONZALEZ HERNANDEZ", `GOHS60031745A`. Así la demo puede registrar y enviar la 3668 sin crear cuentas nuevas. Ninguna prueba depende de su nombre ni de su RFC anteriores.
- **`scripts/cfdi_demo.py`** genera con PyMuPDF y `lxml` la representación impresa y el XML de un CFDI a partir de un diccionario (`invoice_pdf(data) -> bytes`, `invoice_xml(data) -> str`, `EXAMPLE_3668`). Con él se generan `data/demo_documents/factura_3668.pdf` y `factura_3668.xml`, y lo usan las pruebas para variantes con otro UUID u otros importes.
- **Órdenes sembradas** (`seed_db`):
  - 25704872 del ejemplo (`GOHS60031745A`, con entrega);
  - una orden por cada factura demo del proveedor moral (`TIC210101ABC`, una partida "SERVICIOS DESARROLLO POWER AUTOMATE" de 1 SER a 100,000.00 MXN con entrega);
  - la orden de B-EXCEDE (total 100,000.00, contra una factura de 118,000.00: OC-005 y OC-009);
  - una orden con una partida sin entrada de mercancía y otra con dos partidas, ambas del proveedor moral;
  - las dos del recorrido manual (`GAVH810417Q42`, `supplier_id` nulo hasta que se dé de alta);
  - una en USD del proveedor internacional demo (`XEXX010101000`, `supplier_id` asignado), que cuadra con INV-2026-0042.
- **Facturas demo:** se siembran ligadas a su orden si están enviadas o después. Los tres CFDI demo pasan a receptor INTERMODAL MEXICO, emisor con `RegimenFiscal` y nombre del proveedor, y concepto con `ClaveUnidad="E48"`, `Unidad="Servicio"` y `(OC/<convenio>)`. El seed reescribe UUID y convenio por factura.
- **Invoice internacional demo:** su PDF menciona INTERMODAL MEXICO y C.P. 11700 (INT-002, INT-003).

### D16. Pruebas
- **`tests/cfdi.py`** con helpers compartidos:
  - `national_cfdi(**cambios)` (XML) y `printed_cfdi(**cambios)` (PDF), sobre `scripts/cfdi_demo.py`;
  - `register(client, pdf, xml=None)` (Paso 1);
  - la fixture `purchase_orders` (fábrica con convenio aleatorio de 8 dígitos; al terminar borra las órdenes sin facturas);
  - `ready_invoice(client, …)`, que registra, carga el Vo.Bo. y deja la factura "Cargada" con su orden.
- **Módulos nuevos:**
  - `test_orden_compra.py`: entidad, integridad, seed, consulta, reglas OC nacional e internacional, concurrencia de OC-012;
  - `test_extraccion_factura.py`: `parse_cfdi` ampliado, parser impreso sobre la 3668 y sobre los PDF del generador, analizador no disponible;
  - `test_registro_por_archivos.py`: Paso 1, Paso 2, reemplazos y PRV.
- **Pruebas que se reescriben:** las que registraban con `contract_id`, `service_period` y `project_name`.
- **Pruebas que se eliminan:** `test_contratos.py`, `test_requisitos_contrato.py`, los casos de FIN-001, FIN-003, FIN-006, CON-*, SEM-001, SUP-002 y DOC-005, y los de contratos de `test_integridad`, `test_listados_paginados` y `test_migraciones`. Se conservan los casos que prueban que el esquema de contratos sigue en la base.
- **Playwright:** se retira `20-HU-22-requisitos-contrato.spec.ts` y se ajustan HU-12, HU-13, HU-15 y el recorrido del video al nuevo asistente. La suite no se ejecuta en esta tarea (requiere el portal y Keycloak arriba); queda indicado en el resumen.

## Risks / Trade-offs

- **[Parser del PDF probado sólo con PDF sintéticos]** No hay PDF reales de FERROMEX en el repositorio (sección 12 de la HU). La 3668 se reconstruye a partir de la imagen descrita en la HU. → Expresiones por etiqueta tolerantes a saltos de línea; pruebas con dos maquetas distintas (PyMuPDF y Chromium del generador); RD-03 rechaza lo ilegible pidiendo el XML. Al recibir PDF reales se agregan como casos de prueba.
- **[Identificación por primer token]** Separar el "No. Identificación" de la descripción es heurístico. → Sólo se toma si tiene un dígito; OC-007 compara contra la descripción completa más la identificación, así que un error de corte no cambia el emparejamiento.
- **[Ruta del Paso 2 distinta de la HU]** `/invoices/{id}/data` en lugar de `/review`, que ya es del PMO. → Documentado aquí; el texto visible es "Revisión".
- **[Datos reales del ejemplo en la demo]** El nombre y el RFC de la 3668 vienen del documento de negocio. → Se usan sólo en la demo y en las pruebas de la rama `ferromex`, que no se integra a ULTRASIST.
- **[Reescritura amplia de pruebas]** Unas 20 suites cambian. → Helpers comunes en `tests/cfdi.py` y orden de trabajo que mantiene la suite verde por grupos (sección 10 de la HU).
- **[Bloqueo de la orden al verificar]** El bloqueo `FOR UPDATE` de la orden también ocurre al verificar. → Dura sólo la petición; no hay transacciones largas.

## Migration Plan

1. `alembic upgrade head` aplica `0023` sobre bases con contratos y facturas: sólo agrega y actualiza niveles y reglas.
2. Las facturas existentes conservan su `contract_id` y quedan sin orden. Las editables pueden verificarse o reenviarse: el motor busca su orden en los conceptos; sin `OC/<n>`, OC-001 falla y el proveedor debe reemplazar el XML o el PDF.
3. `scripts/reset_demo.py` reconstruye la demo con las órdenes nuevas.
4. Rollback: `alembic downgrade 0022_stored_files` sólo sin órdenes de compra ni facturas ligadas; con ellas, restaurar un respaldo.

## Open Questions

- P-05 Llegada de las O.C. al portal (SAP, archivo o captura): en esta HU, sembradas y de sólo consulta.
- P-06 y P-07 Facturas parciales o con varias O.C.: no se admiten (OC-005, OC-001 y OC-012).
- P-08 Corrección manual en el Paso 2: no; se carga el XML o se reemplaza el PDF.
- P-09 Servicio de OCR: el analizador configurado; en demo, "no disponible".
- P-10 Tabla oficial de equivalencias de unidad: constante inicial de la sección 6.5.
- P-11 Moneda con tipo de cambio: misma moneda exigida (OC-010).
- P-12 Tolerancia: ±0.01.
- P-13 Severidad de OC-011: ERROR.
- P-14 Fecha de la factura contra la de la O.C. o la de entrega: no se valida; se muestra.
- P-15 Identificación del internacional en SAP y sus partidas: por `supplier_id`; sin partidas.
