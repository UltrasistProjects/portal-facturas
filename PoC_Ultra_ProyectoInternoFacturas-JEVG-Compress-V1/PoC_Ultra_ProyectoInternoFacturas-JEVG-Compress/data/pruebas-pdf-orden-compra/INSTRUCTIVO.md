# Prueba: lectura de la factura en PDF y validación contra la orden de compra

Esta prueba demuestra dos cosas del Portal de Proveedores FERROMEX (rama `ferromex`, HU-24):

1. **Lectura del PDF.** El proveedor carga solo el PDF de su factura, sin XML. El portal lee sus datos y los muestra junto a la imagen del PDF, con ✓ o ✗ en cada dato que valida.
2. **Comparación contra la orden de compra.** Al enviar la factura, el portal la compara con la orden de compra precargada. Si no cuadra, detiene el envío y dice por qué.

Todos los documentos son ficticios y están marcados como prueba. El proveedor es **Mantenimiento Ferroviario del Bajío** (persona moral, RFC `MFB140325AB1`) y sus seis órdenes de compra ya vienen sembradas en la demo.

## Resumen de los casos

| Caso | Carpeta | Qué se muestra | Resultado esperado |
|---|---|---|---|
| 1 | `1-factura-correcta` | Factura que cuadra con su orden: 2 conceptos y 2 partidas | Enviada y ligada a la orden 45000611 |
| 2 | `2-monto-distinto` | Factura por más de lo que dice la orden | Detenida: OC-005, OC-006 y OC-009 |
| 3 | `3-sin-entrada-de-mercancia` | Refacciones que todavía no llegan al almacén | Detenida: OC-011 |
| 4 | `4-orden-ya-facturada` | Segunda factura contra la orden del caso 1 | Detenida: OC-012 |
| 5 | `5-orden-de-otro-proveedor` | Factura que cita la orden de otro proveedor | Detenida: OC-002 |
| 6 | `6-sin-orden-en-el-concepto` | El concepto no cita la orden de compra | Aviso en la Revisión; detenida: OC-001 |
| 7 | `7-receptor-incorrecto` | Factura emitida a otra empresa | ✗ en la Revisión; detenida: XML-002, XML-009 y XML-010 |
| 8 | `8-pdf-escaneado` | PDF escaneado, sin texto | Solo con el PDF no se registra; con su XML, se envía |

**Ruta corta (unos 15 minutos):** casos 1, 2, 3, 7 y 8.

Si vas a hacer el caso 4, hazlo después del caso 1: necesita que la orden 45000611 ya tenga una factura.

## Archivos

Todas las rutas son relativas a la carpeta de la app (`PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress`) y están en `data/pruebas-pdf-orden-compra/`.

| Carpeta | Archivos |
|---|---|
| `0-proveedor` | Los 7 documentos del expediente (sección 3) |
| `1-factura-correcta` | `CFDI-F2101-MFB140325AB1.pdf`, `VoBo-F2101.pdf` |
| `2-monto-distinto` | `CFDI-F2102-MFB140325AB1.pdf`, `VoBo-F2102.pdf` |
| `3-sin-entrada-de-mercancia` | `CFDI-F2103-MFB140325AB1.pdf`, `VoBo-F2103.pdf` |
| `4-orden-ya-facturada` | `CFDI-F2104-MFB140325AB1.pdf`, `VoBo-F2104.pdf` |
| `5-orden-de-otro-proveedor` | `CFDI-F2105-MFB140325AB1.pdf`, `VoBo-F2105.pdf` |
| `6-sin-orden-en-el-concepto` | `CFDI-F2106-MFB140325AB1.pdf`, `VoBo-F2106.pdf` |
| `7-receptor-incorrecto` | `CFDI-F2107-MFB140325AB1.pdf`, `VoBo-F2107.pdf` |
| `8-pdf-escaneado` | `CFDI-F2108-MFB140325AB1-escaneado.pdf`, `CFDI-F2108-MFB140325AB1.xml`, `VoBo-F2108.pdf` |
| `_generador` | El script que genera los documentos (sección 8) |

---

# Antes de la reunión

