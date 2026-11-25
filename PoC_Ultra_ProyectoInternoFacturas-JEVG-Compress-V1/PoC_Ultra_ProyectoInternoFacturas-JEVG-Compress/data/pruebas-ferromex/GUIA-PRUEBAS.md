# Pruebas Ferromex: recorrido completo desde cero

Recorrido de la rama `ferromex` con la orden de compra en lugar del contrato (HU-24):
- alta del proveedor;
- una factura que pasa por Observaciones y termina autorizada y pagada;
- una factura rechazada por no cuadrar con su orden de compra;
- la factura 3668 del documento de negocio, registrada sólo con su PDF.

Todos los documentos son ficticios y están marcados como prueba. Los valores exactos de cada formulario están en `DATOS-A-CAPTURAR.txt`.

## Antes de empezar

- **Portal:** el de la rama `ferromex` en http://127.0.0.1:8000, con la demo sembrada (`scripts/reset_demo.py`). Con `MAIL_BACKEND=file`, los correos (credenciales y avisos) no se envían: quedan como `.eml` en `outbox/`.
- **Órdenes de compra:** la demo siembra las del recorrido, consultables en *Órdenes de compra* (PMO o Administrador):

  | Convenio | Proveedor | Total + IVA | Uso |
  |---|---|---|---|
  | 45000451 | `GAVH810417Q42` | 45,000.00 + 7,200.00 | Factura A-1001: cuadra y tiene entrada de mercancía |
  | 45000452 | `GAVH810417Q42` | 45,000.00 + 7,200.00 | Factura A-1002: factura 52,000.00 y no cuadra |
  | 25704872 | `GOHS60031745A` | 3,559.05 + 569.45 | Factura 3668 del ejemplo |

  El proveedor `GAVH810417Q42` todavía no existe en el portal: sus órdenes se encuentran por RFC en cuanto se da de alta.
- **Receptor de los CFDI:** INTERMODAL MEXICO, RFC `IME010718PU3`, régimen 601, uso G03 y C.P. 11700. Son los valores iniciales de *Reglas de Validación* (P-01). Si se cambian, edita `RECEPTOR` en `_generador/generar.mjs` y vuelve a generar (ver al final).
- **Archivos de la factura:** el PDF del CFDI y el Vo.Bo. son obligatorios y el XML es opcional. La orden de compra ya no es un archivo: el portal la lee del concepto del CFDI, por ejemplo `(OC/45000451)`.
- **PMO:** usa la cuenta PMO del seed (`pmo@poc.local`) o crea un PMO desde Administrador antes de empezar.

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
- Propuesta económica: obligatoria porque el alta se marca como "Alta por cotización/licitación".
- Opcional: Opinión de cumplimiento.

Con el expediente completo, elige **Autorizar proveedor** y después **Autorizar y enviar credenciales**. El proveedor entra con la contraseña temporal del correo y la cambia.

## 2. Escenario A: Observaciones y después autorización (carpeta `3-factura-observaciones-autorizada`)

1. **Archivos.** El proveedor entra a *Facturas › Registrar factura* y carga `CFDI-A1001-GAVH810417Q42.pdf` y su XML.
2. **Revisión.** El portal muestra la imagen del PDF y los datos leídos: factura A-1001, periodo 11/2026 (mes de emisión) y orden de compra detectada 45000451. Proveedor, cliente, UUID, moneda y forma y método de pago aparecen con ✓.
3. En la misma pantalla carga **`VoBo-A1001-v1-con-error-periodo-09-2026`**. La factura pasa a "Cargada".
4. **Envío.** Elige **Enviar a validación**. Todas las reglas salen en verde, incluidas `OC-001` a `OC-012` contra la orden 45000451, y la factura queda ligada a esa orden.
5. El PMO revisa: el detalle muestra la orden de compra y su partida. El Vo.Bo. cita el periodo 09/2026, que no es el del servicio. El PMO decide **Observaciones**, por ejemplo: "El Vo.Bo. corresponde al periodo 09/2026; adjunte el Vo.Bo. del periodo 10/2026."
6. El proveedor recibe el correo, reemplaza el Vo.Bo. con **`VoBo-A1001-v2-corregido`** y reenvía.
7. El PMO **Autoriza**.
8. Cierre del ciclo: el Administrador elige **Marcar como pagada** y el proveedor carga `REP-P1001` (XML y PDF). El complemento relaciona el UUID de A-1001.

