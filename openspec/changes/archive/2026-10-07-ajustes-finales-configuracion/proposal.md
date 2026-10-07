## Why

Antes de la entrega quedan cinco ajustes que el negocio considera inviolables o indispensables: las monedas y el total de una factura no pueden quedar a criterio del cliente; ningún proveedor se autoriza ni ninguna factura se envía con requisitos mínimos faltantes, sin importar el camino; las facturas internacionales deben validarse con reglas propias y no con las del CFDI; y el Administrador necesita editar y eliminar cualquier registro de configuración, incluidos los precargados, sin perder historial.

La exploración del código mostró que varios puntos ya están parcialmente cubiertos y que otros parten de supuestos que no coinciden con el modelo actual:
- la factura internacional ya elige la moneda del catálogo; el único campo de moneda en texto libre está en el alta de contrato, y el total capturado se acepta con una tolerancia de 0.02;
- la autorización individual y la masiva ya pasan por `supplier_access_service.authorize()` y respetan los requisitos de alta, pero el modelo `Supplier` nace `ACTIVE` por omisión;
- el envío desde "Borrador" responde 409 con un mensaje genérico, y la regla no vive en el servicio de transición;
- "Reglas de Validación" es una sola fila de parámetros (`validation_settings`), no una lista de registros;
- en Requisitos mínimos, Editar y Eliminar se ocultan para los tipos del sistema (`{% if not t.is_system %}`), los servicios responden 409 y Eliminar borra la fila.

## What Changes

**1. Moneda y total**
- El alta de contrato elige la moneda de las claves activas del catálogo de monedas, en lugar de capturarla como texto libre. El servidor rechaza con 400 una clave inactiva o inexistente, también en una petición directa.
- Factura internacional: el total se muestra en solo lectura y se recalcula en vivo en la página. El servidor calcula `total = subtotal + impuestos` con `Decimal`, redondeado a 2 decimales con ROUND_HALF_UP, e ignora el total que envíe el cliente. **BREAKING**: deja de existir el error "Total: debe ser igual al subtotal más impuestos".
- Factura nacional: una moneda del CFDI que no está activa en el catálogo no se guarda en la factura; XML-007 la reporta y el envío no procede.
- Migración de datos: normaliza `invoices.currency` y `contracts.currency` a claves del catálogo, con alias conocidos y auditoría. Las que no se pueden mapear se conservan y se reportan con `scripts/reporte_monedas.py`.

**2. Autorización de proveedores**
- Se garantiza que el único camino a "Autorizado" es `authorize()`, que exige los requisitos de alta. El modelo nace "Registrado" y una prueba estática impide otro camino.
- Agregar un requisito no cambia a los proveedores ya autorizados; un requisito eliminado deja de exigirse en las autorizaciones siguientes.

**3. Envío a validación**
- `transition_invoice(..., UNDER_REVIEW)` verifica los archivos obligatorios vigentes y responde 409 con sus nombres: "Faltan archivos obligatorios: <nombres>. Cárguelos antes de enviar". El envío desde "Borrador" usa el mismo mensaje con nombres. Las facturas ya enviadas no se reevalúan.

**4. Reglas de Validación por origen** — **BREAKING**
- `validation_settings` se reemplaza por el catálogo `validation_rules`: un registro por regla y origen.
  - Nacional: XML-002, 003, 004, 005, 009 y 010, más XML-011 (régimen fiscal del receptor), que es nueva y nace eliminada.
  - Internacional: INT-001 a INT-004.
- La migración convierte la configuración actual en registros `NATIONAL` y siembra los internacionales con los valores vigentes, para que ninguna validación cambie al migrar.
- Hay dos secciones: "Reglas de validación — Nacionales" y "— Internacionales". El motor toma solo las reglas activas del origen del proveedor de la factura, leídas por el mismo servicio que alimenta la pantalla.
- XML-007 sigue atada al catálogo de monedas, que es la regla inviolable del punto 1.

