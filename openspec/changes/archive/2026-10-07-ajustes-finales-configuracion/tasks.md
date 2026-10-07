## 1. Rama y base

- [x] 1.1 Crear la rama `hu-ajustes-finales` desde `dev` sin arrastrar los cambios sin confirmar de `hu-tema-login-keycloak` (guardarlos con `git stash` o en un worktree aparte)
- [x] 1.2 Mover `violates()` de `invoice_service` a `app/core/database.py` y actualizar sus importaciones (rompe el ciclo con `document_requirements_service`)

## 2. Baja lógica en los catálogos de requisitos (punto 5)

- [x] 2.1 Revisión `0019_types_soft_delete`: `deleted_at` y `deleted_by` en los tres catálogos, relleno de las filas inactivas, CHECK `is_active = (deleted_at IS NULL)`, retiro de `ck_*_system_active` y `ck_*_fixed_levels`, y un downgrade explícito o `NotImplementedError`
- [x] 2.2 Modelos: columnas nuevas y CHECK actualizados en `InvoiceDocumentType`, `SupplierDocumentType` y `ContractDocumentType`
- [x] 2.3 `app/services/type_catalog.py`: `soft_delete`, `restore` y los auxiliares comunes (bloqueo de fila, unicidad del nombre, flush)
- [x] 2.4 Los tres servicios de requisitos: quitar la restricción `is_system`, `set_active`, el borrado físico y los niveles fijos; usar `type_catalog`; editar cualquier tipo
- [x] 2.5 Retirar `FIXED_*`, `FIXED_*_REASONS` y `fixed_requirement`; agregar `CODE_BOUND_WARNINGS` en `constants.py`
- [x] 2.6 Router admin: rutas `/delete` y `/restore` con un helper común, retiro de `/status`, avisos "Tipo eliminado" y "Tipo restaurado", y `?eliminados=1`
- [x] 2.7 Plantillas: `_type_actions.html` (Editar/Eliminar en toda fila, confirmación con advertencia y sección de eliminados con Restaurar) y las tres pantallas sin candados

## 3. Tolerancia a tipos del sistema eliminados

- [x] 3.1 Cancelación: exigir el acuse sólo si `CANCELLATION_ACK` está activo; ocultar el campo en el detalle si no lo está
- [x] 3.2 Pago: `requires_complement` y `ensure_no_overdue_complements` dependen de que `PAYMENT_COMPLEMENT_XML` esté activo
- [x] 3.3 Motor: XML-001 a XML-011 `NOT_APPLICABLE` cuando el XML no se exige y no se cargó

## 4. Catálogo de Reglas de Validación (punto 4)

- [x] 4.1 `app/rules/definitions.py` con las 11 reglas configurables (origen, código, nombre, campo, severidad y tipo de parámetro)
- [x] 4.2 Modelo `ValidationRule` y revisión `0020_validation_rules`: crear la tabla, migrar desde `validation_settings`, sembrar las internacionales, quitar `validation_settings` y escribir el downgrade
- [x] 4.3 `validation_rules_service`: `rule_set`, listado por origen, `update_rule` (validación por tipo y versión), `delete_rule`, `restore_rule` e `in_use_codes`
- [x] 4.4 `xml_rules` (XML-011 y reglas inactivas) e `international_rules` con `RuleSet`; el motor usa `rule_set(db, origin)`
- [x] 4.5 `catalog_service.in_use` sobre `in_use_codes`; retirar `validation_settings_service` y el modelo `ValidationSettings`
- [x] 4.6 Router y plantillas: `/admin/rules` → 303, `/admin/rules/{origen}`, editar, eliminar y restaurar; menú con "Nacionales" e "Internacionales"

## 5. Moneda y total (punto 1)

- [x] 5.1 `ForeignInvoiceData` sin `total`, con el total calculado (`to_money(subtotal + tax)`); quitar `AMOUNT_TOLERANCE` y el `Form` del total en `/new` y `/amounts`
- [x] 5.2 `static/js/invoice_amounts.js` (cálculo en centavos) y el campo Total de solo lectura en `foreign_invoice_fields.html`
- [x] 5.3 `contract_service.create_contract` con la moneda validada contra el catálogo; router delgado; selector en `contracts/list.html`
- [x] 5.4 Factura nacional: nace con la moneda del contrato; `run_validation` guarda la moneda del XML sólo si está activa
- [x] 5.5 Revisión `0021_currency_catalog_mapping` (normalización con alias y auditoría `CURRENCY_NORMALIZED`) y `scripts/reporte_monedas.py`

## 6. Envío a validación (punto 3)

- [x] 6.1 `document_requirements_service.missing_required` y `missing_message`; `MissingRequiredDocumentsError` (409)
- [x] 6.2 Verificación en `transition_invoice` hacia `UNDER_REVIEW`; `submit_invoice` y el router usan el mensaje con nombres

## 7. Autorización de proveedores (punto 2)

- [x] 7.1 `Supplier.status` con default `REGISTERED`; revisar `scripts/seed_db.py` para que asigne el estatus de forma explícita

## 8. Pruebas (pytest, base temporal)

- [x] 8.1 Moneda y total: moneda inválida en contrato y en factura (petición directa), total manipulado recalculado en alta y edición, moneda del CFDI fuera del catálogo, y la función de normalización
- [x] 8.2 Autorización: bloqueada con requisitos faltantes (individual y masiva), permitida con requisitos completos, un requisito nuevo no desactiva a los autorizados, un requisito eliminado deja de exigirse, default `REGISTERED` y la prueba estática del único camino
- [x] 8.3 Envío: 409 con nombres desde "Borrador" y por la transición directa; permitido con archivos completos; una factura enviada no se afecta; un tipo eliminado deja de exigirse
- [x] 8.4 Motor: una factura internacional usa reglas internacionales y una nacional usa reglas nacionales; regla eliminada `NOT_APPLICABLE`; XML-011; XML no exigido
- [x] 8.5 Reglas de Validación: páginas, edición, concurrencia, eliminar y restaurar, 403 para PMO y Proveedor, CSRF y auditoría
- [x] 8.6 Requisitos: editar y eliminar registros precargados, la fila se conserva con `deleted_at`, deja de exigirse en activaciones y envíos, restaurar, 403 y auditoría; ajustar las pruebas existentes de `/status`, niveles fijos y borrado físico
- [x] 8.7 Migraciones: `alembic check`, contenido sembrado de `validation_rules` y downgrade de 0019, 0020 y 0021; integridad (CHECK de baja lógica)
- [x] 8.8 Ejecutar la suite completa, `ruff` y `scripts/check.py` sin errores

## 9. E2E y verificación

- [x] 9.1 Actualizar las specs de Playwright afectadas (05, 07, 08, 12, 14, 19, 20 y 21) sin ejecutarlas durante pytest
- [x] 9.2 Aplicar las migraciones sobre la base de trabajo, ejecutar `scripts/reporte_monedas.py` y reportar el resultado
- [x] 9.3 Resumen final: cambios por punto, archivos, migraciones, pruebas y pasos de verificación manual
