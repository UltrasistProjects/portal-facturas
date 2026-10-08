import { expect, test, type Browser, type BrowserContext, type Locator, type Page, type TestInfo } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
import { demoPassword, leerEstado, registrarResultadoHU, type Correo } from './estado';
import { EVIDENCIAS, PORTAL_URL } from './rutas';

export type EstadoHU = 'PASS' | 'FAIL' | 'BLOCKED';
type EstadoEscenario = EstadoHU | 'NO EJECUTADO';

interface Evidencia {
  archivo: string;
  descripcion: string;
  tipo: 'aplicacion' | 'correo' | 'fallo';
}

interface Paso {
  paso: string;
  esperado: string;
  obtenido: string;
  estado: 'PASS' | 'FAIL';
  error?: string;
  evidencias: Evidencia[];
}

interface Escenario {
  nombre: string;
  estado: EstadoEscenario;
  motivo?: string;
  pasos: Paso[];
}

/** Un impedimento ajeno a la HU (ambiente, autenticacion, dato previo): el escenario queda BLOCKED, no FAIL. */
export class Bloqueo extends Error {}

export const CUENTAS = {
  admin: 'admin@poc.local',
  pmo: 'pmo@poc.local',
  proveedor1: 'proveedor1@poc.local',
  proveedor2: 'proveedor2@poc.local',
  proveedor3: 'proveedor3@poc.local',
} as const;

export function limpiar(error: unknown): string {
  const texto = error instanceof Error ? error.message : String(error);
  // Sin codigos de color ANSI y sin el "Call log" completo de Playwright.
  return texto
    .replace(/\u001b\[[0-9;]*m/g, '')
    .split('\nCall log:')[0]
    .trim()
    .slice(0, 900);
}

function slug(texto: string): string {
  return texto
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')
    .slice(0, 60);
}

function escaparHtml(texto: string): string {
  return texto.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c] as string);
}

/**
 * Ejecucion de una HU: escenarios con sus pasos (esperado / obtenido / estado) y las capturas reales de Playwright
 * asociadas a cada paso. Al cerrar escribe evidencias/HU-XX/resultado.json, del que sale el PDF.
 */
export class EjecucionHU {
  readonly dir: string;
  readonly escenarios: Escenario[] = [];
  private escenarioActual?: Escenario;
  private pasoActual?: Paso;
  private contador = 0;
  private bloqueo?: string;
  private readonly contextos: BrowserContext[] = [];
  private readonly inicio = new Date();
  readonly notas: string[] = [];

  constructor(
    readonly id: string,
    readonly testInfo: TestInfo,
    readonly browser: Browser,
  ) {
    this.dir = path.join(EVIDENCIAS, id);
    fs.rmSync(this.dir, { recursive: true, force: true });
    fs.mkdirSync(this.dir, { recursive: true });
    const { ambiente } = leerEstado();
    if (!ambiente.portal || !ambiente.keycloak) this.bloqueo = `Ambiente no disponible: ${ambiente.detalle}`;
  }

  /** Dato que dejo una HU previa (dependencia). Si falta, la HU queda BLOCKED. */
  requiere<T = any>(hu: string, clave: string): T {
    const valor = leerEstado().datos[clave];
    if (valor === undefined || valor === null) {
      const resultado = leerEstado().hus[hu];
      throw new Bloqueo(
        `Depende de ${hu}, que no dejó el dato «${clave}»` + (resultado ? ` (resultado de ${hu}: ${resultado}).` : ' (no se ejecutó).'),
      );
    }
    return valor as T;
  }

  nota(texto: string): void {
    this.notas.push(texto);
  }

  async nuevoContexto(): Promise<BrowserContext> {
    const contexto = await this.browser.newContext({
      baseURL: PORTAL_URL,
      viewport: { width: 1440, height: 900 },
      locale: 'es-MX',
      timezoneId: 'America/Mexico_City',
      acceptDownloads: true,
      reducedMotion: 'reduce',
    });
    this.contextos.push(contexto);
    return contexto;
  }

  /** Inicia sesion por Keycloak (OIDC) con una cuenta demo. Si no se puede, el escenario queda BLOCKED. */
  async sesion(cuenta: keyof typeof CUENTAS): Promise<Page> {
    const correo = CUENTAS[cuenta];
    const pagina = await (await this.nuevoContexto()).newPage();
    try {
      await pagina.goto('/login');
      await pagina.locator('#username').fill(correo);
      await pagina.locator('#password').fill(demoPassword());
      await pagina.locator('#kc-login').click();
      await expect(pagina.locator('.sidebar-footer')).toContainText(correo);
    } catch (error) {
      throw new Bloqueo(`No fue posible iniciar sesión como ${correo}: ${limpiar(error)}`);
    }
    return pagina;
  }

