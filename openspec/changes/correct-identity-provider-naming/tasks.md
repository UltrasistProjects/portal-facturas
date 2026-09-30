> Las rutas de la PoC son relativas a `PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress-V1/PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress/`.

## 1. ERS (`docs/source-of-truth/ERS_Portal_Proveedores_ULTRASIST_MVP.docx`)

- [ ] 1.1 Confirmar que el ERS no está abierto en LibreOffice (sin `.~lock.ERS_…docx#`) y respaldar su texto por párrafo para compararlo después.
- [ ] 1.2 Reescribir con python-docx, run a run, los párrafos 55, 56, 84, 89, 194, 311, 316 y 332 con los textos de D5, conservando el formato.
- [ ] 1.3 Portada "Versión 1.4" con la fecha de la corrección, y fila 1.4 en el control de versiones copiada de la fila 1.3 (D4, D5).
- [ ] 1.4 Comparar el texto antes y después: sólo cambian los párrafos de 1.2 y 1.3. Si alguno no pudo editarse, listarlo con el texto actual y el propuesto para edición manual.

## 2. PoC y documentación

- [ ] 2.1 `README.md:459` y `:572`: proveedor de identidad (Keycloak) en lugar de ClickCloud/gestor de secretos (D6).
- [ ] 2.2 Docstrings de `app/services/secret_vault.py` y `app/services/supplier_access_service.py` (D6), sin cambiar nombres ni lógica.
- [ ] 2.3 `tests/test_acceso_proveedores.py`: renombrar `test_resguardo_en_el_gestor_de_secretos` y los mensajes "Gestor de secretos" (D6).
- [ ] 2.4 `docs/stories/epics/EP-01 Acceso y gestion de facturas del proveedor.md:458`: Keycloak como proveedor de identidad.

## 3. Verificación

- [ ] 3.1 La búsqueda de D2 no devuelve resultados, y `rg -n -i "gestor de secretos"` con las mismas exclusiones tampoco.
- [ ] 3.2 `pytest tests/test_acceso_proveedores.py` en verde, y `ruff check` y `ruff format --check` limpios.
- [ ] 3.3 `openspec validate correct-identity-provider-naming --strict` sin errores.
