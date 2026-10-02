## Context

Tras HU-12/HU-13, el flujo de la factura es: alta → carga documental ("Borrador" ⇄ "Cargada" según el checklist) → "Verificar" opcional → envío, que ejecuta el motor y pasa a "Enviada" sólo sin ningún `FAIL` (`submission_service`).

Estado para el proveedor internacional (`suppliers.origin = INTERNATIONAL`, con `country` y `foreign_tax_id`, sin RFC):

- **Documentos:** HU-04 ya le ofrece `FOREIGN_INVOICE` (Invoice en PDF, obligatorio y fijo), orden de compra, Vo.Bo. y soportes; DOC-001 y DOC-002 resultan `NOT_APPLICABLE` y DOC-008 exige el Invoice.
- **Motor** (`run_validation`): sin XML, `xml_rules` devuelve XML-001 `FAIL`/`CRITICAL`; `supplier_rules` evalúa SUP-003 con el Anexo A del tipo de persona; `financial_rules` usa `invoice.subtotal`/`tax`/`total`/`currency` cuando no hay XML, pero valen cero.
- **Alta:** `InvoiceCreate` ya declara `subtotal`, `tax`, `total` y `currency`, pero el router no los usa y crea la factura en cero.
- **Carga del PDF:** `analyze_pdf` extrae hasta 100 000 caracteres y `has_extractable_text`; la carga guarda sólo `text_preview` (2 000 caracteres) en `metadata_json`.
- **Bloqueos consultivos:** HU-04, HU-07 y HU-08 usan `pg_advisory_xact_lock` con una clave por HU.

## Goals / Non-Goals

**Goals:**
- Que una factura internacional correcta pueda enviarse, con los mismos bloqueos de negocio que la nacional salvo los que dependen del CFDI.
- Que el PMO vea las comprobaciones posibles sobre el Invoice sin que una lectura imperfecta del PDF bloquee al proveedor.
- Cero cambios en los resultados de las facturas nacionales.

**Non-Goals:**
- Extracción de datos del Invoice con IA; comparación semántica del Invoice con el contrato.
- Expediente del proveedor internacional.
- Excluir facturas canceladas del control de duplicados (HU-14).

## Decisions

### D1. Los datos del Invoice usan las columnas existentes
`invoice_date`, `subtotal`, `tax`, `total` y `currency` ya existen y ya los usan las reglas FIN, el listado y el tablero. No hay migración. Para el nacional el XML los sigue sobrescribiendo al validar, como hoy.

*Alternativa:* columnas `foreign_*` aparte. Duplicaría los importes y obligaría a cada consumidor a elegir cuál leer.

### D2. Esquema `ForeignInvoiceData` y validación con catálogo
Un esquema Pydantic con `invoice_date`, `subtotal`, `tax`, `total` y `currency`:
- los importes pasan por un validador que quita `$`, `,` y espacios; exige `Decimal` finito con a lo sumo 2 decimales y 16 dígitos;
- `subtotal > 0`, `tax >= 0`, `total > 0` y `|subtotal + tax - total| <= 0.02` (la tolerancia de FIN-002);
- `invoice_date` no posterior a hoy en la zona de negocio;
- `currency` en mayúsculas con 3 letras.

`foreign_invoice_service.parse_data(db, values)` aplica el esquema, agrega el error de moneda inactiva (`catalog_service.active_codes`) y devuelve los datos o la lista de errores con la forma "<Campo>: <mensaje>". La usan el alta y la edición.

### D3. El servidor decide por el origen del proveedor
`create_invoice` recibe los campos del Invoice como opcionales. Si `user.supplier.origin` es Internacional los valida y los guarda; si es Nacional los ignora. La plantilla sólo los muestra al internacional, con la moneda preseleccionada con la del primer contrato activo.

### D4. Edición con `POST /invoices/{id}/amounts`
Formulario "Datos del Invoice" en la carga documental de una factura internacional editable. La ruta bloquea la fila (`lock_invoice`), exige estatus editable (409) y origen Internacional (400), valida con D2, compara campo por campo y audita `INVOICE_AMOUNTS_UPDATED` sólo con lo que cambió (valores como texto: `"1000.00"`, `"2026-09-15"`). Redirige a la carga documental; un error vuelve a pintarla con HTTP 400 y lo capturado.

*Alternativa:* editar en el detalle. La carga documental es donde el proveedor corrige su factura antes de enviar; el detalle queda de lectura.

### D5. Duplicado por nombre: bloqueo por proveedor más regla al enviar
`foreign_invoice_service.duplicate_folios(db, invoice, filename)` busca documentos `FOREIGN_INVOICE` vigentes (`is_current`) de otras facturas del mismo proveedor con `lower(trim(original_filename)) = lower(trim(:nombre))` y devuelve sus folios.

Al cargar un `FOREIGN_INVOICE`, el router toma `pg_advisory_xact_lock(FOREIGN_INVOICE_LOCK_KEY, supplier_id)` (clave `15_1500_0001`, forma de dos enteros para bloquear sólo a ese proveedor) antes de consultar y responde 409 si hay folios. El bloqueo se libera al confirmar la transacción, así que dos cargas concurrentes con el mismo nombre se serializan y la segunda ve la primera.

