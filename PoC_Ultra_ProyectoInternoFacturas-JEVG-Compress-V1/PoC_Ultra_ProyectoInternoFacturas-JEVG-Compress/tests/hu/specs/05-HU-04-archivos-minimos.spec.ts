import { expect, test, type Page } from '@playwright/test';
import { leerEstado } from '../lib/estado';
import { ejecutarHU } from '../lib/hu';
import { cargarDocumento, clicNavegando, resumenObligatorios, texto } from '../lib/portal';
import { escenarioEditarEliminar } from '../lib/requisitos';

/** Abre la carga documental de una factura del proveedor buscandola por su numero. */
async function cargaDocumental(page: Page, numero: string): Promise<void> {
  await page.goto(`/invoices?q=${encodeURIComponent(numero)}`);
  await page.locator('table tbody tr').filter({ hasText: numero }).first().locator('a.icon-action').click();
  await page.getByRole('link', { name: /Gestionar documentos/ }).click();
  await expect(page.locator('h1')).toHaveText('Carga documental');
}

test('HU-04 · Definición de archivos requeridos por tipo de proveedor', async ({ browser }, testInfo) => {
  await ejecutarHU('HU-04', browser, testInfo, async (hu) => {
    const { run, fixtures } = leerEstado();
    const tipo = `Constancia QA ${run}`;
    const admin = await hu.sesion('admin');

    await hu.escenario('Configuración diferenciada para proveedores Nacional e Internacional', async () => {
      await hu.paso(
        admin,
        'Abrir Requisitos mínimos › Archivos de factura',
        'La tabla muestra cada tipo de documento con un nivel (Obligatorio / Opcional / No aplica) para Nacional y otro para Internacional; todos los niveles son editables, también los de los tipos del sistema.',
        async () => {
          await admin.goto('/admin/required-documents');
          await expect(admin.locator('h1')).toHaveText('Archivos mínimos');
          const encabezados = await admin.locator('.requirements-table thead th').allInnerTexts();
          expect(encabezados.map((h) => h.trim().toUpperCase())).toEqual(['TIPO DE DOCUMENTO', 'FORMATOS', 'NACIONAL', 'INTERNACIONAL', 'ACCIONES']);
          const xml = admin.locator('.requirements-table tbody tr').filter({ hasText: 'XML del CFDI' });
          await expect(xml.locator('td').nth(2).locator('select')).toHaveValue('REQUIRED');
          await expect(xml.locator('td').nth(3).locator('select')).toHaveValue('NOT_APPLICABLE');
          const invoice = admin.locator('.requirements-table tbody tr').filter({ hasText: 'Invoice (PDF)' });
          await expect(invoice.locator('td').nth(2).locator('select')).toHaveValue('NOT_APPLICABLE');
          await expect(invoice.locator('td').nth(3).locator('select')).toHaveValue('REQUIRED');
          await expect(admin.locator('.requirements-table .bi-lock-fill')).toHaveCount(0);
          await hu.captura(admin, 'configuracion-por-origen', 'Archivos mínimos por origen: columnas Nacional e Internacional, todos los niveles editables.', { completa: true });
          return `Columnas: ${encabezados.join(' | ')}. XML del CFDI: Nacional "Obligatorio" / Internacional "No aplica"; Invoice (PDF): Nacional "No aplica" / Internacional "Obligatorio". Sin niveles fijos: todos tienen selector.`;
        },
      );
      await hu.paso(
        admin,
        'Pulsar "Guardar configuración" sin cambiar nada',
        'El sistema responde "Sin cambios".',
        async () => {
          await admin.getByRole('button', { name: 'Guardar configuración' }).click();
          await expect(admin.locator('.alert-success')).toHaveText('Sin cambios');
          await hu.captura(admin, 'guardar-sin-cambios', 'Aviso "Sin cambios" al guardar la configuración sin modificaciones.');
          return `Aviso: "${await texto(admin, '.alert-success')}".`;
        },
      );
    });

    await hu.escenario('Alta de un tipo de documento soporte obligatorio sólo para el proveedor Internacional', async () => {
      await hu.paso(
        admin,
        `Crear el tipo soporte "${tipo}" (PDF; Nacional: No aplica; Internacional: Obligatorio)`,
        'Se crea el tipo ("Tipo de documento creado") y aparece en la configuración con esos niveles.',
        async () => {
          await admin.locator('summary', { hasText: 'Nuevo tipo de documento soporte' }).click();
          await admin.locator('#new-name').fill(tipo);
          await admin.locator('#new-description').fill('Documento soporte de prueba funcional HU-04');
          await admin.locator('#new-PDF').check();
          await admin.locator('#new-national').selectOption('NOT_APPLICABLE');
          await admin.locator('#new-international').selectOption('REQUIRED');
          await hu.captura(admin, 'formulario-tipo-soporte', 'Formulario "Nuevo tipo de documento soporte" capturado.', { enfocar: admin.locator('#new-name') });
          await admin.getByRole('button', { name: 'Crear tipo de documento' }).click();
          await expect(admin.locator('.alert-success')).toHaveText('Tipo de documento creado');
          const fila = admin.locator('.requirements-table tbody tr').filter({ hasText: tipo });
          await expect(fila.locator('td').nth(2).locator('select')).toHaveValue('NOT_APPLICABLE');
          await expect(fila.locator('td').nth(3).locator('select')).toHaveValue('REQUIRED');
          await hu.captura(admin, 'tipo-soporte-creado', `Tipo "${tipo}" en la configuración: Nacional "No aplica", Internacional "Obligatorio".`, { enfocar: fila });
          return `Aviso "${await texto(admin, '.alert-success')}"; fila "${tipo}" con Nacional = No aplica e Internacional = Obligatorio.`;
        },
      );
    });

    await hu.escenario(
      'La configuración condiciona la carga documental según el origen del proveedor',
      async () => {
        const internacional = await hu.sesion('proveedor3');
        await hu.paso(
          internacional,
          'El proveedor internacional abre la carga documental de su factura INV-2026-0042',
          `El checklist incluye "${tipo}" como Obligatorio y Pendiente, se ofrece Invoice (PDF) y no se ofrecen el XML ni el PDF del CFDI.`,
          async () => {
            await cargaDocumental(internacional, 'INV-2026-0042');
            const opciones = await internacional.locator('#document_type option').allInnerTexts();
            expect(opciones.some((o) => o.startsWith(tipo))).toBe(true);
            expect(opciones.some((o) => o.startsWith('Invoice (PDF)'))).toBe(true);
            expect(opciones.some((o) => o.startsWith('XML del CFDI') || o.startsWith('PDF del CFDI'))).toBe(false);
            const fila = internacional.locator('.document-row').filter({ hasText: tipo });
            await expect(fila).toContainText('Obligatorio · Pendiente');
            await expect(internacional.locator('.required-summary')).toContainText('Falta 1 archivo obligatorio');
            await hu.captura(internacional, 'internacional-tipo-obligatorio', `Carga documental del proveedor internacional: "${tipo}" obligatorio y pendiente.`);
            return `Checklist: "${await resumenObligatorios(internacional)}"; tipos ofrecidos: ${opciones.map((o) => o.split(' (')[0]).join(', ')}.`;
          },
        );
        await hu.paso(
          internacional,
          'El proveedor internacional intenta "Enviar a validación" INV-2026-0042 sin cargar el nuevo archivo obligatorio',
          'El envío no procede por el archivo obligatorio faltante y la factura no queda "Enviada".',
          async () => {
            const enviar = internacional.getByRole('button', { name: /Enviar a validación/ });
            let resultado: string;
            if (await enviar.count()) {
              await clicNavegando(internacional, enviar.first());
              const error = internacional.locator('.error-page, .alert-danger').first();
              await expect(error).toContainText(/obligatori/i);
              await hu.captura(internacional, 'envio-bloqueado-por-obligatorio', 'Intento de envío sin el archivo obligatorio: el envío no procede.');
              resultado = `Respuesta del portal: "${(await error.innerText()).replace(/\s+/g, ' ').trim()}"`;
            } else {
              await hu.captura(internacional, 'envio-no-ofrecido', 'Sin el archivo obligatorio, la carga documental no ofrece "Enviar a validación".');
              resultado = 'La carga documental no ofrece el botón "Enviar a validación"';
            }
            await internacional.goto('/invoices?status=&q=INV-2026-0042');
            const estatus = (await internacional.locator('table tbody tr').filter({ hasText: 'INV-2026-0042' }).locator('.status').innerText()).trim();
            expect(estatus).not.toBe('Enviada');
            return `${resultado}; estatus de INV-2026-0042: "${estatus}".`;
          },
        );
        const nacional = await hu.sesion('proveedor1');
        await hu.paso(
          nacional,
          'El proveedor nacional abre la carga documental de su factura D-SIN-VOBO',
          `Se ofrecen el XML y el PDF del CFDI; "${tipo}" no se ofrece porque no aplica al Nacional.`,
          async () => {
            await cargaDocumental(nacional, 'D-SIN-VOBO');
            const opciones = await nacional.locator('#document_type option').allInnerTexts();
            expect(opciones.some((o) => o.startsWith('XML del CFDI'))).toBe(true);
            expect(opciones.some((o) => o.startsWith('PDF del CFDI'))).toBe(true);
            expect(opciones.some((o) => o.startsWith(tipo))).toBe(false);
            await expect(nacional.locator('.document-row').filter({ hasText: tipo })).toHaveCount(0);
            await hu.captura(nacional, 'nacional-sin-tipo', `Carga documental del proveedor nacional: se ofrecen XML/PDF del CFDI y no "${tipo}".`);
            return `Checklist: "${await resumenObligatorios(nacional)}"; tipos ofrecidos: ${opciones.map((o) => o.split(' (')[0]).join(', ')}.`;
          },
        );
      },
      { requiere: ['Alta de un tipo de documento soporte obligatorio sólo para el proveedor Internacional'] },
    );

    await hu.escenario(
      'Eliminar el tipo soporte (baja lógica): deja de exigirse',
      async () => {
        await hu.paso(
          admin,
          `Eliminar "${tipo}" y confirmar`,
          'El portal responde "Tipo eliminado"; el tipo deja de listarse y se conserva en "Mostrar eliminados".',
          async () => {
            await admin.goto('/admin/required-documents');
            const fila = admin.locator('.requirements-table tbody tr').filter({ hasText: tipo });
            const confirmar = fila.locator('details.delete-confirm');
            await confirmar.locator('summary').click();
            await clicNavegando(admin, confirmar.getByRole('button', { name: 'Sí, eliminar' }));
            await expect(admin.locator('.alert-success')).toHaveText('Tipo eliminado');
            await expect(admin.locator('.requirements-table tbody tr').filter({ hasText: tipo })).toHaveCount(0);
            await admin.goto('/admin/required-documents?eliminados=1');
            const eliminado = admin.locator('#eliminados tbody tr').filter({ hasText: tipo });
            await expect(eliminado).toHaveCount(1);
            await hu.captura(admin, 'tipo-eliminado', `"${tipo}" en "Tipos eliminados", con "Restaurar".`, { enfocar: eliminado });
            return `Aviso "Tipo eliminado"; "${tipo}" listado en Tipos eliminados.`;
          },
        );
        const internacional = await hu.sesion('proveedor3');
        await hu.paso(
          internacional,
          'El proveedor internacional vuelve a la carga documental de INV-2026-0042 y reemplaza su Orden de compra',
          'El tipo eliminado ya no aparece, los obligatorios están completos y la factura vuelve a "Cargada" ("Factura cargada. Ya puede enviarla a validación.").',
          async () => {
            await cargaDocumental(internacional, 'INV-2026-0042');
            await expect(internacional.locator('.document-row').filter({ hasText: tipo })).toHaveCount(0);
            await cargarDocumento(internacional, 'PURCHASE_ORDER', fixtures.orden_compra);
            await expect(internacional.locator('.required-summary')).toContainText('Archivos obligatorios completos');
            await expect(internacional.locator('.required-summary')).toContainText('Factura cargada. Ya puede enviarla a validación.');
            await hu.captura(internacional, 'internacional-sin-tipo', 'Tras eliminar el tipo, el checklist está completo y la factura vuelve a "Cargada".');
            return `Checklist: "${await resumenObligatorios(internacional)}"; "${tipo}" ya no se lista.`;
          },
        );
      },
      { requiere: ['Alta de un tipo de documento soporte obligatorio sólo para el proveedor Internacional'] },
    );

    await escenarioEditarEliminar(hu, admin, {
      url: '/admin/required-documents',
      nombre: `Temporal QA ${run}`,
      avisoEditado: 'Tipo de documento actualizado',
      avisoEliminado: 'Tipo eliminado',
      crear: async (nombre) => {
        await admin.locator('summary', { hasText: 'Nuevo tipo de documento soporte' }).click();
        await admin.locator('#new-name').fill(nombre);
        await admin.locator('#new-PDF').check();
        await clicNavegando(admin, admin.getByRole('button', { name: 'Crear tipo de documento' }));
        await expect(admin.locator('.alert-success')).toHaveText('Tipo de documento creado');
      },
    });
  });
});