## 1. Preparar el portal

Desde la carpeta de la app:

```bash
# Base de datos y Keycloak de la rama ferromex
DOCKER_CONTEXT=default docker compose up -d --wait db keycloak

# Base limpia con las órdenes de compra de esta prueba. Con el portal detenido: el reinicio necesita la base libre.
# Respalda antes en backups/ y borra todos los datos de la base de trabajo.
DOCKER_CONTEXT=default .venv/bin/python scripts/reset_demo.py --yes

# Portal en el puerto 8000 (Keycloak solo acepta ese puerto); los correos se guardan como archivos y no se envían
MAIL_BACKEND=file MAIL_FROM="Portal de Proveedores FERROMEX <no-reply@portal.local>" \
MAIL_OUTBOX_DIR=./evidencias/_correos .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Abre <http://127.0.0.1:8000>.

**Cuentas:**

| Rol | Usuario | Contraseña |
|---|---|---|
| Administrador | `admin@poc.local` | la de `DEMO_PASSWORD` en `.env` |
| PMO | `pmo@poc.local` | la de `DEMO_PASSWORD` en `.env` |
| Proveedor | el correo que captures en la sección 3 | temporal, la manda el portal al autorizarlo |

**Correo:** con las variables `MAIL_*` de arriba no sale ningún correo real. Si prefieres que el correo de credenciales llegue de verdad, arranca el portal sin esas variables (usa el SMTP del `.env`) y en **Email** captura un buzón tuyo.

## 2. Verificar las órdenes de compra precargadas (Administrador)

En el portal las órdenes de compra no se capturan: llegan de SAP. En esta demo las siembra `reset_demo.py`.

1. Inicia sesión como `admin@poc.local`.
2. Menú **Órdenes de compra**. En el buscador escribe `MFB140325AB1` y pulsa **Buscar**.
3. Deben aparecer 6 órdenes, todas a nombre de MANTENIMIENTO FERROVIARIO DEL BAJIO y con 0 facturas:

| Convenio | Fecha | Partidas (Txt.brv · cantidad · unidad · precio) | Total | Impuestos | Entrada de mercancía | Caso |
|---|---|---|---|---|---|---|
| 45000611 | 06/10/2026 | MANTENIMIENTO PREVENTIVO LOCOMOTORA · 1 · SER · 85,000.00 / ZAPATA DE FRENO COMPOSITE · 40 · PZA · 950.00 | 123,000.00 | 19,680.00 | Sí, las dos partidas | 1 y 4 |
| 45000612 | 13/10/2026 | REVISION SISTEMA DE FRENOS DE AIRE · 1 · SER · 60,000.00 | 60,000.00 | 9,600.00 | Sí | 2 |
| 45000613 | 20/10/2026 | RODAMIENTO PARA EJE DE CARRO TOLVA · 8 · PZA · 4,200.00 | 33,600.00 | 5,376.00 | **No** | 3 |
| 45000614 | 27/10/2026 | INSPECCION ULTRASONICA DE RUEDAS · 1 · SER · 42,000.00 | 42,000.00 | 6,720.00 | Sí | 7 |
| 45000615 | 03/11/2026 | CALIBRACION DE BASCULA DE VIA · 1 · SER · 27,500.00 | 27,500.00 | 4,400.00 | Sí | 8 |
| 45000616 | 04/11/2026 | MANTENIMIENTO CORRECTIVO LOCOMOTORA · 1 · SER · 38,000.00 | 38,000.00 | 6,080.00 | Sí | 6 |

Abre la **45000611** para ver sus partidas. Las columnas **Docto. material** y **Fecha contab.** son la entrada de mercancía: en la 45000613 están vacías.

Las órdenes existen antes que el proveedor. Se ligan a él por su RFC en cuanto se da de alta.

## 3. Alta del proveedor (Administrador)

Menú **Proveedores** › **+ Agregar proveedor**. Captura:

| Campo | Valor |
|---|---|
| Origen | Nacional |
| Razon social / nombre | `Mantenimiento Ferroviario del Bajío` |
| RFC (nacional) | `MFB140325AB1` |
| Tipo de persona | Persona moral |
| Email | `facturacion@mfbajio.example`, o un buzón tuyo si el portal envía correo real |
| Teléfono | `442 218 7740` |
| Clasificación | Externo |
| Actividad principal | 81 · Otros servicios excepto actividades gubernamentales |
| Fecha de constitución | `25/03/2014` |
| Página web | `https://www.mfbajio.example` |
| Nombre del contacto | `Laura Méndez Ocampo` |
| Teléfono del contacto | `442 218 7741` |
| Nombre del representante legal | `Arturo Villaseñor Pacheco` |
| Teléfono del representante legal | `442 218 7742` |
| Información bancaria | `Banco Demo, S.A. - Cuenta 0213458790 - CLABE 000680002134587906` |
| Convenio de confidencialidad firmado | Marcado |
| Alta por cotización o licitación | **Sin marcar** (si se marca, la Propuesta económica pasa a ser obligatoria) |

