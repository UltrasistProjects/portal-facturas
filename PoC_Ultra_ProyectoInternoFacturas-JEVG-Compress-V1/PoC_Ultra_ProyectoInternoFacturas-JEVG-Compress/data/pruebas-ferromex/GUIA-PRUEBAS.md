# Pruebas Ferromex: recorrido completo desde cero

Es el mismo recorrido de la demo de Ultrasist (`data/demo-flujo-completo` en `dev`), con datos de Ferromex: alta del proveedor, contrato, una factura que pasa por Observaciones y termina autorizada y pagada, y una factura rechazada. Todos los documentos son ficticios y están marcados como prueba. Los valores exactos de cada formulario están en `DATOS-A-CAPTURAR.txt`.

## Antes de empezar

- **Portal:** el de la rama `ferromex` en http://127.0.0.1:8000. Con `MAIL_BACKEND=file`, los correos (credenciales y avisos) no se envían: quedan como `.eml` en `outbox/`.
- **Receptor de los CFDI:** el XML trae los datos que hoy tienen las Reglas de Validación del portal: RFC `ULT940623AG0`, razón social `FERROMEX` y C.P. `03930`. Son provisionales mientras llegan los datos fiscales reales de Ferromex. Si se cambian en *Reglas de Validación*, edita `RECEPTOR` en `_generador/generar.mjs` y vuelve a generar (ver al final). Si no, los XML fallan XML-002, XML-009 y XML-010.
- **Archivos mínimos de la factura (configuración actual):** solo el XML del CFDI es obligatorio. El PDF del CFDI, la orden de compra y el Vo.Bo. son opcionales, pero conviene cargarlos: el escenario A se basa en el Vo.Bo.
- **Número de contrato:** los PDF dicen "Contrato 4", el número que tendrá el próximo contrato en la base local de Ferromex (ahora hay 3). Si antes se crea otro contrato, el número no coincidirá. Es solo un dato impreso: el portal no lo valida.
- **PMO:** usa la cuenta PMO del seed (`pmo@poc.local`) o, como en el video de Ultrasist, crea un PMO desde Administrador antes de empezar.

## 1. Alta del proveedor nacional (Administrador)

| Campo | Valor |
|---|---|
| Tipo | Persona física, origen Nacional |
| Nombre | Héctor Garza Villarreal |
| RFC | GAVH810417Q42 |
| Correo | un buzón de prueba (recibe las credenciales) |
| Domicilio | Av. Constitución 2050, Int. 3, Col. Obispado, Monterrey, Nuevo León, C.P. 64060 |
| Banco / CLABE | Banco Demo, S.A. / 000580004578123964 |

Expediente (carpeta `1-proveedor`):

- Obligatorios: Cédula fiscal (`Constancia-Situacion-Fiscal`), Comprobante de domicilio, Estado de cuenta bancario e Identificación oficial.
- Opcionales: Opinión de cumplimiento y Propuesta económica.

Con el expediente completo: **Autorizar proveedor**, y después **Autorizar y enviar credenciales**. El proveedor entra con la contraseña temporal del correo y la cambia.

## 2. Contrato (Administrador)

Carpeta `2-contrato`.

| Campo | Valor |
|---|---|
| Proyecto | Monitoreo de Flota Ferroviaria FERROMEX |
| Líder de proyecto | Mariana Cortés Elizondo |
| Tecnología autorizada | React + Python Fast API |
| Monto autorizado | 45,000.00 MXN |
| Vigencia | 2026-10-01 a 2027-03-31 |

Carga el contrato firmado y elige **Activar contrato**.

## 3. Escenario A: Observaciones y después autorización (carpeta `3-factura-observaciones-autorizada`)

Captura (proveedor): contrato "Monitoreo de Flota Ferroviaria FERROMEX", factura **A-1001**, periodo **10/2026**, orden de compra OC-2026-0451.

1. El proveedor carga el XML y el PDF `CFDI-A1001`, la `OrdenCompra-OC-2026-0451` y **`VoBo-A1001-v1-con-error-periodo-09-2026`**, y envía. Todas las reglas del CFDI, del contrato y financieras deben salir en verde.
2. El PMO revisa: el Vo.Bo. cita el periodo 09/2026, anterior al inicio del contrato. Decide **Observaciones**, por ejemplo: "El Vo.Bo. corresponde al periodo 09/2026; adjunte el Vo.Bo. del periodo 10/2026."
3. El proveedor recibe el correo, reemplaza el Vo.Bo. con **`VoBo-A1001-v2-corregido`** y reenvía.
4. El PMO **Autoriza**.
5. Cierre del ciclo: el Administrador elige **Marcar como pagada** y el proveedor carga `REP-P1001` (XML y PDF). El complemento relaciona el UUID de A-1001.

**Happy path directo**, sin Observaciones: en el paso 1 carga `VoBo-A1001-v2-corregido` y el PMO autoriza a la primera. Después sigue con el paso 5.

## 4. Escenario B: rechazo directo (carpeta `4-factura-rechazada`)

Captura (proveedor): mismo contrato, factura **A-1002**, periodo **11/2026**, orden de compra OC-2026-0452.

1. El proveedor carga `CFDI-A1002` (XML y PDF), `OrdenCompra-OC-2026-0452` y `VoBo-A1002`, y envía.
2. El portal marca FIN-001 y FIN-006: el subtotal de la factura ($52,000) excede el monto autorizado del contrato y de la orden de compra ($45,000).
3. El PMO decide **Rechazar**, por ejemplo: "El importe facturado ($52,000.00 + IVA) excede el monto autorizado del contrato y de la orden de compra OC-2026-0452 ($45,000.00 + IVA)."

## Repetir la prueba en la misma base

Los UUID de los CFDI son fijos, así que la segunda carga en la misma base marca FIN-004 (UUID duplicado). Además, el RFC del proveedor ya no se puede volver a dar de alta. Para repetir el recorrido, cambia en el generador los UUID (`FACTURA_A`, `FACTURA_B`, `PAGO_A`) y los datos del proveedor, o hazlo en una base limpia.

## Regenerar los documentos

```bash
# desde la carpeta de la app; requiere npm ci en tests/hu (o HU_DIR=<otra carpeta tests/hu con node_modules>)
node data/pruebas-ferromex/_generador/generar.mjs
```

El script reescribe los XML y los PDF de las carpetas 1 a 4. No modifica esta guía ni `DATOS-A-CAPTURAR.txt`: si cambias datos del proveedor o del contrato, actualízalos también aquí.
