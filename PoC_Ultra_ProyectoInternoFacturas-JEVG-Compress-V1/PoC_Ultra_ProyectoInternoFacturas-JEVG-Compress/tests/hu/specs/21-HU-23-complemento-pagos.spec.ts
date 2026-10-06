import { expect, test, type Page } from '@playwright/test';
import { buscarCorreo, guardarDato, leerEstado, type Correo } from '../lib/estado';
import { Bloqueo, ejecutarHU, limpiar } from '../lib/hu';
import { cargarDocumento, clicNavegando, enviarAValidacion, registrarFacturaNacional, texto } from '../lib/portal';

const PROVEEDOR = 'Tecnologia Integral del Centro SA de CV';
const CORREO_PROVEEDOR = 'proveedor1@poc.local';
const AVISO = 'Es importante que adjunte su “Complemento de Pago” a dicha factura pagada antes del';

/** Fecha limite que muestra el bloque "Complemento de pago" ("… antes del dd/mm/aaaa HH:MM"). */
async function fechaLimite(pagina: Page): Promise<string> {
  const contenido = await texto(pagina, '#complement');
  const coincidencia = contenido.match(/(\d{2}\/\d{2}\/\d{4} \d{2}:\d{2})/);
  if (!coincidencia) throw new Error(`El bloque "Complemento de pago" no muestra una fecha: ${contenido}`);
  return coincidencia[1];
}

