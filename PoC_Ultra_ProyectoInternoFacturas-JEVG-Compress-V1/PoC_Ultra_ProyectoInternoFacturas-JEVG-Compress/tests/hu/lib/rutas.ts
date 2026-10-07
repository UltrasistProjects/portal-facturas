import path from 'node:path';

export const APP_ROOT = path.resolve(__dirname, '..', '..', '..');
export const EVIDENCIAS = path.join(APP_ROOT, 'evidencias');
// La aplicacion se arranca con MAIL_BACKEND=file y MAIL_OUTBOX_DIR=./evidencias/_correos (ver tests/hu/README.md).
export const OUTBOX = process.env.HU_OUTBOX ?? path.join(EVIDENCIAS, '_correos');
export const DATOS = path.join(EVIDENCIAS, '_datos-prueba');
export const ESTADO = path.join(EVIDENCIAS, '_estado-ejecucion.json');
export const PYTHON = path.join(APP_ROOT, '.venv', 'bin', 'python');
export const HERRAMIENTAS = path.join(APP_ROOT, 'tests', 'hu', 'fixtures', 'herramientas.py');
export const PORTAL_URL = process.env.PORTAL_URL ?? 'http://127.0.0.1:8000';
export const KEYCLOAK_URL = process.env.KEYCLOAK_URL ?? 'http://127.0.0.1:58080';
