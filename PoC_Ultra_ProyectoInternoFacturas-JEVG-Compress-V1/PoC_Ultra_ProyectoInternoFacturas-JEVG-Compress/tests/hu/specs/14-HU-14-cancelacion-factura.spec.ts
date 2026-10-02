import { expect, test } from '@playwright/test';
import { buscarCorreo, guardarDato, leerEstado, type Correo } from '../lib/estado';
import { ejecutarHU } from '../lib/hu';
import { clicNavegando, texto } from '../lib/portal';

const PROVEEDOR = 'Tecnologia Integral del Centro SA de CV';

/** "dd/mm/aaaa HH:MM" (hora de negocio) a minutos desde la epoca, para comparar fechas sin zona horaria. */
function minutos(fecha: string): number {
  const [d, m, a, h, mi] = fecha.match(/(\d{2})\/(\d{2})\/(\d{4}) (\d{2}):(\d{2})/)!.slice(1).map(Number);
  return Date.UTC(a, m - 1, d, h, mi) / 60000;
}

test('HU-14 · Cancelación de factura', async ({ browser }, testInfo) => {
  await ejecutarHU('HU-14', browser, testInfo, async (hu) => {
    const { fixtures } = leerEstado();
    const factura = hu.requiere<{ id: number; numero: string }>('HU-13', 'hu13.noEnviada');
    const recepcion = hu.requiere<string[]>('HU-08', 'hu08.recepcion');
    const proveedor = await hu.sesion('proveedor1');
    let cancelada = '';
    let limite = '';
    let desde = '';

    await hu.escenario('La cancelación obliga a cargar el "Acuse de cancelación"', async () => {
      await hu.paso(
        proveedor,
        `Abrir ${factura.numero} ("Cargada") y desplegar "Cancelar factura"`,
        'Se muestra el formulario con el archivo "Acuse de cancelación" y la confirmación "Confirmo que la factura se canceló y adjunto su acuse".',
        async () => {
          await proveedor.goto(`/invoices/${factura.id}`);
          await expect(proveedor.locator('.page-heading .status')).toHaveText('Cargada');
          await proveedor.locator('#cancellation summary').click();
          await expect(proveedor.locator('label[for=cancellation-ack]')).toHaveText('Acuse de cancelación');
          await expect(proveedor.locator('label[for=cancellation-confirm]')).toHaveText('Confirmo que la factura se canceló y adjunto su acuse');
          await hu.captura(proveedor, 'formulario-cancelacion', 'Sección "Cancelar factura" con el acuse obligatorio y la confirmación.', {
            enfocar: proveedor.locator('#cancellation'),
          });
          return `Formulario con "${await texto(proveedor, 'label[for=cancellation-ack]')}" (${await texto(proveedor, '#cancellation .form-text')}) y la casilla de confirmación.`;
        },
      );
      await hu.paso(
        proveedor,
        'Pulsar "Cancelar factura" sin acuse ni confirmación',
        'El formulario no se envía: se indica junto a cada campo que falta el archivo y la confirmación; la factura sigue "Cargada".',
        async () => {
          await proveedor.locator('#cancellation').getByRole('button', { name: 'Cancelar factura' }).click();
          const errores = proveedor.locator('#cancellation .invalid-feedback').filter({ hasText: /\S/ });
          await expect(errores.first()).toBeVisible();
          const lista = await errores.allInnerTexts();
          await expect(proveedor).toHaveURL(new RegExp(`/invoices/${factura.id}`));
          await hu.captura(proveedor, 'cancelacion-sin-acuse', 'Validación junto a los campos: falta el acuse y la confirmación.', { enfocar: proveedor.locator('#cancellation') });
          return `Mensajes: ${lista.join(' / ')}; no hubo envío.`;
        },
      );
      await hu.paso(
        proveedor,
        'Enviar la cancelación confirmada sin acuse, quitando la validación del navegador (prueba de la validación del servidor)',
        'El servidor rechaza la petición con "Cargue el Acuse de cancelación" y la factura no cambia.',
        async () => {
          await proveedor.locator('#cancellation-confirm').check();
          await proveedor.locator('#cancellation form').evaluate((form) => {
            (form as HTMLFormElement).noValidate = true;
          });
          await clicNavegando(proveedor, proveedor.locator('#cancellation').getByRole('button', { name: 'Cancelar factura' }));
          const error = proveedor.locator('#cancellation .alert-danger');
          await expect(error).toContainText('Acuse de cancelación');
          await expect(proveedor.locator('.page-heading .status')).toHaveText('Cargada');
          await hu.captura(proveedor, 'servidor-exige-acuse', 'Respuesta del servidor: exige el Acuse de cancelación; la factura sigue "Cargada".', { enfocar: error });
          return `Servidor: "${await error.innerText()}"; estatus "${await texto(proveedor, '.page-heading .status')}".`;
        },
      );
    });

    await hu.escenario(
      'Cancelación con acuse: factura "Cancelada" con fecha límite de 72 horas',
      async () => {
        await hu.paso(
          proveedor,
          'Adjuntar el acuse (PDF), confirmar y pulsar "Cancelar factura"',
          'La factura queda "Cancelada"; se informa "Se notificó a Recepción de Facturas" y "… debe aceptar la cancelación antes del <fecha + 72 h>".',
          async () => {
            await proveedor.goto(`/invoices/${factura.id}`);
            await proveedor.locator('#cancellation summary').click();
            await proveedor.locator('#cancellation-ack').setInputFiles(fixtures.acuse);
            await proveedor.locator('#cancellation-confirm').check();
            desde = new Date(Date.now() - 2000).toISOString();
            await clicNavegando(proveedor, proveedor.locator('#cancellation').getByRole('button', { name: 'Cancelar factura' }));
            await expect(proveedor.locator('.page-heading .status')).toHaveText('Cancelada');
            await expect(proveedor.locator('#cancellation-result')).toHaveText('Factura cancelada. Se notificó a Recepción de Facturas.');
            const aviso = await texto(proveedor, '#cancelled');
            [cancelada, limite] = (aviso.match(/\d{2}\/\d{2}\/\d{4} \d{2}:\d{2}/g) ?? []) as string[];
            expect(minutos(limite) - minutos(cancelada)).toBe(72 * 60);
            await hu.captura(proveedor, 'factura-cancelada', 'Factura "Cancelada": aviso a Recepción de Facturas y fecha límite (+72 h).', {
              enfocar: proveedor.locator('.page-heading'),
            });
            return `Estatus "Cancelada"; "${await texto(proveedor, '#cancellation-result')}"; "${aviso}" (diferencia: 72 h).`;
          },
        );
        await hu.paso(
          proveedor,
          'Revisar los documentos de la factura',
          'El "Acuse de cancelación" aparece entre los documentos y ya no se ofrecen cambios (sin "Gestionar documentos", "Enviar" ni "Cancelar factura").',
          async () => {
            await expect(proveedor.locator('.document-row').filter({ hasText: 'Acuse de cancelación' })).toBeVisible();
            await expect(proveedor.getByRole('link', { name: /Gestionar documentos/ })).toHaveCount(0);
            await expect(proveedor.getByRole('button', { name: /Enviar a validación/ })).toHaveCount(0);
            await expect(proveedor.locator('#cancellation')).toHaveCount(0);
            await hu.captura(proveedor, 'acuse-en-documentos', 'Documentos de la factura cancelada con el "Acuse de cancelación".', {
              enfocar: proveedor.locator('.document-row').filter({ hasText: 'Acuse de cancelación' }),
            });
            return `Documentos: ${(await proveedor.locator('.document-list .document-row strong').allInnerTexts()).join(', ')}; sin acciones de edición.`;
          },
        );
        guardarDato('hu14.cancelada', { ...factura, cancelada, limite });
      },
      { requiere: ['La cancelación obliga a cargar el "Acuse de cancelación"'] },
    );

    await hu.escenario(
      'Correo a "Recepción de Facturas" con número de factura, proveedor y fecha límite',
      async () => {
        await hu.paso(
          null,
          'Abrir el correo "Cancelada" generado por el portal',
          `Va a Recepción de Facturas (${recepcion.join(', ')}) e indica el número de factura, el nombre del proveedor y que acepte la cancelación antes de la fecha límite (+72 h).`,
          async () => {
            const correo = buscarCorreo(recepcion[0], `Cancelación de la factura ${factura.numero}`, desde) as Correo;
            expect(correo, 'No se encontró el correo de cancelación').not.toBeNull();
            expect(correo.para.sort()).toEqual([...recepcion].sort());
            expect(correo.texto).toContain(`La factura número ${factura.numero} del proveedor ${PROVEEDOR} ha sido cancelada.`);
            expect(correo.texto).toContain(`Por favor acepte la “Cancelación” antes del ${limite}`);
            await hu.capturaCorreo(correo, 'correo-cancelacion', `Correo "Cancelada" a Recepción de Facturas para ${factura.numero}.`);
            return `Para: ${correo.para.join(', ')}; asunto "${correo.asunto}"; texto: "La factura número ${factura.numero} del proveedor ${PROVEEDOR} ha sido cancelada. Por favor acepte la “Cancelación” antes del ${limite}".`;
          },
        );
      },
      { requiere: ['Cancelación con acuse: factura "Cancelada" con fecha límite de 72 horas'] },
    );
  });
});
