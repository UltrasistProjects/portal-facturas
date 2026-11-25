// Genera los documentos de data/pruebas-pdf-orden-compra: expediente del proveedor, factura de cada caso (PDF del
// CFDI y Vo.Bo.) y, para el caso del PDF escaneado, su imagen sin texto y su XML. Los PDF se imprimen con el Chromium
// de Playwright de tests/hu (npm ci en tests/hu, o HU_DIR=<otro tests/hu con node_modules>).
//
//   node data/pruebas-pdf-orden-compra/_generador/generar.mjs
//
// Las órdenes de compra que citan las facturas las siembra scripts/seed_db.py (PDF_TEST_ORDERS): si cambias montos,
// partidas o textos aquí, cámbialos también allá, en INSTRUCTIVO.md y en tests/test_set_pdf_orden_compra.py.
// RECEPTOR copia la configuración inicial de Reglas de Validación (XML-002, XML-009, XML-010 y XML-011, HU-24 P-01).
// Los PDF del CFDI usan las etiquetas de la representación impresa que lee el portal (sección 6.3 de la HU-24).
import { mkdirSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const AQUI = dirname(fileURLToPath(import.meta.url));
const SALIDA = join(AQUI, '..');
const HU_DIR = process.env.HU_DIR ?? join(AQUI, '../../../tests/hu');

const RECEPTOR = {
  rfc: 'IME010718PU3',
  nombre: 'INTERMODAL MEXICO',
  cp: '11700',
  regimen: '601',
  regimenNombre: 'General de Ley Personas Morales',
  usoCfdi: 'G03',
  usoCfdiNombre: 'Gastos en general',
};

// Cliente equivocado del caso 7: empresa ficticia.
const OTRO_RECEPTOR = {
  ...RECEPTOR,
  rfc: 'LIP101010AB1',
  nombre: 'LOGISTICA INTEGRAL DEL PACIFICO',
  cp: '82000',
};

const PROVEEDOR = {
  nombre: 'Mantenimiento Ferroviario del Bajío',
  nombreCfdi: 'MANTENIMIENTO FERROVIARIO DEL BAJIO',
  regimenCapital: 'SOCIEDAD ANONIMA DE CAPITAL VARIABLE',
  rfc: 'MFB140325AB1',
  regimen: '601',
  regimenNombre: 'General de Ley Personas Morales',
  constitucion: '2014-03-25',
  domicilio: 'Av. 5 de Febrero 1530, Zona Industrial Benito Juárez, Querétaro, Qro., C.P. 76120',
  cp: '76120',
  banco: 'Banco Demo, S.A.',
  cuenta: '0213458790',
  clabe: '000680002134587906',
  sucursal: '0680 Querétaro Industrial',
  representante: 'Arturo Villaseñor Pacheco',
  curpRepresentante: 'VIPA750812HQTLCR04',
  domicilioRepresentante: 'Calle Hacienda El Jacal 214, Col. Jardines de la Hacienda, Querétaro, Qro., C.P. 76180',
};

const PROYECTO = { nombre: 'Mantenimiento de equipo ferroviario · Patio Querétaro', lider: 'Ing. Daniela Ochoa Ramírez' };

const servicio = (descripcion, importe) => ({ clave: '78181500', cantidad: 1, unidad: 'E48', unidadNombre: 'Servicio', descripcion, precio: importe });
const pieza = (descripcion, cantidad, precio) => ({ clave: '25171700', cantidad, unidad: 'H87', unidadNombre: 'Pieza', descripcion, precio });

const CONCEPTOS_CORRECTA = [
  servicio('Mantenimiento preventivo locomotora GE AC4400, unidad económica 4512, servicio de 92 días (OC/45000611)', 85000),
  pieza('Zapata de freno composite para carro tolva (OC/45000611)', 40, 950),
];

// Un caso por carpeta. `oc` es la orden que cita el concepto (null si no cita ninguna).
const FACTURAS = [
  {
    carpeta: '1-factura-correcta',
    folio: '2101',
    fecha: '2026-11-20T10:15:00',
    oc: 45000611,
    conceptos: CONCEPTOS_CORRECTA,
    letra: 'CIENTO CUARENTA Y DOS MIL SEISCIENTOS OCHENTA PESOS 00/100 M.N.',
    uuid: '2489226A-7C76-42A4-91B5-92A3D419F8CC',
  },
  {
    carpeta: '2-monto-distinto',
    folio: '2102',
    fecha: '2026-11-20T11:00:00',
    oc: 45000612,
    conceptos: [servicio('Revisión sistema de frenos de aire en 6 locomotoras, patio Querétaro (OC/45000612)', 68500)],
    letra: 'SETENTA Y NUEVE MIL CUATROCIENTOS SESENTA PESOS 00/100 M.N.',
    uuid: '291A16BB-6679-4464-82A4-E49E9A43B3BE',
  },
  {
    carpeta: '3-sin-entrada-de-mercancia',
    folio: '2103',
    fecha: '2026-11-20T11:40:00',
    oc: 45000613,
    conceptos: [pieza('Rodamiento para eje de carro tolva, tipo AP clase K (OC/45000613)', 8, 4200)],
    letra: 'TREINTA Y OCHO MIL NOVECIENTOS SETENTA Y SEIS PESOS 00/100 M.N.',
    uuid: 'A46DB604-8A69-488A-B857-6F3234811779',
  },
  {
    carpeta: '4-orden-ya-facturada',
    folio: '2104',
    fecha: '2026-11-21T09:20:00',
    oc: 45000611,
    conceptos: CONCEPTOS_CORRECTA,
    letra: 'CIENTO CUARENTA Y DOS MIL SEISCIENTOS OCHENTA PESOS 00/100 M.N.',
    uuid: 'EF1EDF67-96A8-4D8A-8E8C-F570681C4A88',
  },
  {
    carpeta: '5-orden-de-otro-proveedor',
    folio: '2105',
    fecha: '2026-11-21T10:05:00',
    oc: 45000451,
    conceptos: [servicio('Inspección de vía, tramo Querétaro - Celaya (OC/45000451)', 45000)],
    letra: 'CINCUENTA Y DOS MIL DOSCIENTOS PESOS 00/100 M.N.',
    uuid: 'F6F84FBE-A1F5-4512-B800-DAF2283D28FA',
  },
  {
    carpeta: '6-sin-orden-en-el-concepto',
    folio: '2106',
    fecha: '2026-11-21T10:50:00',
    oc: null,
    ocVobo: 45000616,
    conceptos: [servicio('Mantenimiento correctivo locomotora GE AC4400, unidad económica 4517, cambio de compresor', 38000)],
    letra: 'CUARENTA Y CUATRO MIL OCHENTA PESOS 00/100 M.N.',
    uuid: 'ACA9A163-845C-437A-8101-9B015C628811',
  },
  {
    carpeta: '7-receptor-incorrecto',
    folio: '2107',
    fecha: '2026-11-21T12:30:00',
    oc: 45000614,
    receptor: OTRO_RECEPTOR,
    conceptos: [servicio('Inspección ultrasónica de ruedas, 24 juegos de carro tolva (OC/45000614)', 42000)],
    letra: 'CUARENTA Y OCHO MIL SETECIENTOS VEINTE PESOS 00/100 M.N.',
    uuid: 'A0572ACC-9141-40F9-88F7-1114ABDB1C08',
  },
  {
    carpeta: '8-pdf-escaneado',
    folio: '2108',
    fecha: '2026-11-22T09:10:00',
    oc: 45000615,
    escaneado: true,
    conceptos: [servicio('Calibración de báscula de vía, patio Querétaro, certificado 2026-118 (OC/45000615)', 27500)],
    letra: 'TREINTA Y UN MIL NOVECIENTOS PESOS 00/100 M.N.',
    uuid: '2FD32E72-C1D6-4B5A-B53D-460431DBF574',
  },
];

const DOC_FECHAS = {
  acta: '2014-03-25',
  poder: '2019-06-14',
  constancia: '2026-11-16',
  identificacion: '2023-05-10',
  domicilioRepresentante: '2026-11-03',
  domicilio: '2026-11-05',
  estadoCuenta: '2026-10-31',
};

const centavos = (n) => Math.round(n * 100) / 100;
const importe = (c) => centavos(c.cantidad * c.precio);
const subtotal = (f) => centavos(f.conceptos.reduce((s, c) => s + importe(c), 0));
const iva = (n) => Math.round(n * 16) / 100;
const total = (f) => centavos(subtotal(f) + iva(subtotal(f)));
const fix = (n) => n.toFixed(2);
const money = (n) => '$' + n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const numero = (f) => `F-${f.folio}`;
const timbrado = (f) => f.fecha.replace(/:(\d{2}):00$/, (_, m) => `:${String(Number(m) + 4).padStart(2, '0')}:00`);
const receptorDe = (f) => f.receptor ?? RECEPTOR;

// ---------------------------------------------------------------- XML (solo el caso del PDF escaneado)

function cfdiIngreso(f) {
  const r = receptorDe(f);
  const conceptos = f.conceptos
    .map((c) => {
      const base = fix(importe(c));
      return `        <cfdi:Concepto ClaveProdServ="${c.clave}" Cantidad="${c.cantidad}" ClaveUnidad="${c.unidad}" Unidad="${c.unidadNombre}" Descripcion="${esc(c.descripcion)}" ValorUnitario="${fix(c.precio)}" Importe="${base}" ObjetoImp="02">
            <cfdi:Impuestos>
                <cfdi:Traslados>
                    <cfdi:Traslado Base="${base}" Impuesto="002" TipoFactor="Tasa" TasaOCuota="0.160000" Importe="${fix(iva(importe(c)))}"/>
                </cfdi:Traslados>
            </cfdi:Impuestos>
        </cfdi:Concepto>`;
    })
    .join('\n');
  const sub = fix(subtotal(f));
  const imp = fix(iva(subtotal(f)));
  return `<?xml version="1.0" encoding="UTF-8"?>
<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://www.sat.gob.mx/cfd/4 http://www.sat.gob.mx/sitio_internet/cfd/4/cfdv40.xsd" Version="4.0" Serie="F" Folio="${f.folio}" Fecha="${f.fecha}" FormaPago="99" MetodoPago="PPD" SubTotal="${sub}" Moneda="MXN" Total="${fix(total(f))}" TipoDeComprobante="I" Exportacion="01" LugarExpedicion="${PROVEEDOR.cp}" NoCertificado="00001000000500000001" Certificado="" Sello="">
    <cfdi:Emisor Rfc="${PROVEEDOR.rfc}" Nombre="${PROVEEDOR.nombreCfdi}" RegimenFiscal="${PROVEEDOR.regimen}"/>
    <cfdi:Receptor Rfc="${r.rfc}" Nombre="${esc(r.nombre)}" DomicilioFiscalReceptor="${r.cp}" RegimenFiscalReceptor="${r.regimen}" UsoCFDI="${r.usoCfdi}"/>
    <cfdi:Conceptos>
${conceptos}
    </cfdi:Conceptos>
    <cfdi:Impuestos TotalImpuestosTrasladados="${imp}">
        <cfdi:Traslados>
            <cfdi:Traslado Base="${sub}" Impuesto="002" TipoFactor="Tasa" TasaOCuota="0.160000" Importe="${imp}"/>
        </cfdi:Traslados>
    </cfdi:Impuestos>
    <cfdi:Complemento>
        <tfd:TimbreFiscalDigital Version="1.1" UUID="${f.uuid}" FechaTimbrado="${timbrado(f)}" RfcProvCertif="SAT970701NN3" SelloCFD="" NoCertificadoSAT="00001000000500000002" SelloSAT=""/>
    </cfdi:Complemento>
</cfdi:Comprobante>
`;
}

// ---------------------------------------------------------------- HTML

const CSS = `
@page { size: Letter; margin: 16mm 15mm; }
* { box-sizing: border-box; }
body { font-family: Arial, Helvetica, sans-serif; font-size: 9pt; color: #1d1d1f; margin: 0; }
.head { display: flex; justify-content: space-between; align-items: flex-end; border-bottom: 2px solid #7a2e1f;
  padding-bottom: 7px; margin-bottom: 14px; }
.head h1 { font-size: 15pt; margin: 0 0 3px; }
.head .sub { font-size: 7.5pt; color: #555; line-height: 1.45; }
.head .meta { text-align: right; font-size: 7.5pt; color: #333; line-height: 1.5; }
.head .meta b { color: #1d1d1f; }
table + p { margin-top: 10px; }
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

const AVISO = '<div class="prueba">DOCUMENTO DE PRUEBA PARA DEMOSTRACIÓN · SIN VALIDEZ OFICIAL</div>';

function pagina({ titulo, sub = [], meta = [], cuerpo, aviso = true }) {
  return `<!doctype html><html lang="es"><head><meta charset="utf-8"><title>${esc(titulo)}</title><style>${CSS}</style></head>
<body><div class="head"><div><h1>${titulo}</h1><div class="sub">${sub.join('<br>')}</div></div>
<div class="meta">${meta.join('<br>')}</div></div>${cuerpo}${aviso ? AVISO : ''}</body></html>`;
}

// Tabla de pares clave/valor, dos pares por renglón.
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

const firmas = (...personas) =>
  `<div class="firmas">${personas.map(([n, r]) => `<div class="firma">${n}<small>${r}</small></div>`).join('')}</div>`;

const timbre = (f) =>
  `<h2>Timbre fiscal digital</h2>${kv(
    [
      ['Folio fiscal (UUID)', f.uuid],
      ['Fecha de timbrado', timbrado(f)],
      ['No. certificado emisor', '00001000000500000001'],
      ['No. certificado SAT', '00001000000500000002'],
      ['RFC PAC', 'SAT970701NN3'],
    ],
    1,
  )}<p class="small">Este documento es una representación impresa de un CFDI. Documento de prueba sin sellos digitales válidos.</p>`;

function pdfCfdi(f) {
  const r = receptorDe(f);
  const filas = f.conceptos
    .map(
      (c) =>
        `<tr><td>${c.clave}</td><td>${c.cantidad}</td><td>${c.unidad} - ${c.unidadNombre}</td><td>${esc(c.descripcion)}</td><td class="num">${money(c.precio)}</td><td class="num">${money(importe(c))}</td><td>02</td></tr>`,
    )
    .join('');
  return pagina({
    titulo: PROVEEDOR.nombreCfdi,
    sub: [
      `RFC: ${PROVEEDOR.rfc}`,
      `Régimen fiscal: ${PROVEEDOR.regimen} - ${PROVEEDOR.regimenNombre}`,
      `Lugar de expedición: ${PROVEEDOR.cp}`,
    ],
    meta: [
      `<b>Factura ${numero(f)}</b>`,
      'CFDI 4.0',
      `Fecha y hora de emisión de CFDI: ${f.fecha}`,
      'Tipo de comprobante: I - Ingreso',
      'Exportación: 01 - No aplica',
    ],
    aviso: false,
    cuerpo: `<h2>Receptor</h2>${kv([
      ['RFC', r.rfc],
      ['Nombre', esc(r.nombre)],
      ['Domicilio fiscal', r.cp],
      ['Régimen fiscal', `${r.regimen} - ${r.regimenNombre}`],
      ['Uso CFDI', `${r.usoCfdi} - ${r.usoCfdiNombre}`],
    ])}
<h2>Conceptos</h2><table><tr><th>Clave</th><th>Cant.</th><th>Unidad</th><th>Descripción</th><th class="num">Valor unitario</th><th class="num">Importe</th><th>Obj. Imp.</th></tr>
${filas}</table>
<h2>Totales</h2><table class="totals"><tr><td class="k">Subtotal</td><td class="num">${money(subtotal(f))}</td></tr>
<tr><td class="k">Traslado IVA Tasa 0.160000</td><td class="num">${money(iva(subtotal(f)))}</td></tr>
<tr><td class="k">Total</td><td class="num"><b>${money(total(f))} MXN</b></td></tr></table>
<p><b>Importe con letra:</b> ${f.letra}</p>
<table><tr><td class="k">Moneda</td><td>MXN</td><td class="k">Forma de pago</td><td>99 - Por definir</td><td class="k">Método de pago</td><td>PPD - Pago en parcialidades o diferido</td></tr></table>
${timbre(f)}`,
  });
}

function pdfVobo(f) {
  const oc = f.oc ?? f.ocVobo;
  return pagina({
    titulo: RECEPTOR.nombre,
    sub: ['Visto Bueno del Líder de Proyecto'],
    meta: [`Fecha: ${f.fecha.slice(0, 10)}`, `Folio: VOBO-2026-${f.folio}`],
    cuerpo: `<h2>Referencia</h2>${kv([
      ['Proyecto', PROYECTO.nombre],
      ['Proveedor', PROVEEDOR.nombreCfdi],
      ['RFC', PROVEEDOR.rfc],
      ['Orden de compra', oc],
      ['Factura', numero(f)],
      ['UUID', f.uuid],
      ['Subtotal', `${money(subtotal(f))} MXN`],
      ['Total', `${money(total(f))} MXN`],
    ])}
<h2>Dictamen</h2><p>Por medio del presente, como líder del proyecto <b>${PROYECTO.nombre}</b>, hago constar que los trabajos y
suministros de la orden de compra <b>${oc}</b> fueron recibidos a entera satisfacción, por lo que otorgo mi <b>Visto Bueno</b>
para el trámite de pago de la factura arriba referida.</p>
${kv(
  [
    ['Trabajos revisados', f.conceptos.map((c) => esc(c.descripcion.replace(/\s*\(OC\/\d+\)$/, ''))).join('<br>')],
    ['Resultado', '<b>APROBADO</b>'],
  ],
  1,
)}
${firmas([PROYECTO.lider, 'Líder de proyecto FERROMEX'])}`,
  });
}

// ---------------------------------------------------------------- Expediente (persona moral)

function pdfActa() {
  return pagina({
    titulo: 'TESTIMONIO DE ESCRITURA PÚBLICA',
    sub: ['Notaría Pública número 23 de Santiago de Querétaro, Qro. · Representación de prueba'],
    meta: ['<b>ACTA CONSTITUTIVA</b>', 'Escritura número 18,452', `Fecha: ${DOC_FECHAS.acta}`],
    cuerpo: `<h2>Constitución de sociedad</h2>${kv([
      ['Denominación', `${PROVEEDOR.nombreCfdi}`],
      ['Régimen de capital', PROVEEDOR.regimenCapital],
      ['Domicilio social', 'Santiago de Querétaro, Querétaro'],
      ['Duración', 'Indefinida'],
      ['Capital social mínimo', '$500,000.00 MXN'],
      ['Nacionalidad', 'Mexicana'],
    ])}
<h2>Objeto social</h2><p>Mantenimiento preventivo y correctivo de locomotoras, carros de ferrocarril y equipo de vía; suministro de
refacciones ferroviarias; inspección y calibración de equipo de patio.</p>
<h2>Socios fundadores</h2>${kv(
  [
    ['Socio', `${PROVEEDOR.representante} · 60% de las acciones`],
    ['Socio', 'Gabriela Ruiz Montaño · 40% de las acciones'],
    ['Administrador único', PROVEEDOR.representante],
  ],
  1,
)}
${firmas(['Lic. Ernesto Galván Rangel', 'Notario Público 23'])}`,
  });
}

function pdfPoder() {
  return pagina({
    titulo: 'TESTIMONIO DE ESCRITURA PÚBLICA',
    sub: ['Notaría Pública número 23 de Santiago de Querétaro, Qro. · Representación de prueba'],
    meta: ['<b>PODER GENERAL</b>', 'Escritura número 27,915', `Fecha: ${DOC_FECHAS.poder}`],
    cuerpo: `${kv([
      ['Poderdante', `${PROVEEDOR.nombreCfdi}, ${PROVEEDOR.regimenCapital}`],
      ['Apoderado', PROVEEDOR.representante],
      ['Tipo de poder', 'General para pleitos y cobranzas y actos de administración'],
      ['Vigencia', 'Indefinida'],
    ])}
<p>La sociedad otorga al apoderado poder general para actos de administración, con facultades para suscribir contratos, presentar
facturas y gestionar cobros ante clientes y autoridades, en los términos del artículo 2554 del Código Civil Federal.</p>
${firmas(['Lic. Ernesto Galván Rangel', 'Notario Público 23'])}`,
  });
}

function pdfConstancia() {
  return pagina({
    titulo: 'CONSTANCIA DE SITUACIÓN FISCAL',
    sub: ['Representación de prueba'],
    meta: ['<b>Cédula de identificación fiscal</b>', `Fecha de emisión: ${DOC_FECHAS.constancia}`, `RFC: ${PROVEEDOR.rfc}`],
    cuerpo: `<h2>Datos de identificación del contribuyente</h2>${kv([
      ['RFC', PROVEEDOR.rfc],
      ['Denominación o razón social', PROVEEDOR.nombreCfdi],
      ['Régimen capital', PROVEEDOR.regimenCapital],
      ['Estatus en el padrón', 'ACTIVO'],
      ['Fecha de inicio de operaciones', PROVEEDOR.constitucion],
      ['Tipo de persona', 'Persona moral'],
    ])}
<h2>Datos del domicilio registrado</h2>${kv([['Domicilio fiscal', PROVEEDOR.domicilio]], 1)}
<h2>Regímenes</h2><table><tr><td class="k">Régimen</td><td>${PROVEEDOR.regimen} - ${PROVEEDOR.regimenNombre}</td><td class="k">Fecha de inicio</td><td>${PROVEEDOR.constitucion}</td></tr></table>
<h2>Actividades económicas</h2>${kv([['Actividad', 'Reparación y mantenimiento de equipo de transporte ferroviario (100%)']], 1)}`,
  });
}

function pdfIdentificacionRepresentante() {
  return pagina({
    titulo: 'IDENTIFICACIÓN OFICIAL',
    sub: ['Representación de prueba (no reproduce ningún formato oficial)'],
    meta: ['<b>DATOS DEL TITULAR</b>', `Fecha de emisión: ${DOC_FECHAS.identificacion}`],
    cuerpo: `<h2>Titular</h2>${kv([
      ['Nombre', PROVEEDOR.representante],
      ['CURP', PROVEEDOR.curpRepresentante],
      ['Fecha de nacimiento', '1975-08-12'],
      ['Sexo', 'H'],
      ['Domicilio', PROVEEDOR.domicilioRepresentante],
      ['Vigencia', '2033'],
    ])}`,
  });
}

function pdfReciboLuz(titular, domicilio, servicio, fecha) {
  return pagina({
    titulo: 'COMPAÑÍA DE LUZ DEMO',
    sub: ['Recibo de servicio'],
    meta: ['<b>AVISO RECIBO</b>', 'Periodo: 01/09/2026 - 31/10/2026', `Fecha de emisión: ${fecha}`, 'Fecha límite de pago: 2026-11-28'],
    cuerpo: `<h2>Datos del servicio</h2>${kv([
      ['Titular', titular],
      ['No. de servicio', servicio],
      ['Domicilio', domicilio],
      ['Tarifa', titular === PROVEEDOR.nombreCfdi ? 'GDMTO' : '1C'],
    ])}
<h2>Importe</h2>${kv([
      ['Consumo (kWh)', titular === PROVEEDOR.nombreCfdi ? '12,480' : '392'],
      ['Importe del periodo', titular === PROVEEDOR.nombreCfdi ? '$38,214.00' : '$842.00'],
      ['IVA', titular === PROVEEDOR.nombreCfdi ? '$6,114.24' : '$134.72'],
      ['Total a pagar', titular === PROVEEDOR.nombreCfdi ? '<b>$44,328.24</b>' : '<b>$976.72</b>'],
    ])}`,
  });
}

function pdfEstadoCuenta() {
  return pagina({
    titulo: 'BANCO DEMO, S.A.',
    sub: ['Estado de cuenta · Carátula'],
    meta: ['<b>CUENTA DE CHEQUES EMPRESARIAL</b>', 'Periodo: 01/10/2026 - 31/10/2026', `Fecha de corte: ${DOC_FECHAS.estadoCuenta}`],
    cuerpo: `<h2>Titular</h2>${kv(
      [
        ['Razón social', PROVEEDOR.nombreCfdi],
        ['RFC', PROVEEDOR.rfc],
        ['Domicilio', PROVEEDOR.domicilio],
      ],
      1,
    )}
<h2>Datos de la cuenta</h2>${kv([
      ['Número de cuenta', PROVEEDOR.cuenta],
      ['CLABE interbancaria', PROVEEDOR.clabe],
      ['Moneda', 'MXN'],
      ['Sucursal', PROVEEDOR.sucursal],
    ])}
<h2>Resumen del periodo</h2>${kv([
      ['Saldo anterior', '$1,284,630.15'],
      ['Depósitos', '$612,480.00'],
      ['Retiros', '$548,917.62'],
      ['Saldo final', '$1,348,192.53'],
    ])}`,
  });
}

// ---------------------------------------------------------------- Salida

const rfc = PROVEEDOR.rfc;
const expediente = (n) => join('0-proveedor', `${n}-${rfc}.pdf`);

const PDFS = {
  [expediente('Acta-Constitutiva')]: pdfActa(),
  [expediente('Poder-Representante-Legal')]: pdfPoder(),
  [expediente('Constancia-Situacion-Fiscal')]: pdfConstancia(),
  [expediente('Identificacion-Representante-Legal')]: pdfIdentificacionRepresentante(),
  [expediente('Comprobante-Domicilio-Representante-Legal')]: pdfReciboLuz(
    PROVEEDOR.representante,
    PROVEEDOR.domicilioRepresentante,
    '762 118 409 551',
    DOC_FECHAS.domicilioRepresentante,
  ),
  [expediente('Comprobante-Domicilio')]: pdfReciboLuz(PROVEEDOR.nombreCfdi, PROVEEDOR.domicilio, '762 905 330 184', DOC_FECHAS.domicilio),
  [expediente('Estado-Cuenta-Bancario')]: pdfEstadoCuenta(),
};
const ESCANEADOS = {};
const XMLS = {};
for (const f of FACTURAS) {
  const cfdi = join(f.carpeta, `CFDI-F${f.folio}-${rfc}`);
  if (f.escaneado) {
    ESCANEADOS[`${cfdi}-escaneado.pdf`] = pdfCfdi(f);
    XMLS[`${cfdi}.xml`] = cfdiIngreso(f);
  } else {
    PDFS[`${cfdi}.pdf`] = pdfCfdi(f);
  }
  PDFS[join(f.carpeta, `VoBo-F${f.folio}.pdf`)] = pdfVobo(f);
}

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
  // PDF escaneado: la hoja carta se fotografía (captura a 2x) y el PDF solo lleva esa imagen, sin capa de texto, como
  // lo deja un escáner. Gris, un poco girada y con el contraste de una copia.
  const escaner = await navegador.newPage({ viewport: { width: 816, height: 1056 }, deviceScaleFactor: 2 });
  for (const [ruta, html] of Object.entries(ESCANEADOS)) {
    const hoja = html.replace('<body>', '<body style="width:8.5in;height:11in;padding:16mm 15mm;overflow:hidden;background:#fff">');
    await escaner.setContent(hoja, { waitUntil: 'load' });
    const imagen = (await escaner.screenshot({ clip: { x: 0, y: 0, width: 816, height: 1056 } })).toString('base64');
    await tab.setContent(
      `<!doctype html><html><head><style>@page{size:Letter;margin:0}body{margin:0;background:#f4f3ef}
img{display:block;width:8.5in;height:11in;filter:grayscale(1) contrast(1.12) brightness(.97);transform:rotate(-.45deg) scale(.985)}</style></head>
<body><img src="data:image/png;base64,${imagen}"></body></html>`,
      { waitUntil: 'load' },
    );
    mkdirSync(dirname(join(SALIDA, ruta)), { recursive: true });
    await tab.pdf({ path: join(SALIDA, ruta), format: 'Letter', printBackground: true, preferCSSPageSize: true });
    console.log('pdf ', ruta, '(escaneado, sin texto)');
  }
} finally {
  await navegador.close();
}
