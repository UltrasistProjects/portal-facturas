import { expect, test, type Page } from '@playwright/test';
import { buscarCorreo, guardarDato, leerEstado, type Correo } from '../lib/estado';
import { Bloqueo, ejecutarHU, limpiar } from '../lib/hu';
import { clicNavegando, enviarAValidacion, registrarFacturaNacional, texto } from '../lib/portal';

const PROVEEDOR = 'Tecnologia Integral del Centro SA de CV';
const CORREO_PROVEEDOR = 'proveedor1@poc.local';

async function abrirDecision(pmo: Page, id: number): Promise<void> {
  await pmo.goto(`/invoices/${id}`);
  await expect(pmo.locator('.page-heading .status')).toHaveText('Enviada');
  await pmo.getByRole('link', { name: /Decidir/ }).click();
  await expect(pmo.locator('#decision')).toBeInViewport();
}

test('HU-20 · Cambio de estatus de factura', async ({ browser }, testInfo) => {
  await ejecutarHU('HU-20', browser, testInfo, async (hu) => {
    const { run, fixtures } = leerEstado();
    const n1 = hu.requiere<{ id: number; numero: string }>('HU-13', 'hu13.enviada');
    const recepcion = hu.requiere<string[]>('HU-08', 'hu08.recepcion');
    const pmo = await hu.sesion('pmo');
    const rechazo = { id: 0, numero: `QA-${run}-N4`, texto: `QA ${run}: el subtotal del XML no coincide con la orden de compra OC-QA-${run}.` };
    const observacion = { id: 0, numero: `QA-${run}-N5`, texto: `QA ${run}: falta el Vo.Bo. firmado por el líder de proyecto; corrija y reenvíe.` };

    await hu.escenario('Precondición: el proveedor envía dos facturas más para decidir', async () => {
      const proveedor = await hu.sesion('proveedor1');
      await hu.paso(
        proveedor,
        `El proveedor registra y envía ${rechazo.numero} y ${observacion.numero} (XML correctos, UUID nuevos)`,
        'Ambas facturas quedan "Enviada".',
        async () => {
          try {
            for (const [factura, xml] of [[rechazo, fixtures.cfdi_ok_b], [observacion, fixtures.cfdi_ok_c]] as const) {
              factura.id = await registrarFacturaNacional(proveedor, factura.numero, {
                xml,
                pdf: fixtures.pdf_cfdi,
                ordenCompra: fixtures.orden_compra,
                vobo: fixtures.vobo,
              });
              await proveedor.goto(`/invoices/${factura.id}`);
              await enviarAValidacion(proveedor);
              await expect(proveedor.locator('.page-heading .status')).toHaveText('Enviada');
            }
          } catch (error) {
            throw new Bloqueo(`No se pudieron preparar las facturas para decidir: ${limpiar(error)}`);
          }
          await proveedor.goto(`/invoices?status=UNDER_REVIEW&q=QA-${run}`);
          await hu.captura(proveedor, 'precondicion-enviadas', 'Precondición: facturas de la corrida en "Enviada" (vista del proveedor).');
          return `${rechazo.numero} (#${rechazo.id}) y ${observacion.numero} (#${observacion.id}) en "Enviada".`;
        },
      );
    });

    await hu.escenario('Panel de decisión con tres botones: Autorizar, Observaciones y Rechazar', async () => {
      await hu.paso(pmo, `Abrir ${n1.numero} ("Enviada") y pulsar "Decidir"`, 'El panel "Decisión" ofrece los tres botones; el campo "Observaciones" aún no se despliega.', async () => {
        await abrirDecision(pmo, n1.id);
        const panel = pmo.locator('#decision');
        const botones = (await panel.locator('.decision-actions button').allInnerTexts()).map((b) => b.trim());
        expect(botones).toEqual(['Autorizar', 'Observaciones', 'Rechazar']);
        await expect(panel.locator('.observations-field')).toBeHidden();
        await hu.captura(pmo, 'panel-tres-botones', 'Panel de decisión: botones Autorizar, Observaciones y Rechazar.', { enfocar: panel });
        return `Botones: ${botones.join(', ')}; campo Observaciones oculto.`;
      });
    });

    await hu.escenario(
      'Rechazar: se despliega el campo "Observaciones" y es obligatorio (RN-HU20-01)',
      async () => {
        await hu.paso(pmo, `En ${rechazo.numero}, pulsar "Rechazar"`, 'Se despliega el campo "Observaciones" para capturar la causa, sin enviar todavía.', async () => {
          await abrirDecision(pmo, rechazo.id);
          await pmo.locator('#decision').getByRole('button', { name: 'Rechazar' }).click();
          await expect(pmo.locator('#observations')).toBeVisible();
          await expect(pmo.locator('#observations')).toBeFocused();
          await expect(pmo.locator('.page-heading .status')).toHaveText('Enviada');
          await hu.captura(pmo, 'rechazar-despliega-observaciones', 'Al pulsar Rechazar se despliega el campo "Observaciones".', { enfocar: pmo.locator('#decision') });
          return `Campo "${await texto(pmo, 'label[for=observations]')}" visible y con el foco; la factura sigue "Enviada".`;
        });
        await hu.paso(pmo, 'Pulsar "Rechazar" otra vez con el campo vacío', 'No se envía: se indica "Capture las observaciones." y la factura sigue "Enviada".', async () => {
          await pmo.locator('#decision').getByRole('button', { name: 'Rechazar' }).click();
          const error = pmo.locator('#decision .invalid-feedback').filter({ hasText: /\S/ });
          await expect(error).toHaveText('Capture las observaciones.');
          await hu.captura(pmo, 'observaciones-obligatorias', 'Rechazar sin observaciones: "Capture las observaciones."', { enfocar: pmo.locator('#decision') });
          const mensaje = await error.innerText();
          await pmo.reload();
          await expect(pmo.locator('.page-heading .status')).toHaveText('Enviada');
          return `Mensaje "${mensaje}"; tras recargar, la factura sigue "Enviada".`;
        });
      },
      { requiere: ['Precondición: el proveedor envía dos facturas más para decidir'] },
    );

    await hu.escenario(
      'Rechazar con observaciones: estatus "Rechazada" y correo al proveedor con la causa (RN-HU20-03)',
      async () => {
        let desde = '';
        await hu.paso(pmo, `Capturar la causa y pulsar "Rechazar" en ${rechazo.numero}`, `La factura pasa a "Rechazada" y se informa "Correo enviado a ${CORREO_PROVEEDOR}".`, async () => {
          await abrirDecision(pmo, rechazo.id);
          await pmo.locator('#decision').getByRole('button', { name: 'Rechazar' }).click();
          await pmo.locator('#observations').fill(rechazo.texto);
          desde = new Date(Date.now() - 2000).toISOString();
          await clicNavegando(pmo, pmo.locator('#decision').getByRole('button', { name: 'Rechazar' }));
          await expect(pmo.locator('.page-heading .status')).toHaveText('Rechazada');
          await expect(pmo.locator('#decision-result')).toHaveText(`Rechazada. Correo enviado a ${CORREO_PROVEEDOR}`);
          await hu.captura(pmo, 'factura-rechazada', `${rechazo.numero} "Rechazada": correo enviado al proveedor.`, { enfocar: pmo.locator('.page-heading') });
          return `Estatus "${await texto(pmo, '.page-heading .status')}"; "${await texto(pmo, '#decision-result')}".`;
        });
        await hu.paso(null, 'Abrir el correo "Rechazada" generado', 'El correo va al correo del proveedor (catálogo) e indica la causa capturada en "Observaciones".', async () => {
          const correo = buscarCorreo(CORREO_PROVEEDOR, `Factura ${rechazo.numero} rechazada`, desde) as Correo;
          expect(correo, 'No se encontró el correo "Rechazada"').not.toBeNull();
          expect(correo.para).toEqual([CORREO_PROVEEDOR]);
          expect(correo.texto).toContain(`La factura número ${rechazo.numero} ha sido “Rechazada” por la siguiente causa:`);
          expect(correo.texto).toContain(rechazo.texto);
          await hu.capturaCorreo(correo, 'correo-rechazada', `Correo "Rechazada" al proveedor con la causa de ${rechazo.numero}.`);
          return `Para ${correo.para.join(', ')}; asunto "${correo.asunto}"; incluye la causa "${rechazo.texto}".`;
        });
        guardarDato('hu20.rechazada', rechazo);
      },
      { requiere: ['Precondición: el proveedor envía dos facturas más para decidir'] },
    );

    await hu.escenario(
      'Observaciones: estatus "Observaciones" y correo al proveedor con la causa (RN-HU20-01, RN-HU20-03)',
      async () => {
        let desde = '';
        await hu.paso(pmo, `En ${observacion.numero}, pulsar "Observaciones", capturar la causa y confirmar`, `La factura pasa a "Observaciones" y se informa "Correo enviado a ${CORREO_PROVEEDOR}".`, async () => {
          await abrirDecision(pmo, observacion.id);
          await pmo.locator('#decision').getByRole('button', { name: 'Observaciones' }).click();
          await expect(pmo.locator('#observations')).toBeVisible();
          await pmo.locator('#observations').fill(observacion.texto);
          await hu.captura(pmo, 'observaciones-capturadas', 'Campo "Observaciones" capturado antes de confirmar.', { enfocar: pmo.locator('#decision') });
          desde = new Date(Date.now() - 2000).toISOString();
          await clicNavegando(pmo, pmo.locator('#decision').getByRole('button', { name: 'Observaciones' }));
          await expect(pmo.locator('.page-heading .status')).toHaveText('Observaciones');
          await expect(pmo.locator('#decision-result')).toHaveText(`Observaciones. Correo enviado a ${CORREO_PROVEEDOR}`);
          await hu.captura(pmo, 'factura-observaciones', `${observacion.numero} en "Observaciones": correo enviado al proveedor.`, { enfocar: pmo.locator('.page-heading') });
          return `Estatus "${await texto(pmo, '.page-heading .status')}"; "${await texto(pmo, '#decision-result')}".`;
        });
        await hu.paso(null, 'Abrir el correo "Observaciones" generado', 'El correo va al proveedor e indica la causa capturada.', async () => {
          const correo = buscarCorreo(CORREO_PROVEEDOR, `Factura ${observacion.numero} con observaciones`, desde) as Correo;
          expect(correo, 'No se encontró el correo "Observaciones"').not.toBeNull();
          expect(correo.para).toEqual([CORREO_PROVEEDOR]);
          expect(correo.texto).toContain(observacion.texto);
          await hu.capturaCorreo(correo, 'correo-observaciones', `Correo "Observaciones" al proveedor con la causa de ${observacion.numero}.`);
          return `Para ${correo.para.join(', ')}; asunto "${correo.asunto}"; incluye la causa "${observacion.texto}".`;
        });
        guardarDato('hu20.observaciones', observacion);
      },
      { requiere: ['Precondición: el proveedor envía dos facturas más para decidir'] },
    );

    await hu.escenario('Autorizar: confirmación y correo a "Recepción de Facturas" (RN-HU20-02)', async () => {
      let desde = '';
      await hu.paso(pmo, `En ${n1.numero}, pulsar "Autorizar"`, 'Un modal pide confirmar la autorización avisando que se notificará a Recepción de Facturas.', async () => {
        await abrirDecision(pmo, n1.id);
        await pmo.locator('#decision').getByRole('button', { name: 'Autorizar' }).click();
        await expect(pmo.locator('#decision-confirm')).toBeVisible();
        await expect(pmo.locator('#decision-confirm-text')).toHaveText(`¿Autorizar la factura ${n1.numero} para su pago? Se notificará a Recepción de Facturas.`);
        await hu.captura(pmo, 'modal-autorizar', 'Modal de confirmación de la autorización.');
        return `Modal: "${await texto(pmo, '#decision-confirm-text')}".`;
      });
      await hu.paso(pmo, 'Confirmar con "Autorizar"', `La factura pasa a "Autorizada" y el correo se envía a Recepción de Facturas (${recepcion.join(', ')}).`, async () => {
        desde = new Date(Date.now() - 2000).toISOString();
        await clicNavegando(pmo, pmo.locator('#decision-confirm-accept'));
        await expect(pmo.locator('.page-heading .status')).toHaveText('Autorizada');
        const resultado = await texto(pmo, '#decision-result');
        for (const destino of recepcion) expect(resultado).toContain(destino);
        await hu.captura(pmo, 'factura-autorizada', `${n1.numero} "Autorizada": correo enviado a Recepción de Facturas.`, { enfocar: pmo.locator('.page-heading') });
        return `Estatus "${await texto(pmo, '.page-heading .status')}"; "${resultado}".`;
      });
      await hu.paso(null, 'Abrir el correo "Autorizada" generado', 'Indica que la factura número X del proveedor Y por el monto Z ha sido autorizada para su pago.', async () => {
        const correo = buscarCorreo(recepcion[0], `Factura ${n1.numero} autorizada para pago`, desde) as Correo;
        expect(correo, 'No se encontró el correo "Autorizada"').not.toBeNull();
        expect(correo.para.sort()).toEqual([...recepcion].sort());
        const frase = `La factura número ${n1.numero} del proveedor ${PROVEEDOR} por el monto $116,000.00 MXN ha sido Autorizada para su pago.`;
        expect(correo.texto).toContain(frase);
        await hu.capturaCorreo(correo, 'correo-autorizada', `Correo "Autorizada" a Recepción de Facturas para ${n1.numero}.`);
        return `Para ${correo.para.join(', ')}; "${frase}"`;
      });
      guardarDato('hu20.autorizada', n1);
    });

    await hu.escenario('Una decisión por envío y registro en el historial', async () => {
      await hu.paso(pmo, `Volver a abrir ${n1.numero} ("Autorizada")`, 'Ya no se ofrece el panel "Decisión" ni el botón "Decidir"; el historial registra la decisión con el revisor.', async () => {
        await pmo.goto(`/invoices/${n1.id}`);
        await expect(pmo.locator('#decision')).toHaveCount(0);
        await expect(pmo.getByRole('link', { name: /Decidir/ })).toHaveCount(0);
        await expect(pmo.locator('#history')).toContainText('PMO Demo');
        await hu.captura(pmo, 'historial-decision', 'Historial de la factura autorizada, sin panel de decisión.', { enfocar: pmo.locator('#history') });
        return `Sin panel de decisión; historial: ${(await pmo.locator('#history ol').innerText()).replace(/\s+/g, ' ')}.`;
      });
    });
  });
});