**Happy path directo**, sin Observaciones: en el paso 3 carga `VoBo-A1001-v2-corregido` y el PMO autoriza a la primera. Después sigue con el paso 8.

## 3. Escenario B: rechazo por no cuadrar con la orden de compra (carpeta `4-factura-rechazada`)

1. El proveedor registra `CFDI-A1002-GAVH810417Q42` (PDF y XML). La revisión detecta la orden de compra 45000452.
2. Carga `VoBo-A1002` y envía.
3. El envío no procede. El portal lista las diferencias contra la orden 45000452:
   - `OC-005`: subtotal 52,000.00 distinto del total de la orden, 45,000.00;
   - `OC-006`: IVA 8,320.00 distinto de 7,200.00;
   - `OC-009`: "Concepto 1: importe 52000.00 vs 45000.00".

   La factura sigue "Cargada" y no llega al PMO.

## 4. Escenario C: la factura 3668 del ejemplo, sólo con PDF

Proveedor del ejemplo: la cuenta demo `proveedor2@poc.local` (SOCORRO PATRICIA GONZALEZ HERNANDEZ, `GOHS60031745A`).

1. **Archivos.** Carga sólo `data/demo_documents/factura_3668.pdf`, sin XML.
2. **Revisión.** El portal toma los datos del texto del PDF: factura 3668, periodo 01/2026, UUID `A328F91A-DDDD-4624-89AC-877819F5B540`, concepto "LTH TIPO L-31T-900 AR BATERIA (OC/25704872)" y orden de compra 25704872. `PRV-001` a `PRV-003` y las reglas del cliente aparecen con ✓.
3. Carga un Vo.Bo. (por ejemplo `data/demo_documents/vobo_demo.txt`) y envía.
4. `OC-001` a `OC-012` resultan en verde contra la orden 25704872. La factura pasa a "Enviada" ligada a la orden, que el PMO ve en el detalle y en *Órdenes de compra › 25704872*.

El flujo completo de esta factura, hasta el pago y su complemento, con un PDF que reproduce la maqueta del documento de negocio, está en [`data/pruebas-factura-3668`](../pruebas-factura-3668/INSTRUCTIVO.md).

## Repetir la prueba en la misma base

Los UUID de los CFDI son fijos y cada orden de compra admite una sola factura vigente (`OC-012`). La segunda carga en la misma base marca `FIN-004` (UUID duplicado). Una orden ya ocupada sólo se libera si su factura se rechaza o se cancela. Además, el RFC del proveedor ya no se puede volver a dar de alta. Para repetir el recorrido, usa una base limpia (`scripts/reset_demo.py`) o cambia en el generador los UUID (`FACTURA_A`, `FACTURA_B`, `PAGO_A`) y los datos del proveedor.

## Regenerar los documentos

```bash
# desde la carpeta de la app; requiere npm ci en tests/hu (o HU_DIR=<otra carpeta tests/hu con node_modules>)
node data/pruebas-ferromex/_generador/generar.mjs
# la factura 3668 y los CFDI demo del seed:
python scripts/cfdi_demo.py
```

El script reescribe los XML y los PDF de las carpetas 1, 3 y 4. No modifica esta guía ni `DATOS-A-CAPTURAR.txt`: si cambias datos del proveedor o de las facturas, actualízalos también aquí y en las órdenes de compra de `scripts/seed_db.py`.
