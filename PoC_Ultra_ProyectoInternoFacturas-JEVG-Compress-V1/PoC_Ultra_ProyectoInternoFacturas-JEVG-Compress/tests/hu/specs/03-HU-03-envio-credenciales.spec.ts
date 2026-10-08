import { expect, test } from '@playwright/test';
import { buscarCorreo, guardarDato, herramienta, type Correo } from '../lib/estado';
import { ejecutarHU } from '../lib/hu';
import { texto } from '../lib/portal';

test('HU-03 · Envío de credenciales al proveedor', async ({ browser }, testInfo) => {
  await ejecutarHU('HU-03', browser, testInfo, async (hu) => {
    const { proveedores, desde } = hu.requiere<{ proveedores: { razon_social: string; correo: string }[]; desde: string }>(
      'HU-02',
      'hu02.autorizados',
    );
    const proveedor = proveedores[0];
    const admin = await hu.sesion('admin');
    let correo: Correo | null = null;

    await hu.escenario('Envío automático del correo con usuario y contraseña temporal al autorizar', async () => {
      await hu.paso(
        admin,
        'Abrir Administración › Notificaciones y revisar la bitácora de envíos',
        'La bitácora registra un envío "Credenciales de acceso" con resultado "Enviado" para cada proveedor autorizado en HU-02.',
        async () => {
          await admin.goto('/admin/notifications');
          const bitacora = admin.locator('section.panel').filter({ hasText: 'Bitácora de envíos' });
          for (const p of proveedores) {
            const fila = bitacora.locator('tbody tr').filter({ hasText: p.correo });
            await expect(fila.first()).toContainText('Credenciales de acceso');
            await expect(fila.first().locator('.status')).toHaveText('Enviado');
          }
          await hu.captura(admin, 'bitacora-credenciales', 'Bitácora de envíos: "Credenciales de acceso" enviado a cada proveedor autorizado.', {
            enfocar: bitacora.locator('tbody tr').filter({ hasText: proveedores[0].correo }),
          });
          return `Bitácora con ${proveedores.length} envíos "Credenciales de acceso" en estado "Enviado" para: ${proveedores.map((p) => p.correo).join(', ')}.`;
        },
      );
      await hu.paso(
        null,
        `Abrir el correo generado para ${proveedor.correo}`,
        'El correo va al correo del proveedor e incluye el usuario, la contraseña temporal y la dirección de inicio de sesión del portal.',
        async () => {
          correo = buscarCorreo(proveedor.correo, 'Acceso al Portal de Proveedores ULTRASIST', desde);
          expect(correo, 'No se encontró el correo de credenciales en el outbox').not.toBeNull();
          const c = correo as Correo;
          expect(c.para).toEqual([proveedor.correo]);
          expect(c.texto).toContain(`Usuario: ${proveedor.correo}`);
          const temporal = c.texto.match(/Contraseña temporal: (\S+)/)?.[1] ?? '';
          expect(temporal.length).toBeGreaterThanOrEqual(8);
          expect(c.texto).toMatch(/Portal: http:\/\/127\.0\.0\.1:8000\/login/);
          await hu.capturaCorreo(c, 'correo-credenciales', `Correo "Credenciales de acceso" generado por el portal para ${proveedor.correo}.`);
          return `Correo "${c.asunto}" para ${c.para.join(', ')}: incluye "Usuario: ${proveedor.correo}", una contraseña temporal de ${temporal.length} caracteres y "Portal: http://127.0.0.1:8000/login".`;
        },
      );
    });

    await hu.escenario('Expediente del proveedor: acceso al portal con contraseña temporal', async () => {
      await hu.paso(
        admin,
        `Abrir el expediente de ${proveedor.razon_social}`,
        'La sección "Acceso al portal" muestra el usuario, la contraseña "Temporal, pendiente de cambio" (leída de Keycloak) y "Credenciales enviadas el …".',
        async () => {
          await admin.goto(`/suppliers?q=${encodeURIComponent(proveedor.correo)}`);
          await admin.locator('table tbody tr').filter({ hasText: proveedor.razon_social }).getByRole('link', { name: 'Ver expediente' }).click();
          const acceso = admin.locator('.access-panel');
          await expect(acceso.locator('dd').nth(0)).toHaveText(proveedor.correo);
          await expect(acceso.locator('dd').nth(1)).toHaveText('Nunca');
          await expect(acceso.locator('dd').nth(2)).toHaveText('Temporal, pendiente de cambio');
          await expect(acceso.locator('dd').nth(3)).toContainText('Credenciales enviadas el');
          await hu.captura(admin, 'expediente-acceso-portal', 'Expediente: "Acceso al portal" con usuario, contraseña temporal pendiente de cambio y envío de credenciales.', {
            enfocar: acceso,
          });
          return `Acceso al portal: ${(await acceso.locator('dl').innerText()).replace(/\s+/g, ' ')}`;
        },
      );
    });

    await hu.escenario('RN-HU03-01: el portal no almacena la contraseña (sólo Keycloak)', async () => {
      await hu.paso(
        null,
        `Consultar en la base del portal el usuario ${proveedor.correo} (sólo lectura)`,
        'El usuario existe con rol Proveedor, enlazado a Keycloak por su "sub", sin contraseña ni hash guardados (password_hash vacío).',
        async () => {
          const usuario = herramienta('usuario', proveedor.correo);
          expect(usuario).not.toBeNull();
          expect(usuario.rol).toBe('Proveedor');
          expect(usuario.password_hash_vacio).toBe(true);
          expect(usuario.keycloak_sub_registrado).toBe(true);
          return `Usuario ${usuario.correo}: rol ${usuario.rol}, keycloak_sub registrado = ${usuario.keycloak_sub_registrado}, password_hash vacío = ${usuario.password_hash_vacio}.`;
        },
      );
    });

    guardarDato('hu03.credencial', { correo: proveedor.correo, razon_social: proveedor.razon_social, desde });
  });
});
