# Prueba: flujo completo de la factura 3668 con su proveedora

Esta prueba lleva la factura 3668 del documento de negocio (HU-24) de punta a punta en el Portal de Proveedores FERROMEX (rama `ferromex`):

1. La proveedora la registra **solo con el PDF**. El portal lee sus datos del texto del PDF y la valida contra la orden de compra **25704872**.
2. El PMO la devuelve con **Observaciones** porque el Vo.Bo. cita otra orden. La proveedora corrige y reenvía.
3. El PMO la **autoriza** y el Administrador la marca como **pagada**.
4. Es PPD, así que la proveedora adjunta su **Complemento de Pago**.

La proveedora es la cuenta demo `proveedor2@poc.local`: **SOCORRO PATRICIA GONZALEZ HERNANDEZ**, persona física, RFC `GOHS60031745A`. La demo ya la trae autorizada, con su expediente, y siembra su orden 25704872.

El PDF de la factura reproduce la representación impresa del ejemplo: los RFC sin etiqueta, los datos del timbre a la derecha y el detalle del concepto debajo de su renglón. Tiene capa de texto, como el que emite un PAC. Los sellos son de prueba, no lleva código QR y su pie lo marca como documento ficticio. El Vo.Bo. y el complemento de pago también son ficticios.

## Resumen del flujo

| Paso | Quién | Qué hace | Estatus de la factura |
|---|---|---|---|
| 3 | Proveedora | Registra la factura solo con el PDF | Borrador |
| 4 | Proveedora | Carga el Vo.Bo. con la orden equivocada y envía | Enviada |
| 5 | PMO | Devuelve con Observaciones | Observaciones |
| 6 | Proveedora | Reemplaza el Vo.Bo. y reenvía | Enviada |
| 7 | PMO | Autoriza | Autorizada |
| 8 | Administrador | Marca como pagada | Pagada, complemento pendiente |
| 9 | Proveedora | Adjunta el complemento de pago | Pagada, complemento adjuntado |

**Ruta corta, sin Observaciones:** en el paso 4 carga `VoBo-3668-v2-corregido.pdf`, salta los pasos 5 y 6 y sigue en el 7.

## Archivos

Todas las rutas son relativas a la carpeta de la app (`PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress`) y están en `data/pruebas-factura-3668/`.

| Carpeta | Archivo | Para qué |
|---|---|---|
| `1-factura` | `CFDI-3668-GOHS60031745A.pdf` | La factura 3668 (PDF con texto) |
| | `CFDI-3668-GOHS60031745A-escaneado.pdf` | La misma factura, sólo imagen (sin texto): para la variante con IA de la sección 3 |
| | `VoBo-3668-v1-orden-equivocada.pdf` | Vo.Bo. que cita la orden 25704827: provoca las Observaciones |
| | `VoBo-3668-v2-corregido.pdf` | Vo.Bo. con la orden correcta, 25704872 |
| `2-pago` | `REP-P-3701-GOHS60031745A.xml` | Complemento de pago (CFDI tipo P) que liquida la 3668 |
| | `REP-P-3701-GOHS60031745A.pdf` | Su representación impresa |
| `_generador` | `generar.mjs` | El script que genera los documentos (sección 11) |

---

# Antes de la prueba

## 1. Preparar el portal

Desde la carpeta de la app:

