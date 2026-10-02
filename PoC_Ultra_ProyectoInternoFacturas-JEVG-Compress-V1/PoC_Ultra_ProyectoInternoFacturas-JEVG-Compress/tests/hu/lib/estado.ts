import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import { ESTADO, HERRAMIENTAS, OUTBOX, PYTHON } from './rutas';

// Estado compartido de una ejecucion: los specs corren en orden en un solo worker y cada HU deja aqui lo que crea
// (proveedores, facturas) para las HUs que dependen de ella.
export interface Estado {
  run: string;
  inicio: string;
  ambiente: { portal: boolean; keycloak: boolean; detalle: string };
  fixtures: Record<string, string>;
  datos: Record<string, any>;
  hus: Record<string, string>;
}

export function leerEstado(): Estado {
  return JSON.parse(fs.readFileSync(ESTADO, 'utf8'));
}

export function guardarDato(clave: string, valor: unknown): void {
  const estado = leerEstado();
  estado.datos[clave] = valor;
  fs.writeFileSync(ESTADO, JSON.stringify(estado, null, 2));
}

export function registrarResultadoHU(id: string, resultado: string): void {
  const estado = leerEstado();
  estado.hus[id] = resultado;
  fs.writeFileSync(ESTADO, JSON.stringify(estado, null, 2));
}

export function herramienta(...args: string[]): any {
  const salida = execFileSync(PYTHON, [HERRAMIENTAS, ...args], { encoding: 'utf8' });
  return JSON.parse(salida.trim().split('\n').pop() as string);
}

export interface Correo {
  archivo: string;
  fecha_utc: string;
  de: string;
  para: string[];
  cc: string[];
  asunto: string;
  texto: string;
  html: string | null;
}

/** Ultimo correo generado por el portal para el destinatario cuyo asunto contiene el texto (desde una fecha). */
export function buscarCorreo(destinatario: string, asunto: string, desde?: string): Correo | null {
  return herramienta('correo', OUTBOX, destinatario, asunto, ...(desde ? [desde] : []));
}

export function demoPassword(): string {
  const env = fs.readFileSync(`${__dirname}/../../../.env`, 'utf8');
  const match = env.match(/^DEMO_PASSWORD=(.*)$/m);
  if (!match || !match[1].trim()) throw new Error('DEMO_PASSWORD no está definida en .env');
  return match[1].trim();
}
