import fs from 'node:fs';
import path from 'node:path';
import { herramienta, type Estado } from './estado';
import { DATOS, ESTADO, EVIDENCIAS, KEYCLOAK_URL, OUTBOX, PORTAL_URL } from './rutas';

async function disponible(url: string): Promise<[boolean, string]> {
  try {
    const respuesta = await fetch(url, { redirect: 'manual' });
    return [respuesta.status < 500, `${url} → HTTP ${respuesta.status}`];
  } catch (error) {
    return [false, `${url} → ${(error as Error).message}`];
  }
}

// Antes de ejecutar las HUs: comprueba que el portal y Keycloak respondan y genera los datos de prueba de esta
// ejecucion (identificadores unicos, para que la suite se pueda repetir sobre la misma base).
// HU_RUN_ID reutiliza la ejecucion anterior (para repetir un solo spec sin perder los datos que dejo otra HU).
export default async function globalSetup(): Promise<void> {
  fs.mkdirSync(EVIDENCIAS, { recursive: true });
  fs.mkdirSync(OUTBOX, { recursive: true });
  if (process.env.HU_RUN_ID && fs.existsSync(ESTADO)) {
    const previo: Estado = JSON.parse(fs.readFileSync(ESTADO, 'utf8'));
    if (previo.run === process.env.HU_RUN_ID) return;
  }
  const [portal, detallePortal] = await disponible(`${PORTAL_URL}/health`);
  const [keycloak, detalleKeycloak] = await disponible(
    `${KEYCLOAK_URL}/realms/ultrasist-portal/.well-known/openid-configuration`,
  );
  const run = `R${Date.now().toString(36).toUpperCase()}`;
  const carpeta = path.join(DATOS, run);
  const fixtures = herramienta('fixtures', run, carpeta);
  const estado: Estado = {
    run,
    inicio: new Date().toISOString(),
    ambiente: { portal, keycloak, detalle: `${detallePortal} · ${detalleKeycloak}` },
    fixtures,
    datos: {},
    hus: {},
  };
  fs.writeFileSync(ESTADO, JSON.stringify(estado, null, 2));
}
