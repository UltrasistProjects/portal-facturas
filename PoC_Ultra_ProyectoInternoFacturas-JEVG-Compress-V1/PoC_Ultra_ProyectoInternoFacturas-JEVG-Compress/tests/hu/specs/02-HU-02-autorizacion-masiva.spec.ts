import { expect, test } from '@playwright/test';
import { guardarDato, leerEstado } from '../lib/estado';
import { ejecutarHU } from '../lib/hu';
import { abrirExpediente, cargarRequisitosAlta, texto } from '../lib/portal';

test('HU-02 · Autorización masiva de proveedores', async ({ browser }, testInfo) => {
  await ejecutarHU('HU-02', browser, testInfo, async (hu) => {
    const { run, fixtures } = leerEstado();
    const proveedores = hu.requiere<{ razon_social: string; correo: string }[]>('HU-01', 'hu01.proveedores');
    const admin = await hu.sesion('admin');
    let inicioAutorizacion = '';

    await hu.escenario('Selección múltiple y autorización en una sola operación', async () => {
      await hu.paso(
        admin,
        'Cargar desde su expediente los requisitos de alta de los proveedores cargados en HU-01 (HU-21)',
        'Cada expediente queda con "Requisitos de alta completos"; el proveedor internacional no tiene requisitos.',
        async () => {
          const cargados: string[] = [];
          for (const proveedor of proveedores) {
            await abrirExpediente(admin, proveedor.razon_social);
            const nombres = await cargarRequisitosAlta(admin, fixtures.requisito_alta);
            await expect(admin.locator('.requirements-summary')).toHaveText(
              nombres.length ? 'Requisitos de alta completos' : 'Sin requisitos de alta configurados para proveedores internacionales',
            );
            cargados.push(`${proveedor.razon_social}: ${nombres.length} documentos`);
          }
          return cargados.join('; ') + '.';
        },
      );
      await hu.paso(
        admin,
        'Filtrar el catálogo por estatus "Registrado" y seleccionar los proveedores cargados en HU-01',
        'Sólo los proveedores "Registrado" con sus requisitos de alta completos tienen casilla; al marcar 3, el contador indica "3 seleccionados".',
        async () => {
          await admin.goto('/suppliers');
          await admin.locator('select[name=status]').selectOption('REGISTERED');
          await admin.locator('input[name=q]').fill(run);
          await admin.getByRole('button', { name: 'Filtrar' }).click();
          await expect(admin).toHaveURL(/status=REGISTERED/);
          for (const proveedor of proveedores) {
            await admin
              .locator('table tbody tr')
              .filter({ hasText: proveedor.razon_social })
              .locator('input.authorize-check')
              .check();
          }
          await expect(admin.locator('#authorize-count')).toHaveText('3 seleccionados');
          await expect(admin.locator('#authorize-submit')).toBeEnabled();
          await hu.captura(admin, 'seleccion-registrados', 'Proveedores en "Registrado" con 3 casillas marcadas y el contador "3 seleccionados".');
          return `Contador: "${await texto(admin, '#authorize-count')}"; botón "Autorizar seleccionados" habilitado.`;
        },
      );
      await hu.paso(
        admin,
        'Pulsar "Autorizar seleccionados"',
        'Un modal pide confirmación porque se enviarán las credenciales a cada proveedor.',
        async () => {
          await admin.locator('#authorize-submit').click();
          await expect(admin.locator('#authorize-confirm')).toBeVisible();
          await expect(admin.locator('#authorize-confirm-text')).toHaveText(
            'Se autorizarán 3 proveedores y se enviará a cada uno su usuario y contraseña temporal por correo.',
          );
          await hu.captura(admin, 'modal-confirmacion', 'Modal "Autorizar proveedores" con el texto de confirmación.');
          return `Modal: "${await texto(admin, '#authorize-confirm-text')}".`;
        },
      );
      await hu.paso(
        admin,
        'Confirmar con "Autorizar y enviar credenciales"',
        'Los 3 proveedores quedan "Autorizado" en una sola operación y el resumen indica "Autorizado · Credenciales enviadas" para cada uno.',
        async () => {
          inicioAutorizacion = new Date(Date.now() - 2000).toISOString();
          await Promise.all([admin.waitForURL(/\/suppliers/), admin.locator('#authorize-confirm-accept').click()]);
          const resumen = admin.locator('.authorization-summary');
          await expect(resumen).toBeVisible();
          await expect(resumen.locator('.panel-header p')).toHaveText('3 autorizados · 0 omitidos · 0 no autorizados');
          for (const proveedor of proveedores) {
            await expect(resumen.locator('tr').filter({ hasText: proveedor.razon_social })).toContainText(
              'Autorizado · Credenciales enviadas',
            );
          }
          await hu.captura(admin, 'resultado-autorizacion', 'Resultado de la autorización: 3 autorizados, credenciales enviadas a cada proveedor.', {
            enfocar: resumen,
          });
          return `Resumen: "${await texto(admin, '.authorization-summary .panel-header p')}"; cada fila: "Autorizado · Credenciales enviadas".`;
        },
      );
      await hu.paso(
        admin,
        'Consultar el catálogo filtrado por estatus "Autorizado"',
        'Los 3 proveedores aparecen con estatus "Autorizado" y ya no tienen casilla de selección.',
        async () => {
          await admin.goto(`/suppliers?q=${encodeURIComponent(run)}&status=ACTIVE`);
          for (const proveedor of proveedores) {
            const fila = admin.locator('table tbody tr').filter({ hasText: proveedor.razon_social });
            await expect(fila.locator('.status')).toHaveText('Autorizado');
            await expect(fila.locator('input.authorize-check')).toHaveCount(0);
          }
          await hu.captura(admin, 'catalogo-autorizados', 'Catálogo filtrado por "Autorizado": los 3 proveedores con su nuevo estatus.');
          return `${proveedores.length} proveedores con estatus "Autorizado" y sin casilla de selección.`;
        },
      );
      guardarDato('hu02.autorizados', { proveedores, desde: inicioAutorizacion });
    });

    await hu.escenario(
      'El proveedor sin autorizar sigue "Registrado"',
      async () => {
        await hu.paso(
          admin,
          'Consultar el proveedor de la carga parcial de HU-01 (no seleccionado)',
          'Conserva el estatus "Registrado": la autorización sólo afecta a los seleccionados.',
          async () => {
            await admin.goto(`/suppliers?q=${encodeURIComponent(`Delta Valida ${run}`)}`);
            const fila = admin.locator('table tbody tr').filter({ hasText: `QA Delta Valida ${run}` });
            await expect(fila.locator('.status')).toHaveText('Registrado');
            await hu.captura(admin, 'no-seleccionado-registrado', 'El proveedor que no se seleccionó sigue en "Registrado".');
            return `"QA Delta Valida ${run} SA de CV" sigue con estatus "${await fila.locator('.status').innerText()}".`;
          },
        );
      },
      { requiere: ['Selección múltiple y autorización en una sola operación'] },
    );
  });
});
