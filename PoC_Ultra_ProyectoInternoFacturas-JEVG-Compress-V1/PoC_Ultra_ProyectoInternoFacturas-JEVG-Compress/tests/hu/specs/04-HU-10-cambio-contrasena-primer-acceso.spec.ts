import { expect, test, type Page } from '@playwright/test';
import { buscarCorreo, leerEstado } from '../lib/estado';
import { Bloqueo, ejecutarHU } from '../lib/hu';
import { clicNavegando, texto } from '../lib/portal';
import { KEYCLOAK_URL } from '../lib/rutas';

const errorKeycloak = (page: Page) => page.locator('.kc-feedback-text, #input-error, #input-error-username').filter({ hasText: /\S/ }).first();

async function loginKeycloak(page: Page, usuario: string, contrasena: string): Promise<void> {
  await page.locator('#username').fill(usuario);
  await page.locator('#password').fill(contrasena);
  await clicNavegando(page, page.locator('#kc-login'));
}

test('HU-10 · Cambio de contraseña en primer inicio de sesión', async ({ browser }, testInfo) => {
  await ejecutarHU('HU-10', browser, testInfo, async (hu) => {
    const { run } = leerEstado();
    const credencial = hu.requiere<{ correo: string; razon_social: string; desde: string }>('HU-03', 'hu03.credencial');
    const correo = buscarCorreo(credencial.correo, 'Acceso al Portal de Proveedores ULTRASIST', credencial.desde);
    const temporal = correo?.texto.match(/Contraseña temporal: (\S+)/)?.[1];
    if (!temporal) throw new Bloqueo(`No se encontró el correo de credenciales de ${credencial.correo} (HU-03).`);
    const nueva = `Qa#${run}x9`;
    const proveedor = await (await hu.nuevoContexto()).newPage();

    await hu.escenario('Primer inicio de sesión: el sistema exige cambiar la contraseña temporal', async () => {
      await hu.paso(
        proveedor,
        'Abrir el portal y llegar al inicio de sesión',
        'El portal redirige al inicio de sesión de Keycloak (proveedor de identidad).',
        async () => {
          await proveedor.goto('/');
          await expect(proveedor).toHaveURL(new RegExp(`^${KEYCLOAK_URL}/realms/ultrasist-portal/`));
          await expect(proveedor.locator('#kc-login')).toBeVisible();
          await hu.captura(proveedor, 'login-keycloak', 'Pantalla de inicio de sesión de Keycloak a la que redirige el portal.');
          return `Redirigido a ${new URL(proveedor.url()).origin}${new URL(proveedor.url()).pathname} con el título "${(await proveedor.title()).trim()}".`;
        },
      );
      await hu.paso(
        proveedor,
        `Iniciar sesión con el usuario (${credencial.correo}) y la contraseña temporal del correo de HU-03`,
        'En lugar de entrar al portal, Keycloak muestra "Cambiar contraseña" (acción requerida UPDATE_PASSWORD).',
        async () => {
          await loginKeycloak(proveedor, credencial.correo, temporal);
          await expect(proveedor).toHaveURL(/required-action\?execution=UPDATE_PASSWORD/);
          await expect(proveedor.locator('h1')).toHaveText(/Cambiar contraseña/);
          await expect(proveedor.locator('#password-new')).toBeVisible();
          await hu.captura(proveedor, 'solicitud-cambio-contrasena', 'Keycloak exige "Cambiar contraseña" en el primer inicio de sesión.');
          return `Pantalla "${await texto(proveedor, 'h1')}" con los campos nueva contraseña y confirmación (URL con execution=UPDATE_PASSWORD).`;
        },
      );
    });

    await hu.escenario(
      'No permite continuar la operación sin cambiar la contraseña',
      async () => {
        await hu.paso(
          proveedor,
          'Intentar abrir directamente la página de Facturas del portal sin cambiar la contraseña',
          'El portal no abre: no hay sesión y se vuelve al inicio de sesión de Keycloak.',
          async () => {
            await proveedor.goto('/invoices');
            await expect(proveedor).toHaveURL(new RegExp(`^${KEYCLOAK_URL}/`));
            await expect(proveedor.locator('.sidebar')).toHaveCount(0);
            await hu.captura(proveedor, 'acceso-directo-bloqueado', 'Al pedir /invoices sin haber cambiado la contraseña, se regresa a Keycloak.');
            return `Navegar a /invoices terminó en ${new URL(proveedor.url()).origin}${new URL(proveedor.url()).pathname} ("${await texto(proveedor, 'h1')}"); el portal no se mostró.`;
          },
        );
        await hu.paso(
          proveedor,
          'Volver a iniciar sesión con la contraseña temporal',
          'Keycloak vuelve a exigir "Cambiar contraseña".',
          async () => {
            await loginKeycloak(proveedor, credencial.correo, temporal);
            await expect(proveedor.locator('h1')).toHaveText(/Cambiar contraseña/);
            return `Se muestra otra vez "${await texto(proveedor, 'h1')}".`;
          },
        );
      },
      { requiere: ['Primer inicio de sesión: el sistema exige cambiar la contraseña temporal'] },
    );

    const invalidas = [
      { clave: 'Password123', motivo: 'sin carácter especial' },
      { clave: 'Ab#1x', motivo: 'menos de 8 caracteres' },
      { clave: 'Clave#Segura', motivo: 'sin número' },
      { clave: '12345678#', motivo: 'sin letra' },
    ];
    await hu.escenario(
      'Política de la nueva contraseña: mínimo 8 caracteres, una letra, un número y un carácter especial',
      async () => {
        for (const { clave, motivo } of invalidas) {
          await hu.paso(
            proveedor,
            `Capturar la contraseña "${clave}" (${motivo})`,
            'Se rechaza con un mensaje de la política y se permanece en "Cambiar contraseña".',
            async () => {
              await proveedor.locator('#password-new').fill(clave);
              await proveedor.locator('#password-confirm').fill(clave);
              await clicNavegando(proveedor, proveedor.locator('#kc-submit'));
              await expect(proveedor.locator('h1')).toHaveText(/Cambiar contraseña/);
              const mensaje = errorKeycloak(proveedor);
              await expect(mensaje).toBeVisible();
              await hu.captura(proveedor, `rechazo-${motivo}`, `Contraseña "${clave}" rechazada (${motivo}).`);
              const textoError = (await mensaje.innerText()).replace(/\s+/g, ' ').trim();
              if (/expresión regular/i.test(textoError)) {
                hu.nota(
                  `Observación de usabilidad (no bloquea el criterio): la contraseña "${clave}" (${motivo}) se rechaza con el mensaje genérico de Keycloak "${textoError}", que no le indica al proveedor que falta una letra.`,
                );
              }
              return `Rechazada: "${textoError}".`;
            },
          );
        }
      },
      { requiere: ['No permite continuar la operación sin cambiar la contraseña'] },
    );

    await hu.escenario(
      'Cambio exitoso con una contraseña que cumple la política',
      async () => {
        await hu.paso(
          proveedor,
          'Capturar una contraseña válida (letra, número, carácter especial y 14 caracteres) y confirmarla',
          'Keycloak acepta la contraseña y el proveedor entra al portal (tablero con su usuario y rol Proveedor).',
          async () => {
            await proveedor.locator('#password-new').fill(nueva);
            await proveedor.locator('#password-confirm').fill(nueva);
            await proveedor.locator('#kc-submit').click();
            await expect(proveedor.locator('.sidebar-footer')).toContainText(credencial.correo);
            await expect(proveedor.locator('.role-pill')).toHaveText('Proveedor');
            await expect(proveedor.locator('h1')).toContainText('Hola');
            await hu.captura(proveedor, 'acceso-portal-tras-cambio', 'Tras cambiar la contraseña, el proveedor entra al tablero del portal.');
            return `Portal abierto en ${proveedor.url()}: "${await texto(proveedor, 'h1')}", rol "${await texto(proveedor, '.role-pill')}", usuario ${credencial.correo}.`;
          },
        );
        const admin = await hu.sesion('admin');
        await hu.paso(
          admin,
          'El Administrador consulta el expediente del proveedor',
          'La sección "Acceso al portal" muestra la contraseña "Cambiada por el proveedor" y el último acceso.',
          async () => {
            await admin.goto(`/suppliers?q=${encodeURIComponent(credencial.correo)}`);
            await admin.locator('table tbody tr').first().getByRole('link', { name: 'Ver expediente' }).click();
            const acceso = admin.locator('.access-panel');
            await expect(acceso.locator('dd').nth(2)).toHaveText('Cambiada por el proveedor');
            await expect(acceso.locator('dd').nth(1)).not.toHaveText('Nunca');
            await hu.captura(admin, 'expediente-contrasena-cambiada', 'Expediente: contraseña "Cambiada por el proveedor" y último acceso registrado.', { enfocar: acceso });
            return `Acceso al portal: ${(await acceso.locator('dl').innerText()).replace(/\s+/g, ' ')}`;
          },
        );
      },
      { requiere: ['Política de la nueva contraseña: mínimo 8 caracteres, una letra, un número y un carácter especial'] },
    );

    await hu.escenario(
      'La contraseña temporal deja de funcionar',
      async () => {
        await hu.paso(
          proveedor,
          'Cerrar sesión e intentar entrar otra vez con la contraseña temporal',
          'Keycloak rechaza la contraseña temporal.',
          async () => {
            await clicNavegando(proveedor, proveedor.getByRole('button', { name: 'Cerrar sesion' }));
            await proveedor.goto('/login');
            await loginKeycloak(proveedor, credencial.correo, temporal);
            await expect(proveedor).toHaveURL(new RegExp(`^${KEYCLOAK_URL}/`));
            const mensaje = errorKeycloak(proveedor);
            await expect(mensaje).toBeVisible();
            await hu.captura(proveedor, 'temporal-rechazada', 'La contraseña temporal ya no permite iniciar sesión.');
            return `Inicio de sesión rechazado: "${(await mensaje.innerText()).replace(/\s+/g, ' ').trim()}".`;
          },
        );
        await hu.paso(
          proveedor,
          'Iniciar sesión con la contraseña nueva',
          'El proveedor entra directamente al portal, sin que se le pida otro cambio.',
          async () => {
            await loginKeycloak(proveedor, credencial.correo, nueva);
            await expect(proveedor.locator('.sidebar-footer')).toContainText(credencial.correo);
            await hu.captura(proveedor, 'acceso-con-contrasena-nueva', 'Con la contraseña nueva el proveedor entra directamente al portal.');
            return `Acceso directo al portal: "${await texto(proveedor, 'h1')}".`;
          },
        );
      },
      { requiere: ['Cambio exitoso con una contraseña que cumple la política'] },
    );
  });
});
