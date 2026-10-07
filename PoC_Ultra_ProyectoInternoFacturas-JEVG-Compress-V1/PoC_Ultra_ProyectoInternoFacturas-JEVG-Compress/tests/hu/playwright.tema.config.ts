import { defineConfig } from '@playwright/test';
import path from 'node:path';

// Recorrido del tema de login "ultrasist" de Keycloak (tema/tema-login.spec.ts), en escritorio y en movil. Va aparte de
// la suite de HUs: no escribe evidencias/playwright-resultados.json ni el estado de ejecucion de las HUs. Las capturas
// quedan en evidencias/tema-login-keycloak/. Requiere el portal con MAIL_BACKEND=file y Mailpit (docker compose).
const APP_ROOT = path.resolve(__dirname, '..', '..');

export default defineConfig({
  testDir: './tema',
  workers: 1,
  retries: 0,
  timeout: 6 * 60_000,
  expect: { timeout: 15_000 },
  outputDir: path.join(APP_ROOT, 'test-results', 'tema'),
  reporter: [['list']],
  use: {
    baseURL: process.env.PORTAL_URL ?? 'http://127.0.0.1:8000',
    locale: 'es-MX',
    timezoneId: 'America/Mexico_City',
    actionTimeout: 20_000,
    navigationTimeout: 30_000,
    trace: 'retain-on-failure',
  },
  projects: [
    { name: 'escritorio', use: { viewport: { width: 1440, height: 900 } } },
    { name: 'movil', use: { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true } },
  ],
});