  async escenario(nombre: string, cuerpo: () => Promise<void>, opciones: { requiere?: string[] } = {}): Promise<void> {
    const escenario: Escenario = { nombre, estado: 'PASS', pasos: [] };
    this.escenarios.push(escenario);
    this.escenarioActual = escenario;
    this.pasoActual = undefined;
    if (this.bloqueo) {
      escenario.estado = 'BLOCKED';
      escenario.motivo = this.bloqueo;
      return;
    }
    const pendientes = (opciones.requiere ?? []).filter(
      (previo) => this.escenarios.find((e) => e.nombre === previo)?.estado !== 'PASS',
    );
    if (pendientes.length) {
      escenario.estado = 'NO EJECUTADO';
      escenario.motivo = `No se ejecutó: depende de «${pendientes.join('», «')}», que no terminó en PASS.`;
      return;
    }
    try {
      await cuerpo();
    } catch (error) {
      if (error instanceof Bloqueo) {
        escenario.estado = 'BLOCKED';
        escenario.motivo = error.message;
      } else {
        escenario.estado = 'FAIL';
        escenario.motivo = limpiar(error);
      }
    }
  }

  /** Bloquea la HU completa (p. ej., falta una dependencia de otra HU). */
  bloquear(motivo: string): void {
    this.bloqueo = motivo;
  }

  async paso(pagina: Page | null, paso: string, esperado: string, accion: () => Promise<string>): Promise<void> {
    const registro: Paso = { paso, esperado, obtenido: '', estado: 'PASS', evidencias: [] };
    this.escenarioActual?.pasos.push(registro);
    this.pasoActual = registro;
    try {
      registro.obtenido = await accion();
    } catch (error) {
      if (error instanceof Bloqueo) throw error;
      registro.estado = 'FAIL';
      registro.error = limpiar(error);
      registro.obtenido = registro.obtenido || `No se cumplió lo esperado. ${registro.error.split('\n').slice(0, 6).join(' ')}`;
      if (pagina && !pagina.isClosed()) {
        await this.captura(pagina, `fallo-${paso}`, `Estado exacto de la aplicación al fallar el paso «${paso}».`, {
          tipo: 'fallo',
        }).catch(() => undefined);
      }
      throw error;
    }
  }

  async captura(
    pagina: Page,
    nombre: string,
    descripcion: string,
    opciones: { completa?: boolean; enfocar?: Locator; tipo?: Evidencia['tipo'] } = {},
  ): Promise<void> {
    if (opciones.enfocar) {
      // Desplazamiento instantaneo: Bootstrap usa scroll-behavior smooth y la captura saldria a mitad del movimiento.
      await opciones.enfocar.first().evaluate((el) => el.scrollIntoView({ block: 'center', inline: 'nearest', behavior: 'instant' }));
      await pagina.waitForTimeout(150);
    }
    this.contador += 1;
    const archivo = `${String(this.contador).padStart(2, '0')}-${slug(nombre)}.png`;
    const ruta = path.join(this.dir, archivo);
    if (opciones.completa) {
      // Pagina completa con el viewport a la altura real del documento: con fullPage, la barra lateral fija (alto =
      // viewport) saldria cortada. El contenido se renderiza igual; solo cambia el alto de la ventana.
      const original = pagina.viewportSize() ?? { width: 1440, height: 900 };
      const alto = await pagina.evaluate(() => document.documentElement.scrollHeight);
      await pagina.setViewportSize({ width: original.width, height: Math.max(original.height, Math.min(alto, 4000)) });
      await pagina.waitForTimeout(150);
      await pagina.screenshot({ path: ruta, animations: 'disabled' });
      await pagina.setViewportSize(original);
    } else {
      await pagina.screenshot({ path: ruta, animations: 'disabled' });
    }
    const evidencia: Evidencia = { archivo: `${this.id}/${archivo}`, descripcion, tipo: opciones.tipo ?? 'aplicacion' };
    if (!this.pasoActual) {
      this.pasoActual = { paso: 'Estado de la pantalla', esperado: '—', obtenido: '—', estado: 'PASS', evidencias: [] };
      this.escenarioActual?.pasos.push(this.pasoActual);
    }
    this.pasoActual.evidencias.push(evidencia);
    await this.testInfo.attach(archivo, { path: ruta, contentType: 'image/png' });
  }

