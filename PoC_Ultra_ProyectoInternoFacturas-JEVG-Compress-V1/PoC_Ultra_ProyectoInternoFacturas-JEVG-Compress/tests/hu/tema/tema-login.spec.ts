import { expect, test, type Browser, type Page } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
import { demoPassword } from '../lib/estado';
import { CUENTAS } from '../lib/hu';
import { clicNavegando } from '../lib/portal';
import { EVIDENCIAS, KEYCLOAK_URL, PORTAL_URL } from '../lib/rutas';

// Criterios de aceptacion del tema de login "ultrasist" (change tema-login-keycloak), contra Keycloak real: login,
// credenciales invalidas, primer acceso con contrasena temporal, cambio voluntario, restablecimiento completo por
// correo (Mailpit), enlace ya usado, contrasena anterior, confirmacion de cierre de sesion, cuenta deshabilitada y los
// eventos del restablecimiento en Keycloak. En cada pagina de Keycloak se verifica que no aparezca el diseno por defecto
// y que no haya desplazamiento horizontal.

const MAILPIT_URL = process.env.MAILPIT_URL ?? 'http://127.0.0.1:58025';
const REALM_URL = `${KEYCLOAK_URL}/realms/ultrasist-portal`;
const LINK_DE_ACCION = /https?:\/\/\S+\/login-actions\/action-token\?key=[^\s"<>]+/;
const CREDENCIALES_INVALIDAS = 'Correo o contraseña incorrectos.';
// Keycloak informa los errores de politica de la contrasena nueva en la alerta de la pagina o junto al campo.
const errorDePolitica = (page: Page) => page.locator('.kc-feedback-text, #input-error-password').filter({ hasText: /\S/ }).first();

interface Verificacion {
  captura: string;
  pagina: string;
  titulo: string;
  hojas: string[];
  anchoDocumento: number;
  anchoVentana: number;
}

/** Ejecucion en un tamano de ventana: capturas numeradas y verificaciones del tema en evidencias/tema-login-keycloak/. */
class Recorrido {
  private contador = 0;
  readonly verificaciones: Verificacion[] = [];

  constructor(
    readonly page: Page,
    readonly dir: string,
  ) {
    fs.rmSync(dir, { recursive: true, force: true });
    fs.mkdirSync(dir, { recursive: true });
  }

  /** Verifica que la pagina de Keycloak use el tema ultrasist y la captura. */
  async keycloak(nombre: string): Promise<void> {
    const { page } = this;
    expect(page.url().startsWith(KEYCLOAK_URL), `${nombre}: se esperaba una pagina de Keycloak (${page.url()})`).toBe(true);
    await expect(page.locator('body.login-body')).toBeVisible();
    const hojas = await page.locator('link[rel="stylesheet"]').evaluateAll((links) => links.map((l) => (l as HTMLLinkElement).href));
    const recursos = await page
      .locator('link[href], script[src]')
      .evaluateAll((nodos) => nodos.map((n) => n.getAttribute('href') ?? n.getAttribute('src') ?? ''));
    expect(hojas.length, `${nombre}: sin hojas de estilo`).toBeGreaterThan(0);
    expect(hojas.every((href) => href.includes('/login/ultrasist/')), `${nombre}: ${hojas.join(', ')}`).toBe(true);
    expect(recursos.filter((r) => /keycloak\.v2|patternfly/i.test(r)), `${nombre}: recursos del tema por defecto`).toEqual([]);
    await expect(page.locator('img.brand-logo:visible').first()).toBeVisible();
    const [anchoDocumento, anchoVentana] = await page.evaluate(() => [document.documentElement.scrollWidth, window.innerWidth]);
    expect(anchoDocumento, `${nombre}: desplazamiento horizontal`).toBeLessThanOrEqual(anchoVentana);
    const captura = await this.captura(nombre);
    this.verificaciones.push({ captura, pagina: new URL(page.url()).pathname, titulo: await page.title(), hojas, anchoDocumento, anchoVentana });
  }

  async captura(nombre: string, page: Page = this.page): Promise<string> {
    this.contador += 1;
    const archivo = `${String(this.contador).padStart(2, '0')}-${nombre}.png`;
    await page.screenshot({ path: path.join(this.dir, archivo), fullPage: true });
    return archivo;
  }

  guardar(datos: Record<string, unknown>): void {
    fs.writeFileSync(path.join(this.dir, 'verificaciones.json'), JSON.stringify({ ...datos, paginas: this.verificaciones }, null, 2));
  }
}

async function iniciarSesionKeycloak(page: Page, correo: string, contrasena: string): Promise<void> {
  if (!page.url().startsWith(KEYCLOAK_URL)) await page.goto('/login');
  await page.locator('#username').fill(correo);
  await page.locator('#password').fill(contrasena);
  await clicNavegando(page, page.locator('#kc-login'));
}

async function cerrarSesionPortal(page: Page): Promise<void> {
  // En movil el pie de la barra lateral se reduce: se envia el formulario (con su CSRF) sin depender de su visibilidad.
  // El portal cierra la sesion de Keycloak y vuelve a su raiz, que sin sesion lleva al inicio de sesion de Keycloak.
  await page.locator('form[action="/logout"]').evaluate((form) => (form as HTMLFormElement).requestSubmit());
  await page.waitForURL((url) => url.href.startsWith(KEYCLOAK_URL));
  await expect(page.locator('#kc-login')).toBeVisible();
}

async function nuevaContrasena(page: Page, clave: string): Promise<void> {
  await page.locator('#password-new').fill(clave);
  await page.locator('#password-confirm').fill(clave);
  await clicNavegando(page, page.locator('#kc-submit'));
}

async function correosPara(destinatario: string): Promise<{ ID: string; Subject: string }[]> {
  const respuesta = await fetch(`${MAILPIT_URL}/api/v1/search?query=${encodeURIComponent(`to:"${destinatario}"`)}`);
  if (!respuesta.ok) throw new Error(`Mailpit no responde (${respuesta.status}) en ${MAILPIT_URL}`);
  return (await respuesta.json()).messages ?? [];
}

async function esperarCorreo(destinatario: string, previos: number): Promise<{ id: string; enlace: string }> {
  let mensajes: { ID: string }[] = [];
  await expect
    .poll(async () => (mensajes = await correosPara(destinatario)).length, { timeout: 30_000, message: `correo para ${destinatario}` })
    .toBeGreaterThan(previos);
  const id = mensajes[0].ID; // Mailpit devuelve primero el mas reciente
  const mensaje = await (await fetch(`${MAILPIT_URL}/api/v1/message/${id}`)).json();
  const enlace = String(mensaje.Text ?? '').match(LINK_DE_ACCION)?.[0];
  if (!enlace) throw new Error(`El correo de restablecimiento no trae el enlace: ${String(mensaje.Text).slice(0, 300)}`);
  return { id, enlace };
}

interface EventoKeycloak {
  time: number;
  type: string;
  userId?: string;
  error?: string;
  details?: Record<string, string>;
}

/** Valor del .env de la aplicacion (como demoPassword): las credenciales del administrador inicial de Keycloak local. */
function valorEnv(clave: string): string {
  const env = fs.readFileSync(path.join(__dirname, '..', '..', '..', '.env'), 'utf8');
  const valor = env.match(new RegExp(`^${clave}=(.*)$`, 'm'))?.[1]?.trim();
  if (!valor) throw new Error(`${clave} no está definida en .env`);
  return valor;
}

/** Eventos de usuario del realm desde un instante, leidos con la API de administracion de Keycloak. */
async function eventosDesde(desde: number): Promise<EventoKeycloak[]> {
  const token = await fetch(`${KEYCLOAK_URL}/realms/master/protocol/openid-connect/token`, {
    method: 'POST',
    body: new URLSearchParams({
      grant_type: 'password',
      client_id: 'admin-cli',
      username: valorEnv('KC_BOOTSTRAP_ADMIN_USERNAME'),
      password: valorEnv('KC_BOOTSTRAP_ADMIN_PASSWORD'),
    }),
  });
  if (!token.ok) throw new Error(`No se pudo consultar la API de administración de Keycloak (${token.status})`);
  const { access_token } = await token.json();
  const dia = new Date(desde).toISOString().slice(0, 10);
  const respuesta = await fetch(`${KEYCLOAK_URL}/admin/realms/ultrasist-portal/events?dateFrom=${dia}&max=1000`, {
    headers: { Authorization: `Bearer ${access_token}` },
  });
  const eventos: EventoKeycloak[] = await respuesta.json();
  return eventos.filter((evento) => evento.time >= desde);
}

async function solicitarRestablecimiento(page: Page, correo: string): Promise<void> {
  await page.goto('/login');
  await clicNavegando(page, page.locator('#kc-forgot-password'));
  await page.locator('#username').fill(correo);
  await clicNavegando(page, page.locator('#kc-submit'));
  await expect(page.locator('.kc-feedback-text')).toContainText('Si el correo está registrado');
}

/** Alta del usuario PMO por el Administrador, en una ventana de escritorio (la pantalla de usuarios no es el objeto). */
async function crearPmo(browser: Browser, nombre: string, correo: string): Promise<string> {
  const contexto = await browser.newContext({ baseURL: PORTAL_URL, viewport: { width: 1440, height: 900 }, locale: 'es-MX' });
  try {
    const page = await contexto.newPage();
    await iniciarSesionKeycloak(page, CUENTAS.admin, demoPassword());
    await expect(page.locator('.sidebar-footer')).toContainText(CUENTAS.admin);
    await page.goto('/admin/users');
    await page.locator('details.admin-create summary').click();
    await page.locator('#user-name').fill(nombre);
    await page.locator('#user-email').fill(correo);
    await page.locator('#user-role').selectOption('PMO');
    await clicNavegando(page, page.locator('details.admin-create').getByRole('button', { name: 'Crear usuario' }));
    await expect(page.locator('.alert-success')).toHaveText('Usuario creado');
    return (await page.locator('.temporary-credentials code').innerText()).trim();
  } finally {
    await contexto.close();
  }
}

async function deshabilitarUsuario(browser: Browser, correo: string): Promise<void> {
  const contexto = await browser.newContext({ baseURL: PORTAL_URL, viewport: { width: 1440, height: 900 }, locale: 'es-MX' });
  try {
    const page = await contexto.newPage();
    await iniciarSesionKeycloak(page, CUENTAS.admin, demoPassword());
    await page.goto(`/admin/users?q=${encodeURIComponent(correo)}`);
    await clicNavegando(page, page.locator('table tbody tr').filter({ hasText: correo }).getByRole('button', { name: 'Deshabilitar' }));
    await expect(page.locator('table tbody tr').filter({ hasText: correo })).toContainText('Deshabilitado');
  } finally {
    await contexto.close();
  }
}

test('tema de login ultrasist: inicio de sesión, primer acceso y restablecimiento', async ({ page, browser }, testInfo) => {
  const run = `${Date.now().toString(36)}${testInfo.project.name.slice(0, 3)}`.toUpperCase();
  const correo = `pmo.tema.${run.toLowerCase()}@ultrasist-qa.example`;
  const clave1 = `Tema#${run}a1`;
  const clave2 = `Tema#${run}b2`;
  const recorrido = new Recorrido(page, path.join(EVIDENCIAS, 'tema-login-keycloak', testInfo.project.name));
  const inexistente = `noexiste.${run.toLowerCase()}@ultrasist-qa.example`;
  const inicio = Date.now() - 1_000;
  const temporal = await crearPmo(browser, `PMO Tema ${run}`, correo);

  await test.step('Pantalla de inicio de sesión', async () => {
    await page.goto('/login');
    await expect(page.locator('#kc-page-title')).toHaveText('Iniciar sesión');
    await expect(page.locator('#kc-forgot-password')).toHaveText('¿Olvidó su contraseña?');
    await expect(page.locator('[data-demo]')).toHaveCount(0);
    await recorrido.keycloak('inicio-de-sesion');
  });

  await test.step('Credenciales inválidas', async () => {
    await iniciarSesionKeycloak(page, correo, 'Incorrecta#2026x');
    await expect(page.locator('#input-error')).toHaveText(CREDENCIALES_INVALIDAS);
    await recorrido.keycloak('credenciales-invalidas');
  });

  await test.step('Primer acceso con contraseña temporal: cambio obligatorio con errores de política', async () => {
    await iniciarSesionKeycloak(page, correo, temporal);
    await expect(page.locator('#kc-page-title')).toHaveText('Cambiar contraseña');
    await expect(page.locator('#password-requirements')).toContainText('al menos 8 caracteres');
    await expect(page.locator('#kc-cancel')).toHaveCount(0);
    await recorrido.keycloak('primer-acceso');
    await nuevaContrasena(page, 'Password123');
    await expect(errorDePolitica(page)).toContainText('carácter especial');
    await recorrido.keycloak('primer-acceso-error-de-politica');
    await nuevaContrasena(page, 'Portal2026!');
    await expect(errorDePolitica(page)).toContainText('contraseña común');
    await recorrido.keycloak('primer-acceso-contrasena-comun');
    await nuevaContrasena(page, clave1);
    await expect(page.locator('.sidebar-footer')).toContainText(correo);
    await expect(page.locator('.sidebar-footer')).toContainText('PMO');
    await recorrido.captura('portal-tras-primer-acceso');
  });

  await test.step('Cambio voluntario con cancelación', async () => {
    await page.goto('/account/password');
    await expect(page.locator('#kc-cancel')).toBeVisible();
    await recorrido.keycloak('cambio-voluntario');
    await clicNavegando(page, page.locator('#kc-cancel'));
    await expect(page.locator('.sidebar-footer')).toContainText(correo);
    await cerrarSesionPortal(page);
  });

  await test.step('Restablecimiento con un correo no registrado: mismo mensaje y ningún correo', async () => {
    await page.goto('/login');
    await clicNavegando(page, page.locator('#kc-forgot-password'));
    await expect(page.locator('#kc-page-title')).toHaveText('Restablecer contraseña');
    await recorrido.keycloak('solicitud-de-restablecimiento');
    await page.locator('#username').fill(inexistente);
    await clicNavegando(page, page.locator('#kc-submit'));
    await expect(page.locator('.kc-feedback-text')).toContainText('Si el correo está registrado');
    await recorrido.keycloak('confirmacion-correo-no-registrado');
    await page.waitForTimeout(5_000);
    expect(await correosPara(inexistente)).toHaveLength(0);
  });

  let enlace = '';
  await test.step('Restablecimiento completo: correo, errores de política y contraseña nueva', async () => {
    const previos = (await correosPara(correo)).length;
    await solicitarRestablecimiento(page, correo);
    await recorrido.keycloak('confirmacion-correo-registrado');
    const correoRecibido = await esperarCorreo(correo, previos);
    enlace = correoRecibido.enlace;
    const vista = await page.context().newPage();
    await vista.goto(`${MAILPIT_URL}/view/${correoRecibido.id}.html`);
    await recorrido.captura('correo-de-restablecimiento', vista);
    await vista.close();
    await page.goto(enlace);
    await expect(page.locator('#kc-page-title')).toHaveText('Cambiar contraseña');
    await recorrido.keycloak('nueva-contrasena-desde-el-correo');
    await nuevaContrasena(page, 'Password123');
    await expect(errorDePolitica(page)).toContainText('carácter especial');
    await recorrido.keycloak('nueva-contrasena-error-de-politica');
    await nuevaContrasena(page, clave2);
    // En el mismo navegador Keycloak continua el inicio de sesion pendiente; si no, muestra su pagina de informacion.
    if (page.url().startsWith(KEYCLOAK_URL)) {
      await recorrido.keycloak('contrasena-actualizada');
    } else {
      await expect(page.locator('.sidebar-footer')).toContainText(correo);
      await recorrido.captura('portal-tras-restablecer');
      await cerrarSesionPortal(page);
    }
  });

  await test.step('Enlace ya usado: página con el diseño del portal', async () => {
    await page.goto(enlace);
    await expect(page.locator('#kc-content')).toContainText(/expiró o ya se usó/);
    await expect(page.locator('#password-new')).toHaveCount(0);
    await recorrido.keycloak('enlace-ya-usado');
  });

  await test.step('La contraseña anterior ya no sirve y la nueva sí', async () => {
    await page.goto('/login');
    await iniciarSesionKeycloak(page, correo, clave1);
    await expect(page.locator('#input-error')).toHaveText(CREDENCIALES_INVALIDAS);
    await recorrido.keycloak('contrasena-anterior-rechazada');
    await iniciarSesionKeycloak(page, correo, clave2);
    await expect(page.locator('.sidebar-footer')).toContainText(correo);
    await expect(page.locator('.sidebar-footer')).toContainText('PMO');
    await recorrido.captura('portal-con-la-contrasena-nueva');
  });

  await test.step('Confirmación de cierre de sesión de Keycloak', async () => {
    await page.goto(`${REALM_URL}/protocol/openid-connect/logout?client_id=portal-facturas-web`);
    await expect(page.locator('#kc-logout')).toBeVisible();
    await recorrido.keycloak('confirmacion-de-cierre-de-sesion');
    await clicNavegando(page, page.locator('#kc-logout'));
    if (page.url().startsWith(KEYCLOAK_URL)) await recorrido.keycloak('sesion-cerrada');
  });

  await test.step('Cuenta deshabilitada: mismo mensaje y ningún correo', async () => {
    await deshabilitarUsuario(browser, correo);
    const previos = (await correosPara(correo)).length;
    await solicitarRestablecimiento(page, correo);
    await recorrido.keycloak('confirmacion-cuenta-deshabilitada');
    await page.waitForTimeout(5_000);
    expect(await correosPara(correo)).toHaveLength(previos);
  });

  let eventos: EventoKeycloak[] = [];
  await test.step('Los restablecimientos quedan en los eventos de Keycloak', async () => {
    const tiene = (tipo: string, error?: string, usuario = correo) =>
      eventos.some((e) => e.type === tipo && (error === undefined || e.error === error) && (e.details?.username === usuario || e.details?.email === usuario));
    await expect
      .poll(async () => {
        eventos = await eventosDesde(inicio);
        return tiene('RESET_PASSWORD_ERROR', 'user_disabled');
      }, { timeout: 15_000, message: 'eventos del restablecimiento en Keycloak' })
      .toBe(true);
    const enviado = eventos.find((e) => e.type === 'SEND_RESET_PASSWORD' && e.details?.email === correo);
    expect(enviado, 'solicitud con correo enviado').toBeTruthy();
    expect(tiene('RESET_PASSWORD_ERROR', 'user_not_found', inexistente), 'correo no registrado').toBe(true);
    expect(tiene('UPDATE_PASSWORD'), 'contraseña nueva guardada').toBe(true);
    expect(tiene('UPDATE_PASSWORD_ERROR', 'password_rejected'), 'contraseña rechazada por la política').toBe(true);
    expect(
      eventos.some((e) => e.type === 'RESET_PASSWORD_ERROR' && e.error === 'expired_code' && e.userId === enviado?.userId),
      'enlace ya usado',
    ).toBe(true);
  });

  recorrido.guardar({
    proyecto: testInfo.project.name,
    viewport: page.viewportSize(),
    usuario: correo,
    eventosKeycloak: eventos
      .filter((e) => /RESET_PASSWORD|ACTION_TOKEN|UPDATE_PASSWORD/.test(e.type))
      .sort((a, b) => a.time - b.time)
      .map((e) => ({
        hora: new Date(e.time).toISOString(),
        tipo: e.type,
        error: e.error ?? null,
        usuario: e.details?.username ?? e.details?.email ?? null,
        idUsuario: e.userId ?? null,
        motivo: e.details?.reason ?? null,
      })),
  });
});
