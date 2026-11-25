// Genera los documentos de data/pruebas-factura-3668: la factura 3668 del documento de negocio (HU-24) como PDF con
// texto, sus dos Vo.Bo. y el complemento de pago (XML y PDF). Los PDF se imprimen con el Chromium de Playwright de
// tests/hu (npm ci en tests/hu, o HU_DIR=<otro tests/hu con node_modules>).
//
//   node data/pruebas-factura-3668/_generador/generar.mjs
//
// La factura reproduce la representación impresa del ejemplo con su maqueta: RFC sin etiqueta, bloque CLIENTE,
// columna de datos del timbre, renglón del concepto con su detalle debajo, importe con letra, totales y sellos. Los
// sellos son de prueba y no hay código QR. Sus datos son los de EXAMPLE_3668 en scripts/cfdi_demo.py, y la orden que
// cita (25704872) la siembra scripts/seed_db.py (EXAMPLE_ORDER). Si cambias algo aquí, cámbialo también allá, en
// INSTRUCTIVO.md y en tests/test_set_factura_3668.py.
import { mkdirSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const AQUI = dirname(fileURLToPath(import.meta.url));
const SALIDA = join(AQUI, '..');
const HU_DIR = process.env.HU_DIR ?? join(AQUI, '../../../tests/hu');

const EMISOR = {
  nombre: 'SOCORRO PATRICIA GONZALEZ HERNANDEZ',
  rfc: 'GOHS60031745A',
  regimen: '612',
  regimenNombre: 'Personas Físicas con Actividades Empresariales y Profesionales',
  domicilio: 'BLVD. RAUL BAILLERES, 3, ZONA CENTRO, 36100, SILAO, Guanajuato, México',
  telefono: 'Tel. 01 (472) 722 32 61',
  cp: '36100',
};

// Configuración inicial de Reglas de Validación (XML-002, XML-009, XML-010 y XML-011, HU-24 P-01).
const RECEPTOR = {
  rfc: 'IME010718PU3',
  nombre: 'INTERMODAL MEXICO',
  cp: '11700',
  regimen: '601',
  regimenNombre: 'General de Ley Personas Morales',
  domicilio: 'BOSQUE DE CIRUELOS #99, Bosque de las Lomas, 11700, Ciudad de México, Miguel Hidalgo, Ciudad de México, México',
};

const ORDEN = 25704872;

const FACTURA = {
  folio: '3668',
  uuid: 'A328F91A-DDDD-4624-89AC-877819F5B540',
  emision: '2026-01-03T14:24:46',
  certificacion: '2026-01-03T14:36:54',
  certificadoSat: '00001000000711762511',
  certificadoEmisor: '00001000000512000612',
  rfcPac: 'STA0903206B9',
  concepto: {
    cantidad: '1.00',
    unidad: 'H87 - PZ',
    identificacion: 'L-31T-900',
    descripcion: `LTH TIPO L-31T-900 AR BATERIA (OC/${ORDEN})`,
    claveProdServ: '26111707 Baterías de plomo-ácido',
    precio: 3559.05,
  },
  subtotal: 3559.05,
  iva: 569.45,
  total: 4128.5,
  letra: 'CUATRO MIL CIENTO VEINTIOCHO PESOS, 50/100 MXN',
};

// Complemento de pago que liquida la factura (Pagos 2.0). Lo emite la proveedora; ficticio y sin timbrar.
const PAGO = {
  serie: 'P',
  folio: '3701',
  uuid: '6B0E2C47-91D3-4A8F-B5E6-3C8D17A92F40',
  emision: '2026-02-04T10:12:08',
  fechaPago: '2026-02-02T12:00:00',
  forma: '03',
  formaNombre: 'Transferencia electrónica de fondos',
};

// Vo.Bo. del líder de proyecto. El primero cita la orden con dos dígitos invertidos: lo detecta el PMO.
const PROYECTO = { nombre: 'Mantenimiento eléctrico de locomotoras · Estación Guadalajara', lider: 'Ing. Marco Antonio Ruelas Ibarra' };
const VOBOS = [
  { archivo: 'VoBo-3668-v1-orden-equivocada.pdf', orden: 25704827, fecha: '2026-01-05', folio: 'VOBO-2026-0031' },
  { archivo: 'VoBo-3668-v2-corregido.pdf', orden: ORDEN, fecha: '2026-01-07', folio: 'VOBO-2026-0034' },
];

const fix = (n) => n.toFixed(2);
const pesos = (n) => '$ ' + n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const numero = `${PAGO.serie}-${PAGO.folio}`;

// Texto que ocupa el lugar de un sello digital: deja ver la maqueta sin parecer un sello real.
const sello = (n) => Array(n).fill('SELLO-DE-PRUEBA-SIN-VALIDEZ-FISCAL').join('+') + '==';

// ---------------------------------------------------------------- Factura 3668 (representación impresa)

const CSS_CFDI = `
@page { size: Letter; margin: 12mm 11mm; }
* { box-sizing: border-box; }
body { font-family: Arial, Helvetica, sans-serif; font-size: 7.4pt; color: #000; margin: 0; }
.top { display: flex; gap: 10px; }
.logo { width: 118px; height: 82px; border: 1px solid #ddd; background: #f6f6f6; flex: none; }
.centro { flex: 1; text-align: center; line-height: 1.35; }
.centro .nombre { font-size: 11pt; font-weight: bold; white-space: nowrap; }
.centro .cliente { font-size: 10pt; font-weight: bold; margin-top: 8px; }
.timbre { width: 236px; flex: none; text-align: right; line-height: 1.3; }
.timbre .factura { font-size: 11pt; font-weight: bold; }
.timbre .k { font-weight: bold; }
.barra { background: #000; color: #fff; text-align: center; font-weight: bold; padding: 2px; margin-top: 24px; }
table { width: 100%; border-collapse: collapse; }
.conceptos th { background: #000; color: #fff; font-weight: normal; padding: 2px 4px; text-align: left; }
.conceptos td { padding: 3px 4px; vertical-align: top; }
.conceptos .num { text-align: right; white-space: nowrap; }
.conceptos .detalle { padding-top: 0; line-height: 1.35; }
.pie { display: flex; justify-content: space-between; margin-top: 150px; }
.pie table td { padding: 2px 4px; vertical-align: top; }
.pie .k { font-weight: bold; width: 150px; }
.pie .totales { width: 240px; align-self: flex-start; }
.pie .totales td { text-align: right; }
.pie .totales .total { font-weight: bold; }
.sellos { display: flex; gap: 12px; margin-top: 18px; }
.qr { width: 112px; height: 112px; flex: none; border: 1px dashed #999; color: #777; font-size: 6.5pt;
  display: flex; align-items: center; justify-content: center; text-align: center; padding: 8px; }
.sellos .k { font-weight: bold; margin-top: 4px; }
.sellos .v { font-size: 6pt; word-break: break-all; line-height: 1.25; }
.aviso { border-top: 1px solid #999; margin-top: 10px; padding-top: 3px; font-size: 6.5pt; color: #555; text-align: center; }
`;

function pdfFactura() {
  const c = FACTURA.concepto;
  const cadena = `||1.1|${FACTURA.uuid}|${FACTURA.certificacion}|${FACTURA.rfcPac}|${sello(2)}|${FACTURA.certificadoSat}||`;
  return `<!doctype html><html lang="es"><head><meta charset="utf-8"><title>Factura ${FACTURA.folio}</title><style>${CSS_CFDI}</style></head><body>
<div class="top">
  <div class="logo"></div>
  <div class="centro">
    <div class="nombre">${EMISOR.nombre}</div>
    <div>${EMISOR.rfc}</div>
    <div>RÉGIMEN FISCAL: ${EMISOR.regimen} - ${EMISOR.regimenNombre}</div>
    <div>${EMISOR.domicilio}</div>
    <div>${EMISOR.telefono}</div>
    <div class="cliente">CLIENTE</div>
    <div>${RECEPTOR.nombre}</div>
    <div>${RECEPTOR.rfc}</div>
    <div>USO CFDI: G03 - Gastos en general.</div>
    <div>DOMICILIO FISCAL: ${RECEPTOR.cp}</div>
    <div>REGIMEN FISCAL: ${RECEPTOR.regimen} - ${RECEPTOR.regimenNombre}</div>
    <div>${esc(RECEPTOR.domicilio)}</div>
  </div>
  <div class="timbre">
    <div class="factura">Factura ${FACTURA.folio}</div>
    <div class="k">FOLIO FISCAL (UUID)</div><div>${FACTURA.uuid}</div>
    <div class="k">NO. DE SERIE DEL CERTIFICADO DEL SAT</div><div>${FACTURA.certificadoSat}</div>
    <div class="k">NO. DE SERIE DEL CERTIFICADO DEL EMISOR</div><div>${FACTURA.certificadoEmisor}</div>
    <div class="k">FECHA Y HORA DE CERTIFICACIÓN</div><div>${FACTURA.certificacion}</div>
    <div class="k">RFC PROVEEDOR DE CERTIFICACIÓN</div><div>${FACTURA.rfcPac}</div>
    <div class="k">FECHA Y HORA DE EMISIÓN DE CFDI</div><div>${FACTURA.emision}</div>
    <div class="k">LUGAR DE EXPEDICIÓN</div><div>${EMISOR.cp}</div>
  </div>
</div>
<div class="barra">CONCEPTOS</div>
<table class="conceptos">
  <tr><th>Cantidad</th><th>Unidad</th><th>No. Identificación</th><th>Descripción</th><th class="num">Precio Unitario</th><th>Objeto Imp.</th><th class="num">Importe</th></tr>
  <tr><td>${c.cantidad}</td><td>${c.unidad}</td><td>${c.identificacion}</td><td>${esc(c.descripcion)}</td>
    <td class="num">${pesos(c.precio)}</td><td>02 - Sí objeto de impuesto.</td><td class="num">${pesos(c.precio)}</td></tr>
  <tr><td colspan="3"></td><td colspan="4" class="detalle">Clave Prod. Serv. - ${c.claveProdServ}<br>No. Identificación - ${c.identificacion}<br>
    Impuestos:<br>Traslados:<br>002 IVA Base - ${fix(c.precio)} Tasa - 0.160000 Importe - ${pesos(FACTURA.iva)}</td></tr>
</table>
<div class="pie">
  <table style="width:auto">
    <tr><td class="k">IMPORTE CON LETRA</td><td>${FACTURA.letra}</td></tr>
    <tr><td>&nbsp;</td><td></td></tr>
    <tr><td class="k">TIPO DE COMPROBANTE</td><td>I - Ingreso</td></tr>
    <tr><td class="k">FORMA DE PAGO</td><td>99 - Por definir</td></tr>
    <tr><td class="k">MÉTODO DE PAGO</td><td>PPD - Pago en parcialidades o diferido</td></tr>
    <tr><td class="k">MONEDA</td><td>MXN - Peso Mexicano</td></tr>
    <tr><td class="k">VERSION</td><td>4.0</td></tr>
    <tr><td class="k">EXPORTACION</td><td>01 - No aplica</td></tr>
  </table>
  <table class="totales">
    <tr><td>SUBTOTAL</td><td>${pesos(FACTURA.subtotal)}</td></tr>
    <tr><td>TRASLADO IVA TASA 0.160000</td><td>${pesos(FACTURA.iva)}</td></tr>
    <tr class="total"><td>TOTAL</td><td>${pesos(FACTURA.total)}</td></tr>
  </table>
</div>
<div class="sellos">
  <div class="qr">Código QR omitido: documento de prueba</div>
  <div>
    <div class="k">SELLO DIGITAL DEL CFDI</div><div class="v">${sello(4)}</div>
    <div class="k">SELLO DIGITAL DEL SAT</div><div class="v">${sello(4)}</div>
    <div class="k">CADENA ORIGINAL DEL COMPLEMENTO DE CERTIFICACIÓN DIGITAL DEL SAT</div><div class="v">${cadena}</div>
  </div>
</div>
<div class="aviso">Reproducción de la factura ${FACTURA.folio} para pruebas del Portal de Proveedores FERROMEX. Documento ficticio, sin validez fiscal.</div>
</body></html>`;
}

// ---------------------------------------------------------------- Vo.Bo. y complemento de pago

const CSS = `
@page { size: Letter; margin: 16mm 15mm; }
* { box-sizing: border-box; }
body { font-family: Arial, Helvetica, sans-serif; font-size: 9pt; color: #1d1d1f; margin: 0; }
.head { display: flex; justify-content: space-between; align-items: flex-end; border-bottom: 2px solid #7a2e1f;
  padding-bottom: 7px; margin-bottom: 14px; }
.head h1 { font-size: 15pt; margin: 0 0 3px; }
.head .sub { font-size: 7.5pt; color: #555; line-height: 1.45; }
.head .meta { text-align: right; font-size: 7.5pt; color: #333; line-height: 1.5; }
h2 { background: #7a2e1f; color: #fff; font-size: 7pt; font-weight: bold; padding: 4px 6px; margin: 14px 0 6px; }
table { width: 100%; border-collapse: collapse; }
td, th { border: 1px solid #cfc8c4; padding: 4px 6px; vertical-align: top; text-align: left; }
th, td.k { background: #f1ebe8; font-weight: bold; }
td.k { width: 17%; }
.num { text-align: right; white-space: nowrap; }
table.totals { width: 44%; margin-left: auto; }
table.totals td.k { width: 60%; }
p { line-height: 1.5; margin: 6px 0; }
.small { font-size: 7pt; color: #555; }
.prueba { border: 1px dashed #c0392b; color: #c0392b; text-align: center; font-weight: bold; font-size: 7pt;
  padding: 4px; margin-top: 16px; }
.firmas { display: flex; justify-content: space-around; margin-top: 56px; text-align: center; font-size: 8pt; }
.firma { width: 34%; border-top: 1px solid #333; padding-top: 4px; }
.firma small { display: block; color: #555; }
`;

function pagina({ titulo, sub = [], meta = [], cuerpo }) {
  return `<!doctype html><html lang="es"><head><meta charset="utf-8"><title>${esc(titulo)}</title><style>${CSS}</style></head>
<body><div class="head"><div><h1>${titulo}</h1><div class="sub">${sub.join('<br>')}</div></div>
<div class="meta">${meta.join('<br>')}</div></div>${cuerpo}
<div class="prueba">DOCUMENTO DE PRUEBA PARA DEMOSTRACIÓN · SIN VALIDEZ OFICIAL</div></body></html>`;
}

function kv(pares, porRenglon = 2) {
  const filas = [];
  for (let i = 0; i < pares.length; i += porRenglon) {
    const grupo = pares.slice(i, i + porRenglon);
    const celdas = grupo.map(([k, v]) => `<td class="k">${k}</td><td>${v}</td>`).join('');
    const faltan = porRenglon - grupo.length;
    filas.push(`<tr>${celdas}${faltan ? `<td colspan="${faltan * 2}" style="border:none"></td>` : ''}</tr>`);
  }
  return `<table>${filas.join('')}</table>`;
}

function pdfVobo(v) {
  return pagina({
    titulo: RECEPTOR.nombre,
    sub: ['Visto Bueno del Líder de Proyecto'],
    meta: [`Fecha: ${v.fecha}`, `Folio: ${v.folio}`],
    cuerpo: `<h2>Referencia</h2>${kv([
      ['Proyecto', PROYECTO.nombre],
      ['Proveedor', EMISOR.nombre],
      ['RFC', EMISOR.rfc],
      ['Orden de compra', v.orden],
      ['Factura', FACTURA.folio],
      ['UUID', FACTURA.uuid],
      ['Subtotal', `${pesos(FACTURA.subtotal)} MXN`],
      ['Total', `${pesos(FACTURA.total)} MXN`],
    ])}
<h2>Dictamen</h2><p>Por medio del presente, como líder del proyecto <b>${PROYECTO.nombre}</b>, hago constar que el suministro de la
orden de compra <b>${v.orden}</b> fue recibido a entera satisfacción en el almacén GUADALAJARA_1 STATION 1, por lo que otorgo
mi <b>Visto Bueno</b> para el trámite de pago de la factura arriba referida.</p>
${kv(
  [
    ['Suministro revisado', '1 pieza · LTH TIPO L-31T-900 AR BATERIA (No. de identificación L-31T-900)'],
    ['Entrada de mercancía', 'Documento de material 5000527117 del 16.12.2025'],
    ['Resultado', '<b>APROBADO</b>'],
  ],
  1,
)}
<div class="firmas"><div class="firma">${PROYECTO.lider}<small>Líder de proyecto FERROMEX</small></div></div>`,
  });
}

function cfdiPago() {
  const sub = fix(FACTURA.subtotal);
  const imp = fix(FACTURA.iva);
  const tot = fix(FACTURA.total);
  return `<?xml version="1.0" encoding="UTF-8"?>
<!-- DOCUMENTO FICTICIO PARA PRUEBAS. NO ES UN CFDI TIMBRADO VALIDO. -->
<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" xmlns:pago20="http://www.sat.gob.mx/Pagos20" xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://www.sat.gob.mx/cfd/4 http://www.sat.gob.mx/sitio_internet/cfd/4/cfdv40.xsd http://www.sat.gob.mx/Pagos20 http://www.sat.gob.mx/sitio_internet/cfd/Pagos/Pagos20.xsd" Version="4.0" Serie="${PAGO.serie}" Folio="${PAGO.folio}" Fecha="${PAGO.emision}" SubTotal="0" Moneda="XXX" Total="0" TipoDeComprobante="P" Exportacion="01" LugarExpedicion="${EMISOR.cp}" NoCertificado="00001000000500000001" Certificado="" Sello="">
  <cfdi:Emisor Rfc="${EMISOR.rfc}" Nombre="${EMISOR.nombre}" RegimenFiscal="${EMISOR.regimen}"/>
  <cfdi:Receptor Rfc="${RECEPTOR.rfc}" Nombre="${RECEPTOR.nombre}" DomicilioFiscalReceptor="${RECEPTOR.cp}" RegimenFiscalReceptor="${RECEPTOR.regimen}" UsoCFDI="CP01"/>
  <cfdi:Conceptos>
    <cfdi:Concepto ClaveProdServ="84111506" Cantidad="1" ClaveUnidad="ACT" Descripcion="Pago" ValorUnitario="0" Importe="0" ObjetoImp="01"/>
  </cfdi:Conceptos>
  <cfdi:Complemento>
    <pago20:Pagos Version="2.0">
      <pago20:Totales TotalTrasladosBaseIVA16="${sub}" TotalTrasladosImpuestoIVA16="${imp}" MontoTotalPagos="${tot}"/>
      <pago20:Pago FechaPago="${PAGO.fechaPago}" FormaDePagoP="${PAGO.forma}" MonedaP="MXN" TipoCambioP="1" Monto="${tot}">
        <pago20:DoctoRelacionado IdDocumento="${FACTURA.uuid}" Folio="${FACTURA.folio}" MonedaDR="MXN" EquivalenciaDR="1" NumParcialidad="1" ImpSaldoAnt="${tot}" ImpPagado="${tot}" ImpSaldoInsoluto="0.00" ObjetoImpDR="02">
          <pago20:ImpuestosDR><pago20:TrasladosDR><pago20:TrasladoDR BaseDR="${sub}" ImpuestoDR="002" TipoFactorDR="Tasa" TasaOCuotaDR="0.160000" ImporteDR="${imp}"/></pago20:TrasladosDR></pago20:ImpuestosDR>
        </pago20:DoctoRelacionado>
        <pago20:ImpuestosP><pago20:TrasladosP><pago20:TrasladoP BaseP="${sub}" ImpuestoP="002" TipoFactorP="Tasa" TasaOCuotaP="0.160000" ImporteP="${imp}"/></pago20:TrasladosP></pago20:ImpuestosP>
      </pago20:Pago>
    </pago20:Pagos>
    <tfd:TimbreFiscalDigital Version="1.1" UUID="${PAGO.uuid}" FechaTimbrado="${PAGO.emision.replace(/:\d{2}$/, ':41')}" RfcProvCertif="SAT970701NN3" SelloCFD="" NoCertificadoSAT="00001000000500000002" SelloSAT=""/>
  </cfdi:Complemento>
</cfdi:Comprobante>
`;
}

function pdfPago() {
  return pagina({
    titulo: EMISOR.nombre,
    sub: [`RFC: ${EMISOR.rfc}`, `Régimen fiscal: ${EMISOR.regimen} - ${EMISOR.regimenNombre}`, `Lugar de expedición: ${EMISOR.cp}`],
    meta: [`<b>COMPLEMENTO DE PAGO ${numero}</b>`, 'CFDI 4.0 · Pagos 2.0', `Fecha de emisión: ${PAGO.emision}`, 'Tipo: P - Pago'],
    cuerpo: `<h2>Receptor</h2>${kv([
      ['RFC', RECEPTOR.rfc],
      ['Nombre', RECEPTOR.nombre],
      ['Domicilio fiscal', RECEPTOR.cp],
      ['Régimen fiscal', `${RECEPTOR.regimen} - ${RECEPTOR.regimenNombre}`],
      ['Uso CFDI', 'CP01 - Pagos'],
    ])}
<h2>Pago</h2>${kv([
      ['Fecha de pago', PAGO.fechaPago],
      ['Forma de pago', `${PAGO.forma} - ${PAGO.formaNombre}`],
      ['Moneda', 'MXN'],
      ['Monto', `${pesos(FACTURA.total)} MXN`],
    ])}
<h2>Documento relacionado</h2><table><tr><th>UUID</th><th>Folio</th><th>Parcialidad</th><th class="num">Saldo anterior</th><th class="num">Importe pagado</th><th class="num">Saldo insoluto</th></tr>
<tr><td>${FACTURA.uuid}</td><td>${FACTURA.folio}</td><td>1</td><td class="num">${pesos(FACTURA.total)}</td><td class="num">${pesos(FACTURA.total)}</td><td class="num">$ 0.00</td></tr></table>
<h2>Timbre fiscal digital</h2>${kv(
      [
        ['Folio fiscal (UUID)', PAGO.uuid],
        ['RFC PAC', 'SAT970701NN3'],
      ],
      1,
    )}<p class="small">Representación impresa de un CFDI de pago. Documento de prueba sin sellos digitales válidos.</p>`,
  });
}

// ---------------------------------------------------------------- Salida

const XMLS = { [join('2-pago', `REP-${numero}-${EMISOR.rfc}.xml`)]: cfdiPago() };
const PDFS = {
  [join('1-factura', `CFDI-${FACTURA.folio}-${EMISOR.rfc}.pdf`)]: pdfFactura(),
  ...Object.fromEntries(VOBOS.map((v) => [join('1-factura', v.archivo), pdfVobo(v)])),
  [join('2-pago', `REP-${numero}-${EMISOR.rfc}.pdf`)]: pdfPago(),
};

for (const [ruta, contenido] of Object.entries(XMLS)) {
  mkdirSync(dirname(join(SALIDA, ruta)), { recursive: true });
  writeFileSync(join(SALIDA, ruta), contenido, 'utf8');
  console.log('xml ', ruta);
}

const { chromium } = createRequire(join(HU_DIR, 'package.json'))('@playwright/test');
const navegador = await chromium.launch();
try {
  const tab = await navegador.newPage();
  for (const [ruta, html] of Object.entries(PDFS)) {
    mkdirSync(dirname(join(SALIDA, ruta)), { recursive: true });
    await tab.setContent(html, { waitUntil: 'load' });
    await tab.pdf({ path: join(SALIDA, ruta), format: 'Letter', printBackground: true, preferCSSPageSize: true });
    console.log('pdf ', ruta);
  }
} finally {
  await navegador.close();
}
