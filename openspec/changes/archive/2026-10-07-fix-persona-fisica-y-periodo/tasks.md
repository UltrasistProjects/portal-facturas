## 1. Persona física

- [x] 1.1 Representante legal sólo para persona moral en `SupplierProfile`, el formulario y el expediente
- [x] 1.2 Etiqueta "Persona física (con actividad empresarial)" en la interfaz y la plantilla de carga masiva (se sigue aceptando "Física")

## 2. Periodo de la factura

- [x] 2.1 Periodo sin formato estricto, normalizado a `MM/AAAA`, con `pattern` flexible en el navegador
- [x] 2.2 CON-003 por mes con la vigencia en formato "MM/AAAA a MM/AAAA"

## 3. Pruebas

- [x] 3.1 pytest: alta de persona física y moral, periodos aceptados y rechazados, CON-003 por mes y plantilla
- [x] 3.2 Spec Playwright 10 con un periodo realmente inválido
