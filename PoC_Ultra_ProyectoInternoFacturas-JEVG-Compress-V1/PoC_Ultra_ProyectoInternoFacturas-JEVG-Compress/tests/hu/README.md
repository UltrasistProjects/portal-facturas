# Pruebas funcionales de las HUs (Playwright)

Una prueba por HU del ERS v1.4 (`specs/NN-HU-XX-*.spec.ts`), ejecutadas en orden de dependencias. Cada prueba deja en
`evidencias/HU-XX/` sus capturas (`NN-descripcion.png`) y `resultado.json` (escenarios, pasos, esperado/obtenido y
estado). Con esos resultados se genera `EVIDENCIA-PRUEBAS-HUs.pdf` en la raíz del proyecto.

Es un paquete Node aislado: el portal sigue sin requerir Node para operar.

## Ejecutar

1. Levantar PostgreSQL y Keycloak, y la base demo (ver el README del proyecto).
2. Arrancar el portal con el transporte de correo a archivo, para no enviar correos reales y para que las pruebas lean
   los `.eml`:

   ```bash
   MAIL_BACKEND=file MAIL_FROM="Portal de Proveedores ULTRASIST <no-reply@portal.local>" \
   MAIL_OUTBOX_DIR=./evidencias/_correos .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
   ```

3. En `tests/hu/`:

   ```bash
   npm install                      # una vez
   npx playwright test              # las 18 HUs
   node generar-reporte-pdf.mjs     # EVIDENCIA-PRUEBAS-HUs.pdf
   ../../.venv/bin/python verificar-pdf.py   # páginas, imágenes y referencias del PDF
   ```

Cada ejecución genera identificadores propios (RFC, correos, números de factura, UUID), así que la suite se puede repetir
sobre la misma base. Para repetir un solo spec conservando los datos de la ejecución anterior:
`HU_RUN_ID=<id de evidencias/_estado-ejecucion.json> npx playwright test specs/11-*`.

## Resultado

- `PASS`: todos los escenarios pasaron. `FAIL`: algún paso no cumplió lo esperado (se captura la pantalla del fallo).
  `BLOCKED`: no se pudo ejecutar por ambiente, autenticación o una dependencia de otra HU.
- Artefactos: `evidencias/`, `test-results/` (trazas), `playwright-report/` (HTML) y
  `evidencias/playwright-resultados.json`.
- `reporte-contexto.json` contiene el ambiente, los problemas y las observaciones del ejecutor que se incluyen en el PDF.
