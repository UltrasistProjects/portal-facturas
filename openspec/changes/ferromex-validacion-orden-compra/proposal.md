## Why

FERROMEX controla cada compra con una orden de compra (convenio) de SAP, con partidas, precio neto y entrada de mercancía. La rama `ferromex` sigue con el flujo de ULTRASIST: el proveedor elige un contrato, captura a mano datos que ya vienen en sus archivos, el XML es obligatorio, nadie compara al emisor con el proveedor registrado y las reglas miden la factura contra el monto global de un contrato. Negocio pidió (2026-11-24) registrar la factura desde su PDF (y su XML si lo hay), mostrar lo leído junto a la imagen de la factura y, al enviar, validarla contra la orden de compra citada en sus conceptos. También pidió retirar el apartado de contratos y conservar sus tablas sin uso (P-02).

La historia completa, sus reglas (RN-HU24-01 a RN-HU24-12, RD-01 a RD-16) y sus preguntas abiertas están en `docs/stories/new/HU-24 Validacion de factura contra orden de compra.md`.

## What Changes

- **Entidad Orden de compra** (`purchase_orders`): encabezado (convenio, RFC, nombre, fecha, total y impuestos) y partidas de SAP en `data` (JSONB, con las etiquetas `Txt.brv`, `Ctd.Pedido`, `Unidad.Pedido`, `Prc.Neto`, `Moneda`, `Docto Material`, `Fecha Conta`, etc.). La factura se liga con `invoices.purchase_order_id`.
- **Consulta "Órdenes de compra"** (`/purchase-orders` y `/purchase-orders/{id}`) para PMO y Administrador: listado paginado en SQL con búsqueda por convenio, RFC o nombre; detalle con partidas y facturas ligadas. Sustituye al menú "Contratos".
- **BREAKING — Asistente "Registrar factura" nacional en tres pasos: Archivos → Revisión → Envío.**
  - **Archivos** (`POST /invoices/new`, multipart): PDF obligatorio y XML opcional. Sin contrato, número, periodo, proyecto ni líder. El sistema extrae los datos, rechaza un PDF y un XML de facturas distintas (409) y un PDF ilegible sin XML (422), y crea la factura en "Borrador".
  - **Revisión** (`GET /invoices/{id}/data`): páginas del PDF a la izquierda y datos extraídos a la derecha, con la Validación 1 junto a cada dato y el checklist de documentos soporte.
  - **Envío:** `POST /invoices/{id}/submit` sin cambio de ruta; ejecuta también la Validación 2.
- **Extracción de datos** (`invoice_extraction_service`): del XML (con `parse_cfdi` ampliado: serie, folio, régimen del emisor, `ClaveUnidad`, `Unidad`, `NoIdentificacion`, `ObjetoImp` y tipo de cada impuesto). Sin XML, del texto de la representación impresa del CFDI 4.0 y, si el PDF no tiene texto, del analizador documental configurado. El de demo responde "no disponible". Los datos y su fuente (`xml`, `pdf_text`, `ocr`) quedan en `metadata_json` del documento.
- **Validación 1:** reglas nuevas `PRV-001` a `PRV-003` (RFC, nombre y régimen del emisor contra el proveedor del usuario) y las Reglas de Validación del receptor, ahora sembradas con INTERMODAL MEXICO (`IME010718PU3`, 601, G03, 11700; P-01).
- **Validación 2:** reglas nuevas `OC-001` a `OC-012` contra el encabezado y las partidas de la orden (número en los conceptos, RFC, nombre, subtotal, IVA, partida por `Txt.brv`, cantidad y unidad con equivalencias, precio e importe, moneda, entrada de mercancía y orden ya facturada). Se evalúan al verificar y al enviar; al enviar, la factura queda ligada a su orden.
- **Proveedor internacional contra orden de compra** (P-04): el registro del Invoice pide el número de orden de compra (6 a 10 dígitos) en lugar del contrato; las `OC-*` validan encabezado y entrega por `supplier_id`.
- **BREAKING — Retiro de contratos del portal:** rutas `/contracts*` y `/admin/contract-requirements*`, menú, plantillas, servicios y reglas SUP-002, CON-001 a CON-004, DOC-005, FIN-001, FIN-003, FIN-006 y SEM-001. Las tablas `contracts`, `contract_amendments` y `contract_document_types`, y las columnas `invoices.contract_id` y `documents.contract_id`, se conservan con sus datos y sin uso.
- **Archivos de la factura:** `INVOICE_XML` pasa a Opcional para el nacional; `PURCHASE_ORDER`, `CONTRACT` y `CONTRACT_ANNEX` pasan a No aplica.
- **Migración** `0023_ferromex_purchase_orders`: sólo agrega (tabla, FK, nulos en `project_name`) y actualiza niveles y Reglas de Validación; no borra nada de contratos.
- **Datos demo y recorrido manual** rehechos sobre órdenes de compra. Incluyen la orden 25704872 y la factura 3668 del ejemplo, cuyo proveedor es el proveedor persona física demo.

