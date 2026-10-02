import { expect, test } from '@playwright/test';
import { buscarCorreo, leerEstado, type Correo } from '../lib/estado';
import { ejecutarHU } from '../lib/hu';
import { clicNavegando, enviarAlta, llenarAltaFactura, texto } from '../lib/portal';

const URL_RECHAZADA = '/admin/notification-templates/INVOICE_REJECTED';

test('HU-05 · Configuración de plantillas de estatus de factura', async ({ browser }, testInfo) => {
  await ejecutarHU('HU-05', browser, testInfo, async (hu) => {
    const { run, fixtures } = leerEstado();
    const admin = await hu.sesion('admin');
    let asuntoOriginal = '';

    await hu.escenario('Una plantilla configurable por cada cambio de estatus de la factura', async () => {
      await hu.paso(
        admin,
        'Abrir Administración › Plantillas de correo',
        'El listado muestra una plantilla para "Autorizada", "Rechazada", "Observaciones" y "Cancelada", con su destinatario, asunto y botón "Editar".',
        async () => {
          await admin.goto('/admin/notification-templates');
          await expect(admin.locator('h1')).toHaveText('Plantillas de correo');
          const filas = admin.locator('table tbody tr');
          const resumen: string[] = [];
          for (const evento of ['Autorizada', 'Rechazada', 'Observaciones', 'Cancelada']) {
            const fila = filas.filter({ has: admin.locator('td:first-child', { hasText: new RegExp(`^${evento}$`) }) });
            await expect(fila).toHaveCount(1);
            await expect(fila.getByRole('link', { name: 'Editar' })).toBeVisible();
            resumen.push(`${evento} → ${(await fila.locator('td').nth(1).innerText()).trim()}`);
          }
          await hu.captura(admin, 'listado-plantillas', 'Listado de plantillas de correo por evento de estatus, con destinatario y asunto.');
          return `Plantillas: ${resumen.join('; ')}.`;
        },
      );
    });

    await hu.escenario('Edición y vista previa con datos de ejemplo (sin guardar)', async () => {
      await hu.paso(
        admin,
        'Editar la plantilla "Rechazada"',
        'El formulario muestra asunto, cuerpo, el destinatario en solo lectura y la tabla de variables con las obligatorias marcadas.',
        async () => {
          await admin.goto(URL_RECHAZADA);
          await expect(admin.locator('h1')).toHaveText('Plantilla: Rechazada');
          asuntoOriginal = await admin.locator('#subject').inputValue();
          const obligatorias = await admin.locator('table tbody tr').filter({ hasText: 'Obligatoria' }).locator('.mono').allInnerTexts();
          expect(obligatorias).toEqual(expect.arrayContaining(['{{numero_factura}}', '{{observaciones}}']));
          await hu.captura(admin, 'editor-rechazada', 'Editor de la plantilla "Rechazada": asunto, cuerpo y variables (obligatorias marcadas).');
          return `Destinatario: "${await texto(admin, '.page-heading p')}"; asunto vigente "${asuntoOriginal}"; variables obligatorias: ${obligatorias.join(', ')}.`;
        },
      );
      await hu.paso(
        admin,
        'Pulsar "Vista previa"',
        'Se muestra el correo compuesto con los datos de ejemplo; la plantilla no se guarda.',
        async () => {
          await admin.getByRole('button', { name: /Vista previa/ }).click();
          const vista = admin.locator('.template-preview');
          await expect(vista).toBeVisible();
          await expect(vista.locator('dd').first()).toHaveText('Factura A-1024 rechazada');
          await expect(vista).toContainText('La plantilla no se ha guardado');
          await hu.captura(admin, 'vista-previa', 'Vista previa del correo "Rechazada" compuesta con datos de ejemplo.', { enfocar: vista });
          return `Vista previa con asunto "${await texto(admin, '.template-preview dd')}" y el aviso "La plantilla no se ha guardado".`;
        },
      );
    });

    await hu.escenario('Validación de la plantilla: variables obligatorias y desconocidas', async () => {
      await hu.paso(
        admin,
        'Quitar {{observaciones}} del cuerpo, agregar {{variable_inexistente}} y pulsar "Guardar"',
        'El guardado se rechaza y se listan juntos los errores (variable desconocida y variable obligatoria ausente).',
        async () => {
          await admin.goto(URL_RECHAZADA);
          const cuerpo = (await admin.locator('#body').inputValue()).replaceAll('{{observaciones}}', '') + '\n{{variable_inexistente}}';
          await admin.locator('#body').fill(cuerpo);
          await admin.getByRole('button', { name: 'Guardar' }).click();
          const errores = admin.locator('.template-errors li');
          await expect(errores.first()).toBeVisible();
          const lista = await errores.allInnerTexts();
          expect(lista.join(' ')).toMatch(/variable_inexistente/);
          expect(lista.join(' ')).toMatch(/observaciones/);
          await hu.captura(admin, 'errores-validacion', 'Errores de validación de la plantilla mostrados juntos.');
          return `Errores: ${lista.join(' / ')}.`;
        },
      );
      await hu.paso(
        admin,
        'Volver a abrir la plantilla',
        'La plantilla vigente no cambió (sigue con su asunto y cuerpo anteriores).',
        async () => {
          await admin.goto(URL_RECHAZADA);
          await expect(admin.locator('#subject')).toHaveValue(asuntoOriginal);
          await expect(admin.locator('#body')).toHaveValue(/\{\{observaciones\}\}/);
          return `Asunto vigente sin cambios: "${await admin.locator('#subject').inputValue()}"; el cuerpo conserva {{observaciones}}.`;
        },
      );
    });

    await hu.escenario('Guardar una modificación y restaurar el texto predeterminado', async () => {
      const nuevoAsunto = `Factura {{numero_factura}} rechazada (QA ${run})`;
      await hu.paso(
        admin,
        `Cambiar el asunto a "${nuevoAsunto}" y guardar`,
        'Se guarda la plantilla ("Plantilla actualizada: Rechazada.") y el listado muestra el nuevo asunto y quién la modificó.',
        async () => {
          await admin.goto(URL_RECHAZADA);
          await admin.locator('#subject').fill(nuevoAsunto);
          await admin.getByRole('button', { name: 'Guardar' }).click();
          await expect(admin.locator('.alert-success')).toHaveText('Plantilla actualizada: Rechazada.');
          const fila = admin.locator('table tbody tr').filter({ hasText: 'Rechazada' }).first();
          await expect(fila).toContainText(nuevoAsunto);
          await expect(fila).toContainText('Administrador Demo');
          await hu.captura(admin, 'plantilla-guardada', 'Listado tras guardar: asunto modificado y última modificación del Administrador.');
          return `Aviso "${await texto(admin, '.alert-success')}"; fila Rechazada: ${(await fila.innerText()).replace(/\s+/g, ' ')}.`;
        },
      );
      await hu.paso(
        admin,
        'Editar otra vez, pulsar "Cargar texto predeterminado" y guardar',
        'El formulario se llena con el texto predeterminado (aviso "Se cargó el texto predeterminado…") y al guardar el listado vuelve a mostrar el asunto original.',
        async () => {
          await admin.goto(URL_RECHAZADA);
          await admin.getByRole('link', { name: 'Cargar texto predeterminado' }).click();
          await expect(admin.locator('.alert-info')).toHaveText('Se cargó el texto predeterminado. Pulse Guardar para aplicarlo.');
          await expect(admin.locator('#subject')).toHaveValue(asuntoOriginal);
          await hu.captura(admin, 'texto-predeterminado-cargado', 'Texto predeterminado cargado en el formulario (aún sin guardar).');
          await admin.getByRole('button', { name: 'Guardar' }).click();
          await expect(admin.locator('.alert-success')).toHaveText('Plantilla actualizada: Rechazada.');
          await expect(admin.locator('table tbody tr').filter({ hasText: 'Rechazada' }).first()).toContainText(asuntoOriginal);
          await hu.captura(admin, 'plantilla-restaurada', 'Listado con la plantilla "Rechazada" de nuevo con su asunto predeterminado.');
          return `Aviso "${await texto(admin, '.alert-success')}"; asunto restaurado: "${asuntoOriginal}".`;
        },
      );
    });

    await hu.escenario('La plantilla guardada es la que usa la notificación (evento Cancelada)', async () => {
      const URL_CANCELADA = '/admin/notification-templates/INVOICE_CANCELLED';
      const marca = `[QA ${run}]`;
      const numero = `QA-${run}-H05`;
      let asuntoCancelada = '';
      let desde = '';
      await hu.paso(admin, `Agregar "${marca}" al asunto de la plantilla "Cancelada" y guardar`, 'La plantilla "Cancelada" queda guardada con el asunto modificado.', async () => {
        await admin.goto(URL_CANCELADA);
        asuntoCancelada = await admin.locator('#subject').inputValue();
        await admin.locator('#subject').fill(`${asuntoCancelada} ${marca}`);
        await clicNavegando(admin, admin.getByRole('button', { name: 'Guardar' }));
        await expect(admin.locator('.alert-success')).toHaveText('Plantilla actualizada: Cancelada.');
        return `Asunto guardado: "${asuntoCancelada} ${marca}".`;
      });
      const proveedor = await hu.sesion('proveedor1');
      await hu.paso(proveedor, `El proveedor registra ${numero} y la cancela con su acuse (dispara el correo "Cancelada")`, 'La factura queda "Cancelada" y se notifica a Recepción de Facturas.', async () => {
        await proveedor.goto('/invoices/new');
        await llenarAltaFactura(proveedor, { numero });
        const id = await enviarAlta(proveedor);
        await proveedor.goto(`/invoices/${id}`);
        await proveedor.locator('#cancellation summary').click();
        await proveedor.locator('#cancellation-ack').setInputFiles(fixtures.acuse);
        await proveedor.locator('#cancellation-confirm').check();
        desde = new Date(Date.now() - 2000).toISOString();
        await clicNavegando(proveedor, proveedor.locator('#cancellation').getByRole('button', { name: 'Cancelar factura' }));
        await expect(proveedor.locator('#cancellation-result')).toContainText('Se notificó a Recepción de Facturas.');
        return `"${await texto(proveedor, '#cancellation-result')}".`;
      });
      await hu.paso(null, 'Abrir el correo "Cancelada" generado', `El asunto del correo enviado incluye "${marca}": se compuso con la plantilla guardada.`, async () => {
        const correo = buscarCorreo('recepcionfacturas@ultrasist.com.mx', marca, desde) as Correo;
        expect(correo, 'No se encontró el correo con el asunto de la plantilla guardada').not.toBeNull();
        expect(correo.asunto).toContain(numero);
        expect(correo.asunto).toContain(marca);
        await hu.capturaCorreo(correo, 'correo-con-plantilla-guardada', 'Correo "Cancelada" compuesto con la plantilla recién guardada (asunto con la marca QA).');
        return `Asunto del correo: "${correo.asunto}".`;
      });
      await hu.paso(admin, 'Restaurar el texto predeterminado de la plantilla "Cancelada"', 'La plantilla vuelve a su asunto predeterminado.', async () => {
        await admin.goto(URL_CANCELADA);
        await admin.getByRole('link', { name: 'Cargar texto predeterminado' }).click();
        await expect(admin.locator('#subject')).toHaveValue(asuntoCancelada);
        await clicNavegando(admin, admin.getByRole('button', { name: 'Guardar' }));
        await expect(admin.locator('.alert-success')).toHaveText('Plantilla actualizada: Cancelada.');
        return `Asunto restaurado: "${asuntoCancelada}".`;
      });
    });
  });
});
