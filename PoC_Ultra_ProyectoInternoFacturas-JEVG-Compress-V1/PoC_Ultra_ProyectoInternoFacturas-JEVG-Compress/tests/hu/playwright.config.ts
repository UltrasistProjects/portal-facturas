import { defineConfig } from '@playwright/test';
import path from 'node:path';

// Validacion funcional de las HUs. Las HUs dependen unas de otras (DEPENDENCIAS_HUs.md): los specs llevan un prefijo
// numerico con el orden de ejecucion y corren en un solo worker, sin paralelismo.
const APP_ROOT = path.resolve(__dirname, '..', '..');

export default defineConfig({
  testDir: './specs',
  globalSetup: './lib/global-setup.ts',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 6 * 60_000,
  expect: { timeout: 15_000 },
  outputDir: path.join(APP_ROOT, 'test-results'),
  reporter: [
    ['list'],
    ['html', { outputFolder: path.join(APP_ROOT, 'playwright-report'), open: 'never' }],
    ['json', { outputFile: path.join(APP_ROOT, 'evidencias', 'playwright-resultados.json') }],
  ],
  use: {
    baseURL: process.env.PORTAL_URL ?? 'http://127.0.0.1:8000',
    viewport: { width: 1440, height: 900 },
    locale: 'es-MX',
    timezoneId: 'America/Mexico_City',
    acceptDownloads: true,
    contextOptions: { reducedMotion: 'reduce' },
    trace: 'on',
    screenshot: 'only-on-failure',
    actionTimeout: 20_000,
    navigationTimeout: 30_000,
  },
});