**Fuera de alcance** (detalle en la sección 3 de la HU): integración con SAP, alta o edición de órdenes de compra en el portal, facturas parciales o con varias órdenes, partidas del Invoice internacional, corrección manual de los datos extraídos, OCR local y cambios a la revisión del PMO, al pago y a la cancelación.

## Capabilities

### New Capabilities
- `orden-compra`: entidad Orden de compra, datos demo, consulta para PMO y Administrador, reglas `OC-001` a `OC-012` (nacional e internacional) y conservación sin uso de los contratos.
- `registro-factura-extraccion`: registro de la factura nacional desde su PDF y su XML, extracción de los datos (XML, texto del PDF, analizador documental), revisión junto a la imagen y reglas `PRV-001` a `PRV-003`.

### Modified Capabilities
- `flujo-facturas`: el alta pasa a ser por archivos y sin contrato; desaparece el requisito de contratos en el formulario; el envío evalúa la Validación 2 y liga la orden.
- `motor-validacion`: familias DOC, PRV, SUP, XML, FIN, DAT, OC (sin CON ni SEM); las reglas XML se evalúan también sobre datos del PDF; DOC-005 y las reglas contra el contrato se retiran; nuevas reglas que no aplican al internacional.
- `archivos-minimos-factura`: niveles iniciales de la rama (XML Opcional; orden de compra, contrato y anexo No aplica).
- `factura-internacional`: el registro del Invoice pide la orden de compra en lugar del contrato y deja de pedir periodo y proyecto.
- `integridad-datos`: `CHECK` e integridad de `purchase_orders` y su FK desde `invoices`.
- `interfaz-usuario`: menú "Órdenes de compra" en lugar de "Contratos", sin "Alta de contrato", y pasos del asistente "Archivos", "Revisión" y "Envío".
- `listados-paginados`: el listado de contratos y su retorno tras el alta se sustituyen por el de órdenes de compra.
- `catalogos-referencia`: la moneda deja de ofrecerse en un alta de contrato inexistente.
- `observabilidad`: la subida de documentos ya no registra documentos de contrato.
- `requisitos-alta-contrato`: se retiran todos sus requisitos.
- `trazabilidad-contratos`: se retiran todos sus requisitos.

## Impact

- **Código** (raíz de la PoC):
  - nuevos: `app/services/invoice_extraction_service.py`, `app/services/purchase_order_service.py`, `app/rules/supplier_identity_rules.py`, `app/rules/purchase_order_rules.py`, `app/rules/text.py`, `app/routers/purchase_orders.py`, plantillas `purchase_orders/list.html`, `purchase_orders/detail.html` e `invoices/review.html`, y `scripts/cfdi_demo.py`;
  - modificados: modelos, constantes, esquemas, `xml_service`, `validation_engine`, `validation_rules_service`, `submission_service`, `foreign_invoice_service`, reglas `document`, `financial`, `supplier`, `xml` e `international`, analizadores de `app/services/ai`, routers `invoices`, `admin`, `suppliers` y `main.py`, plantillas `base.html`, `invoices/*` y `suppliers/list.html`, `app.js`, `app.css`, `seed_db.py` y `reporte_monedas.py`;
  - eliminados: `routers/contracts.py`, `contract_service.py`, `contract_requirements_service.py`, `rules/contract_rules.py`, `rules/semantic_rules.py`, plantillas `contracts/*` y `admin/contract_requirements.html`, y `contract_activate.js` si existe.
- **Esquema:** revisión `0023_ferromex_purchase_orders` sobre `0022_stored_files`.
- **Rutas:** nuevas `GET /purchase-orders`, `GET /purchase-orders/{id}` y `GET /invoices/{id}/data`; `POST /invoices/new` pasa a multipart; se eliminan `/contracts*` y `/admin/contract-requirements*`.
- **Datos:** `data/demo_documents` (CFDI demo con receptor INTERMODAL MEXICO y `OC/<convenio>`, factura 3668 en PDF y XML) y `data/pruebas-ferromex` regenerado.
- **Pruebas:** nuevas `test_orden_compra.py`, `test_extraccion_factura.py` y `test_registro_por_archivos.py`; se eliminan `test_contratos.py` y `test_requisitos_contrato.py`; se ajusta el resto de la suite que creaba contratos o registraba facturas con el formulario anterior. En Playwright (`tests/hu`) se retira la spec de HU-22 y se ajusta la de HU-12.
- **Documentación:** `README.md` y `docs/source-of-truth/INDICE_HUs.md`.
- **Pago y complemento:** sin cambios, salvo uno. El método de pago que decide si la factura requiere Complemento de Pago se lee del XML o, si no hay XML, del PDF (delta `pago-facturas`).
- **Sin cambios:** Keycloak, notificaciones y plantillas de correo, revisión del PMO, cancelación, catálogos, carga masiva y requisitos de alta del proveedor.