  /**
   * Muestra en Chromium un correo que genero el portal (archivo .eml del transporte "file") y lo captura. La
   * cabecera indica el archivo de origen; el cuerpo es el HTML del correo tal cual.
   */
  async capturaCorreo(correo: Correo, nombre: string, descripcion: string): Promise<void> {
    const contexto = await this.nuevoContexto();
    const pagina = await contexto.newPage();
    await pagina.setViewportSize({ width: 1100, height: 900 });
    const cuerpo = correo.html
      ? `<iframe sandbox srcdoc="${escaparHtml(correo.html)}" style="width:100%;height:760px;border:1px solid #ccd;background:#fff"></iframe>`
      : `<pre style="white-space:pre-wrap">${escaparHtml(correo.texto)}</pre>`;
    await pagina.setContent(`<!doctype html><html lang="es"><head><meta charset="utf-8"><title>Correo</title></head>
      <body style="font:14px Arial,sans-serif;margin:16px;background:#f3f5f8;color:#152235">
      <div style="background:#fff;border:1px solid #ccd;border-radius:8px;padding:12px 16px;margin-bottom:12px">
        <div style="font-size:11px;color:#697789;margin-bottom:6px">Correo generado por el portal · transporte de archivo (MAIL_BACKEND=file) · ${escaparHtml(path.basename(correo.archivo))}</div>
        <table style="border-collapse:collapse;font-size:13px">
          <tr><td style="color:#697789;padding:2px 12px 2px 0">De</td><td>${escaparHtml(correo.de)}</td></tr>
          <tr><td style="color:#697789;padding:2px 12px 2px 0">Para</td><td>${escaparHtml(correo.para.join(', '))}</td></tr>
          ${correo.cc.length ? `<tr><td style="color:#697789;padding:2px 12px 2px 0">Cc</td><td>${escaparHtml(correo.cc.join(', '))}</td></tr>` : ''}
          <tr><td style="color:#697789;padding:2px 12px 2px 0">Asunto</td><td><strong>${escaparHtml(correo.asunto)}</strong></td></tr>
          <tr><td style="color:#697789;padding:2px 12px 2px 0">Generado (UTC)</td><td>${escaparHtml(correo.fecha_utc)}</td></tr>
        </table></div>${cuerpo}</body></html>`);
    await pagina.waitForLoadState('load');
    await this.captura(pagina, nombre, descripcion, { tipo: 'correo' });
    await contexto.close();
  }

  private estadoFinal(): EstadoHU {
    if (this.escenarios.some((e) => e.estado === 'FAIL')) return 'FAIL';
    if (!this.escenarios.length || this.escenarios.some((e) => e.estado !== 'PASS')) return 'BLOCKED';
    return 'PASS';
  }

  /** Cierra los contextos, escribe resultado.json y refleja el resultado en Playwright (FAIL falla, BLOCKED se omite). */
  async cerrar(errorInesperado?: unknown): Promise<void> {
    if (errorInesperado && !(errorInesperado instanceof Bloqueo)) {
      this.escenarios.push({ nombre: 'Error inesperado de la prueba', estado: 'FAIL', motivo: limpiar(errorInesperado), pasos: [] });
    } else if (errorInesperado instanceof Bloqueo) {
      this.bloqueo = errorInesperado.message;
      if (!this.escenarios.length) this.escenarios.push({ nombre: 'Precondiciones', estado: 'BLOCKED', motivo: errorInesperado.message, pasos: [] });
    }
    for (const contexto of this.contextos) await contexto.close().catch(() => undefined);
    const estado = this.estadoFinal();
    const resultado = {
      id: this.id,
      run: leerEstado().run,
      inicio: this.inicio.toISOString(),
      fin: new Date().toISOString(),
      estado,
      bloqueo: this.bloqueo ?? null,
      notas: this.notas,
      prueba: { titulo: this.testInfo.title, archivo: path.basename(this.testInfo.file) },
      escenarios: this.escenarios,
    };
    fs.writeFileSync(path.join(this.dir, 'resultado.json'), JSON.stringify(resultado, null, 2));
    registrarResultadoHU(this.id, estado);
    if (estado === 'FAIL') {
      const fallos = this.escenarios.filter((e) => e.estado === 'FAIL').map((e) => `«${e.nombre}»: ${e.motivo}`);
      throw new Error(`${this.id} FAIL\n${fallos.join('\n')}`);
    }
    if (estado === 'BLOCKED') {
      const motivo = this.bloqueo ?? this.escenarios.find((e) => e.estado !== 'PASS')?.motivo ?? 'sin escenarios';
      test.skip(true, `BLOCKED: ${motivo}`);
    }
  }
}

/** Envoltura comun de cada spec: crea la ejecucion, corre el cuerpo y siempre escribe el resultado. */
export async function ejecutarHU(
  id: string,
  browser: Browser,
  testInfo: TestInfo,
  cuerpo: (hu: EjecucionHU) => Promise<void>,
): Promise<void> {
  const hu = new EjecucionHU(id, testInfo, browser);
  let error: unknown;
  try {
    await cuerpo(hu);
  } catch (e) {
    error = e;
  }
  await hu.cerrar(error);
}
