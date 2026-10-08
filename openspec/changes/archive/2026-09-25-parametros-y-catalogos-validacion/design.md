## Context

- **Parámetros del motor:** `BUSINESS_RULES` en `app/core/constants.py` contiene:
  - receptor: razón social "ULTRASIST", RFC `ULT940623AG0`, CP `03930` y régimen `601`;
  - método de pago `PPD` y forma `99`;
  - usos de CFDI `G03` e `I04`;
  - pesos del score.

  `xml_rules()` los lee directamente. XML-007 fija las monedas `MXN`, `USD` y `EUR`. `/admin/rules` los muestra en solo lectura y la spec `motor-validacion` declara a `BUSINESS_RULES` como fuente única.
- **XML:** `parse_cfdi()` ya extrae `receiver_name` y `receiver_postal_code`, pero ninguna regla los compara.
- **Patrones de configuración:**
  - HU-04: tabla, pantalla, bloqueo consultivo, huella y auditoría;
  - HU-05: una fila con `version` para el bloqueo optimista;
  - HU-08: errores juntos con HTTP 400 y el formulario conserva lo capturado.
- **Excel:** HU-01 lee `.xlsx` con `openpyxl` sobre un paquete ZIP ya inspeccionado:
  - tamaño descomprimido acotado y sin DTD ni entidades;
  - celdas con fórmulas o fechas rechazadas;
  - la función `ImportFileError` para rechazar el archivo completo.

## Goals / Non-Goals

**Goals:**
- Que el Administrador cambie los datos de ULTRASIST y los parámetros del CFDI sin despliegue, y que la siguiente prevalidación los use.
- Comparar RFC, Razón Social y Código Postal del receptor (validación nacional de la minuta).
- Catálogos administrables y cargables desde Excel, con integridad frente a las reglas que los usan.

**Non-Goals:**
- Validación de invoices internacionales (HU-16) y flujo de envío (HU-13).
- Reglas definidas por el Administrador y pesos del score editables.

## Decisions

### D1. `validation_settings`: una fila con versión
Columnas:
- `receiver_rfc`, `receiver_name`, `receiver_address` y `receiver_postal_code`;
- `receiver_tax_regime`, `payment_method`, `payment_form` y `allowed_cfdi_uses` (`VARCHAR(10)[]`);
- seis booleanos `check_*`;
- `version`, `updated_at` y `updated_by`.

Restricciones: `CHECK (id = 1)`, el código postal con cinco dígitos, al menos un uso de CFDI y `version >= 1`. La migración siembra los valores actuales de `BUSINESS_RULES` con las seis comparaciones activas y la dirección vacía.

El guardado sigue el patrón de HU-05: un `UPDATE … WHERE version = :v` que, si no afecta ninguna fila, responde 409.

*Alternativa:* una fila por regla (código, valor, activa). Los valores tienen tipos distintos (texto, lista, CP) y se perderían las restricciones por campo.

### D2. `catalog_entries`: todos los catálogos en una tabla
Columnas:
- `catalog` (enumeración `CatalogType`: `CURRENCY`, `CFDI_USE`, `PAYMENT_FORM`, `PAYMENT_METHOD`, `TAX_REGIME`);
- `code`, `name` e `is_active`;
- fechas y `updated_by`.

Restricciones: `UNIQUE (catalog, code)`, clave `^[A-Z0-9]{1,10}$` y descripción de 1 a 150 caracteres.

El servicio valida además el formato de la clave por catálogo:

| Catálogo | Formato de la clave | Ejemplo |
| --- | --- | --- |
| Moneda | tres letras | `USD` |
| Uso de CFDI | una o dos letras y dos dígitos | `G03`, `CP01` |
| Forma de pago | dos dígitos | `99` |
| Método de pago | tres letras | `PPD` |
| Régimen fiscal | tres dígitos | `601` |

Siembra:
- los catálogos del SAT de CFDI 4.0: 24 usos de CFDI, 22 formas de pago, 2 métodos y 19 regímenes;
- las tres monedas que hoy acepta XML-007: `MXN`, `USD` y `EUR`.

*Alternativa:* una tabla por catálogo. Cinco tablas iguales, cinco pantallas y cinco cargas; el tipo de catálogo cubre las diferencias.

### D3. Parámetros del motor leídos por prevalidación
`validation_settings_service.rule_parameters(db)` devuelve un `RuleParameters` inmutable con la configuración y las monedas activas. `run_validation()` lo lee una vez por prevalidación, sin caché, y lo pasa a `xml_rules(data, error, params)`. Cada comparación desactivada produce `not_applicable(código, …, "Comparación desactivada en Reglas de Validación")`. Mantiene su severidad y no altera el score.

| Regla | Compara | Severidad |
| --- | --- | --- |
| XML-002 | `Receptor.Rfc` = RFC | `CRITICAL` (sin cambio) |
| XML-003 | `MetodoPago` = método | `ERROR` |
| XML-004 | `FormaPago` = forma | `ERROR` |
| XML-005 | `UsoCFDI` ∈ usos | `ERROR` |
| XML-007 | `Moneda` ∈ monedas activas | `ERROR`; no tiene interruptor |
| XML-009 (nueva) | `Receptor.Nombre` = Razón Social, sin distinguir mayúsculas, acentos ni espacios repetidos | `ERROR` |
| XML-010 (nueva) | `Receptor.DomicilioFiscalReceptor` = CP | `ERROR` |

