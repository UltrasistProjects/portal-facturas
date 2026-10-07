## Context

El portal sigue el flujo routers → services → repositories/models. `app/rules/` es dominio puro y ningún servicio hace commit: el commit es del endpoint. Este cambio toca cinco áreas. Antes de diseñar, se confirmó con el usuario lo siguiente:

- **Reglas de Validación** pasan a ser un catálogo de reglas, con un registro por regla y origen. Deja de existir la fila única `validation_settings`.
- **Registros precargados atados al código**: todos se pueden editar y eliminar. Se retiran los niveles fijos y sus CHECK, aun con el riesgo que eso implica.
- **Eliminar** se unifica como baja lógica con "Restaurar". Desaparecen "Desactivar/Reactivar" y el borrado físico.
- **Moneda**: aplica a la factura y al contrato. El contrato es el único lugar con texto libre.

Estado actual relevante:
- La autorización individual y la masiva ya usan `supplier_access_service.authorize()`.
- El envío ya bloquea con DOC-* o desde "Borrador", pero con un mensaje genérico.
- La factura internacional ya elige la moneda del catálogo.

## Goals / Non-Goals

**Goals:**
- Una sola definición de cada regla de negocio en su servicio, sin duplicar código nuevo, para pasar el quality gate de SonarQube.
- Lo que el Administrador ve en Reglas de Validación es exactamente lo que el motor aplica, por origen.
- Ninguna validación cambia al migrar, salvo el resultado nuevo XML-011 `NOT_APPLICABLE`.
- Los borrados no eliminan filas y conservan el historial y los documentos.

**Non-Goals:**
- Crear reglas de validación nuevas desde la interfaz: las reglas son código y solo se configuran.
- Hacer configurables la severidad de las reglas, las reglas DOC, SUP, FIN, CON, DAT o SEM, ni XML-001, XML-006, XML-007 o XML-008.
- Una llave foránea de `invoices.currency` a `catalog_entries`.
- Reevaluar facturas ya enviadas o proveedores ya autorizados.

## Decisions

**D1. Catálogo `validation_rules` con un registro de definiciones en código.**
- La tabla tiene estas columnas:
  - `id`, `origin` (`SupplierOrigin`) y `rule_code` (String 10), con UNIQUE (origin, rule_code);
  - `name` (String 80) y `parameter` (JSONB: texto, o lista para XML-005; NULL en INT-001);
  - `is_active`, `deleted_at` y `deleted_by`, con CHECK `is_active = (deleted_at IS NULL)`;
  - `version` (CHECK ≥ 1), `created_at`, `updated_at` y `updated_by`.
- `app/rules/definitions.py`, que es dominio puro, declara cada regla configurable: origen, código, nombre inicial, campo que compara, severidad, tipo de parámetro (`RFC`, `TEXT`, `ADDRESS`, `POSTAL_CODE`, `CATALOG_CODE` o `CATALOG_CODES`, con su catálogo, o `NONE`) y la etiqueta del campo para los errores.
- `validation_rules_service` es el único acceso al catálogo:
  - `rule_set(db, origin)` devuelve un `RuleSet`: código → (activa, parámetro), más las monedas activas. Lo usan el motor y la página.
  - `page_rules`, `update_rule`, `delete_rule`, `restore_rule` e `in_use_codes`.
- `xml_rules` e `international_rules` reciben el `RuleSet` del origen en lugar de `RuleParameters`. El motor llama `rule_set(db, invoice.supplier.origin)`.
- Una regla inactiva genera `NOT_APPLICABLE` con "Regla inactiva en Reglas de Validación" y su severidad, igual que antes un interruptor apagado.
- *Alternativa descartada*: agregar un discriminador a `validation_settings`, con dos filas. No da registros que se puedan eliminar uno por uno; el usuario eligió el catálogo.

**D2. XML-007 y el régimen fiscal.**
- XML-007 no entra al catálogo de reglas: es la aplicación de la regla inviolable del punto 1 (moneda del catálogo de monedas). Si se pudiera eliminar, una factura podría enviarse con una moneda fuera del catálogo. La página nacional lo explica con una nota.
- El régimen fiscal era un dato de referencia sin comparación. Pasa a XML-011, que compara `RegimenFiscalReceptor` (el parser ya lo extrae) y nace eliminada, para no cambiar la validación.
- *Alternativa descartada*: conservar `validation_settings` solo para el régimen. Dejaría dos fuentes de configuración y columnas muertas.

