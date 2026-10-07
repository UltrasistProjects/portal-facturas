## Why

Tres ajustes reportados en las pruebas del portal:
- al dar de alta una persona física se pedían los datos del representante legal, que no le aplican;
- el tipo "Persona física" debe nombrarse "Persona física (con actividad empresarial)";
- el periodo de la factura exigía exactamente `MM/AAAA` y CON-003 comparaba contra el día exacto de inicio del contrato: un periodo correcto quedaba bloqueado.

## What Changes

- El representante legal (nombre y teléfono) sólo se pide y se guarda para persona moral; en persona física se oculta, no se exige y el expediente muestra "No aplica".
- "Persona física (con actividad empresarial)" en el alta, el listado, el expediente, Requisitos de alta y la plantilla de carga masiva, que sigue aceptando "Física".
- El periodo se acepta con separadores y espacios comunes (8/2026, 08-2026, 2026-08) y se guarda como `MM/AAAA`; CON-003 compara por mes y muestra la vigencia como "MM/AAAA a MM/AAAA".

## Capabilities

### New Capabilities

_Ninguna._

### Modified Capabilities

- `acceso-proveedores`: representante legal sólo de persona moral; etiqueta de persona física.
- `catalogo-proveedores`: valor de lista "Física (con actividad empresarial)" en la plantilla; "Física" se sigue aceptando.
- `flujo-facturas`: periodo sin formato estricto, normalizado a `MM/AAAA`.
- `interfaz-usuario`: el ejemplo de periodo inválido en el navegador.
- `motor-validacion`: CON-003 por mes.

## Impact

`app/schemas/__init__.py`, `app/rules/contract_rules.py`, `app/core/constants.py`, `app/routers/common.py`, plantillas de proveedores y factura, `supplier_template.py` y `supplier_import_service.py`; pruebas en `test_datos_proveedor.py`, `test_altas.py`, `test_motor.py`, `test_carga_masiva_proveedores.py` y la spec Playwright 10. Sin migraciones.
