## Why

El Alcance del MVP (minuta del 21-sep-2026) incluye al proveedor extranjero: "carga de Invoice en PDF y documentos soporte; evitar duplicados inicialmente por nombre de archivo" y "validar, en la medida de lo posible, la información del Invoice, incluyendo datos del proveedor, datos de ULTRASIST y dirección". El ERS lo cubre con HU-15 (RF-14) y HU-16 (RF-15).

Hoy un proveedor internacional puede registrar una factura y cargar su Invoice (HU-04), pero no puede enviarla nunca:

- sin CFDI, XML-001 (`CRITICAL`) y SUP-003 (expediente del Anexo A) resultan `FAIL`, y el envío de HU-13 no procede con ningún `FAIL` (B-06 de EP-01);
- los importes de la factura sólo se llenan desde el XML, así que la factura internacional queda en cero y las reglas FIN comparan contra cero (B-07);
- nada impide cargar dos veces el mismo Invoice.

HU-12/HU-13 ya dejaron el modelo de estatus y el envío con validación que esta HU reutiliza. Es la ola 2 de EP-01.

## What Changes

- **Datos del Invoice en el registro** (HU-15, EP-01 DT-06): cuando el proveedor del usuario es internacional, el alta pide fecha de la factura, subtotal, impuestos, total y moneda (catálogo de monedas activas, HU-07). Se guardan en las columnas que ya existen en `invoices` (`invoice_date`, `subtotal`, `tax`, `total`, `currency`). El total debe ser igual al subtotal más impuestos. El proveedor nacional no ve estos campos: sus importes siguen saliendo del XML.
- **Edición de los datos del Invoice** mientras la factura es editable (Borrador, Cargada u Observaciones), desde la carga documental, con auditoría `INVOICE_AMOUNTS_UPDATED`.
- **Duplicado por nombre de archivo** (HU-15, DT-07):
  - al cargar un Invoice cuyo nombre de archivo, sin distinguir mayúsculas ni espacios de los extremos, ya tiene otra factura del mismo proveedor: HTTP 409 con el folio de esa factura y el archivo no se escribe;
  - al enviar: regla nueva FIN-007 (`CRITICAL`), que cubre cargas concurrentes;
  - reemplazar el Invoice de la misma factura con un archivo del mismo nombre sí se permite.
- **Validación internacional** (HU-16, DT-08):
  - XML-001 a XML-010, FIN-004, SUP-003 y SUP-004 resultan `NOT_APPLICABLE` con "No aplica a proveedores internacionales";
  - reglas nuevas sobre el texto del Invoice, de severidad `WARNING` (no bloquean): INT-001 identificador fiscal del proveedor, INT-002 razón social de ULTRASIST, INT-003 código postal de ULTRASIST e INT-004 dirección de ULTRASIST. INT-002 e INT-003 respetan los interruptores de las Reglas de Validación. Sin texto legible, resultan `NOT_EVALUATED`;
  - SEM-001 resulta `NOT_EVALUATED` ("el Invoice no es un CFDI"): no hay conceptos estructurados que comparar.
- **Envío** con el flujo de HU-13, sin cambios: ahora la factura internacional puede pasar a "Enviada".
- **Detalle de la factura:** "Datos del Invoice" (fecha, importes, moneda, identificador fiscal y si el texto del Invoice es legible) en lugar de "Datos CFDI"; el UUID se muestra como "No aplica (Invoice)".
- **Demo:** proveedor internacional con cuenta demo `proveedor3@poc.local`, contrato en USD y una factura "Cargada" lista para enviar.

**Fuera de alcance:**
- extracción automática de datos del Invoice con IA (P-07 de EP-01);
- expediente del proveedor internacional equivalente al Anexo A (P-06);
- excluir las facturas canceladas del control de duplicados: el estatus "Cancelada" llega con HU-14;
- mostrar las reglas INT en la tabla de `/admin/rules` (sólo se agrega una nota).

## Supuestos

Valores por defecto de las preguntas abiertas de EP-01, a confirmar con negocio:

- **S1 (P-06).** SUP-003 y SUP-004 no aplican al proveedor internacional mientras no se defina su expediente.
- **S2 (P-07).** Las reglas INT se ajustarán con las tres muestras de invoices extranjeros acordadas en la minuta (responsable Octavio Rivera), que no están en el repositorio. Mientras tanto son advertencias.
- **S3 (P-08).** El duplicado por nombre se busca dentro del mismo proveedor, en facturas de cualquier estatus.
- **S4.** Los importes capturados deben cuadrar (total = subtotal + impuestos, con la tolerancia de 0.02 de FIN-002). Un Invoice con otros cargos o descuentos no puede capturarse; si negocio lo requiere, se agrega un campo.
- **S5.** La moneda se elige del catálogo de monedas activas. FIN-003 sigue comparándola con la del contrato.

## Capabilities

### New Capabilities
- `factura-internacional`: datos del Invoice en el registro y su edición, duplicado por nombre de archivo (carga y FIN-007), reglas INT sobre el texto del Invoice y datos del Invoice en el detalle.

### Modified Capabilities
- `motor-validacion`: las reglas del CFDI (XML-001 a XML-010, FIN-004), del expediente (SUP-003, SUP-004) y la comparación semántica (SEM-001) no se evalúan para la factura internacional.

## Impact

- **Código:**
  - `app/schemas/__init__.py`: esquema `ForeignInvoiceData` (fecha, importes y moneda);
  - nuevo `app/services/foreign_invoice_service.py`: validación de los datos del Invoice, duplicados por nombre con bloqueo consultivo por proveedor y texto del Invoice para las reglas;
  - nuevo `app/rules/international_rules.py` (INT-001 a INT-004 y FIN-007); `app/rules/xml_rules.py`, `supplier_rules.py`, `financial_rules.py` y `semantic_rules.py` con la variante internacional;
  - `app/services/validation_engine.py`: rama según el origen del proveedor;
  - `app/services/validation_settings_service.py`: la dirección de ULTRASIST en `RuleParameters`;
  - `app/routers/invoices.py`: alta con los datos del Invoice, `POST /invoices/{id}/amounts` y control de duplicados al cargar.
- **Plantillas:** `invoices/new.html`, `invoices/documents.html`, `invoices/detail.html` y una nota en `admin/rules.html`.
- **Esquema:** sin migración; se reutilizan las columnas de `invoices`.
- **Rutas nuevas:** `POST /invoices/{invoice_id}/amounts`.
- **Demo:** `app/core/demo.py` (cuenta `proveedor3@poc.local`), `scripts/seed_db.py` y `README.md`.
- **Dependencias:** ninguna nueva.
- **Pruebas:** nuevo `tests/test_factura_internacional.py`; ajustes en `tests/conftest.py` (contraseña de la cuenta demo nueva), `tests/test_archivos_minimos.py` (el alta internacional pide los datos del Invoice) y las pruebas que cuentan usuarios, proveedores o facturas demo.