**D3. Migración `0020_validation_rules`.**
- Lee la fila 1 de `validation_settings` e inserta las reglas `NATIONAL` (activa = su interruptor; XML-011 eliminada con el régimen vigente).
- Siembra las `INTERNATIONAL`:
  - INT-001 activa;
  - INT-002 e INT-003 con la Razón Social y el Código Postal, y los interruptores de XML-009 y XML-010;
  - INT-004 con la Dirección, activa solo si no está vacía.
- Después hace `op.drop_table('validation_settings')`.
- El downgrade recrea `validation_settings` a partir de las reglas nacionales. Lanza `NotImplementedError` si las reglas internacionales difieren de lo que la fila única puede representar, porque se perdería configuración.
- `catalog_service.in_use` pasa a `validation_rules_service.in_use_codes(db)`: solo cuentan los parámetros de las reglas activas.

**D4. Baja lógica compartida en los tres catálogos de requisitos.**
- `0019_types_soft_delete` hace lo siguiente en `invoice_document_types`, `supplier_document_types` y `contract_document_types`:
  - agrega `deleted_at` y `deleted_by`;
  - rellena `deleted_at = updated_at` en las filas inactivas;
  - agrega el CHECK `is_active = (deleted_at IS NULL)`;
  - retira `ck_*_system_active` y `ck_*_fixed_levels`.
- Un módulo nuevo, `app/services/type_catalog.py`, concentra lo que hoy se triplica:
  - `soft_delete(db, model, type_id, user_id, entity, action)` y `restore(...)`, que bloquean la fila, son idempotentes (devuelven False sin auditar) y auditan `*_DELETED`/`*_RESTORED`;
  - `_flush` con traducción de unicidad, `_share_lock` y `_ensure_unique_name`.
- Los tres servicios conservan su API, pero se retiran `_admin_type`/`_support_type` (sin restricción por `is_system`), `set_active`, el borrado físico, `MSG_SYSTEM_*`, `MSG_IN_USE`, `FIXED_*` y `fixed_requirement`.
- El router reemplaza las rutas `/status` por `/delete` y `/restore`, con un helper común para los tres pares de rutas y así evitar duplicación nueva.
- La plantilla `_type_actions.html` muestra Editar/Eliminar en toda fila activa y Editar/Restaurar en la sección "Eliminados", que solo se muestra con `?eliminados=1`. Las advertencias de los tipos atados al código salen de un diccionario `CODE_BOUND_WARNINGS` en `constants.py`.
- *Alternativa descartada*: mantener "Desactivar" y "Eliminar" como dos acciones distintas. El usuario eligió unificarlas.

**D5. Tolerancia a tipos del sistema eliminados o con otros niveles.**
- *Motor*: si la factura es nacional, no tiene XML vigente y `INVOICE_XML` no es Obligatorio y activo para Nacional, XML-001 a XML-011 resultan `NOT_APPLICABLE` con "El XML del CFDI no se exige en Archivos mínimos". DOC-* ya siguen la configuración.
- *Cancelación*: `acknowledgment_type` devuelve el tipo solo si está activo. Sin él, `check_request` no exige archivo y la plantilla oculta el campo.
- *Pago*: `requires_complement` exige además que `PAYMENT_COMPLEMENT_XML` esté activo, y `ensure_no_overdue_complements` no bloquea mientras esté eliminado.
- *Contrato*: `SIGNED_CONTRACT` sin nivel fijo no requiere código especial.

