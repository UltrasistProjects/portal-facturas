import { expect, test, type Page } from '@playwright/test';
import { ejecutarHU } from '../lib/hu';
import { resultadoRegla, texto } from '../lib/portal';

/** Abre en una pestaña nueva el visor de un documento ("Ver <tipo>") y espera a que cargue. */
async function verDocumento(page: Page, tipo: string): Promise<Page> {
  const [pestana] = await Promise.all([page.waitForEvent('popup'), page.locator(`a[aria-label="Ver ${tipo}"]`).click()]);
  await pestana.waitForLoadState('load');
  return pestana;
}

test('HU-19 · Visualización de detalle de factura por PMO', async ({ browser }, testInfo) => {
  await ejecutarHU('HU-19', browser, testInfo, async (hu) => {
    const nacional = hu.requiere<{ id: number; numero: string }>('HU-13', 'hu13.enviada');
    const internacional = hu.requiere<{ id: number; numero: string }>('HU-16', 'hu16.enviada');
    const pmo = await hu.sesion('pmo');

    await hu.escenario('Detalle de la factura nacional: datos, proveedor e historial', async () => {
      await hu.paso(
        pmo,
        `Abrir el detalle de ${nacional.numero}`,
        'Se muestran el estatus "Enviada", los datos principales (número, UUID, proyecto, total), los datos del CFDI (emisor y receptor), el bloque "Proveedor" y el "Historial".',
        async () => {
          await pmo.goto(`/invoices/${nacional.id}`);
          await expect(pmo.locator('.page-heading .status')).toHaveText('Enviada');
          await expect(pmo.locator('.metadata-grid')).toContainText(nacional.numero);
          await expect(pmo.locator('.metadata-grid')).toContainText('$116,000.00 MXN');
          await expect(pmo.locator('.panel').filter({ hasText: 'Datos CFDI' }).locator('dl')).toContainText('ULTRASIST · ULT940623AG0');
          await hu.captura(pmo, 'detalle-encabezado', `Detalle de ${nacional.numero}: estatus, score, datos principales, documentos y datos del CFDI.`);
          const proveedor = pmo.locator('#supplier');
          await expect(proveedor).toContainText('Nacional');
          await expect(proveedor).toContainText('TIC210101ABC');
          await expect(proveedor).toContainText('proveedor1@poc.local');
          await expect(pmo.locator('#history')).toContainText('Enviada a validación');
          await hu.captura(pmo, 'detalle-proveedor-historial', 'Bloques "Proveedor" e "Historial" del detalle.', { enfocar: proveedor });
          return `Metadatos: ${(await pmo.locator('.metadata-grid').innerText()).replace(/\s+/g, ' ')}; Proveedor: ${(await proveedor.locator('dl').innerText()).replace(/\s+/g, ' ')}; Historial: ${(await pmo.locator('#history ol').innerText()).replace(/\s+/g, ' ')}.`;
        },
      );
    });

    await hu.escenario('Visualización de la factura (PDF y XML) y de los documentos soporte', async () => {
      await hu.paso(pmo, 'Pulsar "Ver" (ojo) en el PDF del CFDI', 'Se abre una pestaña del portal con las páginas del PDF renderizadas.', async () => {
        const visor = await verDocumento(pmo, 'PDF del CFDI');
        await expect(visor.locator('h1')).toHaveText('PDF del CFDI');
        const pagina = visor.locator('img.document-page').first();
        await expect(pagina).toBeVisible();
        await expect.poll(() => pagina.evaluate((img) => (img as HTMLImageElement).naturalWidth)).toBeGreaterThan(0);
        await hu.captura(visor, 'visor-pdf-cfdi', 'Visor del portal: PDF del CFDI renderizado como imagen.');
        const paginas = await visor.locator('img.document-page').count();
        await visor.close();
        return `Pestaña "${await texto(pmo, 'h1')}" › visor con ${paginas} página(s) renderizada(s) del PDF del CFDI.`;
      });
      await hu.paso(pmo, 'Pulsar "Ver" en el XML del CFDI', 'Se abre el XML como texto (escapado), sin que el navegador lo interprete.', async () => {
        const visor = await verDocumento(pmo, 'XML del CFDI');
        const contenido = visor.locator('pre.document-text');
        await expect(contenido).toContainText('<cfdi:Comprobante');
        await expect(contenido).toContainText('Rfc="ULT940623AG0"');
        await hu.captura(visor, 'visor-xml-cfdi', 'Visor del portal: XML del CFDI mostrado como texto.');
        await visor.close();
        return 'El visor muestra el texto del XML (<cfdi:Comprobante …>, Receptor Rfc="ULT940623AG0").';
      });
      await hu.paso(pmo, 'Pulsar "Ver" en la Orden de compra (documento soporte)', 'Se abre el documento soporte en el visor.', async () => {
        const visor = await verDocumento(pmo, 'Orden de compra');
        await expect(visor.locator('h1')).toHaveText('Orden de compra');
        await expect(visor.locator('.document-viewer')).not.toBeEmpty();
        await hu.captura(visor, 'visor-orden-compra', 'Visor del portal: Orden de compra (documento soporte).');
        const resumen = (await visor.locator('.document-viewer').innerText()).replace(/\s+/g, ' ').slice(0, 120);
        await visor.close();
        return `Visor de la Orden de compra: "${resumen}…".`;
      });
    });

    await hu.escenario('Resultado de las validaciones automáticas previas', async () => {
      await hu.paso(
        pmo,
        'Revisar el score y la matriz de evidencia',
        'Se muestra el score con correctas/advertencias/errores/críticos y cada regla con su resultado, esperado y detectado.',
        async () => {
          await pmo.goto(`/invoices/${nacional.id}`);
          const resumen = (await pmo.locator('.hero-summary').innerText()).replace(/\s+/g, ' ');
          const grupos = await pmo.locator('#validations .rule-group h3').allInnerTexts();
          expect(grupos.length).toBeGreaterThanOrEqual(4);
          const xml010 = await resultadoRegla(pmo, 'XML-010');
          await hu.captura(pmo, 'score-validaciones', 'Score de validación y resumen de resultados.', { enfocar: pmo.locator('.hero-summary') });
          await hu.captura(pmo, 'matriz-evidencia', 'Matriz de evidencia con las reglas evaluadas.', {
            enfocar: pmo.locator('#validations .rule-group').filter({ has: pmo.locator('h3', { hasText: /^XML$/ }) }),
          });
          return `Resumen: ${resumen}; grupos de reglas: ${grupos.join(', ')}; ejemplo XML-010 ${xml010.estado} (esperado ${xml010.esperado}, detectado ${xml010.detectado}).`;
        },
      );
    });

    await hu.escenario('Detalle de la factura internacional: Invoice, datos capturados y reglas INT', async () => {
      await hu.paso(
        pmo,
        `Abrir el detalle de ${internacional.numero}`,
        'Se muestran "Datos del Invoice" (importes capturados) y los resultados INT-001 a INT-004.',
        async () => {
          await pmo.goto(`/invoices/${internacional.id}`);
          await expect(pmo.locator('#invoice-data')).toContainText('$1,000.00 USD');
          const reglas = [];
          for (const codigo of ['INT-001', 'INT-002', 'INT-003', 'INT-004']) {
            const regla = await resultadoRegla(pmo, codigo);
            reglas.push(`${codigo} ${regla.estado}`);
          }
          await hu.captura(pmo, 'detalle-internacional', `Detalle de ${internacional.numero}: documentos y "Datos del Invoice".`, { enfocar: pmo.locator('#invoice-data') });
          await hu.captura(pmo, 'reglas-int-pmo', 'Resultados INT del Invoice vistos por el PMO.', {
            enfocar: pmo.locator('#validations .rule-group').filter({ has: pmo.locator('h3', { hasText: /^INT$/ }) }),
          });
          return `Datos del Invoice: ${(await pmo.locator('#invoice-data dl').innerText()).replace(/\s+/g, ' ')}; ${reglas.join(', ')}.`;
        },
      );
      await hu.paso(pmo, 'Pulsar "Ver" en el Invoice (PDF)', 'El Invoice se muestra renderizado en el visor del portal.', async () => {
        const visor = await verDocumento(pmo, 'Invoice (PDF)');
        const pagina = visor.locator('img.document-page').first();
        await expect(pagina).toBeVisible();
        await expect.poll(() => pagina.evaluate((img) => (img as HTMLImageElement).naturalWidth)).toBeGreaterThan(0);
        await hu.captura(visor, 'visor-invoice', 'Visor del portal: Invoice (PDF) del proveedor internacional.');
        await visor.close();
        return 'Invoice renderizado en el visor del portal.';
      });
    });

    await hu.escenario('Desde el detalle se accede a la decisión (RF-10)', async () => {
      await hu.paso(pmo, `En ${nacional.numero}, pulsar "Decidir"`, 'Se llega al panel "Decisión" con los botones Autorizar, Observaciones y Rechazar.', async () => {
        await pmo.goto(`/invoices/${nacional.id}`);
        await pmo.getByRole('link', { name: /Decidir/ }).click();
        const panel = pmo.locator('#decision');
        await expect(panel).toBeInViewport();
        for (const boton of ['Autorizar', 'Observaciones', 'Rechazar']) await expect(panel.getByRole('button', { name: boton })).toBeVisible();
        await hu.captura(pmo, 'panel-decision', 'Panel "Decisión" del detalle con sus tres botones.', { enfocar: panel });
        return `Panel "${await texto(pmo, '#decision h2')}" con botones: ${(await panel.locator('.decision-actions button').allInnerTexts()).map((b) => b.trim()).join(', ')}.`;
      });
    });
  });
});
