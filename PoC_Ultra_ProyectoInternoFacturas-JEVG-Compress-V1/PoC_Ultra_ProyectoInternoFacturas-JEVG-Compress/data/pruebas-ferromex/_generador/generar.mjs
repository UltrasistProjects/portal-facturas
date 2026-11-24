// Genera los documentos de data/pruebas-ferromex: CFDI (XML), complemento de pago (XML) y los PDF del recorrido.
// Los PDF se imprimen con el Chromium de Playwright de tests/hu (npm ci en tests/hu, o HU_DIR=<otro tests/hu>).
//
//   node data/pruebas-ferromex/_generador/generar.mjs
//
// RECEPTOR copia la configuración vigente de Reglas de Validación (XML-002, XML-009, XML-010). Si cambia el RFC,
// la razón social o el C.P. de FERROMEX, actualízalo aquí y vuelve a generar: los XML deben coincidir con esa regla.
import { mkdirSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const AQUI = dirname(fileURLToPath(import.meta.url));
const SALIDA = join(AQUI, '..');
const HU_DIR = process.env.HU_DIR ?? join(AQUI, '../../../tests/hu');

const RECEPTOR = {
  rfc: 'ULT940623AG0',
  nombre: 'FERROMEX',
  cp: '03930',
  regimen: '601',
  regimenNombre: 'General de Ley Personas Morales',
  usoCfdi: 'G03',
  usoCfdiNombre: 'Gastos en general',
};

const PROVEEDOR = {
  nombre: 'Héctor Garza Villarreal',
  nombreCfdi: 'HECTOR GARZA VILLARREAL',
  rfc: 'GAVH810417Q42',
  curp: 'GAVH810417HNLRLC00',
  nacimiento: '1981-04-17',
  regimen: '612',
  regimenNombre: 'Personas Físicas con Actividades Empresariales y Profesionales',
  inicioOperaciones: '2012-06-04',
  domicilio: 'Av. Constitución 2050, Int. 3, Col. Obispado, Monterrey, Nuevo León, C.P. 64060',
  cp: '64060',
  banco: 'Banco Demo, S.A.',
  cuenta: '0457812396',
  clabe: '000580004578123964',
  sucursal: '0580 Monterrey Obispado',
};

const CONTRATO = {
  numero: 4,
  proyecto: 'Monitoreo de Flota Ferroviaria FERROMEX',
  lider: 'Mariana Cortés Elizondo',
  tecnologia: 'React + Python Fast API',
  monto: 45000,
  inicio: '2026-10-01',
  fin: '2027-03-31',
  firma: '2026-09-28',
};

const concepto = (periodo) =>
  `Desarrollo del sistema de Monitoreo de Flota Ferroviaria con React + Python Fast API, servicio del mes ${periodo}`;

const FACTURA_A = {
  carpeta: '3-factura-observaciones-autorizada',
  serie: 'A',
  folio: '1001',
  fecha: '2026-11-19T09:30:00',
  timbrado: '2026-11-19T09:35:00',
  periodo: '10/2026',
  oc: 'OC-2026-0451',
  ocFecha: '2026-10-01',
  subtotal: 45000,
  letra: 'CINCUENTA Y DOS MIL DOSCIENTOS PESOS 00/100 M.N.',
  uuid: '8E21EC7A-43E0-4C56-8644-D1E9325DE2EE',
};

const FACTURA_B = {
  carpeta: '4-factura-rechazada',
  serie: 'A',
  folio: '1002',
  fecha: '2026-11-19T10:00:00',
  timbrado: '2026-11-19T10:05:00',
  periodo: '11/2026',
  oc: 'OC-2026-0452',
  ocFecha: '2026-11-03',
  subtotal: 52000,
  letra: 'SESENTA MIL TRESCIENTOS VEINTE PESOS 00/100 M.N.',
  uuid: '4CCE1C44-89B6-4EB9-9B0F-657760BAEE08',
};

const PAGO_A = {
  serie: 'P',
  folio: '1001',
  fecha: '2026-11-19T13:00:00',
  timbrado: '2026-11-19T13:05:00',
  uuid: '3985B44F-2E7D-4CBB-9DF2-8FE8F740DE4E',
};

const DOC_FECHAS = {
  constancia: '2026-11-17',
  domicilio: '2026-11-04',
  estadoCuenta: '2026-10-31',
  identificacion: '2025-03-12',
  opinion: '2026-11-17',
  propuesta: '2026-09-15',
};

const iva = (n) => Math.round(n * 16) / 100;
const total = (n) => n + iva(n);
const fix = (n) => n.toFixed(2);
const money = (n) => '$' + n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const serieFolio = (f) => `${f.serie}-${f.folio}`;

// ---------------------------------------------------------------- XML

function cfdiIngreso(f) {
  const sub = fix(f.subtotal);
  const imp = fix(iva(f.subtotal));
  return `<?xml version="1.0" encoding="UTF-8"?>
<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://www.sat.gob.mx/cfd/4 http://www.sat.gob.mx/sitio_internet/cfd/4/cfdv40.xsd" Version="4.0" Serie="${f.serie}" Folio="${f.folio}" Fecha="${f.fecha}" FormaPago="99" MetodoPago="PPD" SubTotal="${sub}" Moneda="MXN" Total="${fix(total(f.subtotal))}" TipoDeComprobante="I" Exportacion="01" LugarExpedicion="${PROVEEDOR.cp}" NoCertificado="00001000000500000001" Certificado="" Sello="">
    <cfdi:Emisor Rfc="${PROVEEDOR.rfc}" Nombre="${PROVEEDOR.nombreCfdi}" RegimenFiscal="${PROVEEDOR.regimen}"/>
    <cfdi:Receptor Rfc="${RECEPTOR.rfc}" Nombre="${esc(RECEPTOR.nombre)}" DomicilioFiscalReceptor="${RECEPTOR.cp}" RegimenFiscalReceptor="${RECEPTOR.regimen}" UsoCFDI="${RECEPTOR.usoCfdi}"/>
    <cfdi:Conceptos>
        <cfdi:Concepto ClaveProdServ="81111500" Cantidad="1" ClaveUnidad="E48" Unidad="Servicio" Descripcion="${esc(concepto(f.periodo))}" ValorUnitario="${sub}" Importe="${sub}" ObjetoImp="02">
            <cfdi:Impuestos>
                <cfdi:Traslados>
                    <cfdi:Traslado Base="${sub}" Impuesto="002" TipoFactor="Tasa" TasaOCuota="0.160000" Importe="${imp}"/>
                </cfdi:Traslados>
            </cfdi:Impuestos>
        </cfdi:Concepto>
    </cfdi:Conceptos>
    <cfdi:Impuestos TotalImpuestosTrasladados="${imp}">
        <cfdi:Traslados>
            <cfdi:Traslado Base="${sub}" Impuesto="002" TipoFactor="Tasa" TasaOCuota="0.160000" Importe="${imp}"/>
        </cfdi:Traslados>
    </cfdi:Impuestos>
    <cfdi:Complemento>
        <tfd:TimbreFiscalDigital Version="1.1" UUID="${f.uuid}" FechaTimbrado="${f.timbrado}" RfcProvCertif="SAT970701NN3" SelloCFD="" NoCertificadoSAT="00001000000500000002" SelloSAT=""/>
    </cfdi:Complemento>
</cfdi:Comprobante>
`;
}

function cfdiPago(p, f) {
  const sub = fix(f.subtotal);
  const imp = fix(iva(f.subtotal));
  const tot = fix(total(f.subtotal));
  return `<?xml version="1.0" encoding="UTF-8"?>
<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" xmlns:pago20="http://www.sat.gob.mx/Pagos20" xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://www.sat.gob.mx/cfd/4 http://www.sat.gob.mx/sitio_internet/cfd/4/cfdv40.xsd http://www.sat.gob.mx/Pagos20 http://www.sat.gob.mx/sitio_internet/cfd/Pagos/Pagos20.xsd" Version="4.0" Serie="${p.serie}" Folio="${p.folio}" Fecha="${p.fecha}" SubTotal="0" Moneda="XXX" Total="0" TipoDeComprobante="P" Exportacion="01" LugarExpedicion="${PROVEEDOR.cp}" NoCertificado="00001000000500000001" Certificado="" Sello="">
  <cfdi:Emisor Rfc="${PROVEEDOR.rfc}" Nombre="${PROVEEDOR.nombreCfdi}" RegimenFiscal="${PROVEEDOR.regimen}"/>
  <cfdi:Receptor Rfc="${RECEPTOR.rfc}" Nombre="${esc(RECEPTOR.nombre)}" DomicilioFiscalReceptor="${RECEPTOR.cp}" RegimenFiscalReceptor="${RECEPTOR.regimen}" UsoCFDI="CP01"/>
  <cfdi:Conceptos>
    <cfdi:Concepto ClaveProdServ="84111506" Cantidad="1" ClaveUnidad="ACT" Descripcion="Pago" ValorUnitario="0" Importe="0" ObjetoImp="01"/>
  </cfdi:Conceptos>
  <cfdi:Complemento>
    <pago20:Pagos Version="2.0">
      <pago20:Totales TotalTrasladosBaseIVA16="${sub}" TotalTrasladosImpuestoIVA16="${imp}" MontoTotalPagos="${tot}"/>
      <pago20:Pago FechaPago="${p.fecha}" FormaDePagoP="03" MonedaP="MXN" TipoCambioP="1" Monto="${tot}">
        <pago20:DoctoRelacionado IdDocumento="${f.uuid}" Serie="${f.serie}" Folio="${f.folio}" MonedaDR="MXN" EquivalenciaDR="1" NumParcialidad="1" ImpSaldoAnt="${tot}" ImpPagado="${tot}" ImpSaldoInsoluto="0.00" ObjetoImpDR="02">
          <pago20:ImpuestosDR><pago20:TrasladosDR><pago20:TrasladoDR BaseDR="${sub}" ImpuestoDR="002" TipoFactorDR="Tasa" TasaOCuotaDR="0.160000" ImporteDR="${imp}"/></pago20:TrasladosDR></pago20:ImpuestosDR>
        </pago20:DoctoRelacionado>
        <pago20:ImpuestosP><pago20:TrasladosP><pago20:TrasladoP BaseP="${sub}" ImpuestoP="002" TipoFactorP="Tasa" TasaOCuotaP="0.160000" ImporteP="${imp}"/></pago20:TrasladosP></pago20:ImpuestosP>
      </pago20:Pago>
    </pago20:Pagos>
    <tfd:TimbreFiscalDigital Version="1.1" UUID="${p.uuid}" FechaTimbrado="${p.timbrado}" RfcProvCertif="SAT970701NN3" SelloCFD="" NoCertificadoSAT="00001000000500000002" SelloSAT=""/>
  </cfdi:Complemento>
</cfdi:Comprobante>
`;
}

// ---------------------------------------------------------------- HTML

const CSS = `
@page { size: Letter; margin: 16mm 15mm; }
* { box-sizing: border-box; }
body { font-family: Arial, Helvetica, sans-serif; font-size: 9pt; color: #1d1d1f; margin: 0; }
.head { display: flex; justify-content: space-between; align-items: flex-end; border-bottom: 2px solid #1f3a5f;
  padding-bottom: 7px; margin-bottom: 14px; }
.head h1 { font-size: 15pt; margin: 0 0 3px; }
.head .sub { font-size: 7.5pt; color: #555; line-height: 1.45; }
.head .meta { text-align: right; font-size: 7.5pt; color: #333; line-height: 1.5; }
.head .meta b { color: #1d1d1f; }
table + p { margin-top: 10px; }
h2 { background: #1f3a5f; color: #fff; font-size: 7pt; font-weight: bold; padding: 4px 6px; margin: 14px 0 6px; }
table { width: 100%; border-collapse: collapse; }
td, th { border: 1px solid #c9ced6; padding: 4px 6px; vertical-align: top; text-align: left; }
th, td.k { background: #e9edf3; font-weight: bold; }
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
.sentido { font-size: 11pt; color: #1e7b34; font-weight: bold; }
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
    const celdas = pares
      .slice(i, i + porRenglon)
      .map(([k, v]) => `<td class="k">${k}</td><td>${v}</td>`)
      .join('');
    const faltan = porRenglon - pares.slice(i, i + porRenglon).length;
    filas.push(`<tr>${celdas}${faltan ? `<td colspan="${faltan * 2}" style="border:none"></td>` : ''}</tr>`);
  }
  return `<table>${filas.join('')}</table>`;
}

const firmas = (...personas) =>
  `<div class="firmas">${personas.map(([n, r]) => `<div class="firma">${n}<small>${r}</small></div>`).join('')}</div>`;

const encabezadoFerromex = (titulo, meta) => ({
  titulo: RECEPTOR.nombre,
  sub: [`RFC: ${RECEPTOR.rfc}`, `C.P. ${RECEPTOR.cp}`],
  meta: [`<b>${titulo}</b>`, ...meta],
});

const encabezadoProveedor = (titulo, meta) => ({
  titulo: PROVEEDOR.nombreCfdi,
  sub: [
    `RFC: ${PROVEEDOR.rfc}`,
    `Régimen fiscal: ${PROVEEDOR.regimen} - ${PROVEEDOR.regimenNombre}`,
    `Lugar de expedición: ${PROVEEDOR.cp}`,
  ],
  meta: [`<b>${titulo}</b>`, ...meta],
});

const timbre = (uuid, fecha) =>
  `<h2>Timbre fiscal digital</h2>${kv(
    [
      ['Folio fiscal (UUID)', uuid],
      ['Fecha de timbrado', fecha],
      ['No. certificado emisor', '00001000000500000001'],
      ['No. certificado SAT', '00001000000500000002'],
      ['RFC PAC', 'SAT970701NN3'],
    ],
    1,
  )}<p class="small">Este documento es una representación impresa de un CFDI. Documento de prueba sin sellos digitales válidos.</p>`;

const receptorCfdi = (uso, usoNombre) =>
  `<h2>Receptor</h2>${kv([
    ['RFC', RECEPTOR.rfc],
    ['Nombre', esc(RECEPTOR.nombre)],
    ['Domicilio fiscal', RECEPTOR.cp],
    ['Régimen fiscal', `${RECEPTOR.regimen} - ${RECEPTOR.regimenNombre}`],
    ['Uso CFDI', `${uso} - ${usoNombre}`],
  ])}`;

function pdfCfdi(f) {
  const tot = total(f.subtotal);
  return pagina({
    ...encabezadoProveedor('FACTURA (CFDI 4.0)', [
      `Serie-Folio: ${serieFolio(f)}`,
      `Fecha: ${f.fecha}`,
      'Tipo: I - Ingreso',
      'Exportación: 01 - No aplica',
    ]),
    aviso: false,
    cuerpo: `${receptorCfdi(RECEPTOR.usoCfdi, RECEPTOR.usoCfdiNombre)}
<h2>Conceptos</h2><table><tr><th>Clave</th><th>Cant.</th><th>Unidad</th><th>Descripción</th><th class="num">Valor unitario</th><th class="num">Importe</th><th>Obj. Imp.</th></tr>
<tr><td>81111500</td><td>1</td><td>E48 - Servicio</td><td>${esc(concepto(f.periodo))}</td><td class="num">${money(f.subtotal)}</td><td class="num">${money(f.subtotal)}</td><td>02</td></tr></table>
<h2>Totales</h2><table class="totals"><tr><td class="k">Subtotal</td><td class="num">${money(f.subtotal)}</td></tr>
<tr><td class="k">IVA Traslado 002 (Tasa 0.160000)</td><td class="num">${money(iva(f.subtotal))}</td></tr>
<tr><td class="k">Total</td><td class="num"><b>${money(tot)} MXN</b></td></tr></table>
<p><b>Importe con letra:</b> ${f.letra}</p>
<table><tr><td class="k">Moneda</td><td>MXN</td><td class="k">Forma de pago</td><td>99 - Por definir</td><td class="k">Método de pago</td><td>PPD - Pago en parcialidades o diferido</td></tr></table>
${timbre(f.uuid, f.timbrado)}`,
  });
}

function pdfPago(p, f) {
  const tot = total(f.subtotal);
  return pagina({
    ...encabezadoProveedor('COMPLEMENTO DE PAGO (CFDI 4.0 / Pagos 2.0)', [
      `Serie-Folio: ${serieFolio(p)}`,
      `Fecha: ${p.fecha}`,
      'Tipo: P - Pago',
      'Moneda: XXX',
    ]),
    aviso: false,
    cuerpo: `${receptorCfdi('CP01', 'Pagos')}
<h2>Pago</h2>${kv([
      ['Fecha de pago', p.fecha],
      ['Forma de pago', '03 - Transferencia electrónica de fondos'],
      ['Moneda', 'MXN (tipo de cambio 1)'],
      ['Monto', money(tot)],
    ])}
<h2>Documento relacionado</h2><table><tr><th>UUID</th><th>Serie-Folio</th><th>Parcialidad</th><th class="num">Saldo anterior</th><th class="num">Pagado</th><th class="num">Saldo insoluto</th></tr>
<tr><td>${f.uuid}</td><td>${serieFolio(f)}</td><td>1</td><td class="num">${money(tot)}</td><td class="num">${money(tot)}</td><td class="num">$0.00</td></tr></table>
<h2>Totales</h2><table class="totals"><tr><td class="k">Base IVA 16%</td><td class="num">${money(f.subtotal)}</td></tr>
<tr><td class="k">IVA 16%</td><td class="num">${money(iva(f.subtotal))}</td></tr>
<tr><td class="k">Monto total de pagos</td><td class="num"><b>${money(tot)} MXN</b></td></tr></table>
${timbre(p.uuid, p.timbrado)}`,
  });
}

function pdfOrdenCompra(f, montoAutorizado) {
  return pagina({
    ...encabezadoFerromex('ORDEN DE COMPRA', [`No.: ${f.oc}`, `Fecha de emisión: ${f.ocFecha}`, `Contrato: ${CONTRATO.numero}`]),
    cuerpo: `<h2>Proveedor</h2>${kv([
      ['Nombre', PROVEEDOR.nombre],
      ['RFC', PROVEEDOR.rfc],
      ['Tipo', 'Persona física'],
      ['Origen', 'Nacional'],
    ])}
<h2>Datos del proyecto</h2>${kv([
      ['Proyecto', CONTRATO.proyecto],
      ['Líder de proyecto', CONTRATO.lider],
      ['Tecnología autorizada', CONTRATO.tecnologia],
      ['Vigencia del contrato', `${CONTRATO.inicio} a ${CONTRATO.fin}`],
      ['Periodo de servicio', f.periodo],
    ])}
<h2>Detalle</h2><table><tr><th>#</th><th>Descripción</th><th>Cant.</th><th class="num">Precio unitario</th><th class="num">Importe</th></tr>
<tr><td>1</td><td>${esc(concepto(f.periodo))}</td><td>1</td><td class="num">${money(montoAutorizado)}</td><td class="num">${money(montoAutorizado)}</td></tr></table>
<table class="totals" style="margin-top:6px"><tr><td class="k">Subtotal</td><td class="num">${money(montoAutorizado)}</td></tr>
<tr><td class="k">IVA 16%</td><td class="num">${money(iva(montoAutorizado))}</td></tr>
<tr><td class="k">Total</td><td class="num"><b>${money(total(montoAutorizado))} MXN</b></td></tr></table>
<h2>Condiciones de facturación</h2><table><tr><td class="k">Uso CFDI</td><td>${RECEPTOR.usoCfdi}</td><td class="k">Método de pago</td><td>PPD</td><td class="k">Forma de pago</td><td>99</td></tr></table>
<p>El monto autorizado de esta orden es de ${money(montoAutorizado)} MXN antes de impuestos. La factura deberá referir el proyecto y el periodo de servicio indicados.</p>
${firmas(['Compras FERROMEX', 'Elaboró'], ['Dirección de Tecnología FERROMEX', 'Autorizó'])}`,
  });
}

function pdfVobo(f, { periodo, folio, fecha }) {
  return pagina({
    titulo: RECEPTOR.nombre,
    sub: ['Visto Bueno del Líder de Proyecto'],
    meta: [`Fecha: ${fecha}`, `Folio: ${folio}`],
    cuerpo: `<h2>Referencia</h2>${kv([
      ['Proyecto', CONTRATO.proyecto],
      ['Contrato', CONTRATO.numero],
      ['Proveedor', PROVEEDOR.nombre],
      ['RFC', PROVEEDOR.rfc],
      ['Orden de compra', f.oc],
      ['Periodo de servicio', periodo],
      ['Factura', serieFolio(f)],
      ['UUID', f.uuid],
      ['Subtotal', `${money(f.subtotal)} MXN`],
      ['Total', `${money(total(f.subtotal))} MXN`],
    ])}
<h2>Dictamen</h2><p>Por medio del presente, como líder del proyecto <b>${CONTRATO.proyecto}</b>, hago constar que los servicios de
<b>desarrollo del sistema de Monitoreo de Flota Ferroviaria con ${CONTRATO.tecnologia}</b> correspondientes al periodo <b>${periodo}</b>
fueron recibidos a entera satisfacción, conforme al alcance, tecnología y monto autorizados en el contrato, por lo que otorgo mi
<b>Visto Bueno</b> para el trámite de pago de la factura arriba referida.</p>
${kv(
  [
    ['Entregables revisados', 'Tablero de ubicación de locomotoras y carros, alertas de detención y API de eventos de patio desplegados en preproducción; código fuente en repositorio'],
    ['Resultado', '<b>APROBADO</b>'],
  ],
  1,
)}
${firmas([CONTRATO.lider, 'Líder de proyecto FERROMEX'])}`,
  });
}

function pdfContrato() {
  return pagina({
    ...encabezadoFerromex('CONTRATO DE PRESTACIÓN DE SERVICIOS', [`Contrato: ${CONTRATO.numero}`, `Fecha de firma: ${CONTRATO.firma}`]),
    cuerpo: `<h2>Partes</h2>${kv([
      ['Contratante', RECEPTOR.nombre],
      ['RFC', RECEPTOR.rfc],
      ['Prestador', PROVEEDOR.nombre],
      ['RFC', PROVEEDOR.rfc],
    ])}
<h2>Objeto y condiciones</h2>${kv([
      ['Proyecto', CONTRATO.proyecto],
      ['Líder de proyecto', CONTRATO.lider],
      ['Tecnología autorizada', CONTRATO.tecnologia],
      ['Monto autorizado', `${money(CONTRATO.monto)} MXN mensuales + IVA`],
      ['Vigencia', `${CONTRATO.inicio} a ${CONTRATO.fin}`],
      ['Facturación', 'Mensual, por periodo de servicio'],
    ])}
<p><b>PRIMERA.</b> El Prestador se obliga a desarrollar el sistema de Monitoreo de Flota Ferroviaria (ubicación de locomotoras y carros,
alertas de detención y eventos de patio) con la tecnología autorizada, conforme al alcance acordado con el líder de proyecto.</p>
<p><b>SEGUNDA.</b> FERROMEX pagará el monto autorizado por cada periodo de servicio, previa recepción del CFDI (XML y PDF), la orden de
compra y el Vo.Bo. del líder de proyecto a través del Portal de Proveedores.</p>
<p><b>TERCERA.</b> Ninguna factura podrá exceder el monto autorizado ni referir periodos fuera de la vigencia.</p>
<p><b>CUARTA.</b> El Prestador emitirá el Complemento de Pago correspondiente a cada pago recibido y lo cargará en el Portal de Proveedores.</p>
${firmas(['Dirección de Tecnología FERROMEX', 'Contratante'], [PROVEEDOR.nombre, 'Prestador'])}`,
  });
}

function pdfConstancia() {
  return pagina({
    titulo: 'CONSTANCIA DE SITUACIÓN FISCAL',
    sub: ['Representación de prueba'],
    meta: ['<b>Cédula de identificación fiscal</b>', `Fecha de emisión: ${DOC_FECHAS.constancia}`, `RFC: ${PROVEEDOR.rfc}`],
    cuerpo: `<h2>Datos de identificación del contribuyente</h2>${kv([
      ['RFC', PROVEEDOR.rfc],
      ['CURP', PROVEEDOR.curp],
      ['Nombre', PROVEEDOR.nombre],
      ['Estatus en el padrón', 'ACTIVO'],
      ['Fecha de inicio de operaciones', PROVEEDOR.inicioOperaciones],
      ['Tipo de persona', 'Persona física'],
    ])}
<h2>Datos del domicilio registrado</h2>${kv([['Domicilio fiscal', PROVEEDOR.domicilio]], 1)}
<h2>Regímenes</h2><table><tr><td class="k">Régimen</td><td>${PROVEEDOR.regimen} - ${PROVEEDOR.regimenNombre}</td><td class="k">Fecha de inicio</td><td>${PROVEEDOR.inicioOperaciones}</td></tr></table>
<h2>Actividades económicas</h2>${kv([['Actividad', 'Servicios de consultoría en computación (100%)']], 1)}`,
  });
}

function pdfDomicilio() {
  return pagina({
    titulo: 'COMPAÑÍA DE LUZ DEMO',
    sub: ['Recibo de servicio doméstico'],
    meta: ['<b>AVISO RECIBO</b>', 'Periodo: 01/09/2026 - 31/10/2026', `Fecha de emisión: ${DOC_FECHAS.domicilio}`, 'Fecha límite de pago: 2026-11-24'],
    cuerpo: `<h2>Datos del servicio</h2>${kv([
      ['Titular', PROVEEDOR.nombre],
      ['No. de servicio', '817 402 215 093'],
      ['Domicilio', PROVEEDOR.domicilio],
      ['Tarifa', '1D'],
    ])}
<h2>Importe</h2>${kv([
      ['Consumo (kWh)', '486'],
      ['Importe del periodo', '$1,036.00'],
      ['IVA', '$165.76'],
      ['Total a pagar', '<b>$1,201.76</b>'],
    ])}`,
  });
}

function pdfEstadoCuenta() {
  return pagina({
    titulo: 'BANCO DEMO, S.A.',
    sub: ['Estado de cuenta · Carátula'],
    meta: ['<b>CUENTA DE CHEQUES</b>', 'Periodo: 01/10/2026 - 31/10/2026', `Fecha de corte: ${DOC_FECHAS.estadoCuenta}`],
    cuerpo: `<h2>Titular</h2>${kv(
      [
        ['Nombre', PROVEEDOR.nombre],
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
      ['Saldo anterior', '$86,430.20'],
      ['Depósitos', '$41,760.00'],
      ['Retiros', '$38,915.47'],
      ['Saldo final', '$89,274.73'],
    ])}`,
  });
}

function pdfIdentificacion() {
  return pagina({
    titulo: 'IDENTIFICACIÓN OFICIAL',
    sub: ['Representación de prueba (no reproduce ningún formato oficial)'],
    meta: ['<b>DATOS DEL TITULAR</b>', `Fecha de emisión: ${DOC_FECHAS.identificacion}`],
    cuerpo: `<h2>Titular</h2>${kv([
      ['Nombre', PROVEEDOR.nombre],
      ['CURP', PROVEEDOR.curp],
      ['Fecha de nacimiento', PROVEEDOR.nacimiento],
      ['Sexo', 'H'],
      ['Domicilio', PROVEEDOR.domicilio],
      ['Vigencia', '2035'],
    ])}`,
  });
}

function pdfOpinion() {
  return pagina({
    titulo: 'OPINIÓN DEL CUMPLIMIENTO DE OBLIGACIONES FISCALES',
    sub: ['Representación de prueba'],
    meta: ['<span class="sentido">SENTIDO: POSITIVO</span>', `Fecha: ${DOC_FECHAS.opinion}`, 'Folio: 26NA0458213'],
    cuerpo: `${kv([
      ['RFC', PROVEEDOR.rfc],
      ['Nombre', PROVEEDOR.nombre],
    ])}
<p>Se informa que, a la fecha de emisión, el contribuyente se encuentra al corriente en el cumplimiento de sus obligaciones fiscales,
por lo que se emite opinión en sentido <b>POSITIVO</b>.</p>`,
  });
}

function pdfPropuesta() {
  return pagina({
    titulo: PROVEEDOR.nombreCfdi,
    sub: [`RFC: ${PROVEEDOR.rfc}`, PROVEEDOR.domicilio],
    meta: ['<b>PROPUESTA ECONÓMICA</b>', `Fecha: ${DOC_FECHAS.propuesta}`, `Dirigida a: ${RECEPTOR.nombre}`],
    cuerpo: `<h2>Servicio propuesto</h2>${kv([
      ['Proyecto', CONTRATO.proyecto],
      ['Tecnología', CONTRATO.tecnologia],
      ['Vigencia propuesta', `${CONTRATO.inicio} a ${CONTRATO.fin}`],
      ['Monto mensual', `${money(CONTRATO.monto)} MXN + IVA`],
    ])}
<p>Desarrollo y mantenimiento evolutivo del sistema de Monitoreo de Flota Ferroviaria: tablero de ubicación de locomotoras y carros,
alertas de detención en vía y patio, y API de eventos para los sistemas operativos de FERROMEX. Facturación mensual por periodo de
servicio, con Vo.Bo. del líder de proyecto.</p>
${firmas([PROVEEDOR.nombre, 'Proveedor'], ['Autorizó', 'Líder de proyecto FERROMEX'])}`,
  });
}

// ---------------------------------------------------------------- Salida

const rfc = PROVEEDOR.rfc;
const docA = (n) => join(FACTURA_A.carpeta, n);
const docB = (n) => join(FACTURA_B.carpeta, n);

const XMLS = {
  [docA(`CFDI-A${FACTURA_A.folio}-${rfc}.xml`)]: cfdiIngreso(FACTURA_A),
  [docA(`REP-P${PAGO_A.folio}-${rfc}.xml`)]: cfdiPago(PAGO_A, FACTURA_A),
  [docB(`CFDI-A${FACTURA_B.folio}-${rfc}.xml`)]: cfdiIngreso(FACTURA_B),
};

const PDFS = {
  [`1-proveedor/Constancia-Situacion-Fiscal-${rfc}.pdf`]: pdfConstancia(),
  [`1-proveedor/Comprobante-Domicilio-${rfc}.pdf`]: pdfDomicilio(),
  [`1-proveedor/Estado-Cuenta-Bancario-${rfc}.pdf`]: pdfEstadoCuenta(),
  [`1-proveedor/Identificacion-Oficial-${rfc}.pdf`]: pdfIdentificacion(),
  [`1-proveedor/Opinion-Cumplimiento-${rfc}.pdf`]: pdfOpinion(),
  [`1-proveedor/Propuesta-Economica-${rfc}.pdf`]: pdfPropuesta(),
  [`2-contrato/Contrato-${CONTRATO.numero}-MonitoreoFlota-${rfc}.pdf`]: pdfContrato(),
  [docA(`CFDI-A${FACTURA_A.folio}-${rfc}.pdf`)]: pdfCfdi(FACTURA_A),
  [docA(`OrdenCompra-${FACTURA_A.oc}.pdf`)]: pdfOrdenCompra(FACTURA_A, CONTRATO.monto),
  [docA(`VoBo-A${FACTURA_A.folio}-v1-con-error-periodo-09-2026.pdf`)]: pdfVobo(FACTURA_A, {
    periodo: '09/2026',
    folio: 'VOBO-2026-0451',
    fecha: '2026-11-18',
  }),
  [docA(`VoBo-A${FACTURA_A.folio}-v2-corregido.pdf`)]: pdfVobo(FACTURA_A, {
    periodo: FACTURA_A.periodo,
    folio: 'VOBO-2026-0451-R1',
    fecha: '2026-11-19',
  }),
  [docA(`REP-P${PAGO_A.folio}-${rfc}.pdf`)]: pdfPago(PAGO_A, FACTURA_A),
  [docB(`CFDI-A${FACTURA_B.folio}-${rfc}.pdf`)]: pdfCfdi(FACTURA_B),
  [docB(`OrdenCompra-${FACTURA_B.oc}.pdf`)]: pdfOrdenCompra(FACTURA_B, CONTRATO.monto),
  [docB(`VoBo-A${FACTURA_B.folio}.pdf`)]: pdfVobo(FACTURA_B, {
    periodo: FACTURA_B.periodo,
    folio: 'VOBO-2026-0452',
    fecha: '2026-11-19',
  }),
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