Pulsa **Crear proveedor**. El portal abre su expediente con el estatus "Registrado".

> **La razón social se captura sin "S.A. de C.V.".** La regla PRV-002 compara el nombre del emisor del CFDI con la razón social registrada. En el CFDI 4.0, el nombre va sin el régimen de capital, igual que en la Constancia de Situación Fiscal. Si se captura con "S.A. de C.V.", todas las facturas marcarán ✗ en PRV-002.

**Expediente.** En **Agregar o reemplazar documento del expediente**, carga uno por uno. Para cada documento, elige el **Documento**, captura la **Fecha del documento**, selecciona el **Archivo** de `0-proveedor/` y pulsa **Guardar documento**:

| Documento | Fecha del documento | Archivo |
|---|---|---|
| Acta constitutiva (obligatorio) | 25/03/2014 | `Acta-Constitutiva-MFB140325AB1.pdf` |
| Poderes (obligatorio) | 14/06/2019 | `Poder-Representante-Legal-MFB140325AB1.pdf` |
| Cédula fiscal (obligatorio) | 16/11/2026 | `Constancia-Situacion-Fiscal-MFB140325AB1.pdf` |
| Identificación del representante legal (obligatorio) | 10/05/2023 | `Identificacion-Representante-Legal-MFB140325AB1.pdf` |
| Comprobante de domicilio del representante legal (obligatorio) | 03/11/2026 | `Comprobante-Domicilio-Representante-Legal-MFB140325AB1.pdf` |
| Comprobante de domicilio (obligatorio) | 05/11/2026 | `Comprobante-Domicilio-MFB140325AB1.pdf` |
| Estado de cuenta bancario (obligatorio) | 31/10/2026 | `Estado-Cuenta-Bancario-MFB140325AB1.pdf` |

Al terminar, **Requisitos de alta** dice "Requisitos de alta completos". Pulsa **Autorizar proveedor** y luego **Autorizar y enviar credenciales**. El resultado debe decir "1 autorizados · 0 omitidos · 0 no autorizados".

> Las fechas de la cédula, los comprobantes de domicilio y el estado de cuenta tienen que ser de los últimos 3 meses. Si la prueba se hace después de enero de 2027, el expediente mostrará "Advertencia de vigencia (+3 meses)". Es solo un aviso: no impide autorizar.

## 4. Primer acceso del proveedor

1. **Contraseña temporal.** Si el portal envía correo real, está en el correo "Acceso al Portal de Proveedores FERROMEX". Con los correos en archivos, se lee así:

   ```bash
   .venv/bin/python tests/hu/fixtures/herramientas.py correo evidencias/_correos facturacion@mfbajio.example "Acceso al Portal" \
     | .venv/bin/python -c "import json,sys; print(json.loads(sys.stdin.read().splitlines()[-1])['texto'])"
   ```

2. Cierra la sesión del Administrador. Inicia sesión con el correo del proveedor y la contraseña temporal.
3. Keycloak pide una contraseña nueva: mínimo 8 caracteres, con letra, número y carácter especial (por ejemplo `Bajio#2026qro`). Captúrala dos veces y confirma.
4. Entras al tablero del proveedor ("Hola, Mantenimiento": saluda con la razón social). Déjalo listo para la reunión.

