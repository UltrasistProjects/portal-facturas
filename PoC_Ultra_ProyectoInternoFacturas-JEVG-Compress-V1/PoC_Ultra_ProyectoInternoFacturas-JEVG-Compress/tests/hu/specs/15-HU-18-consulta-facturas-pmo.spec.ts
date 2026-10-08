import { expect, test } from '@playwright/test';
import { leerEstado } from '../lib/estado';
import { ejecutarHU } from '../lib/hu';
import { clicNavegando, texto } from '../lib/portal';

test('HU-18 · Consulta de facturas por PMO', async ({ browser }, testInfo) => {
  await ejecutarHU('HU-18', browser, testInfo, async (hu) => {
    const { run } = leerEstado();
    const nacional = hu.requiere<{ id: number; numero: string }>('HU-13', 'hu13.enviada');
    const internacional = hu.requiere<{ id: number; numero: string }>('HU-16', 'hu16.enviada');
    const cancelada = hu.requiere<{ id: number; numero: string }>('HU-14', 'hu14.cancelada');
    const pmo = await hu.sesion('pmo');
    const filas = () => pmo.locator('table.enterprise-table tbody tr');

    await hu.escenario('Bandeja por omisión: facturas "Enviada", la que más ha esperado primero', async () => {
      await hu.paso(
        pmo,
        'El PMO abre "Facturas"',
        'Se muestra la bandeja de revisión con sólo facturas "Enviada", con proveedor, folio y número, origen, proyecto, fecha de envío, monto, score y estatus, ordenadas de la más antigua a la más reciente.',
        async () => {
          await pmo.goto('/');
          await clicNavegando(pmo, pmo.locator('.sidebar a.nav-item', { hasText: 'Facturas' }));
          await expect(pmo.locator('.page-heading p')).toHaveText('Bandeja de revisión: facturas enviadas, las que más han esperado primero.');
          await expect(pmo.locator('select[name=status]')).toHaveValue('UNDER_REVIEW');
          const encabezados = (await pmo.locator('table.enterprise-table thead th').allInnerTexts()).map((t) => t.trim().toUpperCase()).filter(Boolean);
          expect(encabezados).toEqual(['PROVEEDOR', 'FOLIO / FACTURA', 'ORIGEN', 'PROYECTO', 'ENVÍO', 'MONTO', 'SCORE', 'ESTADO']);
          const estatus = await filas().locator('.status').allInnerTexts();
          expect(estatus.length).toBeGreaterThan(0);
          expect(new Set(estatus)).toEqual(new Set(['Enviada']));
          await hu.captura(pmo, 'bandeja-enviadas', 'Bandeja del PMO: facturas "Enviada" con sus datos principales, la más antigua primero.', { completa: true });
          return `${estatus.length} facturas en la página, todas "Enviada"; columnas: ${encabezados.join(' | ')}; aviso "${await texto(pmo, '.page-heading p')}".`;
        },
      );
      await hu.paso(
        pmo,
        `Buscar en la bandeja las facturas de la corrida ("QA-${run}")`,
        `${nacional.numero} (enviada primero, en HU-13) aparece antes que ${internacional.numero} (enviada después, en HU-16); la factura cancelada ${cancelada.numero} no aparece.`,
        async () => {
          await pmo.locator('input[name=q]').fill(`QA-${run}`);
          await clicNavegando(pmo, pmo.getByRole('button', { name: 'Filtrar' }));
          await expect(pmo.locator('select[name=status]')).toHaveValue('UNDER_REVIEW');
          const textos = await filas().allInnerTexts();
          const posNacional = textos.findIndex((t) => t.includes(nacional.numero));
          const posInternacional = textos.findIndex((t) => t.includes(internacional.numero));
          expect(posNacional, `${nacional.numero} en la bandeja`).toBeGreaterThanOrEqual(0);
          expect(posInternacional, `${internacional.numero} en la bandeja`).toBeGreaterThan(posNacional);
          expect(textos.some((t) => t.includes(cancelada.numero))).toBe(false);
          await hu.captura(pmo, 'bandeja-orden-envio', `Bandeja filtrada por "QA-${run}": orden por fecha de envío y sin la factura cancelada.`);
          return `Orden: ${textos.map((t) => t.split('\n').find((l) => l.includes('QA-')) ?? '').filter(Boolean).join(' → ')}; ${cancelada.numero} no aparece.`;
        },
      );
    });

    await hu.escenario('Filtro por origen del proveedor', async () => {
      await hu.paso(
        pmo,
        `Elegir el origen "Internacional" y filtrar (búsqueda "QA-${run}")`,
        'Sólo se listan facturas de proveedores internacionales.',
        async () => {
          await pmo.goto(`/invoices?status=UNDER_REVIEW&q=${encodeURIComponent(`QA-${run}`)}`);
          await pmo.locator('select[name=origin]').selectOption('INTERNATIONAL');
          await clicNavegando(pmo, pmo.getByRole('button', { name: 'Filtrar' }));
          const origenes = await filas().locator('td:nth-child(3)').allInnerTexts();
          expect(origenes.length).toBeGreaterThan(0);
          expect(new Set(origenes.map((o) => o.trim()))).toEqual(new Set(['Internacional']));
          await expect(filas().filter({ hasText: internacional.numero })).toHaveCount(1);
          await hu.captura(pmo, 'filtro-internacional', 'Bandeja filtrada por origen "Internacional".');
          return `${origenes.length} factura(s), todas de origen "Internacional", incluida ${internacional.numero}.`;
        },
      );
      await hu.paso(
        pmo,
        `Elegir el origen "Nacional" y filtrar (búsqueda "QA-${run}")`,
        'Sólo se listan facturas de proveedores nacionales.',
        async () => {
          await pmo.locator('select[name=origin]').selectOption('NATIONAL');
          await clicNavegando(pmo, pmo.getByRole('button', { name: 'Filtrar' }));
          const origenes = await filas().locator('td:nth-child(3)').allInnerTexts();
          expect(new Set(origenes.map((o) => o.trim()))).toEqual(new Set(['Nacional']));
          await hu.captura(pmo, 'filtro-nacional', 'Bandeja filtrada por origen "Nacional".');
          return `${origenes.length} factura(s), todas de origen "Nacional".`;
        },
      );
    });

    await hu.escenario('Consulta de todas las facturas registradas con su estatus', async () => {
      await hu.paso(
        pmo,
        `Elegir "Todos los estados", "Todos los orígenes" y buscar "QA-${run}"`,
        'Se listan las facturas de la corrida de ambos proveedores, cada una con su estatus actual (incluida la Cancelada).',
        async () => {
          await pmo.goto('/invoices');
          await pmo.locator('select[name=status]').selectOption('');
          await pmo.locator('select[name=origin]').selectOption('');
          await pmo.locator('input[name=q]').fill(`QA-${run}`);
          await clicNavegando(pmo, pmo.getByRole('button', { name: 'Filtrar' }));
          await expect(filas().filter({ hasText: cancelada.numero }).locator('.status')).toHaveText('Cancelada');
          await expect(filas().filter({ hasText: nacional.numero }).locator('.status')).toHaveText('Enviada');
          await expect(filas().filter({ hasText: internacional.numero }).locator('.status')).toHaveText('Enviada');
          const resumen = await filas().evaluateAll((trs) =>
            trs.map((tr) => {
              const celdas = [...tr.querySelectorAll('td')].map((td) => (td as HTMLElement).innerText.replace(/\s+/g, ' ').trim());
              return `${celdas[1]} (${celdas[2]}): ${celdas[7]}`;
            }),
          );
          await hu.captura(pmo, 'todas-las-facturas', `Todas las facturas de la corrida (búsqueda "QA-${run}") con su estatus.`, { completa: true });
          return `Listado: ${resumen.join('; ')}.`;
        },
      );
    });

    await hu.escenario('Selección de una factura para su revisión', async () => {
      await hu.paso(
        pmo,
        `Seleccionar ${nacional.numero} en el listado`,
        'Se abre el detalle de la factura con el botón "Decidir".',
        async () => {
          await pmo.goto(`/invoices?status=UNDER_REVIEW&q=${encodeURIComponent(`QA-${run}`)}`);
          await clicNavegando(pmo, filas().filter({ hasText: nacional.numero }).locator('a.icon-action'));
          await expect(pmo).toHaveURL(new RegExp(`/invoices/${nacional.id}$`));
          await expect(pmo.getByRole('link', { name: /Decidir/ })).toBeVisible();
          await hu.captura(pmo, 'detalle-seleccionado', `Detalle de ${nacional.numero} abierto desde la bandeja, con "Decidir".`);
          return `Detalle /invoices/${nacional.id} ("${await texto(pmo, 'h1')}", estatus "${await texto(pmo, '.page-heading .status')}") con el botón "Decidir".`;
        },
      );
    });
  });
});