FIN-007 repite la consulta al validar. Cubre lo que la carga no ve: documentos anteriores a este cambio o cargados por otra vía.

*Alternativa:* índice único. La condición depende del tipo, de `is_current` y del proveedor de la factura, y el nombre de archivo no es parte de la identidad del documento en otros tipos.

### D6. Rama internacional en el motor
`run_validation` toma `origin = invoice.supplier.origin`. Para el internacional:
- no busca XML; `xml_rules` recibe `international=True` y devuelve XML-001 a XML-010 `NOT_APPLICABLE` con sus severidades;
- `supplier_rules` y `financial_rules` reciben el origen: SUP-003, SUP-004 y FIN-004 `NOT_APPLICABLE`;
- `international_rules(text, readable, supplier, params)` devuelve INT-001 a INT-004, y `invoice_duplicate_rule(folios, has_invoice)` FIN-007;
- el analizador semántico no se llama: SEM-001 `NOT_EVALUATED`.

Los resultados nacionales no cambian: las reglas nuevas sólo se generan para el origen que las usa.

### D7. Texto del Invoice leído en cada validación
El motor relee el PDF del Invoice vigente con `analyze_pdf` (hasta 100 000 caracteres): `text_preview` sólo guarda 2 000. Si `analyze_pdf` falla o `has_extractable_text` es falso, las reglas INT resultan `NOT_EVALUATED`. El texto no se guarda en los resultados: la evidencia sólo lleva el valor buscado.

### D8. Comparación tolerante en las reglas INT
`compact(texto)`: sin acentos (NFKD), en minúsculas y sólo con letras y dígitos. INT-001, INT-002 e INT-004 buscan `compact(valor)` dentro de `compact(texto del Invoice)`: "ULTRASIST SA DE CV" coincide con "ULTRASIST, S.A. de C.V." y "987654321" con "98-7654321". INT-003 busca el código postal como número aislado (`(?<!\d)03930(?!\d)`) para no confundirlo con parte de otro número. Un valor vacío tras `compact` resulta `NOT_APPLICABLE`.

Todas son `WARNING` con `warning=True`: el Invoice no tiene formato fijo, así que una ausencia es una señal para el PMO, no un error del proveedor (S2 de la propuesta).

### D9. `RuleParameters` con la dirección
Se agrega `receiver_address` a `RuleParameters`; `rule_parameters()` lo lee de la configuración. Las reglas XML no lo usan.

### D10. Interfaz
- **Alta** (`new.html`): bloque "Datos del Invoice" sólo para el internacional.
- **Carga documental:** panel "Datos del Invoice" con el formulario de edición (D4).
- **Detalle:** "Datos del Invoice" (fecha, subtotal, impuestos, total, moneda, identificador fiscal y país, y "Texto legible" o "Sin texto legible (posible escaneo)" según `has_extractable_text` del Invoice vigente); UUID "No aplica (Invoice)".
- **Reglas de validación:** una nota indica que las comparaciones de Razón social y Código postal también gobiernan INT-002 e INT-003.

### D11. Demo internacional
`DEMO_ACCOUNTS` agrega "Proveedor internacional" (`proveedor3@poc.local`, `Proveedor#Demo2026`, sin acceso rápido). El seed crea "Global Data Services Inc. (DEMO)" (US, `foreign_tax_id` `98-7654321`, Autorizado), su usuario, un contrato "Analítica Global 2026" por 20,000.00 USD y la factura "INV-2026-0042" con un Invoice PDF generado con fitz que menciona el identificador fiscal, "ULTRASIST SA DE CV" y "C.P. 03930", más orden de compra y Vo.Bo.; queda "Cargada" y su envío procede. El mensaje final del seed pasa a "5 usuarios, 3 proveedores, 3 contratos y 11 facturas demo".

## Risks / Trade-offs

- **[Las reglas INT fallan con invoices reales]** → Son advertencias; se calibran con las muestras (P-07). No bloquean al proveedor.
- **[Un Invoice con cargos o descuentos no cuadra]** → S4: la captura exige total = subtotal + impuestos. Si negocio lo requiere, se agrega un campo "otros cargos".
- **[El PDF se lee dos veces por validación]** → La carga y cada validación leen el Invoice; es local y el tamaño está acotado por `MAX_UPLOAD_MB`.
- **[Cuenta demo nueva]** → Cambia `TEST_PASSWORDS`, el README y los conteos del seed; no aparece en el acceso rápido para no saturar el login.

## Migration Plan

Sin migración de esquema. `reset_demo` siembra el escenario internacional. Rollback: revertir el código; los importes capturados quedan en columnas que la versión anterior ya usa.

## Open Questions

- P-06, P-07 y P-08 de EP-01 siguen abiertas; este change aplica sus valores por defecto.
- ¿El total del Invoice puede no ser subtotal + impuestos (retenciones, descuentos)? Hoy se exige que cuadre.