---

# Durante la reunión

## 5. Cómo se registra una factura (igual en todos los casos)

Con la sesión del proveedor:

1. **+ Nueva factura**, en el tablero o en **Facturas**.
2. **Paso 1 · Archivos**
   - **PDF de la factura (obligatorio):** el `CFDI-…pdf` del caso.
   - **XML del CFDI (opcional):** vacío, salvo en el caso 8b.
   - Pulsa **Continuar a la revisión**.
3. **Paso 2 · Revisión.** A la izquierda, la imagen del PDF. A la derecha, los datos que leyó el portal y, arriba, "Datos tomados de: **Texto del PDF**". Junto a cada dato que valida aparece ✓, o ✗ con el valor esperado.
4. En **Cargar o reemplazar un archivo**:
   - **Tipo de documento:** "Vo.Bo. del líder de proyecto".
   - Selecciona el `VoBo-…pdf` del caso y pulsa **Cargar documento**.
   - **Archivos de la factura** cambia a "Archivos obligatorios completos".
5. **Paso 3 · Enviar a validación.** El portal valida la factura contra su orden de compra.
   - **Si procede:** el detalle dice "Factura enviada a validación", el estatus pasa a **Enviada** y aparece el panel de la orden de compra con sus partidas.
   - **Si no procede:** aparece "**El envío no procedió.** Corrija las reglas que lo impiden y vuelva a enviar la factura.", con la tabla **Reglas que impiden el envío**. La factura sigue en **Cargada** y no llega al PMO.

Las reglas de la orden de compra se ven en la **Matriz de evidencia** del detalle, grupo **OC**:

| Regla | Qué revisa |
|---|---|
| OC-001 | El concepto cita un número de orden de compra, por ejemplo `(OC/45000611)` |
| OC-002 | La orden existe y es del proveedor |
| OC-003 / OC-004 | RFC y nombre coinciden con la orden |
| OC-005 / OC-006 | Subtotal e IVA iguales al total y a los impuestos de la orden |
| OC-007 | Cada concepto corresponde a una partida (por su texto `Txt.brv`) |
| OC-008 / OC-009 | Cantidad, unidad e importe de cada concepto coinciden con la partida |
| OC-010 | Moneda |
| OC-011 | La partida tiene entrada de mercancía (Docto. material y Fecha contab.) |
| OC-012 | La orden no tiene otra factura vigente |

## 6. Casos

### Caso 1 · Factura correcta, solo con PDF

**Archivos:** `1-factura-correcta/CFDI-F2101-MFB140325AB1.pdf` y `VoBo-F2101.pdf`.

**En la Revisión**, compara los datos leídos con la imagen del PDF:

| Sección | Dato | Valor leído del PDF |
|---|---|---|
| Factura | Serie y folio | F-2101 |
| | UUID | 2489226A-7C76-42A4-91B5-92A3D419F8CC ✓ |
| | Fecha | 2026-11-20T10:15:00 (el periodo queda en 11/2026, el mes de emisión) |
| | Tipo · Moneda | I · MXN ✓ |
| | Forma de pago · Método de pago | 99 ✓ · PPD ✓ |
| Proveedor | RFC · Nombre · Régimen fiscal | MFB140325AB1 ✓ · MANTENIMIENTO FERROVIARIO DEL BAJIO ✓ · 601 ✓ |
| Cliente | RFC · Nombre | IME010718PU3 ✓ · INTERMODAL MEXICO ✓ |
| | Régimen · Uso de CFDI · Código postal | 601 ✓ · G03 ✓ · 11700 ✓ |
| Conceptos | Encabezado | "Orden de compra detectada: **45000611**" |
| | Concepto 1 | 1 · E48 - SERVICIO · Mantenimiento preventivo locomotora GE AC4400… · 85,000.00 |
| | Concepto 2 | 40 · H87 - PIEZA · Zapata de freno composite para carro tolva · 950.00 · 38,000.00 |
| Totales | Subtotal · IVA · Total | 123,000.00 · 19,680.00 · 142,680.00 |

