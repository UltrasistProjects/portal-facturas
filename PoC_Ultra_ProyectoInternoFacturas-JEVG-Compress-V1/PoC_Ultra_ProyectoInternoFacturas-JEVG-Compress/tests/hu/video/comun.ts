import { expect, type Locator, type Page } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
import type { Correo } from '../lib/estado';
import { clicNavegando } from '../lib/portal';
import { APP_ROOT } from '../lib/rutas';

// Utilidades de los recorridos en video: capa con rotulo y cursor, tarjetas entre partes, correos del buzon, resaltado
// de elementos y cargas de archivos paso a paso, con pausas para que el video se pueda seguir.

// Incrustado: una about:blank a la que se llega navegando no carga imagenes del portal.
export const LOGO = `data:image/png;base64,${fs.readFileSync(path.join(APP_ROOT, 'app', 'static', 'img', 'Ferromexlogo.png')).toString('base64')}`;

/** Capa del video (rotulo inferior y cursor visible), instalada en cada documento que abre la pagina. */
export function instalarCapa(): void {
  const w = window as any;
  if (w.__recorrido) return;
  let raiz: ShadowRoot | null = null;
  const obtener = (): ShadowRoot => {
    if (raiz) return raiz;
    const host = document.createElement('div');
    host.style.cssText = 'position:fixed;inset:0;pointer-events:none;z-index:2147483647';
    (document.body ?? document.documentElement).appendChild(host);
    raiz = host.attachShadow({ mode: 'open' });
    // La CSP del portal (default-src 'self') bloquea <style> en linea; una hoja construida no esta sujeta a ella.
    const hoja = new CSSStyleSheet();
    hoja.replaceSync(`
      .cursor{position:fixed;left:0;top:0;width:22px;height:22px;border-radius:50%;opacity:0;
        background:rgba(245,158,11,.35);border:2px solid #f59e0b;transition:transform .12s ease-out,opacity .2s}
      .cursor.clic{background:rgba(245,158,11,.8);box-shadow:0 0 0 10px rgba(245,158,11,.25)}
      .rotulo{position:fixed;left:50%;bottom:22px;transform:translate(-50%,12px);max-width:1080px;opacity:0;
        display:flex;gap:14px;align-items:center;padding:12px 22px;border-radius:12px;
        background:rgba(15,23,42,.9);color:#fff;font:500 19px/1.35 system-ui,'Segoe UI',Arial,sans-serif;
        box-shadow:0 8px 28px rgba(0,0,0,.3);transition:opacity .3s,transform .3s}
      .rotulo.visible{opacity:1;transform:translate(-50%,0)}
      .etapa{flex:none;font-size:13px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:#fbbf24}
    `);
    raiz.adoptedStyleSheets = [hoja];
    raiz.innerHTML = '<div class="cursor"></div><div class="rotulo"><span class="etapa"></span><span class="texto"></span></div>';
    return raiz;
  };
  window.addEventListener('mousemove', (e) => {
    const cursor = obtener().querySelector('.cursor') as HTMLElement;
    cursor.style.transform = `translate(${e.clientX - 11}px, ${e.clientY - 11}px)`;
    cursor.style.opacity = '1';
  }, true);
  window.addEventListener('mousedown', () => {
    const cursor = obtener().querySelector('.cursor') as HTMLElement;
    cursor.classList.add('clic');
    setTimeout(() => cursor.classList.remove('clic'), 350);
  }, true);
  w.__recorrido = {
    rotulo(etapa: string, texto: string) {
      const r = obtener();
      (r.querySelector('.etapa') as HTMLElement).textContent = etapa;
      (r.querySelector('.texto') as HTMLElement).textContent = texto;
      // Tras un cambio de pagina, un cuadro despues para que se vea la transicion.
      requestAnimationFrame(() => r.querySelector('.rotulo')?.classList.toggle('visible', Boolean(texto)));
    },
  };
}

export function escapar(texto: string): string {
  return texto.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c] as string);
}