**5. Editar y eliminar en todos los registros** — **BREAKING**
- Archivos de factura, Alta de proveedor, Alta de contrato y las dos secciones de Reglas: todo registro, nuevo o precargado, se puede editar y eliminar.
- Se retiran los niveles fijos y sus CHECK en la base de datos, decisión confirmada por el usuario. El motor, la cancelación y el pago toleran la falta de un tipo atado al código.
- "Eliminar" pasa a ser una baja lógica (`is_active = false`, `deleted_at`, `deleted_by`) con confirmación. Sustituye a "Desactivar/Reactivar" y al borrado físico.
- Los listados muestran solo registros activos; "Mostrar eliminados" los lista con "Restaurar".
- Solo el Administrador puede editar o eliminar, con CSRF. Cada edición, eliminación y restauración se audita con su valor anterior y el nuevo.

## Capabilities

### New Capabilities

_Ninguna._ Los cambios modifican capacidades existentes.

### Modified Capabilities

- `reglas-validacion`: la configuración única se convierte en un catálogo de reglas por origen, con dos secciones, edición, eliminación lógica, restauración, control de concurrencia por regla y auditoría por registro.
- `motor-validacion`: la fuente única son las reglas activas del origen de la factura. Una regla eliminada resulta `NOT_APPLICABLE`. Se agrega XML-011. Las reglas del CFDI no aplican si el XML no se exige y no se cargó.
- `factura-internacional`: el total lo calcula el servidor y las reglas INT usan los parámetros de las reglas internacionales.
- `flujo-facturas`: el envío se bloquea en el servicio de transición con 409 y los nombres faltantes; la moneda del CFDI solo se guarda si está en el catálogo.
- `catalogos-referencia`: la moneda del contrato y de la factura sale solo del catálogo; las claves "en uso" se calculan con los parámetros de las reglas activas.
- `archivos-minimos-factura`: todos los tipos se pueden editar y eliminar lógicamente, sin niveles fijos, con restauración y listados de solo activos.
- `requisitos-alta-proveedor`: los mismos cambios de edición, baja lógica y restauración.
- `requisitos-alta-contrato`: los mismos cambios de edición, baja lógica y restauración.
- `acceso-proveedores`: un proveedor nace "Registrado" y solo `authorize()` lo autoriza; los requisitos nuevos no afectan a los ya autorizados.
- `cancelacion-facturas`: el acuse se exige solo mientras su tipo está activo.
- `pago-facturas`: el complemento se exige y bloquea el envío solo mientras su tipo XML está activo.
- `integridad-datos`: se retiran los CHECK de tipo del sistema activo y de niveles fijos, se agrega el CHECK de baja lógica y la integridad de `validation_settings` pasa a `validation_rules`.

## Impact

- **Modelos y migraciones**: tres revisiones de Alembic nuevas.
  - `0019_types_soft_delete`: columnas de baja lógica y retiro de los CHECK fijos.
  - `0020_validation_rules`: tabla nueva, migración de datos y retiro de `validation_settings`.
  - `0021_currency_catalog_mapping`: normalización de monedas.
- **Servicios**: `catalog_service`, `contract_service`, `foreign_invoice_service`, `invoice_service`, `submission_service`, `document_requirements_service`, `supplier_requirements_service`, `contract_requirements_service`, `supplier_access_service`, `cancellation_service`, `payment_service` y `validation_engine`. Se agregan `validation_rules_service` y un módulo compartido de baja lógica, y se retira `validation_settings_service`.
- **Reglas**: `xml_rules` e `international_rules` reciben las reglas del origen. Se agrega el registro de definiciones de reglas en `app/rules/`.
- **Routers**: `admin.py` con las rutas de reglas por origen, Eliminar y Restaurar; se retiran las rutas `/status` de los tipos. `contracts.py` e `invoices.py`.
- **Plantillas y JS**: `admin/rules.html` se reemplaza por una plantilla por origen; se modifican `_type_actions.html`, las tres pantallas de requisitos, `contracts/list.html`, `components/foreign_invoice_fields.html` y `base.html` (menú). Se agrega `static/js/invoice_amounts.js`.
- **Scripts**: `scripts/reporte_monedas.py` (nuevo) y `scripts/seed_db.py`.
- **Pruebas**: pytest sobre la base temporal y la suite Playwright de HUs en `tests/hu`, que ya usan estas pantallas.
- **Rama**: `hu-ajustes-finales` a partir de `dev`; no se tocan `qa` ni `main`.
