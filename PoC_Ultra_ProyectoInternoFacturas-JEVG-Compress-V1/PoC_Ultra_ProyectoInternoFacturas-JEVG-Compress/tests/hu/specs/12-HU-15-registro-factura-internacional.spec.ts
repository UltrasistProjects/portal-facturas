import { expect, test } from '@playwright/test';
import path from 'node:path';
import { guardarDato, leerEstado } from '../lib/estado';
import { ejecutarHU } from '../lib/hu';
import { cargarDocumento, clicNavegando, enviarAlta, estatusFactura, llenarAltaFactura, resumenObligatorios, texto } from '../lib/portal';

const IMPORTES = { fecha: '2026-08-31', moneda: 'USD', subtotal: '1000.00', impuestos: '0.00' };

test('HU-15 · Registro de factura por proveedor internacional', async ({ browser }, testInfo) => {
  await ejecutarHU('HU-15', browser, testInfo, async (hu) => {
    const { run, fixtures } = leerEstado();
    const numero = `QA-${run}-I1`;
    const proveedor = await hu.sesion('proveedor3');
    let facturaId = 0;

    await hu.escenario('Formulario del Invoice: datos e importes del proveedor internacional', async () => {
      await hu.paso(
        proveedor,
        'Abrir "Nueva factura"',
        'El formulario pide, además de los datos generales, la sección "Datos del Invoice" (fecha, moneda del catálogo, subtotal e impuestos; el total se calcula) y sólo ofrece el contrato del proveedor.',
        async () => {
          await proveedor.goto('/invoices/new');
          await expect(proveedor.locator('h1')).toHaveText('Registrar factura');
          await expect(proveedor.locator('.foreign-invoice-heading h2')).toHaveText('Datos del Invoice');
          for (const campo of ['#invoice_date', '#currency', '#subtotal', '#tax', '#total']) await expect(proveedor.locator(campo)).toBeVisible();
          const contratos = await proveedor.locator('#contract option').allInnerTexts();
          expect(contratos).toEqual([expect.stringContaining('Analitica Global 2026')]);
          await hu.captura(proveedor, 'formulario-invoice', 'Formulario de registro del proveedor internacional con "Datos del Invoice".', { completa: true });
          const monedas = await proveedor.locator('#currency option').allInnerTexts();
          return `Contrato ofrecido: ${contratos.join(' | ')}; monedas del catálogo: ${monedas.join(', ')}; total de solo lectura.`;
        },
      );
      await hu.paso(
        proveedor,
        'Capturar subtotal 1,000.50 e impuestos 160.08',
        'El Total se recalcula al capturar (1,160.58) y no se puede editar: el servidor lo vuelve a calcular e ignora cualquier total enviado.',
        async () => {
          await llenarAltaFactura(proveedor, { numero, invoice: { ...IMPORTES, subtotal: '1,000.50', impuestos: '160.08' } });
          const total = proveedor.locator('#total');
          await expect(total).toHaveValue('1,160.58');
          await expect(total).toHaveAttribute('readonly', '');
          await hu.captura(proveedor, 'total-calculado', 'Total calculado en vivo: subtotal + impuestos, de solo lectura.', { enfocar: total });
          return `Total mostrado "${await total.inputValue()}" (solo lectura).`;
        },
      );
    });

    await hu.escenario('Registro y carga del Invoice en PDF y de los documentos soporte configurados', async () => {
      await hu.paso(
        proveedor,
        `Registrar ${numero} con importes consistentes (1,000.00 USD)`,
        'Se abre la carga documental: se ofrecen Invoice (PDF) y los soportes, no el XML ni el PDF del CFDI; faltan 3 obligatorios (Invoice, Orden de compra y Vo.Bo.).',
        async () => {
          await proveedor.goto('/invoices/new');
          await llenarAltaFactura(proveedor, { numero, invoice: IMPORTES });
          facturaId = await enviarAlta(proveedor);
          const opciones = await proveedor.locator('#document_type option').allInnerTexts();
          expect(opciones.some((o) => o.startsWith('Invoice (PDF)'))).toBe(true);
          expect(opciones.some((o) => o.startsWith('XML del CFDI') || o.startsWith('PDF del CFDI'))).toBe(false);
          await expect(proveedor.locator('.required-summary')).toContainText('Faltan 3 archivos obligatorios');
          await hu.captura(proveedor, 'carga-documental-invoice', 'Carga documental del proveedor internacional: Invoice (PDF) y soportes; 3 obligatorios pendientes.');
          return `Factura #${facturaId}; tipos ofrecidos: ${opciones.map((o) => o.split(' (')[0]).join(', ')}; checklist "${await resumenObligatorios(proveedor)}".`;
        },
      );
      await hu.paso(
        proveedor,
        `Cargar el Invoice "${path.basename(fixtures.invoice)}", la Orden de compra y el Vo.Bo.`,
        'Obligatorios completos ("Factura cargada. Ya puede enviarla a validación.") y la factura queda "Cargada".',
        async () => {
          await cargarDocumento(proveedor, 'FOREIGN_INVOICE', fixtures.invoice);
          await cargarDocumento(proveedor, 'PURCHASE_ORDER', fixtures.orden_compra);
          await cargarDocumento(proveedor, 'APPROVAL', fixtures.vobo);
          await expect(proveedor.locator('.required-summary')).toContainText('Archivos obligatorios completos');
          await expect(proveedor.locator('.required-summary')).toContainText('Factura cargada. Ya puede enviarla a validación.');
          await hu.captura(proveedor, 'invoice-cargado', 'Invoice y soportes cargados: obligatorios completos.');
          const checklist = await resumenObligatorios(proveedor);
          const estatus = await estatusFactura(proveedor, facturaId);
          expect(estatus).toBe('Cargada');
          await hu.captura(proveedor, 'detalle-cargada', `Detalle de ${numero} en "Cargada" con los "Datos del Invoice".`);
          return `Checklist "${checklist}"; estatus "${estatus}".`;
        },
      );
      guardarDato('hu15.factura', { id: facturaId, numero });
    });

    await hu.escenario(
      'Invoice duplicado por nombre de archivo',
      async () => {
        const numero2 = `QA-${run}-I2`;
        await hu.paso(
          proveedor,
          `Registrar ${numero2} e intentar cargar un Invoice con el mismo nombre de archivo ("${path.basename(fixtures.invoice)}")`,
          'La carga se rechaza (Invoice duplicado, indicando el folio de la otra factura) y el Invoice sigue pendiente.',
          async () => {
            await proveedor.goto('/invoices/new');
            await llenarAltaFactura(proveedor, { numero: numero2, invoice: IMPORTES });
            await enviarAlta(proveedor);
            await cargarDocumento(proveedor, 'FOREIGN_INVOICE', fixtures.invoice);
            const error = proveedor.locator('.alert-danger');
            await expect(error).toContainText(`Ya existe una factura con un Invoice llamado «${path.basename(fixtures.invoice)}»`);
            await expect(proveedor.locator('.document-row').filter({ hasText: 'Invoice (PDF)' })).toContainText('Pendiente');
            await expect(proveedor.locator('.required-summary')).toContainText('Faltan 3 archivos obligatorios');
            await hu.captura(proveedor, 'invoice-duplicado', 'Carga rechazada: ya existe una factura con un Invoice con ese nombre de archivo.');
            return `Rechazado: "${await texto(proveedor, '.alert-danger')}"; Invoice sigue "Pendiente".`;
          },
        );
        await hu.paso(
          proveedor,
          `Cargar en ${numero2} un Invoice con otro nombre ("${path.basename(fixtures.invoice_otro)}")`,
          'La carga se acepta: el control de duplicados es por nombre de archivo.',
          async () => {
            await cargarDocumento(proveedor, 'FOREIGN_INVOICE', fixtures.invoice_otro);
            await expect(proveedor.locator('.alert-danger')).toHaveCount(0);
            await expect(proveedor.locator('.document-row').filter({ hasText: 'Invoice (PDF)' })).toContainText(path.basename(fixtures.invoice_otro));
            await hu.captura(proveedor, 'invoice-otro-nombre', 'Un Invoice con otro nombre de archivo sí se acepta.');
            return `Aceptado; checklist "${await resumenObligatorios(proveedor)}".`;
          },
        );
      },
      { requiere: ['Registro y carga del Invoice en PDF y de los documentos soporte configurados'] },
    );
  });
});