**Al enviar:** la factura queda **Enviada**. En **Orden de compra** aparece 45000611 y el panel muestra las dos partidas. En la Matriz de evidencia, OC-001 a OC-012 salen en **PASS**.

**Qué decir:** el proveedor no capturó ningún dato. El portal los leyó del PDF y comparó partida por partida contra la orden de SAP: textos, cantidades, unidades, precios, montos, entrada de mercancía y que la orden no estuviera ya facturada.

### Caso 2 · El monto no cuadra con la orden

**Archivos:** `2-monto-distinto/CFDI-F2102-MFB140325AB1.pdf` y `VoBo-F2102.pdf`.

**En la Revisión:** proveedor y cliente con ✓. Orden detectada: **45000612**. Subtotal **68,500.00**; la orden es por 60,000.00.

**Al enviar:** el envío no procede.

| Regla | Resultado |
|---|---|
| OC-005 | Subtotal 68500.00 distinto del total de la orden de compra 60000.00 |
| OC-006 | IVA 10960.00 distinto de los impuestos de la orden de compra 9600.00 |
| OC-009 | Concepto 1: importe 68500.00 vs 60000.00 |

### Caso 3 · Sin entrada de mercancía

**Archivos:** `3-sin-entrada-de-mercancia/CFDI-F2103-MFB140325AB1.pdf` y `VoBo-F2103.pdf`.

**En la Revisión:** todo con ✓. Orden detectada: **45000613**. 8 piezas a 4,200.00, igual que la orden.

**Al enviar:** el envío no procede.

| Regla | Resultado |
|---|---|
| OC-011 | Concepto 1: la partida no tiene entrada de mercancía |

**Qué decir:** montos y cantidades cuadran, pero los rodamientos aún no entran al almacén: la partida de la orden no tiene Docto. material ni Fecha contab. No se paga lo que no se ha recibido.

### Caso 4 · La orden ya está facturada (después del caso 1)

**Archivos:** `4-orden-ya-facturada/CFDI-F2104-MFB140325AB1.pdf` y `VoBo-F2104.pdf`.

**En la Revisión:** es la misma factura del caso 1 con otro folio (F-2104) y otro UUID. Todo con ✓. Orden detectada: **45000611**.

**Al enviar:** el envío no procede.

| Regla | Resultado |
|---|---|
| OC-012 | La orden de compra ya tiene la factura FAC-2026-xxxxx |

FAC-2026-xxxxx es el folio interno de la factura del caso 1 (encabezado de su detalle).

**Qué decir:** cada orden admite una sola factura vigente. Se libera solo si esa factura se rechaza o se cancela.

### Caso 5 · Orden de otro proveedor

**Archivos:** `5-orden-de-otro-proveedor/CFDI-F2105-MFB140325AB1.pdf` y `VoBo-F2105.pdf`.

**En la Revisión:** todo con ✓. Orden detectada: **45000451**. Esa orden existe, pero es de otro proveedor (Héctor Garza Villarreal).

**Al enviar:** el envío no procede.

| Regla | Resultado |
|---|---|
| OC-002 | La orden de compra 45000451 no existe para el proveedor |

### Caso 6 · El concepto no cita la orden de compra

**Archivos:** `6-sin-orden-en-el-concepto/CFDI-F2106-MFB140325AB1.pdf` y `VoBo-F2106.pdf`.

**En la Revisión:** en **Conceptos** aparece en rojo "No se encontró el número de orden de compra en los conceptos". El resto, con ✓.

**Al enviar:** el envío no procede.

| Regla | Resultado |
|---|---|
| OC-001 | No se encontró el número de orden de compra en los conceptos |

**Qué decir:** la orden existe (45000616, y el Vo.Bo. la menciona), pero el portal liga la factura a la orden por lo que dice el CFDI. El proveedor debe refacturar citando `(OC/45000616)` en el concepto.

### Caso 7 · Factura emitida a otra empresa

**Archivos:** `7-receptor-incorrecto/CFDI-F2107-MFB140325AB1.pdf` y `VoBo-F2107.pdf`.

**En la Revisión**, sección **Cliente**:

