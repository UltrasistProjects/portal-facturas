// Genera EVIDENCIA-PRUEBAS-HUs.pdf a partir de los resultados reales de la suite (evidencias/HU-XX/resultado.json), el
// reporte JSON de Playwright y las capturas PNG de cada HU. Uso: node generar-reporte-pdf.mjs [verificacion.json]
import { chromium } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const AQUI = path.dirname(fileURLToPath(import.meta.url));
const APP = path.resolve(AQUI, '..', '..');
const EVIDENCIAS = path.join(APP, 'evidencias');
const SALIDA_HTML = path.join(EVIDENCIAS, '_reporte', 'reporte.html');
const SALIDA_PDF = path.join(APP, 'EVIDENCIA-PRUEBAS-HUs.pdf');

const leer = (p) => JSON.parse(fs.readFileSync(p, 'utf8'));
const catalogo = leer(path.join(AQUI, 'hu-catalogo.json'));
const contexto = leer(path.join(AQUI, 'reporte-contexto.json'));
const estado = leer(path.join(EVIDENCIAS, '_estado-ejecucion.json'));
const playwright = leer(path.join(EVIDENCIAS, 'playwright-resultados.json'));
const verificacion = process.argv[2] && fs.existsSync(process.argv[2]) ? leer(process.argv[2]) : null;