export const ESTILO_TARJETA = `margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
  font-family:system-ui,'Segoe UI',Arial,sans-serif;background:linear-gradient(135deg,#0b1f3a,#16406f);color:#fff`;

/** Pagina propia del video. setContent conserva el origen y la CSP de la pagina actual (el portal bloquea los estilos
 * en linea), asi que primero se pasa a about:blank, que no tiene CSP. */
export async function pantalla(page: Page, html: string): Promise<void> {
  await page.goto('about:blank');
  await page.setContent(html, { waitUntil: 'load' });
}

/** Tarjeta de titulo a pantalla completa entre las partes del recorrido. */
export async function tarjeta(page: Page, antetitulo: string, titulo: string, puntos: string[], ms = 5000): Promise<void> {
  await pantalla(page, `<!doctype html><html lang="es"><head><meta charset="utf-8"></head>
    <body style="${ESTILO_TARJETA}"><main style="max-width:1000px;padding:48px">
      <img src="${LOGO}" alt="" style="height:54px;background:#fff;padding:8px 14px;border-radius:10px">
      <p style="margin:36px 0 8px;font-size:18px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:#fbbf24">${escapar(antetitulo)}</p>
      <h1 style="margin:0 0 28px;font-size:46px;line-height:1.15">${escapar(titulo)}</h1>
      <ul style="margin:0;padding-left:26px;font-size:24px;line-height:1.7;color:#dbe7f5">${puntos.map((p) => `<li>${escapar(p)}</li>`).join('')}</ul>
    </main></body></html>`);
  await page.waitForTimeout(ms);
}

/** Muestra un correo que genero el portal (archivo .eml del transporte "file"), como lo veria su destinatario. */
export async function mostrarCorreo(page: Page, titulo: string, correo: Correo, ms = 8000): Promise<void> {
  const cuerpo = correo.html
    ? `<iframe sandbox srcdoc="${escapar(correo.html)}" style="flex:1;width:100%;border:0;background:#fff"></iframe>`
    : `<pre style="flex:1;margin:0;padding:20px;white-space:pre-wrap;font:15px/1.5 system-ui">${escapar(correo.texto)}</pre>`;
  const fila = (campo: string, valor: string) =>
    `<tr><td style="color:#697789;padding:3px 16px 3px 0">${campo}</td><td>${escapar(valor)}</td></tr>`;
  await pantalla(page, `<!doctype html><html lang="es"><head><meta charset="utf-8"></head>
    <body style="${ESTILO_TARJETA};align-items:stretch"><main style="width:1100px;margin:28px auto;display:flex;flex-direction:column">
      <p style="margin:0 0 12px;font-size:16px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:#fbbf24">
        <span style="font-size:20px">✉</span> ${escapar(titulo)}</p>
      <section style="flex:1;display:flex;flex-direction:column;background:#fff;color:#152235;border-radius:12px;overflow:hidden;box-shadow:0 12px 40px rgba(0,0,0,.35)">
        <table style="border-collapse:collapse;font-size:15px;margin:16px 20px;align-self:flex-start">
          ${fila('De', correo.de)}${fila('Para', correo.para.join(', '))}${correo.cc.length ? fila('Cc', correo.cc.join(', ')) : ''}
          <tr><td style="color:#697789;padding:3px 16px 3px 0">Asunto</td><td><strong>${escapar(correo.asunto)}</strong></td></tr>
        </table>
        <div style="flex:1;display:flex;border-top:1px solid #dde3ea">${cuerpo}</div>
      </section></main></body></html>`);
  await page.waitForTimeout(ms);
}

/** Desplaza suavemente hasta el elemento, lo resalta y deja tiempo para leerlo. */
export async function senalar(page: Page, objetivo: Locator, ms = 2200, desplazar = true): Promise<void> {
  const elemento = objetivo.first();
  if (desplazar) {
    await elemento.evaluate((el) => el.scrollIntoView({ behavior: 'smooth', block: 'center' }));
    await page.waitForTimeout(700);
  }
  await elemento.evaluate((el, duracion) => {
    const h = el as HTMLElement;
    const previo = [h.style.outline, h.style.outlineOffset, h.style.borderRadius];
    Object.assign(h.style, { outline: '3px solid #f59e0b', outlineOffset: '4px', borderRadius: h.style.borderRadius || '6px' });
    setTimeout(() => ([h.style.outline, h.style.outlineOffset, h.style.borderRadius] = previo), duracion);
  }, ms);
  await page.waitForTimeout(ms);
}

