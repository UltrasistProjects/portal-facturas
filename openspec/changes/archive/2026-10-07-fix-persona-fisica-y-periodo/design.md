## Context

Fixes acotados; no cambian el esquema.

## Decisions

- **Representante legal:** igual que la fecha de constitución: `SupplierProfile` lo descarta para persona física y lo exige para persona moral; en el formulario se declara con `data-depends-on="supplier_type"` y `data-applies-when="PERSONA_MORAL"`, que `supplier_form.js` ya maneja.
- **Etiqueta:** `SUPPLIER_TYPE_LABELS` en `constants.py`, disponible en las plantillas como `supplier_type_labels`; los valores guardados (`PERSONA_FISICA`) no cambian.
- **Periodo:** `normalize_period` en el esquema acepta mes/año o año/mes con `/`, `-` o `.` y espacios, y guarda `MM/AAAA`. El `pattern` del navegador es igual de flexible; el rango del mes lo valida el servidor. CON-003 compara tuplas (año, mes).

## Risks / Trade-offs

- [Proveedores físicos existentes con representante legal guardado] → se conserva hasta su siguiente edición, que lo deja vacío; el expediente ya muestra "No aplica".
