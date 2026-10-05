import { expect, test } from '@playwright/test';
import { leerEstado } from '../lib/estado';
import { ejecutarHU } from '../lib/hu';
import { cargarRequisitosAlta, clicNavegando, texto } from '../lib/portal';
import { escenarioEditarEliminar } from '../lib/requisitos';

const OBLIGATORIOS_MORAL = [
  'Acta constitutiva',
  'Poderes',
  'Cédula fiscal',
  'Identificación del representante legal',
  'Comprobante de domicilio del representante legal',
  'Comprobante de domicilio',
  'Estado de cuenta bancario',
];

test('HU-21 · Requisitos de alta del proveedor', async ({ browser }, testInfo) => {
  await ejecutarHU('HU-21', browser, testInfo, async (hu) => {
    const { run, fixtures } = leerEstado();
    const razonSocial = `QA Hotel Requisitos ${run} SA de CV`;
    const rfc = `QAH260101${run.slice(-3)}`;
    const admin = await hu.sesion('admin');
    let expediente = 0;

    await hu.escenario('Requisitos de alta configurados por tipo de proveedor', async () => {
      await hu.paso(
        admin,
        'Abrir Requisitos mínimos › Alta de proveedor',
        'La tabla muestra cada requisito con un nivel para Persona moral, Persona física e Internacional; los siete documentos de la solicitud son obligatorios para la persona moral.',
        async () => {
          await admin.goto('/admin/supplier-requirements');
          await expect(admin.locator('h1')).toHaveText('Requisitos de alta');
          const encabezados = await admin.locator('.requirements-table thead th').allInnerTexts();
          expect(encabezados.map((h) => h.trim().toUpperCase())).toEqual(['REQUISITO', 'PERSONA MORAL', 'PERSONA FÍSICA', 'INTERNACIONAL', 'ACCIONES']);
          for (const nombre of OBLIGATORIOS_MORAL) {
            const fila = admin.locator('.requirements-table tbody tr').filter({ has: admin.getByText(nombre, { exact: true }) });
            await expect(fila.locator('select').first()).toHaveValue('REQUIRED');
          }
          await hu.captura(admin, 'configuracion-requisitos', 'Requisitos de alta por tipo de proveedor: los siete de la solicitud, obligatorios para la persona moral.', {
            completa: true,
          });
          return `Columnas: ${encabezados.join(' | ')}. Obligatorios para persona moral: ${OBLIGATORIOS_MORAL.join(', ')}.`;
        },
      );
    });

    await hu.escenario('El alta pide los requisitos y no permite autorizar sin ellos', async () => {
      await hu.paso(
        admin,
        `Dar de alta la persona moral "${razonSocial}" con el formulario de proveedores`,
        'El proveedor queda "Registrado" y su expediente indica "Faltan 7 requisitos obligatorios"; el botón "Autorizar proveedor" está deshabilitado.',
        async () => {
          await admin.goto('/suppliers');
          const alta = admin.locator('details.admin-create').filter({ hasText: 'Agregar proveedor' });
          await alta.locator('summary').click();
          await alta.locator('[name=business_name]').fill(razonSocial);
          await alta.locator('[name=rfc]').fill(rfc);
          await alta.locator('[name=supplier_type]').selectOption('PERSONA_MORAL');
          await alta.locator('[name=email]').fill(`hotel.${run}@qa.example`.toLowerCase());
          await alta.locator('[name=phone]').fill('55 5555 0000');
          await alta.locator('[name=classification]').selectOption('EXTERNAL');
          await alta.locator('[name=main_activity]').selectOption('54');
          await alta.locator('[name=incorporation_date]').fill('2026-01-01');
          await alta.locator('[name=website]').fill('www.hotel-qa.example');
          await alta.locator('[name=legal_rep_name]').fill('Ana Martinez Ruiz');
          await alta.locator('[name=legal_rep_phone]').fill('55 1234 5678');
          await alta.locator('[name=contact_name]').fill('Luis Gomez Ortiz');
          await alta.locator('[name=contact_phone]').fill('55 8765 4321');
          await clicNavegando(admin, alta.getByRole('button', { name: 'Crear proveedor' }));
          expediente = Number(admin.url().match(/\/suppliers\/(\d+)/)?.[1]);
          await expect(admin.locator('.page-heading .status')).toHaveText('Registrado');
          await expect(admin.locator('.requirements-summary')).toHaveText('Faltan 7 requisitos obligatorios');
          await expect(admin.getByRole('button', { name: 'Autorizar proveedor' })).toBeDisabled();
          await hu.captura(admin, 'expediente-requisitos-pendientes', 'Expediente recién dado de alta: siete requisitos obligatorios pendientes y la autorización deshabilitada.', {
            completa: true,
          });
          return `Expediente ${expediente}: "${await texto(admin, '.requirements-summary')}"; botón "Autorizar proveedor" deshabilitado.`;
        },
      );
      await hu.paso(
        admin,
        'Buscarlo en el listado de proveedores',
        'No tiene casilla de selección; muestra "Faltan 7 requisitos" con la liga a su expediente.',
        async () => {
          await admin.goto(`/suppliers?q=${encodeURIComponent(razonSocial)}`);
          const fila = admin.locator('table tbody tr').filter({ hasText: razonSocial });
          await expect(fila.locator('input.authorize-check')).toHaveCount(0);
          await expect(fila.locator('a.requirement-pending')).toHaveText('Faltan 7 requisitos');
          await hu.captura(admin, 'listado-sin-casilla', 'Listado: el proveedor sin requisitos no se puede seleccionar para autorizar.', { enfocar: fila });
          return `Fila: "${(await fila.innerText()).replace(/\s+/g, ' ').trim()}".`;
        },
      );
    });

    await hu.escenario(
      'Con los requisitos completos se autoriza desde el expediente',
      async () => {
        await hu.paso(
          admin,
          'Cargar desde el expediente un documento por cada requisito obligatorio',
          'El expediente indica "Requisitos de alta completos" y el botón "Autorizar proveedor" se habilita.',
          async () => {
            await admin.goto(`/suppliers/${expediente}`);
            const cargados = await cargarRequisitosAlta(admin, fixtures.requisito_alta);
            expect(cargados).toEqual(OBLIGATORIOS_MORAL);
            await expect(admin.locator('.requirements-summary')).toHaveText('Requisitos de alta completos');
            await expect(admin.getByRole('button', { name: 'Autorizar proveedor' })).toBeEnabled();
            await hu.captura(admin, 'requisitos-completos', 'Expediente con los siete requisitos cargados.', { enfocar: admin.locator('.requirements-panel') });
            return `Cargados: ${cargados.join(', ')}.`;
          },
        );
        await hu.paso(
          admin,
          'Pulsar "Autorizar proveedor" y confirmar',
          'El proveedor queda "Autorizado" y el resumen indica "Autorizado · Credenciales enviadas".',
          async () => {
            await admin.getByRole('button', { name: 'Autorizar proveedor' }).click();
            await expect(admin.locator('#authorize-confirm-text')).toHaveText(
              `Se autorizará a ${razonSocial} y se le enviará su usuario y contraseña temporal por correo.`,
            );
            await Promise.all([admin.waitForURL(/\/suppliers\?authorization=/), admin.locator('#authorize-confirm-accept').click()]);
            const resumen = admin.locator('.authorization-summary');
            await expect(resumen.locator('tr').filter({ hasText: razonSocial })).toContainText('Autorizado · Credenciales enviadas');
            await hu.captura(admin, 'autorizado-desde-expediente', 'Resultado de la autorización desde el expediente.', { enfocar: resumen });
            return `Resumen: "${await texto(admin, '.authorization-summary .panel-header p')}".`;
          },
        );
      },
      { requiere: ['El alta pide los requisitos y no permite autorizar sin ellos'] },
    );

    await escenarioEditarEliminar(hu, admin, {
      url: '/admin/supplier-requirements',
      nombre: `Requisito temporal QA ${run}`,
      avisoEditado: 'Requisito actualizado',
      crear: async (nombre) => {
        await admin.locator('summary', { hasText: 'Nuevo requisito' }).click();
        await admin.locator('#new-name').fill(nombre);
        await clicNavegando(admin, admin.getByRole('button', { name: 'Crear requisito' }));
        await expect(admin.locator('.alert-success')).toHaveText('Requisito creado');
      },
    });
  });
});
