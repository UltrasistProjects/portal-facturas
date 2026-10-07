import { expect, test } from '@playwright/test';
import { buscarCorreo, guardarDato, leerEstado, type Correo } from '../lib/estado';
import { ejecutarHU } from '../lib/hu';
import { clicNavegando, enviarAlta, llenarAltaFactura, texto } from '../lib/portal';

const BUZON = 'recepcionfacturas@ultrasist.com.mx';

test('HU-08 · Configuración de correos de notificación', async ({ browser }, testInfo) => {
  await ejecutarHU('HU-08', browser, testInfo, async (hu) => {
    const { run, fixtures } = leerEstado();
    const buzonQa = `recepcion.qa.${run.toLowerCase()}@ultrasist-qa.example`;
    const copiaQa = `auditoria.qa.${run.toLowerCase()}@ultrasist-qa.example`;
    const admin = await hu.sesion('admin');
    const buzon = () => admin.locator('.recipients-panel textarea').first();
    const copiaCancelada = () => admin.locator('.recipients-panel tbody tr').filter({ hasText: 'Cancelada' }).locator('textarea');
    let buzonInicial = '';

    await hu.escenario('Consulta de destinatarios, copias por evento y transporte', async () => {
      await hu.paso(
        admin,
        'Abrir Administración › Notificaciones',
        'Se muestra el buzón "Recepción de Facturas" (recepcionfacturas@ultrasist.com.mx), las copias por evento (Autorizada, Rechazada, Observaciones, Cancelada) y el transporte vigente.',
        async () => {
          await admin.goto('/admin/notifications');
          await expect(admin.locator('h1')).toHaveText('Notificaciones');
          await expect(buzon()).toHaveValue(new RegExp(BUZON.replace(/\./g, '\\.')));
          buzonInicial = await buzon().inputValue();
          const eventos = await admin.locator('.recipients-panel tbody tr td:first-child').allInnerTexts();
          expect(eventos.map((e) => e.trim())).toEqual(expect.arrayContaining(['Autorizada', 'Rechazada', 'Observaciones', 'Cancelada']));
          await hu.captura(admin, 'destinatarios', 'Destinatarios: buzón "Recepción de Facturas" y copias por evento.');
          const transporte = admin.locator('.transport-list');
          await hu.captura(admin, 'transporte-y-prueba', 'Correo de prueba y transporte vigente (archivo .eml en este ambiente de pruebas).', { enfocar: transporte });
          return `Buzón: "${(await buzon().inputValue()).trim()}"; eventos con copias: ${eventos.map((e) => e.trim()).join(', ')}; transporte: ${(await transporte.innerText()).replace(/\s+/g, ' ')}.`;
        },
      );
    });

    await hu.escenario('Validación de las direcciones capturadas', async () => {
      await hu.paso(
        admin,
        'Agregar "correo-sin-arroba" al buzón y guardar',
        'El guardado se rechaza con un error de dirección inválida y la configuración no cambia.',
        async () => {
          await admin.goto('/admin/notifications');
          await buzon().fill(`${BUZON}\ncorreo-sin-arroba`);
          await clicNavegando(admin, admin.getByRole('button', { name: 'Guardar destinatarios' }));
          const errores = admin.locator('.template-errors li');
          await expect(errores.first()).toBeVisible();
          const lista = await errores.allInnerTexts();
          await hu.captura(admin, 'direccion-invalida', 'Error al guardar una dirección inválida en el buzón.');
          await admin.goto('/admin/notifications');
          await expect(buzon()).toHaveValue(buzonInicial);
          return `Errores: ${lista.join(' / ')}. Al recargar, el buzón conserva su valor anterior: "${(await buzon().inputValue()).split('\n').join(', ')}".`;
        },
      );
    });

    await hu.escenario('Definir los destinatarios del buzón "Recepción de Facturas" y la copia del evento Cancelada', async () => {
      await hu.paso(
        admin,
        `Agregar ${buzonQa} al buzón y ${copiaQa} como copia de "Cancelada"; guardar`,
        'Se guarda la configuración ("Configuración guardada") con ambas listas.',
        async () => {
          await admin.goto('/admin/notifications');
          await buzon().fill(`${BUZON}\n${buzonQa}`);
          await copiaCancelada().fill(copiaQa);
          await clicNavegando(admin, admin.getByRole('button', { name: 'Guardar destinatarios' }));
          await expect(admin.locator('.alert-success')).toHaveText('Configuración guardada');
          await expect(buzon()).toHaveValue(`${BUZON}\n${buzonQa}`);
          await expect(copiaCancelada()).toHaveValue(copiaQa);
          await hu.captura(admin, 'destinatarios-guardados', 'Configuración guardada: buzón con dos direcciones y copia en "Cancelada".');
          return `Aviso "${await texto(admin, '.alert-success')}"; buzón: ${(await buzon().inputValue()).split('\n').join(', ')}; Cc Cancelada: ${await copiaCancelada().inputValue()}.`;
        },
      );
      guardarDato('hu08.recepcion', [BUZON, buzonQa]);
      guardarDato('hu08.copiaCancelada', copiaQa);
    });

    await hu.escenario('Correo de prueba con la configuración vigente', async () => {
      const destino = `prueba.qa.${run.toLowerCase()}@ultrasist-qa.example`;
      await hu.paso(admin, `Enviar un correo de prueba a ${destino}`, 'Se informa "Correo de prueba enviado a …" y la bitácora registra el envío.', async () => {
        await admin.goto('/admin/notifications');
        await admin.locator('#test-address').fill(destino);
        await clicNavegando(admin, admin.getByRole('button', { name: /Enviar prueba/ }));
        await expect(admin.locator('.alert-success')).toHaveText(`Correo de prueba enviado a ${destino}`);
        const registro = admin.locator('section.panel').filter({ hasText: 'Bitácora de envíos' }).locator('tbody tr').filter({ hasText: destino });
        await expect(registro.first()).toContainText('Prueba');
        await expect(registro.first().locator('.status')).toHaveText('Enviado');
        await hu.captura(admin, 'correo-prueba', 'Aviso del correo de prueba enviado.');
        await hu.captura(admin, 'bitacora-prueba', 'Bitácora de envíos con el correo de prueba.', { enfocar: registro.first() });
        return `Aviso "${await texto(admin, '.alert-success')}"; bitácora: ${(await registro.first().innerText()).replace(/\s+/g, ' ')}.`;
      });
    });

    await hu.escenario(
      'El aviso a "Recepción de Facturas" toma los destinatarios de esta configuración',
      async () => {
        const proveedor = await hu.sesion('proveedor1');
        const desde = new Date(Date.now() - 2000).toISOString();
        const numero = `QA-${run}-H08`;
        await hu.paso(
          proveedor,
          `El proveedor registra la factura ${numero} y la cancela cargando el acuse (dispara el aviso "Cancelada" a Recepción de Facturas)`,
          'La factura queda "Cancelada" y se notifica a Recepción de Facturas.',
          async () => {
            await proveedor.goto('/invoices/new');
            await llenarAltaFactura(proveedor, { numero });
            const id = await enviarAlta(proveedor);
            await proveedor.goto(`/invoices/${id}`);
            await proveedor.locator('#cancellation summary').click();
            await proveedor.locator('#cancellation-ack').setInputFiles(fixtures.acuse);
            await proveedor.locator('#cancellation-confirm').check();
            await clicNavegando(proveedor, proveedor.getByRole('button', { name: 'Cancelar factura' }));
            await expect(proveedor.locator('#cancellation-result')).toContainText('Se notificó a Recepción de Facturas.');
            await hu.captura(proveedor, 'cancelacion-notificada', `Factura ${numero} cancelada: "Se notificó a Recepción de Facturas".`, {
              enfocar: proveedor.locator('.page-heading'),
            });
            return `"${await texto(proveedor, '#cancellation-result')}"; estatus "${await texto(proveedor, '.page-heading .status')}".`;
          },
        );
        await hu.paso(
          null,
          'Revisar el correo "Cancelada" generado',
          `El correo va a ${BUZON} y ${buzonQa} (Para) con copia a ${copiaQa} (Cc), tal como se configuró.`,
          async () => {
            const correo = buscarCorreo(buzonQa, `Cancelación de la factura ${numero}`, desde) as Correo;
            expect(correo, 'No se encontró el correo de cancelación').not.toBeNull();
            expect(correo.para.sort()).toEqual([BUZON, buzonQa].sort());
            expect(correo.cc).toEqual([copiaQa]);
            await hu.capturaCorreo(correo, 'correo-cancelada-destinatarios', 'Correo "Cancelada" con los destinatarios configurados en Notificaciones.');
            return `Para: ${correo.para.join(', ')}; Cc: ${correo.cc.join(', ')}; asunto "${correo.asunto}".`;
          },
        );
      },
      { requiere: ['Definir los destinatarios del buzón "Recepción de Facturas" y la copia del evento Cancelada'] },
    );
  });
});
