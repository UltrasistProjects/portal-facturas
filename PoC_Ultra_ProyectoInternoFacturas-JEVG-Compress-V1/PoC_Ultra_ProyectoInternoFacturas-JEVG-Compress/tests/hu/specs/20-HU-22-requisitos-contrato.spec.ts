import { expect, type Page } from '@playwright/test';
import { test } from '@playwright/test';
import { leerEstado } from '../lib/estado';
import { ejecutarHU } from '../lib/hu';
import { clicNavegando, texto } from '../lib/portal';
import { escenarioEditarEliminar } from '../lib/requisitos';

// Proveedor demo persona fisica: el contrato activado aqui se suma a sus contratos. El de HU-12 (proveedor1) debe
// conservar un solo contrato activo, por eso no se usa.
const PROVEEDOR = 'Carlos Hernandez Lopez (DEMO)';

async function cargarDocumentoContrato(page: Page, codigo: string, archivo: string): Promise<void> {
  const formulario = page.locator('details.admin-create').filter({ hasText: 'Agregar documento del contrato' });
  if (!(await formulario.evaluate((el) => (el as HTMLDetailsElement).open))) await formulario.locator('summary').click();
  await formulario.locator('#contract-document-type').selectOption(codigo);
  await formulario.locator('input[name=upload]').setInputFiles(archivo);
  await clicNavegando(page, formulario.getByRole('button', { name: 'Guardar documento' }));
  await expect(page.locator('.alert-success')).toHaveText('Documento guardado');
}

