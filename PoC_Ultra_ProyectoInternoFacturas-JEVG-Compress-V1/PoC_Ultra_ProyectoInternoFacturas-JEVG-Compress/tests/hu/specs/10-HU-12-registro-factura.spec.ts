import { expect, test } from '@playwright/test';
import { guardarDato, leerEstado } from '../lib/estado';
import { ejecutarHU } from '../lib/hu';
import { cargarDocumento, clicNavegando, enviarAlta, estatusFactura, llenarAltaFactura, resumenObligatorios, texto } from '../lib/portal';

test('HU-12 · Registro de factura', async ({ browser }, testInfo) => {
  await ejecutarHU('HU-12', browser, testInfo, async (hu) => {
    const { run, fixtures } = leerEstado();
    const numero = `QA-${run}-N1`;
    const proveedor = await hu.sesion('proveedor1');
    let facturaId = 0;

    await hu.escenario('Formulario de registro: sólo los contratos del propio proveedor', async () => {
      await hu.paso(
        proveedor,
        'Desde el tablero, pulsar "Nueva factura"',
        'Se abre "Registrar factura" (paso 1 de 3) con el proveedor del usuario y sólo sus contratos activos; el proyecto se toma del contrato.',
        async () => {
          await proveedor.goto('/');
          await proveedor.getByRole('link', { name: /Nueva factura/ }).first().click();
          await expect(proveedor.locator('h1')).toHaveText('Registrar factura');
          const contratos = await proveedor.locator('#contract option').allInnerTexts();
          expect(contratos).toHaveLength(1);
          expect(contratos[0]).toContain('Automatizacion Operativa 2026');
          const html = await proveedor.content();
          expect(html).not.toContain('Servicios de Analitica 2026');
          expect(html).not.toContain('Analitica Global 2026');
          await expect(proveedor.locator('#project')).toHaveValue('Automatizacion Operativa 2026');
          await hu.captura(proveedor, 'formulario-registro', 'Formulario "Registrar factura" con el proveedor y su único contrato activo.');
          return `Proveedor: "${await texto(proveedor, '.form-control-plaintext')}"; contratos ofrecidos: ${contratos.join(' | ')}; el HTML no contiene contratos de otros proveedores.`;
        },
      );
      await hu.paso(
        proveedor,
        'Capturar el periodo con formato inválido ("2026-08") y continuar',
        'El formulario no se envía y muestra junto al campo "Use el formato MM/AAAA, por ejemplo 08/2026."',
        async () => {
          await llenarAltaFactura(proveedor, { numero, periodo: '2026-08' });
          await proveedor.getByRole('button', { name: /Continuar a documentos/ }).click();
          const error = proveedor.locator('.invalid-feedback').filter({ hasText: /\S/ }).first();
          await expect(error).toHaveText('Use el formato MM/AAAA, por ejemplo 08/2026.');
          await expect(proveedor).toHaveURL(/\/invoices\/new$/);
          await hu.captura(proveedor, 'periodo-invalido', 'Validación junto al campo: periodo con formato inválido.');
          return `Mensaje junto al campo: "${await error.innerText()}"; la página sigue en /invoices/new.`;
        },
      );
    });

    await hu.escenario('Registro y carga de los archivos mínimos del proveedor Nacional (RN-HU12-01)', async () => {
      await hu.paso(
        proveedor,
        `Registrar la factura ${numero} con periodo 08/2026`,
        'Se crea la factura y se abre la carga documental (paso 2 de 3) con los 4 obligatorios del Nacional pendientes; la factura queda en "Borrador".',
        async () => {
          await proveedor.goto('/invoices/new');
          await llenarAltaFactura(proveedor, { numero });
          facturaId = await enviarAlta(proveedor);
          await expect(proveedor.locator('h1')).toHaveText('Carga documental');
          await expect(proveedor.locator('.required-summary')).toContainText('Faltan 4 archivos obligatorios');
          for (const tipo of ['XML del CFDI', 'PDF del CFDI', 'Orden de compra', 'Vo.Bo. del líder de proyecto']) {
            await expect(proveedor.locator('.document-row').filter({ hasText: tipo })).toContainText('Obligatorio · Pendiente');
          }
          const checklist = await resumenObligatorios(proveedor);
          await hu.captura(proveedor, 'carga-documental-inicial', 'Carga documental: checklist con los 4 archivos obligatorios del proveedor Nacional pendientes.');
          const estatus = await estatusFactura(proveedor, facturaId);
          expect(estatus).toBe('Borrador');
          return `Factura #${facturaId} creada; checklist "${checklist}"; estatus en el detalle "${estatus}".`;
        },
      );
      await hu.paso(
        proveedor,
        'Intentar cargar un archivo .txt como "XML del CFDI"',
        'Se rechaza el formato (el tipo sólo admite XML) y el checklist no cambia.',
        async () => {
          await proveedor.goto(`/invoices/${facturaId}/documents`);
          await cargarDocumento(proveedor, 'INVOICE_XML', fixtures.texto_invalido);
          const error = proveedor.locator('.alert-danger');
          await expect(error).toBeVisible();
          await expect(proveedor.locator('.required-summary')).toContainText('Faltan 4 archivos obligatorios');
          await hu.captura(proveedor, 'formato-no-admitido', 'Carga rechazada: el XML del CFDI no admite un archivo .txt.');
          return `Rechazado: "${await texto(proveedor, '.alert-danger')}"; checklist sigue en "Faltan 4 archivos obligatorios".`;
        },
      );
      await hu.paso(
        proveedor,
        'Cargar XML del CFDI, PDF del CFDI y Orden de compra',
        'El checklist indica "Falta 1 archivo obligatorio" (Vo.Bo.), no se ofrece "Enviar a validación" y la factura sigue en "Borrador".',
        async () => {
          await cargarDocumento(proveedor, 'INVOICE_XML', fixtures.cfdi_ok);
          await cargarDocumento(proveedor, 'INVOICE_PDF', fixtures.pdf_cfdi);
          await cargarDocumento(proveedor, 'PURCHASE_ORDER', fixtures.orden_compra);
          await expect(proveedor.locator('.required-summary')).toHaveText('Falta 1 archivo obligatorio');
          await expect(proveedor.getByRole('button', { name: /Enviar a validación/ })).toHaveCount(0);
          await expect(proveedor.locator('.document-row').filter({ hasText: 'Vo.Bo. del líder de proyecto' })).toContainText('Pendiente');
          await hu.captura(proveedor, 'falta-un-obligatorio', 'Tras cargar XML, PDF y Orden de compra: "Falta 1 archivo obligatorio" (Vo.Bo.).');
          const estatus = await estatusFactura(proveedor, facturaId);
          expect(estatus).toBe('Borrador');
          return `Checklist "Falta 1 archivo obligatorio"; no se ofrece "Enviar a validación"; estatus "${estatus}".`;
        },
      );
      await hu.paso(
        proveedor,
        'Cargar el Vo.Bo. del líder de proyecto',
        'Checklist "Archivos obligatorios completos" con el aviso "Factura cargada. Ya puede enviarla a validación." y el botón "Enviar a validación" disponible.',
        async () => {
          await proveedor.goto(`/invoices/${facturaId}/documents`);
          await cargarDocumento(proveedor, 'APPROVAL', fixtures.vobo);
          await expect(proveedor.locator('.required-summary')).toContainText('Archivos obligatorios completos');
          await expect(proveedor.locator('.required-summary')).toContainText('Factura cargada. Ya puede enviarla a validación.');
          await expect(proveedor.getByRole('button', { name: /Enviar a validación/ })).toBeVisible();
          await hu.captura(proveedor, 'obligatorios-completos', 'Obligatorios completos: "Factura cargada. Ya puede enviarla a validación."');
          return `Checklist: "${await resumenObligatorios(proveedor)}".`;
        },
      );
      await hu.paso(
        proveedor,
        'Abrir el detalle de la factura',
        'La factura tiene el estatus "Cargada" (RN-HU12-01) y lista sus 4 documentos.',
        async () => {
          await proveedor.goto(`/invoices/${facturaId}`);
          await expect(proveedor.locator('.page-heading .status')).toHaveText('Cargada');
          await expect(proveedor.locator('.document-list .document-row')).toHaveCount(4);
          await hu.captura(proveedor, 'detalle-cargada', `Detalle de ${numero}: estatus "Cargada".`);
          const documentos = await proveedor.locator('.document-list .document-row strong').allInnerTexts();
          return `Estatus "${await texto(proveedor, '.page-heading .status')}"; documentos: ${documentos.join(', ')}.`;
        },
      );
      guardarDato('hu12.factura', { id: facturaId, numero });
    });
  });
});