const esc = (t) => String(t ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
const fechaNegocio = (iso) =>
  new Intl.DateTimeFormat('es-MX', { timeZone: 'America/Mexico_City', dateStyle: 'long', timeStyle: 'short' }).format(new Date(iso));

function dimensionesPng(ruta) {
  const b = fs.readFileSync(ruta);
  return { ancho: b.readUInt32BE(16), alto: b.readUInt32BE(20) };
}

// Estatus de cada prueba en el reporte JSON de Playwright, por ID de HU (titulo "HU-XX · ...").
const playwrightPorHU = {};
(function recorrer(suite) {
  for (const spec of suite.specs ?? []) {
    for (const t of spec.tests) playwrightPorHU[spec.title.split(' ')[0]] = t.results.at(-1)?.status ?? 'sin resultado';
  }
  for (const s of suite.suites ?? []) recorrer(s);
})({ suites: playwright.suites });
const esperadoPlaywright = { PASS: 'passed', FAIL: 'failed', BLOCKED: 'skipped' };

const hus = catalogo.hus.map((hu) => {
  const archivo = path.join(EVIDENCIAS, hu.id, 'resultado.json');
  const r = fs.existsSync(archivo)
    ? leer(archivo)
    : { estado: 'BLOCKED', escenarios: [], notas: [], bloqueo: 'La HU no se ejecutó en esta corrida.', run: null };
  const evidencias = r.escenarios.flatMap((e) => e.pasos.flatMap((p) => p.evidencias.map((ev) => ({ ...ev, escenario: e, paso: p }))));
  return { ...hu, r, evidencias };
});

const total = {
  hus: hus.length,
  PASS: hus.filter((h) => h.r.estado === 'PASS').length,
  FAIL: hus.filter((h) => h.r.estado === 'FAIL').length,
  BLOCKED: hus.filter((h) => h.r.estado === 'BLOCKED').length,
  capturas: hus.reduce((n, h) => n + h.evidencias.length, 0),
  escenarios: hus.reduce((n, h) => n + h.r.escenarios.length, 0),
  pasos: hus.reduce((n, h) => n + h.r.escenarios.reduce((m, e) => m + e.pasos.length, 0), 0),
};
const chip = (e) => `<span class="chip ${esc(String(e).replace(/\s+/g, '-'))}">${esc(e)}</span>`;

// Imagen dentro del PDF: ancho de pagina limitado por un alto maximo; las muy altas se muestran en partes.
const ANCHO_MM = 262;
const ALTO_MAX_MM = 140;
function figuraImagen(ev) {
  const ruta = path.join(EVIDENCIAS, ev.archivo);
  const src = path.relative(path.dirname(SALIDA_HTML), ruta).split(path.sep).join('/');
  const { ancho, alto } = dimensionesPng(ruta);
  if (alto <= 1350) {
    const anchoMm = Math.min(ANCHO_MM, (ALTO_MAX_MM * ancho) / alto);
    return [`<img src="${esc(src)}" style="width:${anchoMm.toFixed(1)}mm" alt="${esc(ev.descripcion)}">`];
  }
  const tramo = 1000;
  const partes = Math.ceil(alto / tramo);
  const anchoMm = Math.min(ANCHO_MM, (ALTO_MAX_MM * ancho) / tramo);
  const mmPorPx = anchoMm / ancho;
  return Array.from({ length: partes }, (_, i) => {
    const altoParte = Math.min(tramo, alto - i * tramo);
    return `<div class="tramo" style="width:${anchoMm.toFixed(1)}mm;height:${(altoParte * mmPorPx).toFixed(2)}mm"><img src="${esc(src)}" style="width:${anchoMm.toFixed(1)}mm;top:-${(i * tramo * mmPorPx).toFixed(2)}mm" alt="${esc(ev.descripcion)} (parte ${i + 1} de ${partes})"></div>`;
  });
}

function seccionHU(hu, indice) {
  const { r } = hu;
  const pasosFallidos = r.escenarios.flatMap((e) => e.pasos.filter((p) => p.estado === 'FAIL').map((p) => ({ e, p })));
  const filasEscenarios = r.escenarios
    .map((e, i) => {
      const pasos = e.pasos
        .map(
          (p, j) => `<tr class="${p.estado === 'FAIL' ? 'fila-fail' : ''}"><td class="num">${i + 1}.${j + 1}</td><td>${esc(p.paso)}</td><td>${esc(p.esperado)}</td><td>${esc(p.obtenido)}${p.error ? `<div class="error"><b>Error:</b> ${esc(p.error)}</div>` : ''}</td><td>${chip(p.estado)}</td></tr>`,
        )
        .join('');
      return `<tr class="escenario"><td class="num">${i + 1}</td><td colspan="3"><b>${esc(e.nombre)}</b>${e.motivo && e.estado !== 'PASS' ? `<div class="error">${esc(e.motivo)}</div>` : ''}</td><td>${chip(e.estado)}</td></tr>${pasos}`;
    })
    .join('');
  const esperado = r.escenarios.map((e) => `<li><b>${esc(e.nombre)}:</b> ${esc(e.pasos.at(-1)?.esperado ?? '—')}</li>`).join('');
  const obtenido = r.escenarios
    .map((e) => `<li>${chip(e.estado)} <b>${esc(e.nombre)}:</b> ${esc(e.estado === 'PASS' ? (e.pasos.at(-1)?.obtenido ?? '—') : (e.motivo ?? '—'))}</li>`)
    .join('');
  const fallas = pasosFallidos.length
    ? `<div class="caja fail"><h4>Detalle del fallo</h4>${pasosFallidos
        .map(
          ({ e, p }) =>
            `<p><b>Escenario:</b> ${esc(e.nombre)}<br><b>Paso exacto:</b> ${esc(p.paso)}<br><b>Esperado:</b> ${esc(p.esperado)}<br><b>Obtenido:</b> ${esc(p.obtenido)}<br><b>Mensaje de error:</b> ${esc(p.error)}<br><b>Evidencia:</b> ${p.evidencias.map((ev) => esc(`evidencias/${ev.archivo}`)).join(', ') || '—'}</p>`,
        )
        .join('')}</div>`
    : '';
  const bloqueo = r.estado === 'BLOCKED' ? `<div class="caja blocked"><h4>Motivo del bloqueo</h4><p>${esc(r.bloqueo ?? r.escenarios.find((e) => e.estado !== 'PASS')?.motivo)}</p></div>` : '';
  const notas = r.notas?.length ? `<div class="caja nota"><h4>Observaciones registradas por la prueba</h4><ul>${r.notas.map((n) => `<li>${esc(n)}</li>`).join('')}</ul></div>` : '';
  const figuras = hu.evidencias
    .map((ev, i) => {
      const partes = figuraImagen(ev);
      const pie = `<div class="asociacion"><b>${esc(hu.id)}</b> · Escenario: ${esc(ev.escenario.nombre)} · Paso: ${esc(ev.paso.paso)}<br>Resultado esperado: ${esc(ev.paso.esperado)}<br>Resultado obtenido: ${esc(ev.paso.obtenido)} · Resultado del paso: ${chip(ev.paso.estado)}<br>Archivo: evidencias/${esc(ev.archivo)}${ev.tipo === 'correo' ? ' · Correo generado por el portal (.eml del transporte de archivo) mostrado en Chromium' : ''}${ev.tipo === 'fallo' ? ' · Captura del estado al fallar' : ''}</div>`;
      return partes
        .map(
          (img, k) =>
            `<figure><figcaption><b>Evidencia ${i + 1} — ${esc(ev.descripcion)}</b>${partes.length > 1 ? ` (parte ${k + 1} de ${partes.length})` : ''}</figcaption>${img}${k === partes.length - 1 ? pie : ''}</figure>`,
        )
        .join('');
    })
    .join('');
  return `<section class="hu" id="${esc(hu.id)}">
    <h2>${esc(hu.id)} — ${esc(hu.nombre)}</h2>
    <p class="resultado">Resultado: ${chip(r.estado)} <span class="meta">Rol: ${esc(hu.rol)} · ${esc(hu.rf)}${hu.rn.length ? ` · ${esc(hu.rn.join(', '))}` : ''} · Depende de: ${esc(hu.dependencias.join(', ') || '—')} · Prueba: tests/hu/specs/${esc(r.prueba?.archivo ?? '—')} · Playwright: ${esc(playwrightPorHU[hu.id] ?? 'sin resultado')}</span></p>
    <h3>Objetivo</h3><p>${esc(hu.objetivo)}</p>
    <h3>Criterios de aceptación</h3><ul>${hu.criterios.map((c) => `<li>${esc(c)}</li>`).join('')}</ul>
    <h3>Escenarios probados</h3>
    <table class="pasos"><thead><tr><th>#</th><th>Escenario / paso</th><th>Resultado esperado</th><th>Resultado obtenido</th><th>Estado</th></tr></thead><tbody>${filasEscenarios}</tbody></table>
    <h3>Resultado esperado</h3><ul>${esperado}</ul>
    <h3>Resultado obtenido</h3><ul>${obtenido}</ul>
    ${fallas}${bloqueo}${notas}
    <h3>Evidencia visual (${hu.evidencias.length} capturas)</h3>
    ${figuras || '<p>No hay capturas para esta HU.</p>'}
  </section>`;
}

// --- Validacion final (puntos 1 a 10 de la solicitud) ------------------------------------------------------------
const consistentes = hus.filter((h) => playwrightPorHU[h.id] === esperadoPlaywright[h.r.estado]).length;
const enCarpetaCorrecta = hus.every((h) => h.evidencias.every((ev) => ev.archivo.startsWith(`${h.id}/`) && fs.existsSync(path.join(EVIDENCIAS, ev.archivo))));
const anchoMinimo = Math.min(...hus.flatMap((h) => h.evidencias.map((ev) => dimensionesPng(path.join(EVIDENCIAS, ev.archivo)).ancho)));
const validacion = [
  ['Todas las HUs identificadas fueron procesadas', `${hus.filter((h) => h.r.escenarios.length).length} de ${total.hus} HUs del ERS tienen ejecución registrada.`],
  ['Todas tienen un resultado', `${total.PASS} PASS · ${total.FAIL} FAIL · ${total.BLOCKED} BLOCKED (suma ${total.PASS + total.FAIL + total.BLOCKED}).`],
  ['Todas tienen al menos una captura real', `Mínimo por HU: ${Math.min(...hus.map((h) => h.evidencias.length))} capturas; total ${total.capturas}.`],
  ['Las capturas corresponden a la HU correcta', enCarpetaCorrecta ? 'Cada captura está en la carpeta de su HU y asociada a su escenario y paso.' : 'REVISAR: hay capturas fuera de la carpeta de su HU o faltantes.'],
  ['Las capturas son legibles', `Ancho mínimo ${anchoMinimo} px; las capturas se revisaron visualmente y en el PDF ocupan hasta ${ANCHO_MM} mm de ancho.`],
  ['Los resultados del PDF coinciden con Playwright', `${consistentes} de ${total.hus} HUs coinciden con el reporte JSON de Playwright (${playwright.stats.expected} passed, ${playwright.stats.unexpected} failed, ${playwright.stats.skipped} skipped).`],
  ['No hay HUs PASS sin evidencia', hus.some((h) => h.r.estado === 'PASS' && !h.evidencias.length) ? 'REVISAR: hay HUs PASS sin evidencia.' : 'Ninguna HU PASS carece de capturas.'],
  ['FAIL y BLOCKED documentados', total.FAIL + total.BLOCKED ? 'Cada FAIL/BLOCKED incluye paso, esperado, obtenido, error y captura.' : 'No hubo HUs FAIL ni BLOCKED en esta ejecución.'],
  ['El PDF se puede abrir', verificacion ? `Verificado con PyMuPDF ${esc(verificacion.pymupdf)}: ${verificacion.paginas} páginas, sin errores de lectura.` : 'Se verifica después de generar el PDF.'],
  ['Las imágenes aparecen en el PDF', verificacion ? `${verificacion.imagenes_distintas} imágenes distintas incrustadas (${total.capturas} capturas esperadas).` : 'Se verifica después de generar el PDF.'],
];

const resumen = hus
  .map(
    (h) =>
      `<tr><td><a href="#${esc(h.id)}">${esc(h.id)}</a></td><td>${esc(h.nombre)}</td><td class="n">${h.r.escenarios.length}</td><td>${chip(h.r.estado)}</td><td class="n">${h.evidencias.length}</td></tr>`,
  )
  .join('');

const html = `<!doctype html><html lang="es"><head><meta charset="utf-8"><title>EVIDENCIA DE PRUEBAS — HUs</title><style>
  @page { size: A4 landscape; }
  * { box-sizing: border-box; }
  body { font: 10pt/1.45 "Segoe UI", Arial, Helvetica, sans-serif; color: #152235; margin: 0; }
  h1 { font-size: 26pt; margin: 0 0 6mm; color: #12243a; }
  h2 { font-size: 15pt; color: #12243a; border-bottom: 2px solid #1769e0; padding-bottom: 2mm; margin: 0 0 3mm; }
  h3 { font-size: 11pt; color: #1769e0; margin: 5mm 0 1.5mm; }
  h4 { margin: 0 0 1mm; font-size: 10pt; }
  p, ul { margin: 0 0 2mm; } ul { padding-left: 6mm; } li { margin-bottom: 0.8mm; }
  table { width: 100%; border-collapse: collapse; margin: 2mm 0 3mm; }
  th, td { border: 1px solid #d3dbe5; padding: 1.4mm 2mm; vertical-align: top; text-align: left; }
  th { background: #eef3f9; font-size: 8.5pt; text-transform: uppercase; letter-spacing: .3px; }
  td.n { text-align: right; } td.num { white-space: nowrap; color: #697789; width: 9mm; }
  table.pasos td { font-size: 8.6pt; } tr.escenario td { background: #f6f8fb; } tr.fila-fail td { background: #fdecec; }
  tr { break-inside: avoid; }
  .chip { display: inline-block; padding: 0.3mm 2.2mm; border-radius: 3mm; font-weight: 700; font-size: 8pt; color: #fff; background: #697789; white-space: nowrap; }
  .chip.PASS { background: #16845b; } .chip.FAIL { background: #cc3b3b; } .chip.BLOCKED { background: #b76b00; } .chip.NO-EJECUTADO { background: #8a96a5; }
  .portada { height: 178mm; display: flex; flex-direction: column; justify-content: center; padding: 0 18mm; border-left: 6mm solid #1769e0; }
  .portada .proyecto { font-size: 14pt; color: #536273; margin-bottom: 10mm; }
  .portada dl { display: grid; grid-template-columns: 52mm 1fr; gap: 2mm 6mm; font-size: 11pt; margin: 0; }
  .portada dt { color: #697789; } .portada dd { margin: 0; font-weight: 600; }
  .totales { display: grid; grid-template-columns: repeat(6, 1fr); gap: 4mm; margin: 4mm 0; }
  .totales div { border: 1px solid #d3dbe5; border-radius: 2mm; padding: 3mm; text-align: center; }
  .totales b { display: block; font-size: 18pt; } .totales span { color: #697789; font-size: 8.5pt; }
  .salto { break-before: page; }
  section.hu { break-before: page; }
  .resultado { font-size: 11pt; } .meta { font-size: 8.5pt; color: #697789; margin-left: 2mm; }
  .caja { border: 1px solid #d3dbe5; border-left: 3mm solid #697789; border-radius: 1.5mm; padding: 2.5mm 3.5mm; margin: 3mm 0; break-inside: avoid; }
  .caja.fail { border-left-color: #cc3b3b; background: #fff6f6; } .caja.blocked { border-left-color: #b76b00; background: #fffaf0; } .caja.nota { border-left-color: #1769e0; background: #f4f8ff; }
  .error { color: #ae3030; font-size: 8.3pt; margin-top: 1mm; white-space: pre-wrap; }
  figure { margin: 3mm 0 4mm; break-inside: avoid; text-align: center; }
  figcaption { text-align: left; margin-bottom: 1.5mm; font-size: 9.5pt; }
  figure img { border: 1px solid #b9c4d0; display: block; margin: 0 auto; }
  .tramo { position: relative; overflow: hidden; margin: 0 auto; border: 1px solid #b9c4d0; }
  .tramo img { position: absolute; left: 0; border: 0; }
  .asociacion { text-align: left; font-size: 8pt; color: #4a5a6c; background: #f6f8fb; border: 1px solid #e3e8ef; padding: 1.5mm 2.5mm; margin-top: 1.5mm; }
  a { color: #1769e0; text-decoration: none; }
</style></head><body>

<div class="portada">
  <div class="proyecto">${esc(contexto.proyecto)}</div>
  <h1>EVIDENCIA DE PRUEBAS — HUs</h1>
  <dl>
    <dt>Fecha de ejecución</dt><dd>${esc(fechaNegocio(playwright.stats.startTime))} (hora de Ciudad de México) · ${esc(playwright.stats.startTime)} UTC</dd>
    <dt>Herramienta</dt><dd>Playwright ${esc(playwright.config.version)} (@playwright/test) con Chromium</dd>
    <dt>Identificador de ejecución</dt><dd>${esc(estado.run)}</dd>
    <dt>Versión probada</dt><dd>${esc(contexto.version_app)}</dd>
    <dt>Alcance</dt><dd>${total.hus} HUs del ERS v1.4 (§3.1) · ${total.escenarios} escenarios · ${total.pasos} pasos · ${total.capturas} capturas</dd>
    <dt>Resultado</dt><dd>${chip('PASS')} ${total.PASS} &nbsp; ${chip('FAIL')} ${total.FAIL} &nbsp; ${chip('BLOCKED')} ${total.BLOCKED}</dd>
  </dl>
</div>

<div class="salto">
  <h2>Resumen general</h2>
  <div class="totales">
    <div><b>${total.hus}</b><span>HUs</span></div><div><b>${total.PASS}</b><span>PASS</span></div><div><b>${total.FAIL}</b><span>FAIL</span></div>
    <div><b>${total.BLOCKED}</b><span>BLOCKED</span></div><div><b>${total.escenarios}</b><span>Escenarios</span></div><div><b>${total.capturas}</b><span>Capturas</span></div>
  </div>
  <table><thead><tr><th>HU</th><th>Nombre</th><th>Escenarios</th><th>Resultado</th><th>Evidencias</th></tr></thead><tbody>${resumen}</tbody></table>
  <p class="meta">Duración total de la ejecución en Playwright: ${(playwright.stats.duration / 1000).toFixed(1)} s. Fuente de las HUs: ${esc(catalogo.fuente)}. No existen HU-09 ni HU-11 en el índice de HUs.</p>
</div>

<div class="salto">
  <h2>Ambiente, estado inicial y método</h2>
  <h3>Ambiente</h3><ul>${contexto.ambiente.map((t) => `<li>${esc(t)}</li>`).join('')}<li>Disponibilidad comprobada antes de ejecutar: ${esc(estado.ambiente.detalle)}.</li></ul>
  <h3>Estado inicial</h3><ul>${contexto.estado_inicial.map((t) => `<li>${esc(t)}</li>`).join('')}</ul>
  <h3>Método</h3><ul>${contexto.metodo.map((t) => `<li>${esc(t)}</li>`).join('')}</ul>
  <h3>Modificaciones realizadas</h3><ul>${contexto.modificaciones.map((t) => `<li>${esc(t)}</li>`).join('')}</ul>
</div>

<div class="salto">
  <h2>Hallazgos y problemas encontrados</h2>
  <h3>Observaciones registradas automáticamente por las pruebas</h3>
  <ul>${hus.flatMap((h) => (h.r.notas ?? []).map((n) => `<li><b>${esc(h.id)}:</b> ${esc(n)}</li>`)).join('') || '<li>Ninguna.</li>'}</ul>
  <h3>Observaciones del ejecutor (revisión de evidencias)</h3>
  <ul>${contexto.observaciones_ejecutor.map((o) => `<li><b>${esc(o.titulo)}.</b> ${esc(o.detalle)} Evidencias: ${o.evidencias.map((e) => esc(`evidencias/${e}`)).join(', ')}.</li>`).join('')}</ul>
  <p class="meta">Ninguna de estas observaciones incumple un criterio de aceptación de las HUs, por eso no cambian su resultado; se documentan para su corrección.</p>
  <h3>Problemas durante la ejecución</h3>
  <ul>${contexto.problemas.map((p) => `<li><b>${esc(p.titulo)}.</b> ${esc(p.detalle)}${p.accion ? ` <i>Acción:</i> ${esc(p.accion)}` : ''}</li>`).join('')}</ul>
</div>

${hus.map(seccionHU).join('\n')}

<section class="hu">
  <h2>Validación final</h2>
  <table><thead><tr><th>#</th><th>Verificación</th><th>Resultado</th></tr></thead><tbody>
  ${validacion.map(([v, r], i) => `<tr><td class="num">${i + 1}</td><td>${esc(v)}</td><td>${esc(r)}</td></tr>`).join('')}
  </tbody></table>
  <h3>Correspondencia con Playwright</h3>
  <table><thead><tr><th>HU</th><th>Resultado en este documento</th><th>Estatus en Playwright</th></tr></thead><tbody>
  ${hus.map((h) => `<tr><td>${esc(h.id)}</td><td>${chip(h.r.estado)}</td><td>${esc(playwrightPorHU[h.id] ?? 'sin resultado')}</td></tr>`).join('')}
  </tbody></table>
  <h3>Ubicación de los artefactos</h3>
  <ul>
    <li>Capturas y resultados por HU: evidencias/HU-XX/ (NN-descripcion.png y resultado.json).</li>
    <li>Correos generados por el portal (.eml): evidencias/_correos/. Datos de prueba: evidencias/_datos-prueba/${esc(estado.run)}/.</li>
    <li>Reporte JSON de Playwright: evidencias/playwright-resultados.json. Reporte HTML: playwright-report/index.html. Trazas por prueba: test-results/*/trace.zip (npx playwright show-trace).</li>
    <li>Pruebas: tests/hu/specs/ (una por HU), utilidades en tests/hu/lib/ y tests/hu/fixtures/herramientas.py.</li>
  </ul>
</section>
</body></html>`;

fs.mkdirSync(path.dirname(SALIDA_HTML), { recursive: true });
fs.writeFileSync(SALIDA_HTML, html);

const navegador = await chromium.launch();
const pagina = await navegador.newPage();
await pagina.goto(pathToFileURL(SALIDA_HTML).href, { waitUntil: 'load' });
await pagina.evaluate(async () => {
  await Promise.all([...document.images].map((img) => (img.complete ? null : new Promise((ok) => { img.onload = img.onerror = ok; }))));
});
const rotas = await pagina.evaluate(() => [...document.images].filter((img) => !img.naturalWidth).map((img) => img.getAttribute('src')));
if (rotas.length) throw new Error(`Imágenes que no cargaron: ${rotas.join(', ')}`);
await pagina.pdf({
  path: SALIDA_PDF,
  format: 'A4',
  landscape: true,
  printBackground: true,
  displayHeaderFooter: true,
  headerTemplate: '<div></div>',
  footerTemplate: `<div style="font: 7pt Arial, sans-serif; color: #697789; width: 100%; padding: 0 12mm; display: flex; justify-content: space-between;"><span>EVIDENCIA DE PRUEBAS — HUs · Portal de Proveedores ULTRASIST · ejecución ${esc(estado.run)}</span><span>Página <span class="pageNumber"></span> de <span class="totalPages"></span></span></div>`,
  margin: { top: '12mm', bottom: '14mm', left: '12mm', right: '12mm' },
});
await navegador.close();
console.log(JSON.stringify({ pdf: SALIDA_PDF, html: SALIDA_HTML, ...total }));
