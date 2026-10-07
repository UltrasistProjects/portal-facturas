import { expect, test, type Locator, type Page } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
import { buscarCorreo, demoPassword, herramienta, type Correo } from '../lib/estado';
import { CUENTAS } from '../lib/hu';
import { abrirExpediente, clicNavegando, enviarAlta, enviarAValidacion } from '../lib/portal';
import { APP_ROOT, EVIDENCIAS } from '../lib/rutas';

// Recorrido del flujo completo en una sola pagina (un solo video): el Administrador da de alta y autoriza
// proveedores y crea un usuario PMO, un proveedor nuevo entra por primera vez, un proveedor con contrato registra y
// envia una factura, el PMO nuevo entra por primera vez, la autoriza y registra el pago, y el proveedor adjunta el
// Complemento de Pago. Los roles se cambian cerrando sesion. Requiere el portal con MAIL_BACKEND=file (ver
// tests/hu/README.md): los correos se muestran desde el buzon. Las cargas de archivos van paso a paso, con pausas.

const VIDEO = path.join(EVIDENCIAS, 'video', 'recorrido-flujo-completo.webm');
// Incrustado: una about:blank a la que se llega navegando no carga imagenes del portal.
const LOGO = `data:image/png;base64,${fs.readFileSync(path.join(APP_ROOT, 'app', 'static', 'img', 'Ultrasistlogo.png')).toString('base64')}`;

/** Capa del video (rotulo inferior y cursor visible), instalada en cada documento que abre la pagina. */
function instalarCapa(): void {
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

function escapar(texto: string): string {
  return texto.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c] as string);
}

const ESTILO_TARJETA = `margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
  font-family:system-ui,'Segoe UI',Arial,sans-serif;background:linear-gradient(135deg,#0b1f3a,#16406f);color:#fff`;

/** Pagina propia del video. setContent conserva el origen y la CSP de la pagina actual (el portal bloquea los estilos
 * en linea), asi que primero se pasa a about:blank, que no tiene CSP. */
async function pantalla(page: Page, html: string): Promise<void> {
  await page.goto('about:blank');
  await page.setContent(html, { waitUntil: 'load' });
}