test('HU-23 · Complemento de pagos', async ({ browser }, testInfo) => {
  await ejecutarHU('HU-23', browser, testInfo, async (hu) => {
    const { run, fixtures } = leerEstado();
    const recepcion = hu.requiere<string[]>('HU-08', 'hu08.recepcion');
    const factura = { id: 0, numero: `QA-${run}-PAGO`, limite: '' };
    hu.nota(
      'El bloqueo del envío por un complemento vencido (más de 72 horas sin adjuntar) no se ejecuta aquí: la suite no ' +
        'modifica la base de datos ni puede esperar 72 horas. Lo verifican las pruebas automatizadas ' +
        'tests/test_pago_facturas.py (vencido a las 73 h, dentro del plazo a las 71 h, levantado al adjuntar).',
    );
    if (!fixtures.cfdi_ppd || !fixtures.complemento_pago) {
      throw new Bloqueo('Los datos de prueba de esta ejecución no incluyen el CFDI PPD ni su Complemento de Pago.');
    }

    await hu.escenario('Configuración de requisitos: "Complemento de pago" Opcional (nota de la HU)', async () => {
      const admin = await hu.sesion('admin');
      await hu.paso(admin, 'Abrir Administración › Archivos mínimos', 'El Complemento de pago (XML y PDF) aparece como Opcional para Nacional y No aplica para Internacional, con candado.', async () => {
        await admin.goto('/admin/required-documents');
        const filas = admin.locator('tr').filter({ hasText: /^Complemento de pago/ });
        const resultados: string[] = [];
        for (const nombre of ['Complemento de pago (XML)', 'Complemento de pago (PDF)']) {
          const fila = admin.locator('tr').filter({ has: admin.locator('strong', { hasText: nombre }) });
          await expect(fila).toHaveCount(1);
          await expect(fila.locator('select')).toHaveCount(0);
          await expect(fila).toContainText('Opcional');
          await expect(fila).toContainText('No aplica');
          await expect(fila).toContainText('Se carga después del pago de la factura');
          resultados.push(`${nombre}: ${(await fila.innerText()).replace(/\s+/g, ' ').trim()}`);
        }
        await hu.captura(admin, 'requisitos-complemento-opcional', 'Configuración de archivos mínimos: Complemento de pago Opcional fijo para Nacional.', {
          enfocar: filas.first(),
        });
        return resultados.join(' · ');
      });
    });

    await hu.escenario('Precondición: factura nacional con método de pago PPD autorizada por el PMO', async () => {
      const proveedor = await hu.sesion('proveedor1');
      const pmo = await hu.sesion('pmo');
      await hu.paso(proveedor, `El proveedor registra y envía ${factura.numero} (CFDI con MetodoPago PPD)`, 'La factura queda "Enviada".', async () => {
        try {
          factura.id = await registrarFacturaNacional(proveedor, factura.numero, {
            xml: fixtures.cfdi_ppd,
            pdf: fixtures.pdf_cfdi,
            ordenCompra: fixtures.orden_compra,
            vobo: fixtures.vobo,
          });
          await proveedor.goto(`/invoices/${factura.id}`);
          await enviarAValidacion(proveedor);
          await expect(proveedor.locator('.page-heading .status')).toHaveText('Enviada');
        } catch (error) {
          throw new Bloqueo(`No se pudo preparar la factura PPD: ${limpiar(error)}`);
        }
        return `${factura.numero} (#${factura.id}) en "Enviada".`;
      });
      await hu.paso(pmo, `El PMO autoriza ${factura.numero}`, 'La factura queda "Autorizada" y el detalle ofrece el panel "Pago".', async () => {
        try {
          await pmo.goto(`/invoices/${factura.id}`);
          await pmo.locator('#decision').getByRole('button', { name: 'Autorizar' }).click();
          await expect(pmo.locator('#decision-confirm')).toBeVisible();
          await clicNavegando(pmo, pmo.locator('#decision-confirm-accept'));
          await expect(pmo.locator('.page-heading .status')).toHaveText('Autorizada');
        } catch (error) {
          throw new Bloqueo(`No se pudo autorizar la factura PPD: ${limpiar(error)}`);
        }
        await expect(pmo.locator('#payment')).toBeVisible();
        await hu.captura(pmo, 'autorizada-con-panel-pago', `${factura.numero} "Autorizada": el PMO ve el panel "Pago".`, { enfocar: pmo.locator('#payment') });
        return `Estatus "${await texto(pmo, '.page-heading .status')}"; panel "${await texto(pmo, '#payment h2')}" visible.`;
      });
    });

    const precondicion = ['Precondición: factura nacional con método de pago PPD autorizada por el PMO'];

    await hu.escenario(
      'El PMO marca la factura como "Pagada"',
      async () => {
        const pmo = await hu.sesion('pmo');
        await hu.paso(pmo, 'Marcar la casilla de confirmación y pulsar "Marcar como pagada"', `La factura pasa a "Pagada", se informa "Correo enviado a ${CORREO_PROVEEDOR}" y el complemento queda pendiente con su fecha límite.`, async () => {
          await pmo.goto(`/invoices/${factura.id}`);
          const panel = pmo.locator('#payment');
          await expect(panel).toContainText(`Confirmo que la factura ${factura.numero} fue pagada. Se notificará al proveedor.`);
          await panel.locator('#payment-confirm').check();
          await hu.captura(pmo, 'confirmacion-de-pago', 'Panel "Pago" con la confirmación marcada.', { enfocar: panel });
          await clicNavegando(pmo, panel.getByRole('button', { name: /Marcar como pagada/ }));
          await expect(pmo.locator('.page-heading .status')).toHaveText('Pagada');
          await expect(pmo.locator('#decision-result')).toHaveText(`Pagada. Correo enviado a ${CORREO_PROVEEDOR}`);
          await expect(pmo.locator('#paid')).toContainText('Pagada el');
          await expect(pmo.locator('#complement')).toContainText('Pendiente: adjúntelo antes del');
          await expect(pmo.locator('#payment')).toHaveCount(0);
          factura.limite = await fechaLimite(pmo);
          // La redireccion lleva al ancla del resultado del correo: la captura completa empieza desde el encabezado.
          await pmo.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }));
          await hu.captura(pmo, 'factura-pagada', `${factura.numero} "Pagada": correo enviado al proveedor y complemento pendiente.`, { completa: true });
          return `Estatus "${await texto(pmo, '.page-heading .status')}"; "${await texto(pmo, '#decision-result')}"; "${await texto(pmo, '#complement p')}".`;
        });
      },
      { requiere: precondicion },
    );

    const pagada = ['El PMO marca la factura como "Pagada"'];

    await hu.escenario(
      'Correo "Pagada" al proveedor con el aviso del Complemento de Pago (nacional PPD)',
      async () => {
        await hu.paso(null, 'Abrir el correo "Pagada" generado', `Va al correo del proveedor, indica que la factura ${factura.numero} ha sido pagada y pide adjuntar el Complemento de Pago antes de la fecha límite.`, async () => {
          const correo = buscarCorreo(CORREO_PROVEEDOR, `Factura ${factura.numero} pagada`) as Correo;
          expect(correo, 'No se encontró el correo "Pagada"').not.toBeNull();
          expect(correo.para).toEqual([CORREO_PROVEEDOR]);
          expect(correo.texto).toContain(`Su factura número ${factura.numero} ha sido pagada.`);
          expect(correo.texto).toContain(`${AVISO} ${factura.limite}.`);
          await hu.capturaCorreo(correo, 'correo-pagada', `Correo "Pagada" al proveedor con el aviso del Complemento de Pago de ${factura.numero}.`);
          return `Para ${correo.para.join(', ')}; asunto "${correo.asunto}"; incluye "${AVISO} ${factura.limite}."`;
        });
      },
      { requiere: pagada },
    );

    await hu.escenario(
      'El proveedor ve su complemento pendiente',
      async () => {
        const proveedor = await hu.sesion('proveedor1');
        await hu.paso(proveedor, 'Abrir el tablero', `El aviso "Tiene complementos de pago pendientes" lista ${factura.numero} con su fecha límite.`, async () => {
          await proveedor.goto('/');
          const aviso = proveedor.locator('#pending-complements');
          await expect(aviso).toContainText('Tiene complementos de pago pendientes');
          await expect(aviso).toContainText(`Factura ${factura.numero} · Adjúntelo antes del ${factura.limite}`);
          await hu.captura(proveedor, 'tablero-complemento-pendiente', 'Tablero del proveedor con el aviso de complementos pendientes.', { enfocar: aviso });
          return (await aviso.innerText()).replace(/\s+/g, ' ').trim();
        });
        await hu.paso(proveedor, `Abrir el detalle de ${factura.numero}`, 'Muestra "Pagada", el complemento pendiente, el enlace "Adjuntar Complemento de Pago" y ya no ofrece "Cancelar factura".', async () => {
          await proveedor.goto(`/invoices/${factura.id}`);
          await expect(proveedor.locator('.page-heading .status')).toHaveText('Pagada');
          await expect(proveedor.locator('#complement')).toContainText(`Pendiente: adjúntelo antes del ${factura.limite}`);
          await expect(proveedor.getByRole('link', { name: /Adjuntar Complemento de Pago/ })).toBeVisible();
          await expect(proveedor.locator('#cancellation')).toHaveCount(0);
          await hu.captura(proveedor, 'detalle-proveedor-pagada', 'Detalle de la factura pagada para el proveedor.', { enfocar: proveedor.locator('#complement') });
          return `"${await texto(proveedor, '#complement p')}"; sin sección "Cancelar factura".`;
        });
      },
      { requiere: pagada },
    );

    await hu.escenario(
      'Sólo se acepta un Complemento de Pago válido',
      async () => {
        const proveedor = await hu.sesion('proveedor1');
        await hu.paso(proveedor, 'Abrir "Adjuntar Complemento de Pago"', 'La carga documental de la factura pagada sólo ofrece el Complemento de pago (XML y PDF).', async () => {
          await proveedor.goto(`/invoices/${factura.id}`);
          await clicNavegando(proveedor, proveedor.getByRole('link', { name: /Adjuntar Complemento de Pago/ }));
          const opciones = await proveedor.locator('#document_type option').allInnerTexts();
          expect(opciones.map((o) => o.trim())).toEqual(['Complemento de pago (XML) (XML)', 'Complemento de pago (PDF) (PDF)']);
          await hu.captura(proveedor, 'carga-solo-complemento', 'Carga documental de la factura pagada: sólo el Complemento de Pago.', { completa: true });
          return `Tipos ofrecidos: ${opciones.join(', ')}.`;
        });
        await hu.paso(proveedor, 'Cargar como Complemento de pago (XML) el CFDI de ingreso de la propia factura', 'Se rechaza: "El XML no es un Complemento de Pago (CFDI de tipo P)" y el complemento sigue pendiente.', async () => {
          await cargarDocumento(proveedor, 'PAYMENT_COMPLEMENT_XML', fixtures.cfdi_ppd);
          const error = proveedor.locator('.alert-danger').first();
          await expect(error).toHaveText('El XML no es un Complemento de Pago (CFDI de tipo P)');
          await expect(proveedor.locator('#complement')).toContainText('Pendiente');
          await hu.captura(proveedor, 'complemento-invalido', 'Un CFDI que no es de tipo P se rechaza como Complemento de Pago.', { enfocar: error });
          return `Mensaje "${await error.innerText()}"; "${await texto(proveedor, '#complement')}".`;
        });
      },
      { requiere: pagada },
    );

    await hu.escenario(
      'Adjuntar el Complemento de Pago avisa a "Recepción de Facturas"',
      async () => {
        const proveedor = await hu.sesion('proveedor1');
        let desde = '';
        await hu.paso(proveedor, 'Cargar el XML del Complemento de Pago (CFDI de tipo P que relaciona la factura)', 'Se guarda, se informa "Se notificó a Recepción de Facturas" y el complemento queda "Adjuntado".', async () => {
          await proveedor.goto(`/invoices/${factura.id}/documents`);
          desde = new Date(Date.now() - 2000).toISOString();
          await cargarDocumento(proveedor, 'PAYMENT_COMPLEMENT_XML', fixtures.complemento_pago);
          await expect(proveedor.locator('#complement-result')).toHaveText('Se notificó a Recepción de Facturas.');
          await expect(proveedor.locator('#complement')).toContainText('Adjuntado el');
          await hu.captura(proveedor, 'complemento-adjuntado', 'Complemento de Pago adjuntado: aviso a Recepción de Facturas.', { completa: true });
          return `"${await texto(proveedor, '#complement-result')}"; "${await texto(proveedor, '#complement')}".`;
        });
        await hu.paso(null, 'Abrir el correo "Complemento de pago adjuntado" generado', `Va a Recepción de Facturas (${recepcion.join(', ')}) e indica que el Complemento de Pago ha sido adjuntado a la factura ${factura.numero}.`, async () => {
          const correo = buscarCorreo(recepcion[0], `Complemento de pago de la factura ${factura.numero}`, desde) as Correo;
          expect(correo, 'No se encontró el correo "Complemento de pago adjuntado"').not.toBeNull();
          expect([...correo.para].sort()).toEqual([...recepcion].sort());
          const frase = `El Complemento de Pago ha sido adjuntado a la factura ${factura.numero} del proveedor ${PROVEEDOR}.`;
          expect(correo.texto).toContain(frase);
          await hu.capturaCorreo(correo, 'correo-complemento-adjuntado', `Correo a Recepción de Facturas: complemento adjuntado a ${factura.numero}.`);
          return `Para ${correo.para.join(', ')}; "${frase}"`;
        });
        await hu.paso(proveedor, 'Volver al tablero', 'El aviso de complementos pendientes ya no lista la factura.', async () => {
          await proveedor.goto('/');
          const aviso = proveedor.locator('#pending-complements');
          if (await aviso.count()) await expect(aviso).not.toContainText(factura.numero);
          await hu.captura(proveedor, 'tablero-sin-pendiente', 'Tablero del proveedor después de adjuntar el complemento.');
          return (await aviso.count()) ? `El aviso sigue por otras facturas, sin ${factura.numero}.` : 'Sin aviso de complementos pendientes.';
        });
        guardarDato('hu23.pagada', factura);
      },
      { requiere: pagada },
    );

    await hu.escenario(
      'Historial del pago y del complemento',
      async () => {
        const pmo = await hu.sesion('pmo');
        await hu.paso(pmo, `Abrir el detalle de ${factura.numero} como PMO`, 'El historial registra "Pagada" con la fecha límite del complemento y "Complemento de pago adjuntado"; el bloque muestra "Adjuntado el …".', async () => {
          await pmo.goto(`/invoices/${factura.id}`);
          const historial = pmo.locator('#history');
          await expect(historial).toContainText('Pagada');
          await expect(historial).toContainText(`Fecha límite del complemento: ${factura.limite}`);
          await expect(historial).toContainText('Complemento de pago adjuntado');
          await expect(pmo.locator('#complement')).toContainText('Adjuntado el');
          await hu.captura(pmo, 'historial-pago-complemento', 'Historial de la factura con el pago y el complemento.', { enfocar: historial });
          return `Historial: ${(await historial.locator('ol').innerText()).replace(/\s+/g, ' ')}.`;
        });
      },
      { requiere: ['Adjuntar el Complemento de Pago avisa a "Recepción de Facturas"'] },
    );
  });
});
