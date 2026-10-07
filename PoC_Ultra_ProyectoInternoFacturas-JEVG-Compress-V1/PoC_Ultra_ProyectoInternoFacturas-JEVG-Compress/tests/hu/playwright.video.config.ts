import { defineConfig } from '@playwright/test';
import path from 'node:path';

// Recorrido del flujo completo grabado en video (video/recorrido.spec.ts). Va aparte de la suite de HUs: no escribe
// evidencias/playwright-resultados.json ni el estado de ejecucion de las HUs. El video queda en evidencias/video/.
const APP_ROOT = path.resolve(__dirname, '..', '..');

export default defineConfig({
  testDir: './video',
  workers: 1,
  retries: 0,
  timeout: 20 * 60_000,
  expect: { timeout: 15_000 },
  outputDir: path.join(APP_ROOT, 'test-results', 'recorrido'),
  reporter: [['list']],
  use: {
    baseURL: process.env.PORTAL_URL ?? 'http://127.0.0.1:8000',
    viewport: { width: 1440, height: 900 },
    locale: 'es-MX',
    timezoneId: 'America/Mexico_City',
    acceptDownloads: true,
    actionTimeout: 20_000,
    navigationTimeout: 30_000,
    video: { mode: 'on', size: { width: 1440, height: 900 } },
    // Pausa entre acciones para que el video se pueda seguir (RECORRIDO_SLOWMO=0 lo acelera).
    launchOptions: { slowMo: Number(process.env.RECORRIDO_SLOWMO ?? 250) },
  },
});