/** Tarjeta de titulo a pantalla completa entre las partes del recorrido. */
async function tarjeta(page: Page, antetitulo: string, titulo: string, puntos: string[], ms = 5000): Promise<void> {
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
async function mostrarCorreo(page: Page, titulo: string, correo: Correo, ms = 8000): Promise<void> {
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
async function senalar(page: Page, objetivo: Locator, ms = 2200, desplazar = true): Promise<void> {
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

async function escribir(campo: Locator, texto: string): Promise<void> {
  await campo.click();
  await campo.fill('');
  await campo.pressSequentially(texto, { delay: 30 });
}

async function loginKeycloak(page: Page, usuario: string, contrasena: string): Promise<void> {
  await page.goto('/login');
  await expect(page.locator('#username')).toBeVisible();
  await escribir(page.locator('#username'), usuario);
  await escribir(page.locator('#password'), contrasena);
  await clicNavegando(page, page.locator('#kc-login'));
}

async function iniciarSesion(page: Page, usuario: string, contrasena: string): Promise<void> {
  await loginKeycloak(page, usuario, contrasena);
  await expect(page.locator('.sidebar-footer')).toContainText(usuario);
}

async function cerrarSesion(page: Page): Promise<void> {
  // Sin desplazar: el boton esta al pie de la barra lateral fija, y desplazarla cortaria el logo.
  await senalar(page, page.getByRole('button', { name: 'Cerrar sesion' }), 900, false);
  await clicNavegando(page, page.getByRole('button', { name: 'Cerrar sesion' }));
}

// El nombre accesible del enlace empieza con el glifo del icono (Bootstrap Icons): se ignora lo que no es texto.
const menu = (page: Page, nombre: string) => page.locator('.sidebar').getByRole('link', { name: new RegExp(`^\\W*${nombre}\\s*$`) });


/** Muestra el Excel lleno como hoja de calculo (las filas que se van a cargar). */
async function mostrarExcel(
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
async function subirDocumento(page: Page, tipo: string, archivo: string, etiqueta: string, conChecklist = true): Promise<void> {
  const formulario = page.locator('form.upload-form');
  await senalar(page, formulario, 1000);
  await page.locator('#document_type').selectOption(tipo);
  await senalar(page, page.locator('#document_type'), 1500, false);
  await formulario.locator('input[name=upload]').setInputFiles(archivo);
  await senalar(page, formulario.locator('input[name=upload]'), 2000, false);
  await clicNavegando(page, page.getByRole('button', { name: 'Cargar documento' }));
  await senalar(page, page.locator('.document-row').filter({ hasText: etiqueta }), 2200);
  if (conChecklist) await senalar(page, page.locator('.required-summary'), 1800);
}

/** Requisitos de alta pendientes del expediente abierto, uno por uno (HU-21). `ritmo` < 1 acorta las pausas. */
async function subirRequisitosAlta(
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

test('Recorrido del flujo completo del portal', async ({ page }) => {
  const run = `V${Date.now().toString(36).toUpperCase()}`;
  const carpeta = path.join(APP_ROOT, 'test-results', 'recorrido-datos', run);
  fs.mkdirSync(carpeta, { recursive: true });
  const fx = herramienta('fixtures', run, carpeta);
  const clave = demoPassword();
  const numero = `FAC-${run}`;
  const pmo = { nombre: `PMO de Proyectos ${run}`, correo: `pmo.${run.toLowerCase()}@ultrasist-qa.example`, clave: `Pmo#${run}x7` };
  let facturaId = 0;

  let actual: [string, string] = ['', ''];
  await page.context().addInitScript(instalarCapa);
  page.on('domcontentloaded', () => {
    void page.evaluate(([etapa, texto]) => (window as any).__recorrido?.rotulo(etapa, texto), actual).catch(() => undefined);
  });
  const rotular = async (etapa: string, texto: string): Promise<void> => {
    actual = [etapa, texto];
    await page.evaluate(([e, t]) => (window as any).__recorrido?.rotulo(e, t), actual).catch(() => undefined);
  };

  await tarjeta(page, 'Portal de Proveedores ULTRASIST', 'Recorrido del flujo completo', [
    '1. Administrador: alta y autorización de proveedores',
    '2. Administrador: alta del usuario PMO',
    '3. Proveedor nuevo: primer acceso y cambio de contraseña',
    '4. Proveedor: registro y envío de una factura',
    '5. PMO: primer acceso, revisión, autorización y pago',
    '6. Proveedor: Complemento de Pago',
  ], 7000);

  // ---------------------------------------------------------------- 1. Administrador: alta de proveedores
  await tarjeta(page, 'Parte 1 de 6 · Administrador', 'Alta y autorización de proveedores', [
    'Carga masiva con la plantilla de Excel',
    'Requisitos de alta en el expediente de cada proveedor',
    'Autorización masiva y envío automático de credenciales',
  ]);
  await rotular('Administrador', 'El portal redirige al inicio de sesión de Keycloak, el proveedor de identidad');
  await iniciarSesion(page, CUENTAS.admin, clave);
  await rotular('Administrador', 'Tablero con el resumen operativo de la recepción de facturas');
  await page.waitForTimeout(3000);

  await clicNavegando(page, menu(page, 'Proveedores'));
  await rotular('Administrador · Proveedores', 'Catálogo de proveedores: aquí empieza el alta');
  await page.waitForTimeout(2500);
  await senalar(page, page.getByRole('link', { name: /Carga masiva/ }), 1500);
  await clicNavegando(page, page.getByRole('link', { name: /Carga masiva/ }));
  await rotular('Administrador · Carga masiva', 'Instrucciones: se captura en la hoja "Proveedores", sin cambiar los encabezados');
  await senalar(page, page.locator('ol').filter({ hasText: 'Descargue la plantilla' }), 4500);
  await rotular('Administrador · Carga masiva', 'Se descarga la plantilla de Excel');
  await senalar(page, page.getByRole('link', { name: /Descargar plantilla/ }), 2000);
  const [descarga] = await Promise.all([page.waitForEvent('download'), page.getByRole('link', { name: /Descargar plantilla/ }).click()]);
  const plantilla = path.join(carpeta, descarga.suggestedFilename());
  await descarga.saveAs(plantilla);
  const nombreLlena = `carga_proveedores_${run}.xlsx`;
  const llena = path.join(carpeta, nombreLlena);
  const proveedores: { razon_social: string; rfc: string | null; id_fiscal: string | null; correo: string }[] =
    herramienta('plantilla-proveedores', plantilla, llena, run, 'validos').filas;
  await mostrarExcel(page, nombreLlena, herramienta('inspeccionar-xlsx', llena));

  await page.goto('/suppliers/import');
  await rotular('Administrador · Carga masiva', 'Se selecciona el archivo lleno: 2 proveedores nacionales y 1 internacional');
  await page.waitForTimeout(1200);
  await page.locator('#supplier-import-file').setInputFiles(llena);
  await senalar(page, page.locator('#supplier-import-file'), 2500);
  await senalar(page, page.locator('#supplier-import-submit'), 1500, false);
  await page.locator('#supplier-import-submit').click();
  await expect(page.locator('#supplier-import-summary-text')).toContainText('3 proveedores registrados');
  await rotular('Administrador · Carga masiva', 'Resultado: 3 filas leídas y 3 proveedores registrados, sin errores');
  await senalar(page, page.locator('#supplier-import-summary'), 4500);

  await page.goto(`/suppliers?q=${encodeURIComponent(run)}&status=REGISTERED`);
  await rotular('Administrador · Proveedores', 'Los 3 proveedores quedan "Registrado": todavía no tienen acceso al portal');
  await senalar(page, page.locator('table tbody'), 4500);

  for (const [i, proveedor] of proveedores.filter((p) => p.rfc).entries()) {
    await rotular('Administrador · Expediente', `Expediente de ${proveedor.razon_social}: faltan sus requisitos de alta obligatorios`);
    await abrirExpediente(page, proveedor.razon_social);
    await page.waitForTimeout(1500);
    await subirRequisitosAlta(
      page,
      fx.requisito_alta,
      (nombre, n, total) => rotular('Administrador · Expediente', `Requisito ${n} de ${total}: ${nombre}`),
      i === 0 ? 1 : 0.6,
    );
    await expect(page.locator('.requirements-summary')).toHaveText('Requisitos de alta completos');
    await rotular('Administrador · Expediente', 'Requisitos de alta completos: el proveedor ya se puede autorizar');
    await senalar(page, page.locator('.requirements-summary'), 2500);
  }

  await clicNavegando(page, menu(page, 'Proveedores'));
  await rotular('Administrador · Autorización masiva', 'Se filtran los proveedores "Registrado" y se seleccionan los nuevos');
  await page.locator('select[name=status]').selectOption('REGISTERED');
  await escribir(page.locator('input[name=q]'), run);
  await clicNavegando(page, page.getByRole('button', { name: 'Filtrar' }));
  for (const proveedor of proveedores) {
    await page.locator('table tbody tr').filter({ hasText: proveedor.razon_social }).locator('input.authorize-check').check();
    await page.waitForTimeout(500);
  }
  await expect(page.locator('#authorize-count')).toHaveText('3 seleccionados');
  await senalar(page, page.locator('#authorize-count'), 1800);
  await page.locator('#authorize-submit').click();
  await expect(page.locator('#authorize-confirm')).toBeVisible();
  await rotular('Administrador · Autorización masiva', 'Al confirmar, cada proveedor recibe por correo su usuario y una contraseña temporal');
  await page.waitForTimeout(3500);
  const desdeAutorizacion = new Date(Date.now() - 2000).toISOString();
  await Promise.all([page.waitForURL(/\/suppliers/), page.locator('#authorize-confirm-accept').click()]);
  await expect(page.locator('.authorization-summary .panel-header p')).toHaveText('3 autorizados · 0 omitidos · 0 no autorizados');
  await rotular('Administrador · Autorización masiva', 'Los 3 proveedores quedan "Autorizado" en una sola operación');
  await senalar(page, page.locator('.authorization-summary'), 4000);

  const nuevo = proveedores[0];
  const credenciales = buscarCorreo(nuevo.correo, 'Acceso al Portal de Proveedores ULTRASIST', desdeAutorizacion);
  const temporal = credenciales?.texto.match(/Contraseña temporal: (\S+)/)?.[1];
  if (!credenciales || !temporal) throw new Error(`No se generó el correo de credenciales de ${nuevo.correo}`);
  await mostrarCorreo(page, `Correo que recibe el proveedor ${nuevo.razon_social}`, credenciales);

  // ---------------------------------------------------------------- 2. Administrador: alta del PMO
  await tarjeta(page, 'Parte 2 de 6 · Administrador', 'Alta del usuario PMO', [
    'Administración › Usuarios',
    'Usuario con rol PMO (sin proveedor)',
    'Contraseña temporal que se entrega por un medio seguro',
  ]);
  await page.goto('/');
  await clicNavegando(page, menu(page, 'Usuarios'));
  await rotular('Administrador · Usuarios', 'Usuarios del portal y su rol; las credenciales se gestionan en Keycloak');
  await page.waitForTimeout(3000);
  const crear = page.locator('details.admin-create');
  await crear.locator('summary').click();
  await rotular('Administrador · Nuevo usuario', 'Se capturan el nombre y el correo, y se elige el rol PMO');
  await senalar(page, crear, 1500);
  await escribir(page.locator('#user-name'), pmo.nombre);
  await escribir(page.locator('#user-email'), pmo.correo);
  await page.locator('#user-role').selectOption('PMO');
  await senalar(page, page.locator('#user-role'), 1800, false);
  await senalar(page, crear.locator('p.form-text'), 2500, false);
  await clicNavegando(page, crear.getByRole('button', { name: 'Crear usuario' }));
  await expect(page.locator('.alert-success')).toHaveText('Usuario creado');
  const temporalPmo = (await page.locator('.temporary-credentials code').innerText()).trim();
  await rotular('Administrador · Nuevo usuario', 'Usuario creado en Keycloak: la contraseña temporal se muestra una sola vez');
  await senalar(page, page.locator('.temporary-credentials'), 4500);
  await rotular('Administrador · Usuarios', 'El nuevo usuario aparece con el rol PMO y sin accesos todavía');
  await senalar(page, page.locator('table tbody tr').filter({ hasText: pmo.correo }), 3000);
  await rotular('Administrador', 'Cierra sesión');
  await cerrarSesion(page);

  // ---------------------------------------------------------------- 3. Proveedor nuevo: primer acceso
  await tarjeta(page, 'Parte 3 de 6 · Proveedor nuevo', 'Primer acceso al portal', [
    'Inicio de sesión con el usuario y la contraseña temporal del correo',
    'Cambio obligatorio de la contraseña temporal',
    'Entrada al portal con su propia contraseña',
  ]);
  await rotular('Proveedor nuevo', `Inicia sesión como ${nuevo.correo} con la contraseña temporal`);
  await loginKeycloak(page, nuevo.correo, temporal);
  await expect(page).toHaveURL(/required-action\?execution=UPDATE_PASSWORD/);
  await rotular('Proveedor nuevo', 'Keycloak exige cambiar la contraseña temporal: mínimo 8 caracteres con letra, número y carácter especial');
  await page.waitForTimeout(3500);
  const nueva = `Demo#${run}x9`;
  await escribir(page.locator('#password-new'), nueva);
  await escribir(page.locator('#password-confirm'), nueva);
  await page.locator('#kc-submit').click();
  await expect(page.locator('.sidebar-footer')).toContainText(nuevo.correo);
  await rotular('Proveedor nuevo', 'Ya entra al portal con su propia contraseña y el rol Proveedor');
  await senalar(page, page.locator('.sidebar-footer'), 3000, false);
  await cerrarSesion(page);

  // ---------------------------------------------------------------- 4. Proveedor: registro y envio de factura
  await tarjeta(page, 'Parte 4 de 6 · Proveedor', 'Registro y envío de una factura', [
    'Proveedor nacional con contrato activo (Tecnología Integral del Centro)',
    'Carga del XML y PDF del CFDI, la orden de compra y el Vo.Bo.',
    'Prevalidación automática contra las reglas y envío a validación',
  ]);
  await rotular('Proveedor', 'Inicia sesión un proveedor que ya opera con ULTRASIST');
  await iniciarSesion(page, CUENTAS.proveedor1, clave);
  await rotular('Proveedor', 'Tablero del proveedor: sus facturas y avisos');
  await page.waitForTimeout(3000);
  await senalar(page, page.getByRole('link', { name: /Nueva factura/ }).first(), 1500);
  await clicNavegando(page, page.getByRole('link', { name: /Nueva factura/ }).first());
  await rotular('Proveedor · Nueva factura', 'Sólo se ofrecen los contratos activos del propio proveedor; el proyecto se toma del contrato');
  await senalar(page, page.locator('#contract'), 3000);
  await rotular('Proveedor · Nueva factura', 'Se capturan el número de factura, el periodo del servicio y la orden de compra');
  await escribir(page.locator('input[name=invoice_number]'), numero);
  await escribir(page.locator('input[name=service_period]'), '08/2026');
  await escribir(page.locator('input[name=purchase_order_number]'), `OC-${numero}`);
  await page.waitForTimeout(2000);
  facturaId = await enviarAlta(page);
  await rotular('Proveedor · Carga documental', 'Checklist de los 4 archivos obligatorios del proveedor nacional');
  await senalar(page, page.locator('.required-summary'), 3000);
  const documentos = [
    ['INVOICE_XML', fx.cfdi_ppd, 'XML del CFDI', 'XML del CFDI: de él salen los datos fiscales que se validan'],
    ['INVOICE_PDF', fx.pdf_cfdi, 'PDF del CFDI', 'PDF del CFDI: la representación impresa de la factura'],
    ['PURCHASE_ORDER', fx.orden_compra, 'Orden de compra', 'Orden de compra del servicio'],
    ['APPROVAL', fx.vobo, 'Vo.Bo. del líder de proyecto', 'Vo.Bo. del líder de proyecto'],
  ] as const;
  for (const [i, [tipo, archivo, etiqueta, descripcion]] of documentos.entries()) {
    await rotular('Proveedor · Carga documental', `Documento ${i + 1} de ${documentos.length} · ${descripcion}`);
    await subirDocumento(page, tipo, archivo, etiqueta);
  }
  await expect(page.locator('.required-summary')).toContainText('Archivos obligatorios completos');
  await rotular('Proveedor · Carga documental', 'Archivos obligatorios completos: la factura queda "Cargada"');
  await senalar(page, page.locator('.required-summary'), 3000);

  await page.goto(`/invoices/${facturaId}`);
  await expect(page.locator('.page-heading .status')).toHaveText('Cargada');
  await rotular('Proveedor · Envío', 'Al enviarla, el portal valida el XML del CFDI contra las Reglas de Validación');
  await senalar(page, page.locator('.page-heading'), 2500);
  await enviarAValidacion(page);
  await expect(page.locator('.page-heading .status')).toHaveText('Enviada');
  await rotular('Proveedor · Envío', 'Sin reglas que lo impidan, la factura pasa a "Enviada" y ya no se puede modificar');
  await senalar(page, page.locator('.page-heading .status'), 3000);
  await rotular('Proveedor · Prevalidación', 'Matriz de evidencia: cada regla con el valor esperado y el detectado en el XML');
  await senalar(page, page.locator('#validations'), 2500);
  const regla = page.locator('#validations details.rule-card').filter({ hasText: 'XML-002' }).first();
  await regla.locator('summary').click();
  await senalar(page, regla, 3500);
  await cerrarSesion(page);

  // ---------------------------------------------------------------- 5. PMO: primer acceso, revision, autorizacion y pago
  await tarjeta(page, 'Parte 5 de 6 · PMO', 'Revisión, autorización y registro del pago', [
    'Primer acceso del PMO creado en la parte 2',
    'Consulta de las facturas enviadas y su detalle',
    'Autorización con aviso a Recepción de Facturas',
    'Registro del pago y aviso al proveedor',
  ]);
  await rotular('PMO', `Primer acceso de ${pmo.correo} con la contraseña temporal que le entregó el Administrador`);
  await loginKeycloak(page, pmo.correo, temporalPmo);
  await expect(page).toHaveURL(/required-action\?execution=UPDATE_PASSWORD/);
  await rotular('PMO', 'Keycloak le pide definir su propia contraseña antes de entrar');
  await page.waitForTimeout(3000);
  await escribir(page.locator('#password-new'), pmo.clave);
  await escribir(page.locator('#password-confirm'), pmo.clave);
  await page.locator('#kc-submit').click();
  await expect(page.locator('.sidebar-footer')).toContainText(pmo.correo);
  await rotular('PMO', 'Tablero del PMO con el resumen de facturas');
  await senalar(page, page.locator('.sidebar-footer'), 2500, false);
  await clicNavegando(page, menu(page, 'Facturas'));
  await rotular('PMO · Facturas', 'Se filtran las facturas "Enviada", pendientes de decisión');
  await page.locator('select[name=status]').selectOption('UNDER_REVIEW');
  await escribir(page.locator('input[name=q]'), numero);
  await clicNavegando(page, page.getByRole('button', { name: 'Filtrar' }));
  const fila = page.locator('table tbody tr').filter({ hasText: numero }).first();
  await senalar(page, fila, 2500);
  await clicNavegando(page, fila.locator('a.icon-action'));
  await rotular('PMO · Detalle', 'Detalle de la factura: datos del CFDI, documentos y prevalidación');
  await page.waitForTimeout(3000);
  await senalar(page, page.locator('.document-list'), 3000);

  await clicNavegando(page, page.getByRole('link', { name: /Decidir/ }));
  await rotular('PMO · Decisión', 'Tres opciones: Autorizar, Observaciones o Rechazar (estas dos piden la causa)');
  await senalar(page, page.locator('#decision'), 3500);
  await page.locator('#decision').getByRole('button', { name: 'Autorizar' }).click();
  await expect(page.locator('#decision-confirm')).toBeVisible();
  await page.waitForTimeout(3000);
  const desdeAutorizada = new Date(Date.now() - 2000).toISOString();
  await clicNavegando(page, page.locator('#decision-confirm-accept'));
  await expect(page.locator('.page-heading .status')).toHaveText('Autorizada');
  await rotular('PMO · Decisión', 'Factura "Autorizada": se notifica a Recepción de Facturas');
  await senalar(page, page.locator('#decision-result'), 3500);
  const recepcion = ((await page.locator('#decision-result').innerText()).match(/[\w.+-]+@[\w.-]+\.\w+/g) ?? [])[0];
  const autorizada = recepcion ? buscarCorreo(recepcion, `Factura ${numero} autorizada para pago`, desdeAutorizada) : null;
  if (autorizada) await mostrarCorreo(page, 'Correo a Recepción de Facturas', autorizada);

  await page.goto(`/invoices/${facturaId}`);
  await rotular('PMO · Pago', 'Cuando la factura se paga, el PMO lo registra en el portal');
  await senalar(page, page.locator('#payment'), 2500);
  await page.locator('#payment-confirm').check();
  await page.waitForTimeout(1500);
  const desdePagada = new Date(Date.now() - 2000).toISOString();
  await clicNavegando(page, page.locator('#payment').getByRole('button', { name: /Marcar como pagada/ }));
  await expect(page.locator('.page-heading .status')).toHaveText('Pagada');
  await rotular('PMO · Pago', 'Factura "Pagada": el proveedor tiene un plazo para adjuntar el Complemento de Pago');
  await senalar(page, page.locator('.page-heading .status'), 2500);
  await senalar(page, page.locator('#complement'), 3000);
  const pagada = buscarCorreo(CUENTAS.proveedor1, `Factura ${numero} pagada`, desdePagada);
  if (pagada) await mostrarCorreo(page, 'Correo al proveedor: pago y aviso del Complemento de Pago', pagada);
  await page.goto('/');
  await cerrarSesion(page);

  // ---------------------------------------------------------------- 6. Proveedor: complemento de pago
  await tarjeta(page, 'Parte 6 de 6 · Proveedor', 'Complemento de Pago', [
    'Aviso de complementos pendientes en el tablero',
    'Carga del Complemento de Pago (CFDI de tipo P)',
    'Aviso automático a Recepción de Facturas',
  ]);
  await rotular('Proveedor', 'Inicia sesión el proveedor');
  await iniciarSesion(page, CUENTAS.proveedor1, clave);
  await rotular('Proveedor', 'El tablero le avisa que tiene un Complemento de Pago pendiente y su fecha límite');
  await senalar(page, page.locator('#pending-complements'), 4000);
  await page.goto(`/invoices/${facturaId}`);
  await rotular('Proveedor · Factura pagada', 'La factura aparece "Pagada" con el complemento pendiente');
  await senalar(page, page.locator('#complement'), 3000);
  await senalar(page, page.getByRole('link', { name: /Adjuntar Complemento de Pago/ }), 1500);
  await clicNavegando(page, page.getByRole('link', { name: /Adjuntar Complemento de Pago/ }));
  await rotular('Proveedor · Complemento', 'Se carga el XML del Complemento de Pago (CFDI de tipo P) que relaciona la factura');
  await page.waitForTimeout(2000);
  await subirDocumento(page, 'PAYMENT_COMPLEMENT_XML', fx.complemento_pago, 'Complemento de pago (XML)', false);
  await expect(page.locator('#complement-result')).toHaveText('Se notificó a Recepción de Facturas.');
  await rotular('Proveedor · Complemento', 'Complemento adjuntado: el portal avisa a Recepción de Facturas');
  await senalar(page, page.locator('#complement-result'), 3500);

  await page.goto(`/invoices/${facturaId}`);
  await rotular('Historial', 'El historial registra cada paso de la factura con su fecha y responsable');
  await senalar(page, page.locator('#history'), 5000);
  await clicNavegando(page, menu(page, 'Facturas'));
  await rotular('Proveedor · Mis facturas', 'El proveedor consulta en todo momento el estatus de sus facturas');
  await senalar(page, page.locator('table tbody tr').filter({ hasText: numero }).first(), 3500);
  await rotular('', '');
  await cerrarSesion(page);

  await tarjeta(page, 'Portal de Proveedores ULTRASIST', 'Fin del recorrido', [
    `3 proveedores dados de alta y autorizados; usuario PMO creado`,
    `Factura ${numero}: registrada, prevalidada, autorizada, pagada y con su Complemento de Pago`,
    'Correos generados en cada paso: credenciales, autorización, pago y complemento',
  ], 6000);

  const video = page.video();
  await page.context().close();
  fs.mkdirSync(path.dirname(VIDEO), { recursive: true });
  await video?.saveAs(VIDEO);
});