| Dato | Leído del PDF | Marca |
|---|---|---|
| RFC | LIP101010AB1 | ✗ XML-002 · Esperado: IME010718PU3 |
| Nombre | LOGISTICA INTEGRAL DEL PACIFICO | ✗ XML-009 · Esperado: INTERMODAL MEXICO |
| Código postal | 82000 | ✗ XML-010 · Esperado: 11700 |
| Régimen fiscal · Uso de CFDI | 601 · G03 | ✓ |

**Al enviar:** el envío no procede.

| Regla | Resultado |
|---|---|
| XML-002 | RFC receptor incorrecto |
| XML-009 | Razón social del receptor incorrecta |
| XML-010 | Código postal del receptor incorrecto |

**Qué decir:** el error se ve desde la Revisión, antes de enviar. Los datos del receptor esperado son la configuración de **Reglas de Validación** (Administrador).

### Caso 8 · PDF escaneado

**Archivos:** `8-pdf-escaneado/CFDI-F2108-MFB140325AB1-escaneado.pdf`, `CFDI-F2108-MFB140325AB1.xml` y `VoBo-F2108.pdf`.

**8a. Solo el PDF.** En el Paso 1 carga solo el PDF escaneado y pulsa **Continuar a la revisión**. El portal se queda en el Paso 1 con el mensaje:

> No pudimos leer los datos de la factura en el PDF. Adjunte el XML.

No se crea ninguna factura. El PDF es una imagen sin capa de texto, y el portal no tiene OCR.

**8b. PDF y XML.** En la misma pantalla selecciona otra vez el PDF escaneado, y en **XML del CFDI** el `CFDI-F2108-MFB140325AB1.xml`. Pulsa **Continuar a la revisión**.
- La Revisión dice "Datos tomados de: **XML**": factura F-2108, orden detectada 45000615, total 31,900.00, todo con ✓.
- Carga `VoBo-F2108.pdf` y envía. La factura queda **Enviada** y ligada a la orden **45000615**.

**Qué decir:** sin texto en el PDF, el proveedor resuelve adjuntando el XML. Para leer PDF escaneados haría falta un servicio de OCR. El portal ya tiene el punto de conexión, pero no está activo.

## 7. Cierre opcional (PMO)

1. Cierra la sesión del proveedor e inicia como `pmo@poc.local`.
2. **Órdenes de compra** › busca `MFB140325AB1`. La columna **Facturas** muestra 1 en la 45000611 y en la 45000615, y 0 en las demás: las facturas detenidas no se ligan a su orden.
3. Abre la **45000611**: en **Facturas ligadas** aparece F-2101 en "Enviada".
4. En **Facturas**, filtra por "Enviada" y abre F-2101. El PMO ve la orden de compra, sus partidas y la matriz de evidencia, y decide **Autorizar**, **Observaciones** o **Rechazar**. La validación no aprueba la factura: decide qué llega al PMO.

---

## 8. Repetir o regenerar la prueba

- **Repetir.** Los UUID de las facturas son fijos y cada orden admite una sola factura vigente. Para repetir la prueba en la misma base hay que reiniciarla con `scripts/reset_demo.py` (sección 1) y volver a dar de alta al proveedor. Keycloak conserva la cuenta del proveedor: al autorizarlo de nuevo, recibe otra contraseña temporal.
- **Regenerar los documentos.** Hace falta `npm ci` en `tests/hu`:

  ```bash
  node data/pruebas-pdf-orden-compra/_generador/generar.mjs
  ```

  Si cambias montos, partidas o textos, cámbialos también en:
  - las órdenes de `scripts/seed_db.py` (`pdf_test_orders`);
  - este instructivo;
  - `tests/test_set_pdf_orden_compra.py`.
- **Verificación automática.** `tests/test_set_pdf_orden_compra.py` recorre este instructivo con sus mismos archivos y valores, y comprueba cada resultado y cada mensaje de las tablas. Si falla, el instructivo ya no describe lo que hace el portal:

  ```bash
  .venv/bin/python -m pytest tests/test_set_pdf_orden_compra.py --no-cov -q
  ```