**D6. Archivos obligatorios en la transición.**
- `violates()` se mueve de `invoice_service` a `app/core/database.py`, para que `document_requirements_service` deje de importar `invoice_service` y se rompa el ciclo.
- `document_requirements_service.missing_required(db, invoice)` devuelve los tipos obligatorios faltantes y `missing_message(types)` arma el texto.
- `transition_invoice` llama a `missing_required` cuando el destino es `UNDER_REVIEW` y lanza `MissingRequiredDocumentsError(BusinessRuleError)`, que el handler global responde con 409.
- `submit_invoice` devuelve los faltantes en `SubmissionResult` para el caso "Borrador". El router los convierte en la misma excepción después del commit, como hoy.
- *Alternativa descartada*: validar solo en `submit_invoice`. El usuario pidió que la regla viva en la transición.

**D7. Moneda y total.**
- `ForeignInvoiceData` deja de recibir `total`: un `computed_field` o un método calcula `to_money(subtotal + tax)` y se retiran `total_matches` y `AMOUNT_TOLERANCE`. Los endpoints quitan el `Form` del total, así que FastAPI ignora el valor enviado.
- `static/js/invoice_amounts.js` recalcula el total en centavos enteros, sin aritmética en float, y lo muestra en un `<input readonly>`. Respeta la CSP: no usa scripts en línea.
- La creación de contratos se mueve a `contract_service.create_contract`, que valida la moneda con `catalog_service.active_codes`; el router solo traduce HTTP. El formulario usa un `<select>`.
- `run_validation` asigna `invoice.currency` solo si la moneda del XML está activa. La factura nacional nace con `contract.currency`.
- `0021_currency_catalog_mapping` normaliza la moneda con SQL y un diccionario de alias, audita `CURRENCY_NORMALIZED` y escribe en el log los valores que no se pueden mapear. `scripts/reporte_monedas.py` los lista en solo lectura.

**D8. Un solo camino a "Autorizado".**
- `Supplier.status` cambia su default a `REGISTERED` (solo del lado de Python; no hay `server_default`, así que no cambia el esquema).
- Una prueba estática recorre `app/` con AST y verifica que `SupplierStatus.ACTIVE` solo se asigna en `supplier_access_service`.
- `authorize()` ya calcula los pendientes con la configuración vigente y los reporta por nombre en el resumen. No se reescribe.

## Risks / Trade-offs

- [El Administrador elimina o relaja el XML del CFDI, el Invoice, el acuse o el complemento: el portal deja de exigirlos y pueden enviarse facturas sin importes del CFDI] → El usuario lo aceptó explícitamente. La confirmación muestra la consecuencia de cada tipo atado al código, la auditoría registra quién lo hizo y "Restaurar" lo revierte.
- [XML-011 agrega un resultado nuevo a la validación nacional] → Nace eliminada, así que resulta `NOT_APPLICABLE` y no afecta el score. Las pruebas de "sin cambios" se ajustan para esperarla.
- [Retirar `validation_settings` y las rutas `/status` rompe pruebas y especificaciones E2E existentes] → Se actualizan en la misma rama (tareas 9 y 10).
- [Facturas con moneda fuera del catálogo] → Se conservan, se reportan y se entregan al usuario para que decida cómo corregirlas.
- [Nombre único entre registros activos y eliminados] → Crear un tipo con el nombre de uno eliminado responde 409; el Administrador lo restaura en su lugar. Así se evita un índice parcial.
- [SUP-003 bloquea las facturas de un proveedor ya autorizado si se agrega un requisito obligatorio] → Es el comportamiento vigente de HU-21: el proveedor no se desactiva, pero sus envíos piden el documento nuevo. Se documenta y no se cambia.

## Migration Plan

1. Rama `hu-ajustes-finales` a partir de `dev`.
2. Aplicar `alembic upgrade head`, que corre 0019, 0020 y 0021, y luego `alembic check` sin diferencias.
3. Ejecutar `scripts/reporte_monedas.py` sobre la base de trabajo y reportar al usuario las monedas que no se pudieron mapear.
4. Rollback: `alembic downgrade 0018_invoice_payment`.
   - 0021 no revierte la normalización: es idempotente y sus valores son válidos.
   - 0020 reconstruye `validation_settings` o lanza `NotImplementedError` si se perdería configuración internacional.
   - 0019 reinstala los CHECK solo si los datos los cumplen; si no, lanza `NotImplementedError` con el motivo.

## Open Questions

- Ninguna bloqueante. Lo que muestre el reporte de monedas lo decide el usuario después de la migración.