```bash
# Base de datos y Keycloak de la rama ferromex
DOCKER_CONTEXT=default docker compose up -d --wait db keycloak

# Base limpia con la demo. Con el portal detenido: el reinicio necesita la base libre.
# Respalda antes en backups/ y borra todos los datos de la base de trabajo.
DOCKER_CONTEXT=default .venv/bin/python scripts/reset_demo.py --yes

# Portal en el puerto 8000 (Keycloak solo acepta ese puerto); los correos se guardan como archivos y no se envían
MAIL_BACKEND=file MAIL_FROM="Portal de Proveedores FERROMEX <no-reply@portal.local>" \
MAIL_OUTBOX_DIR=./evidencias/_correos .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Abre <http://127.0.0.1:8000>.

**Cuentas** (las tres con la contraseña de `DEMO_PASSWORD` en `.env`):

| Rol | Usuario |
|---|---|
| Administrador | `admin@poc.local` |
| PMO | `pmo@poc.local` |
| Proveedora | `proveedor2@poc.local` |

**Correo:** el buzón de la proveedora es `@poc.local` y no existe. Con las variables `MAIL_*` de arriba, los avisos de Observaciones, Autorizada, Pagada y Complemento adjuntado quedan como `.eml` en `evidencias/_correos`. Si arrancas el portal con el SMTP real del `.env`, los avisos a la proveedora no llegan a ningún buzón.

## 2. Verificar la orden de compra 25704872 (Administrador)

Las órdenes de compra no se capturan en el portal: llegan de SAP. En la demo, `reset_demo.py` siembra esta.

1. Inicia sesión como `admin@poc.local`.
2. Menú **Órdenes de compra**. Escribe `25704872` en el buscador y pulsa **Buscar**. Abre la orden.

| Dato | Valor |
|---|---|
| Convenio · Fecha | 25704872 · 09/12/2025 |
| RFC · Nombre | GOHS60031745A · SOCORRO PATRICIA GONZALEZ HERNANDEZ |
| Total · Impuestos | $3,559.05 · $569.45 |
| Partida 1 | Material E20080 · Txt.brv **LTH TIPO L-31 T-900 AR** · 1 PZA · Prc. neto 3559.05 MXN · ELECTRICO · GUADALAJARA_1 STATION 1 |
| Entrada de mercancía | Docto. material 5000527117 · Fecha contab. 16.12.2025 |
| Facturas ligadas | "Sin facturas ligadas." |

El Txt.brv de SAP dice "L-31 T-900", con un espacio, y la factura dice "L-31T-900". La regla OC-007 compara los textos sin espacios ni signos, así que el concepto sí corresponde a la partida.

---

# Durante la prueba

## 3. Registrar la factura solo con el PDF (Proveedora)

1. Cierra la sesión e inicia como `proveedor2@poc.local`.
2. **+ Nueva factura**, en el tablero o en **Facturas**.
3. **Paso 1 · Archivos**
   - **PDF de la factura (obligatorio):** `1-factura/CFDI-3668-GOHS60031745A.pdf`.
   - **XML del CFDI (opcional):** vacío.
   - Pulsa **Continuar a la revisión**.
4. **Paso 2 · Revisión.** A la izquierda, la imagen del PDF. A la derecha, "Datos tomados de: **Texto del PDF**" y los datos leídos. Compáralos con la imagen:

| Sección | Dato | Valor leído | Marca |
|---|---|---|---|
| Factura | Serie y folio | 3668 | |
| | UUID | A328F91A-DDDD-4624-89AC-877819F5B540 | ✓ XML-006 |
| | Fecha | 2026-01-03T14:24:46 (el periodo queda en 01/2026, el mes de emisión) | |
| | Tipo · Moneda | I · MXN | ✓ XML-007 |
| | Forma de pago · Método de pago | 99 · PPD | ✓ XML-004 · ✓ XML-003 |
| Proveedor | RFC | GOHS60031745A | ✓ PRV-001 |
| | Nombre | SOCORRO PATRICIA GONZALEZ HERNANDEZ | ✓ PRV-002 |
| | Régimen fiscal | 612 | ✓ PRV-003 |
| Cliente | RFC · Nombre | IME010718PU3 · INTERMODAL MEXICO | ✓ XML-002 · ✓ XML-009 |
| | Régimen · Uso de CFDI · Código postal | 601 · G03 · 11700 | ✓ XML-011 · ✓ XML-005 · ✓ XML-010 |
| Conceptos | Encabezado | "Orden de compra detectada: **25704872**" | |
| | Concepto 1 | 1.00 · H87 - PZ · L-31T-900 · LTH TIPO L-31T-900 AR BATERIA (OC/25704872) · $3,559.05 · 02 · $3,559.05 · IVA 002 0.160000: $569.45 | |
| Totales | Subtotal · IVA trasladado · Total | $3,559.05 · $569.45 · $4,128.50 | |

La factura queda en **Borrador**: falta el Vo.Bo.

**Qué decir:** la proveedora no capturó ningún dato. El portal leyó el PDF con la maqueta del documento de negocio: los RFC sin etiqueta, el bloque CLIENTE, los datos del timbre y el detalle del concepto. La orden de compra la tomó del concepto, "(OC/25704872)".

**Variante con IA** (portal con `AI_ENABLED=true` y `DOCUMENT_AI_PROVIDER=document_intelligence_openai`; README, "Lectura de la factura con IA"). Registra `1-factura/CFDI-3668-GOHS60031745A-escaneado.pdf`, que no tiene texto: sin IA da 422 y pide el XML. Con la IA se registra con los mismos datos de la tabla y la Revisión dice "Datos tomados de: **OCR + IA (Azure Document Intelligence + OpenAI)**", con el panel "Lectura con IA" (confianza baja del OCR en la Fecha). Con el PDF con texto, el panel además compara la lectura de la IA con la del texto y dice "Coincide con la lectura del texto del PDF.". El resto del flujo no cambia: la IA sólo lee, las reglas y el PMO deciden. El registro tarda unos 15 segundos.

## 4. Vo.Bo. y envío (Proveedora)

1. En la misma Revisión, en **Cargar o reemplazar un archivo**:
   - **Tipo de documento:** "Vo.Bo. del líder de proyecto".
   - Archivo: `1-factura/VoBo-3668-v1-orden-equivocada.pdf`. Pulsa **Cargar documento**.
   - **Archivos de la factura** cambia a "Archivos obligatorios completos".
2. **Paso 3 · Enviar a validación.**

**Resultado:** "Factura enviada a validación". El estatus pasa a **Enviada** y el detalle muestra **Orden de compra 25704872** con su partida. En la **Matriz de evidencia**, OC-001 a OC-012 salen en **PASS**.

Puede haber dos advertencias que no impiden el envío. DAT-001 sale si la factura se envía después del día 20 del mes. SUP-004 sale por la vigencia de los documentos del expediente demo.

**Qué decir:** la validación compara la factura con la orden de SAP: proveedor, montos, partida, cantidad, unidad, precio, entrada de mercancía y que la orden no tenga otra factura. El Vo.Bo. no lo lee: cita la orden **25704827**, con dos dígitos invertidos, y eso lo revisa el PMO.

## 5. Observaciones (PMO)

1. Cierra la sesión e inicia como `pmo@poc.local`.
2. **Facturas**, filtra por "Enviada" y abre la de número **3668**. Su folio interno, FAC-2026-xxxxx, aparece en el encabezado.
3. Revisa el panel **Orden de compra 25704872** y abre el Vo.Bo. en **Documentos**: cita la orden 25704827.
4. **Decidir** › en el texto de observaciones escribe:

   > El Vo.Bo. cita la orden de compra 25704827; la factura es de la 25704872. Adjunte el Vo.Bo. corregido.

   Pulsa **Observaciones**.

**Resultado:** estatus **Observaciones** y aviso a la proveedora.

## 6. Corrección y reenvío (Proveedora)

1. Inicia como `proveedor2@poc.local` y abre la factura 3668. Arriba aparece **Observaciones del PMO** con el texto del paso 5 y "Corrija lo indicado y vuelva a enviar la factura."
2. **Gestionar documentos** › **Tipo de documento** "Vo.Bo. del líder de proyecto" › `1-factura/VoBo-3668-v2-corregido.pdf` › **Cargar documento**. Reemplaza al anterior.
3. **Enviar a validación.**

**Resultado:** estatus **Enviada** otra vez. OC-012 sigue en PASS: la orden 25704872 ya está ligada a esta misma factura. En **Seguimiento** se ven el primer envío, las Observaciones y el reenvío.

## 7. Autorizar (PMO)

1. Inicia como `pmo@poc.local` y abre la factura 3668.
2. **Decidir** › **Autorizar** y confirma.

**Resultado:** estatus **Autorizada**. El aviso va a Recepción de Facturas con copia a la proveedora.

## 8. Marcar como pagada (Administrador)

1. Inicia como `admin@poc.local` y abre la factura 3668 desde **Facturas**.
2. **Marcar como pagada**. Marca "Confirmo que la factura 3668 fue pagada. Se notificará al proveedor." y pulsa **Marcar como pagada**.

**Resultado:** estatus **Pagada**. El panel **Complemento de pago** dice "Pendiente: adjúntelo antes del <fecha>", 72 horas después del pago. En **Seguimiento**, "Pagada" trae la fecha límite del complemento.

**Qué decir:** la factura es PPD, pago en parcialidades o diferido, así que la proveedora debe emitir su Complemento de Pago. El portal lo sabe aunque la factura se registró sin XML, porque el método de pago lo leyó del PDF. Mientras el complemento esté vencido, la proveedora no puede enviar facturas nuevas.

## 9. Complemento de pago (Proveedora)

1. Inicia como `proveedor2@poc.local` y abre la factura 3668. Pulsa **Adjuntar Complemento de Pago**.
2. **Tipo de documento** "Complemento de pago (XML)" › `2-pago/REP-P-3701-GOHS60031745A.xml` › **Cargar documento**.
3. **Tipo de documento** "Complemento de pago (PDF)" › `2-pago/REP-P-3701-GOHS60031745A.pdf` › **Cargar documento**.

**Resultado:** el panel **Complemento de pago** dice "Adjuntado el <fecha>" y **Seguimiento** agrega "Complemento de pago adjuntado". El aviso va a Recepción de Facturas.

El complemento es el P-3701: pago del 02/02/2026 por transferencia, $4,128.50 MXN, parcialidad 1 y saldo insoluto $0.00. El portal acepta el XML porque es un CFDI de tipo P y relaciona el UUID de la 3668. Rechaza un XML que no sea de tipo P o que no relacione ese UUID.

## 10. Cierre (PMO o Administrador)

**Órdenes de compra** › `25704872`. En **Facturas ligadas** aparece la factura: FAC-2026-xxxxx · 3668 · $4,128.50 MXN · **Pagada**.

---

## 11. Repetir o regenerar la prueba

- **Repetir.** El UUID de la factura es fijo, el número 3668 no se repite para la misma proveedora y la orden admite una sola factura vigente. Para repetir la prueba hay que reiniciar la base con `scripts/reset_demo.py` (sección 1).
- **Regenerar los documentos.** Hace falta `npm ci` en `tests/hu`, o `HU_DIR=<otra carpeta tests/hu con node_modules>`:

  ```bash
  node data/pruebas-factura-3668/_generador/generar.mjs
  ```

  Si cambias datos de la factura, cámbialos también en:
  - `EXAMPLE_3668` de `scripts/cfdi_demo.py`, que genera `data/demo_documents/factura_3668.pdf` y su XML;
  - la orden `EXAMPLE_ORDER` de `scripts/seed_db.py`;
  - este instructivo;
  - `tests/test_set_factura_3668.py`.

  Después, regenera la versión escaneada (sólo imagen) con PyMuPDF:

  ```bash
  python scripts/rasterize_pdf.py data/pruebas-factura-3668/1-factura/CFDI-3668-GOHS60031745A.pdf
  ```
- **Verificación automática.** `tests/test_set_factura_3668.py` recorre este instructivo con sus mismos archivos y valores. `tests/test_extraccion_factura.py` comprueba que del PDF salen los mismos datos que del XML de la 3668. Si fallan, el instructivo ya no describe lo que hace el portal:

  ```bash
  .venv/bin/python -m pytest tests/test_set_factura_3668.py tests/test_extraccion_factura.py --no-cov -q
  ```

  `tests/test_lectura_ia.py` recorre la variante con IA con Document Intelligence y OpenAI simulados, y `tests/test_integracion_ia.py`, con los servicios reales (`-m integration`; se salta sin llaves).
- **Video.** `tests/hu/video/recorrido-factura-3668.spec.ts` graba este mismo recorrido con Playwright en `evidencias/video/recorrido-factura-3668.webm`. Para grabarlo, reinicia la base (sección 1), deja el portal arrancado con los correos en archivos y ejecuta `npm run video-3668` en `tests/hu`. Al terminar, la factura ya quedó registrada: reinicia la base otra vez antes de la prueba manual.