Los mensajes de falla muestran el valor esperado, por ejemplo "MetodoPago debe ser PPD". `BUSINESS_RULES` conserva sólo `score_weights`.

### D4. Integridad entre reglas y catálogos
Las Reglas de Validación sólo aceptan claves activas de su catálogo: régimen, método, forma y cada uso de CFDI. Una clave referenciada por la configuración no se puede desactivar (409 "La clave … está en uso en Reglas de Validación."), ni individualmente ni en la carga desde Excel. La última moneda activa tampoco (409). Así el motor nunca exige una clave que el catálogo ya no ofrece.

### D5. Pantalla de Reglas de validación
`/admin/rules` pasa a ser un formulario con tres bloques:
- Datos de ULTRASIST, cada uno con su interruptor "Comparar";
- Parámetros del CFDI, con listas de los catálogos y casillas para los usos;
- Pesos del score, en solo lectura.

La tabla "Reglas XML" muestra cada código, qué compara, su severidad y si está activa. Validación:
- RFC de persona moral (12 caracteres, patrón SAT) y fecha válida;
- Razón Social de 1 a 254 caracteres;
- Dirección de hasta 300 caracteres;
- CP de 5 dígitos;
- claves activas;
- al menos un uso de CFDI.

El menú cambia "Reglas" por "Reglas de validación".

### D6. Catálogos
- `GET /admin/catalogs` lista los cinco catálogos con el número de claves activas y totales.
- `GET /admin/catalogs/{catalogo}` muestra las claves, marca las que están "En uso", y ofrece alta, edición de la descripción, desactivación y reactivación, y la carga desde Excel.
- El código del catálogo en la ruta es el valor de `CatalogType`; uno desconocido responde 404.
- Las escrituras toman un bloqueo consultivo propio.
- Los avisos de éxito redirigen con `?ok=<clave>`, como en HU-04.

### D7. Carga desde Excel
- **Plantilla** (`GET …/template`): hoja "Catalogo" con las columnas "Clave", "Descripción" y "Activo" (Sí/No) y las claves vigentes, más una hoja "Instrucciones".
- **Carga** (`POST …/import`, formulario `multipart`, sin JavaScript):
  - reutiliza de `supplier_import_service` la inspección del paquete ZIP, el lector de celdas (fórmulas y fechas) e `ImportFileError`. El único cambio en ese módulo es un parámetro opcional `log_failure` en la inspección, para que la carga de catálogos registre `catalog_import.read_failed` en lugar del evento de proveedores; su comportamiento por omisión no cambia;
  - límites: 5 MB, 1000 filas y encabezados exactos;
  - errores por fila: clave con formato del catálogo, descripción de 1 a 150 caracteres, "Activo" Sí/No (vacío = Sí), clave repetida en el archivo, desactivar una clave en uso y dejar el catálogo de monedas sin activas.
  - Con cualquier error no se aplica nada (HTTP 400, lista de errores, máximo 200 mostrados). Sin errores, agrega las claves nuevas y actualiza descripción y estado de las existentes en una transacción. El resumen indica agregadas, actualizadas y sin cambios. Supuesto S7.

### D8. Auditoría y log
- `VALIDATION_SETTINGS_UPDATED`: sólo los campos que cambiaron, anteriores y nuevos, y la versión.
- `CATALOG_ENTRY_CREATED`, `CATALOG_ENTRY_UPDATED` y `CATALOG_ENTRY_STATUS_CHANGED`: entidad `CatalogEntry`.
- `CATALOG_IMPORTED`: catálogo, claves agregadas y actualizadas.
- Eventos de log:
  - `validation_settings.updated`: `fields` (nombres de los campos) y `version`;
  - `catalog.import`: `catalog`, `result` (`imported` o `rejected`), `rows`, `added`, `updated`, `unchanged`, `invalid`, `size_bytes` y `duration_ms`;
  - `catalog_import.read_failed`: tipo y mensaje técnico de la excepción al leer el archivo.

## Risks / Trade-offs

- **[Facturas que antes pasaban y ahora fallan]** XML-009 y XML-010 agregan comparaciones. → Los XML de la demo cumplen; si un proveedor real escribe la razón social distinta, el Administrador puede corregir el dato de ULTRASIST o desactivar la comparación sin despliegue.
- **[Normalización de la razón social]** Se ignoran mayúsculas, acentos y espacios repetidos, pero no el sufijo societario ("SA DE CV"). → El Administrador define la razón social exacta que exige el SAT desde la versión 4.0.
- **[Import de funciones internas]** La carga de catálogos importa funciones internas de `supplier_import_service`. → Se documenta en el código y las pruebas de HU-01 siguen cubriéndolas; extraerlas a un módulo común sería un refactor fuera del alcance.

## Migration Plan

1. `alembic upgrade head` aplica `0007_validation_rules_catalogs`: crea y siembra ambas tablas con los valores que ya aplicaba el motor.
2. La primera prevalidación posterior evalúa también XML-009 y XML-010.
3. Rollback: el downgrade borra las tablas si la configuración sigue en la versión 1 y los catálogos no se modificaron; si no, lanza `NotImplementedError` ("… Restaure un respaldo.").

## Open Questions

- Razón social exacta de ULTRASIST ante el SAT, con o sin régimen societario, y su dirección: se capturan en la pantalla.
- Si la moneda del contrato debe elegirse del catálogo de monedas (hoy es texto libre de 3 letras).