export async function escribir(campo: Locator, texto: string): Promise<void> {
  await campo.click();
  await campo.fill('');
  await campo.pressSequentially(texto, { delay: 30 });
}

export async function loginKeycloak(page: Page, usuario: string, contrasena: string): Promise<void> {
  await page.goto('/login');
  await expect(page.locator('#username')).toBeVisible();
  await escribir(page.locator('#username'), usuario);
  await escribir(page.locator('#password'), contrasena);
  await clicNavegando(page, page.locator('#kc-login'));
}

export async function iniciarSesion(page: Page, usuario: string, contrasena: string): Promise<void> {
  await loginKeycloak(page, usuario, contrasena);
  await expect(page.locator('.sidebar-footer')).toContainText(usuario);
}

export async function cerrarSesion(page: Page): Promise<void> {
  // Sin desplazar: el boton esta al pie de la barra lateral fija, y desplazarla cortaria el logo.
  await senalar(page, page.getByRole('button', { name: 'Cerrar sesion' }), 900, false);
  await clicNavegando(page, page.getByRole('button', { name: 'Cerrar sesion' }));
}

// El nombre accesible del enlace empieza con el glifo del icono (Bootstrap Icons): se ignora lo que no es texto.
export const menu = (page: Page, nombre: string) => page.locator('.sidebar').getByRole('link', { name: new RegExp(`^\\W*${nombre}\\s*$`) });


/** Muestra el Excel lleno como hoja de calculo (las filas que se van a cargar). */
export async function mostrarExcel(
  page: Page,
  archivo: string,
  libro: { hojas: string[]; encabezados: string[]; filas: (string | null)[][] },
  ms = 10000,
): Promise<void> {
  const letras = libro.encabezados.map((_, i) => String.fromCharCode(65 + i));
  const celda = (valor: string | null, estilo = '') =>
    `<td style="border:1px solid #d4d9df;padding:7px 9px;vertical-align:top;${estilo}">${escapar(valor ?? '')}</td>`;
  const encabezado = (valor: string) =>
    `<th style="border:1px solid #c3c9d0;padding:5px 8px;background:#eef1f4;color:#5b6773;font-weight:500">${escapar(valor)}</th>`;
  await pantalla(page, `<!doctype html><html lang="es"><head><meta charset="utf-8"></head>
    <body style="${ESTILO_TARJETA};align-items:stretch"><main style="width:1380px;margin:28px auto;display:flex;flex-direction:column">
      <p style="margin:0 0 12px;font-size:16px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:#fbbf24">
        Plantilla llena · ${libro.filas.length} proveedores por cargar</p>
      <section style="background:#fff;color:#1f2933;border-radius:10px;overflow:hidden;box-shadow:0 12px 40px rgba(0,0,0,.35)">
        <div style="background:#107c41;color:#fff;padding:10px 18px;font-size:15px;font-weight:600">${escapar(archivo)}</div>
        <table style="border-collapse:collapse;font-size:13px;width:100%">
          <tr>${encabezado('')}${letras.map(encabezado).join('')}</tr>
          <tr>${encabezado('1')}${libro.encabezados.map((h) => celda(h, 'font-weight:700;background:#f7f9fa')).join('')}</tr>
          ${libro.filas.map((fila, i) => `<tr>${encabezado(String(i + 2))}${fila.map((v) => celda(v)).join('')}</tr>`).join('')}
        </table>
        <div style="display:flex;gap:2px;padding:0 12px;background:#eef1f4;border-top:1px solid #c3c9d0;font-size:13px">
          ${libro.hojas.map((h, i) => `<span style="padding:6px 16px;${i === 0 ? 'background:#fff;color:#107c41;font-weight:700;border-bottom:2px solid #107c41' : 'color:#5b6773'}">${escapar(h)}</span>`).join('')}
        </div>
      </section></main></body></html>`);
  await page.waitForTimeout(ms);
}

