import { expect, test } from '@playwright/test';
import { buscarCorreo, leerEstado } from '../lib/estado';
import { ejecutarHU } from '../lib/hu';
import { clicNavegando, enviarAValidacion, texto } from '../lib/portal';

test('HU-17 · Consulta de estatus de factura', async ({ browser }, testInfo) => {
  await ejecutarHU('HU-17', browser, testInfo, async (hu) => {
    const { run } = leerEstado();
    const rechazada = hu.requiere<{ id: number; numero: string; texto: string }>('HU-20', 'hu20.rechazada');
    const observaciones = hu.requiere<{ id: number; numero: string; texto: string }>('HU-20', 'hu20.observaciones');
    const autorizada = hu.requiere<{ id: number; numero: string }>('HU-20', 'hu20.autorizada');
    const cancelada = hu.requiere<{ id: number; numero: string; limite: string }>('HU-14', 'hu14.cancelada');
    const ajena = hu.requiere<{ id: number; numero: string }>('HU-16', 'hu16.enviada');
    const proveedor = await hu.sesion('proveedor1');
    const filas = () => proveedor.locator('table.enterprise-table tbody tr');
    let fechaListado = '';

    await hu.escenario('Tablero con indicadores de seguimiento por estatus', async () => {
      await hu.paso(proveedor, 'Abrir el tablero', 'Se muestran el total de facturas y los indicadores Enviadas, Observaciones, Autorizadas, Rechazadas y Canceladas.', async () => {
        await proveedor.goto('/');
        const indicadores = [];
        for (const id of ['kpi-total', 'kpi-under_review', 'kpi-requires_correction', 'kpi-accepted', 'kpi-rejected', 'kpi-cancelled']) {
          const kpi = proveedor.locator(`#${id}`);
          await expect(kpi).toBeVisible();
          indicadores.push(`${(await kpi.locator('span').innerText()).trim()}: ${(await kpi.locator('strong').innerText()).trim()}`);
        }
        await hu.captura(proveedor, 'tablero-indicadores', 'Tablero del proveedor con los indicadores por estatus.');
        return indicadores.join('; ') + '.';
      });
    });

    await hu.escenario('Listado de sus facturas con el estatus actual de cada una', async () => {
      await hu.paso(
        proveedor,
        `Abrir "Facturas" con "Todos los estados" y buscar "QA-${run}"`,
        'Se listan sólo sus facturas con su estatus (Cargada, Autorizada, Rechazada, Observaciones, Cancelada); la factura del proveedor internacional no aparece.',
        async () => {
          await proveedor.goto(`/invoices?status=&q=${encodeURIComponent(`QA-${run}`)}`);
          const esperados: [string, string][] = [
            [autorizada.numero, 'Autorizada'],
            [rechazada.numero, 'Rechazada'],
            [observaciones.numero, 'Observaciones'],
            [cancelada.numero, 'Cancelada'],
            [`QA-${run}-N3`, 'Cargada'],
          ];
          for (const [numero, estatus] of esperados) await expect(filas().filter({ hasText: numero }).locator('.status')).toHaveText(estatus);
          fechaListado = (await filas().filter({ hasText: rechazada.numero }).locator('td').nth(2).innerText()).trim();
          await expect(filas().filter({ hasText: ajena.numero })).toHaveCount(0);
          await expect(proveedor.locator('table.enterprise-table thead')).not.toContainText('Proveedor');
          await hu.captura(proveedor, 'listado-estatus', 'Listado del proveedor: cada factura con su estatus actual.', { completa: true });
          return `Estatus: ${esperados.map(([n, e]) => `${n} = ${e}`).join('; ')}; ${ajena.numero} (de otro proveedor) no se lista.`;
        },
      );
      await hu.paso(proveedor, 'Filtrar por el estatus "Observaciones"', 'Sólo se listan facturas en "Observaciones".', async () => {
        await proveedor.locator('select[name=status]').selectOption('REQUIRES_CORRECTION');
        await proveedor.locator('input[name=q]').fill('');
        await clicNavegando(proveedor, proveedor.getByRole('button', { name: 'Filtrar' }));
        const estatus = await filas().locator('.status').allInnerTexts();
        expect(estatus.length).toBeGreaterThan(0);
        expect(new Set(estatus)).toEqual(new Set(['Observaciones']));
        await expect(filas().filter({ hasText: observaciones.numero })).toHaveCount(1);
        await hu.captura(proveedor, 'filtro-observaciones', 'Listado filtrado por "Observaciones".');
        return `${estatus.length} factura(s), todas en "Observaciones", incluida ${observaciones.numero}.`;
      });
    });

    await hu.escenario('Motivo del rechazo visible para el proveedor', async () => {
      await hu.paso(
        proveedor,
        `Abrir ${rechazada.numero} ("Rechazada")`,
        'El detalle destaca "Motivo del rechazo" con el mismo texto que capturó el PMO y que recibió por correo; el seguimiento atribuye la decisión a "PMO".',
        async () => {
          await proveedor.goto(`/invoices/${rechazada.id}`);
          await expect(proveedor.locator('.page-heading .status')).toHaveText('Rechazada');
          const causa = proveedor.locator('#decision-cause');
          await expect(causa.locator('strong')).toHaveText('Motivo del rechazo');
          await expect(causa.locator('p').first()).toHaveText(rechazada.texto);
          const correo = buscarCorreo('proveedor1@poc.local', `Factura ${rechazada.numero} rechazada`);
          expect(correo?.texto ?? '').toContain(rechazada.texto);
          await expect(proveedor.locator('#history')).toContainText('PMO');
          await expect(proveedor.locator('#history')).not.toContainText('PMO Demo');
          await hu.captura(proveedor, 'motivo-rechazo', 'Detalle "Rechazada" con el motivo del rechazo.');
          // Coherencia de fechas: el seguimiento muestra la hora de negocio (America/Mexico_City).
          const fechaSeguimiento = ((await proveedor.locator('#history li span').first().innerText()).match(/\d{2}\/\d{2}\/\d{4}/) ?? [''])[0];
          if (fechaListado && fechaSeguimiento && fechaListado !== fechaSeguimiento) {
            hu.nota(
              `Defecto observado (no afecta los criterios de la HU): en el listado del proveedor, la columna "Fecha" de ${rechazada.numero} muestra ${fechaListado}, mientras su seguimiento registra el envío el ${fechaSeguimiento} (hora de negocio). La factura se creó y envió minutos antes, después de las 18:00 de Ciudad de México: el listado muestra la fecha en UTC (components/invoice_table.html usa created_at.strftime sin convertir a la zona de negocio). Ver evidencias "listado-estatus" y "seguimiento-rechazo".`,
            );
          }
          await hu.captura(proveedor, 'seguimiento-rechazo', 'Seguimiento: envío y decisión del PMO (sin el nombre del revisor).', { enfocar: proveedor.locator('#history') });
          return `"Motivo del rechazo": "${await causa.locator('p').first().innerText()}" (igual al correo); seguimiento: ${(await proveedor.locator('#history ol').innerText()).replace(/\s+/g, ' ')}.`;
        },
      );
    });

    await hu.escenario('Observaciones del PMO y reenvío de la factura corregida', async () => {
      await hu.paso(
        proveedor,
        `Abrir ${observaciones.numero} ("Observaciones")`,
        'El detalle destaca "Observaciones del PMO" con el texto del correo e indica "Corrija lo indicado y vuelva a enviar la factura" con acceso a la carga documental.',
        async () => {
          await proveedor.goto(`/invoices/${observaciones.id}`);
          await expect(proveedor.locator('.page-heading .status')).toHaveText('Observaciones');
          const causa = proveedor.locator('#decision-cause');
          await expect(causa.locator('strong')).toHaveText('Observaciones del PMO');
          await expect(causa.locator('p').first()).toHaveText(observaciones.texto);
          await expect(causa.locator('.decision-next')).toContainText('Corrija lo indicado y vuelva a enviar la factura.');
          await expect(causa.getByRole('link', { name: 'Gestionar documentos' })).toBeVisible();
          const correo = buscarCorreo('proveedor1@poc.local', `Factura ${observaciones.numero} con observaciones`);
          expect(correo?.texto ?? '').toContain(observaciones.texto);
          await hu.captura(proveedor, 'observaciones-pmo', 'Detalle en "Observaciones" con la causa del PMO y la indicación de corregir y reenviar.');
          return `"Observaciones del PMO": "${await causa.locator('p').first().innerText()}" (igual al correo); "${await texto(proveedor, '#decision-cause .decision-next')}".`;
        },
      );
      await hu.paso(proveedor, 'Pulsar "Enviar a validación" para reenviarla', 'La factura vuelve a "Enviada" y el seguimiento registra el segundo envío.', async () => {
        await enviarAValidacion(proveedor);
        await expect(proveedor.locator('.page-heading .status')).toHaveText('Enviada');
        await expect(proveedor.locator('#history li').filter({ hasText: 'Enviada a validación' })).toHaveCount(2);
        await hu.captura(proveedor, 'reenviada', `${observaciones.numero} reenviada: estatus "Enviada" y seguimiento con dos envíos.`);
        return `Estatus "${await texto(proveedor, '.page-heading .status')}"; seguimiento: ${(await proveedor.locator('#history ol').innerText()).replace(/\s+/g, ' ')}.`;
      });
    });

    await hu.escenario('Factura cancelada: fecha límite de aceptación y acuse', async () => {
      await hu.paso(proveedor, `Abrir ${cancelada.numero} ("Cancelada")`, `Se informa la cancelación y la fecha límite (${cancelada.limite}) y el acuse aparece entre los documentos.`, async () => {
        await proveedor.goto(`/invoices/${cancelada.id}`);
        await expect(proveedor.locator('.page-heading .status')).toHaveText('Cancelada');
        await expect(proveedor.locator('#cancelled')).toContainText(cancelada.limite);
        await expect(proveedor.locator('#history')).toContainText('Fecha límite de aceptación');
        await hu.captura(proveedor, 'cancelada-fecha-limite', 'Detalle "Cancelada" con la fecha límite de aceptación.');
        return `"${await texto(proveedor, '#cancelled')}".`;
      });
    });

    await hu.escenario('Aislamiento: no puede consultar facturas de otro proveedor', async () => {
      await hu.paso(proveedor, `Abrir por URL la factura ${ajena.numero} (del proveedor internacional)`, 'El portal responde 404 y no muestra la factura.', async () => {
        const respuesta = await proveedor.goto(`/invoices/${ajena.id}`);
        expect(respuesta?.status()).toBe(404);
        await expect(proveedor.locator('.error-page')).toBeVisible();
        await expect(proveedor.locator('body')).not.toContainText(ajena.numero);
        await hu.captura(proveedor, 'factura-ajena-404', 'Factura de otro proveedor: respuesta 404.');
        return `HTTP ${respuesta?.status()}: "${await texto(proveedor, '.error-page p')}".`;
      });
    });
  });
});