test('HU-22 · Requisitos de alta del contrato', async ({ browser }, testInfo) => {
  await ejecutarHU('HU-22', browser, testInfo, async (hu) => {
    const { run, fixtures } = leerEstado();
    const proyecto = `QA Contrato ${run}`;
    const admin = await hu.sesion('admin');
    let contrato = 0;

    await hu.escenario('Requisitos del contrato configurados en Requisitos mínimos', async () => {
      await hu.paso(
        admin,
        'Abrir Requisitos mínimos › Alta de contrato',
        'El menú agrupa las tres configuraciones de documentos; la tabla muestra Contrato como Obligatorio fijo (con candado), y Orden de compra y Anexos como Opcionales con varios archivos.',
        async () => {
          await admin.goto('/admin/contract-requirements');
          await expect(admin.locator('h1')).toHaveText('Requisitos de alta del contrato');
          const menu = admin.locator('.sidebar nav');
          for (const opcion of ['Archivos de factura', 'Alta de proveedor', 'Alta de contrato']) {
            await expect(menu.getByRole('link', { name: opcion })).toBeVisible();
          }
          const filas = admin.locator('.requirements-table tbody tr');
          const firmado = filas.filter({ has: admin.getByText('Contrato', { exact: true }) });
          await expect(firmado.locator('.fixed-level')).toContainText('Obligatorio');
          await expect(firmado).toContainText('Todo contrato activo tiene su contrato firmado');
          for (const nombre of ['Orden de compra', 'Anexos']) {
            const fila = filas.filter({ has: admin.getByText(nombre, { exact: true }) });
            await expect(fila.locator('select')).toHaveValue('OPTIONAL');
            await expect(fila.locator('td').nth(1)).toHaveText('Sí');
          }
          await hu.captura(admin, 'configuracion-requisitos-contrato', 'Requisitos del contrato: Contrato obligatorio fijo; Orden de compra y Anexos opcionales.', {
            completa: true,
          });
          return 'Menú "Requisitos mínimos": Archivos de factura, Alta de proveedor y Alta de contrato. Contrato: Obligatorio con candado; Orden de compra y Anexos: Opcional, varios archivos.';
        },
      );
    });

    await hu.escenario('El alta crea el contrato Registrado y pide sus requisitos', async () => {
      await hu.paso(
        admin,
        `Dar de alta el contrato "${proyecto}" de ${PROVEEDOR}`,
        'El contrato queda "Registrado", el sistema abre su expediente con "Contrato creado. Cargue sus requisitos para activarlo." y "Falta 1 requisito obligatorio"; el botón "Activar contrato" está deshabilitado.',
        async () => {
          await admin.goto('/contracts');
          const alta = admin.locator('details.admin-create').filter({ hasText: 'Agregar contrato' });
          await alta.locator('summary').click();
          await alta.locator('[name=supplier_id]').selectOption({ label: PROVEEDOR });
          await alta.locator('[name=project_name]').fill(proyecto);
          await alta.locator('[name=project_leader]').fill('Miguel PMO (DEMO)');
          await alta.locator('[name=authorized_technology]').fill('Python Data Analytics');
          await alta.locator('[name=authorized_amount]').fill('50000');
          await alta.locator('[name=start_date]').fill('2026-01-01');
          await alta.locator('[name=end_date]').fill('2026-12-31');
          await clicNavegando(admin, alta.getByRole('button', { name: 'Crear contrato' }));
          contrato = Number(admin.url().match(/\/contracts\/(\d+)/)?.[1]);
          await expect(admin.locator('.alert-success')).toHaveText('Contrato creado. Cargue sus requisitos para activarlo.');
          await expect(admin.locator('.page-heading .status')).toHaveText('Registrado');
          await expect(admin.locator('.requirements-summary')).toHaveText('Falta 1 requisito obligatorio');
          await expect(admin.getByRole('button', { name: 'Activar contrato' })).toBeDisabled();
          await expect(admin.locator('.authorize-hint')).toHaveText('Cargue los requisitos obligatorios para activar');
          await hu.captura(admin, 'contrato-registrado', 'Expediente del contrato recién creado: el contrato firmado pendiente y la activación deshabilitada.', {
            completa: true,
          });
          return `Contrato ${contrato}: "${await texto(admin, '.requirements-summary')}"; botón "Activar contrato" deshabilitado.`;
        },
      );
      await hu.paso(
        admin,
        'Buscarlo en el listado de contratos',
        'El listado lo muestra "Registrado" con "Faltan 1" en la columna Requisitos y liga a su expediente.',
        async () => {
          await admin.goto(`/contracts?q=${encodeURIComponent(proyecto)}`);
          const fila = admin.locator('table tbody tr').filter({ hasText: proyecto });
          await expect(fila).toContainText('Registrado');
          await expect(fila).toContainText('Faltan 1');
          await expect(fila.getByRole('link', { name: proyecto })).toHaveAttribute('href', `/contracts/${contrato}`);
          await hu.captura(admin, 'listado-contrato-por-activar', 'Listado de contratos: el contrato por activar con su requisito pendiente.', { enfocar: fila });
          return `Fila: "${(await fila.innerText()).replace(/\s+/g, ' ').trim()}".`;
        },
      );
    });

    await hu.escenario(
      'Con el contrato firmado se activa y se ofrece al facturar',
      async () => {
        await hu.paso(
          admin,
          'Cargar el contrato firmado y dos anexos desde el expediente del contrato',
          'El panel indica "Requisitos del contrato completos", lista los dos anexos y el botón "Activar contrato" se habilita.',
          async () => {
            await admin.goto(`/contracts/${contrato}`);
            await cargarDocumentoContrato(admin, 'SIGNED_CONTRACT', fixtures.requisito_alta);
            await cargarDocumentoContrato(admin, 'CONTRACT_ANNEXES', fixtures.requisito_alta);
            await cargarDocumentoContrato(admin, 'CONTRACT_ANNEXES', fixtures.requisito_alta);
            await expect(admin.locator('.requirements-summary')).toHaveText('Requisitos del contrato completos');
            const anexos = admin.locator('.requirements-panel .document-row').filter({ hasText: 'Anexos' }).locator('a.contract-file');
            await expect(anexos).toHaveCount(2);
            await expect(admin.getByRole('button', { name: 'Activar contrato' })).toBeEnabled();
            await hu.captura(admin, 'requisitos-contrato-completos', 'Expediente del contrato con el contrato firmado y dos anexos.', {
              enfocar: admin.locator('.requirements-panel'),
            });
            return `"${await texto(admin, '.requirements-summary')}"; anexos cargados: 2.`;
          },
        );
        await hu.paso(
          admin,
          'Pulsar "Activar contrato" y confirmar',
          'El diálogo de la página pide confirmación; el contrato queda "Activo" con el aviso "Contrato activado".',
          async () => {
            await admin.getByRole('button', { name: 'Activar contrato' }).click();
            await expect(admin.locator('#activate-confirm-text')).toHaveText(
              `Se activará el contrato ${proyecto} de ${PROVEEDOR}. El proveedor podrá registrar facturas con él.`,
            );
            await hu.captura(admin, 'confirmacion-activacion', 'Diálogo de confirmación de la activación.', { enfocar: admin.locator('#activate-confirm .modal-content') });
            await Promise.all([admin.waitForURL(/\?ok=activated/), admin.locator('#activate-confirm-accept').click()]);
            await expect(admin.locator('.alert-success')).toHaveText('Contrato activado');
            await expect(admin.locator('.page-heading .status')).toHaveText('Activo');
            await hu.captura(admin, 'contrato-activo', 'Contrato activado.', { completa: true });
            return `Estatus: "${await texto(admin, '.page-heading .status')}"; aviso: "${await texto(admin, '.alert-success')}".`;
          },
        );
        await hu.paso(
          null,
          'Abrir "Registrar factura" con el usuario del proveedor',
          'El formulario ofrece el contrato activado entre los contratos del proveedor.',
          async () => {
            const proveedor = await hu.sesion('proveedor2');
            await proveedor.goto('/invoices/new');
            const contratos = await proveedor.locator('#contract option').allInnerTexts();
            expect(contratos.some((opcion) => opcion.includes(proyecto))).toBe(true);
            await hu.captura(proveedor, 'contrato-ofrecido-al-facturar', 'Formulario "Registrar factura" del proveedor con el contrato activado.');
            return `Contratos ofrecidos: ${contratos.join(' | ')}.`;
          },
        );
      },
      { requiere: ['El alta crea el contrato Registrado y pide sus requisitos'] },
    );

    await escenarioEditarEliminar(hu, admin, {
      url: '/admin/contract-requirements',
      nombre: `Requisito de contrato temporal QA ${run}`,
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