/** Carga documental de la factura paso a paso: tipo, archivo, "Cargar documento" y el renglon que queda cargado. */
export async function subirDocumento(page: Page, tipo: string, archivo: string, etiqueta: string, conChecklist = true): Promise<void> {
  const formulario = page.locator('form.upload-form');
  await senalar(page, formulario, 1000);
  await page.locator('#document_type').selectOption(tipo);
  await senalar(page, page.locator('#document_type'), 1500, false);
  await formulario.locator('input[name=upload]').setInputFiles(archivo);
  // El input de archivo va oculto dentro de su zona de carga (label.dropzone), que muestra el nombre elegido.
  await senalar(page, formulario.locator('label.dropzone').or(formulario.locator('input[name=upload]')), 2000, false);
  await clicNavegando(page, page.getByRole('button', { name: 'Cargar documento' }));
  await senalar(page, page.locator('.document-row').filter({ hasText: etiqueta }), 2200);
  if (conChecklist) await senalar(page, page.locator('.required-summary'), 1800);
}

/** Requisitos de alta pendientes del expediente abierto, uno por uno (HU-21). `ritmo` < 1 acorta las pausas. */
export async function subirRequisitosAlta(
  page: Page,
  archivo: string,
  avance: (nombre: string, n: number, total: number) => Promise<void>,
  ritmo = 1,
): Promise<void> {
  const pausa = (ms: number) => Math.round(ms * ritmo);
  const pendientes = (
    await page.locator('.requirements-panel .document-row').filter({ hasText: 'Obligatorio · Pendiente' }).locator('strong').allInnerTexts()
  ).map((nombre) => nombre.trim());
  await senalar(page, page.locator('.requirements-summary'), pausa(2500));
  for (const [i, nombre] of pendientes.entries()) {
    await avance(nombre, i + 1, pendientes.length);
    const formulario = page.locator('details.admin-create').filter({ hasText: 'Agregar o reemplazar documento del expediente' });
    if (!(await formulario.evaluate((el) => (el as HTMLDetailsElement).open))) await formulario.locator('summary').click();
    await senalar(page, formulario, pausa(1000));
    await formulario.locator('#supplier-document-type').selectOption({ label: `${nombre} (obligatorio)` });
    await senalar(page, formulario.locator('#supplier-document-type'), pausa(1400), false);
    await formulario.locator('input[name=upload]').setInputFiles(archivo);
    await senalar(page, formulario.locator('input[name=upload]'), pausa(1600), false);
    await clicNavegando(page, formulario.getByRole('button', { name: 'Guardar documento' }));
    await senalar(page, page.locator('.requirements-panel .document-row').filter({ hasText: nombre }), pausa(1800));
  }
}

/** Instala la capa del video en la pagina y devuelve `rotular`: el rotulo inferior se conserva al cambiar de pagina. */
export async function capaDeVideo(page: Page): Promise<(etapa: string, texto: string) => Promise<void>> {
  let actual: [string, string] = ['', ''];
  await page.context().addInitScript(instalarCapa);
  page.on('domcontentloaded', () => {
    void page.evaluate(([etapa, texto]) => (window as any).__recorrido?.rotulo(etapa, texto), actual).catch(() => undefined);
  });
  return async (etapa: string, texto: string): Promise<void> => {
    actual = [etapa, texto];
    await page.evaluate(([e, t]) => (window as any).__recorrido?.rotulo(e, t), actual).catch(() => undefined);
  };
}

/** Cierra el contexto (asi Playwright termina de escribir el video) y lo guarda en `destino`. */
export async function guardarVideo(page: Page, destino: string): Promise<void> {
  const video = page.video();
  await page.context().close();
  fs.mkdirSync(path.dirname(destino), { recursive: true });
  await video?.saveAs(destino);
}
