import { expect, test } from '@playwright/test';
import { guardarDato } from '../lib/estado';
import { ejecutarHU } from '../lib/hu';
import { enviarAValidacion, resultadoRegla, texto, verificar } from '../lib/portal';

test('HU-16 · Envío de factura por proveedor internacional', async ({ browser }, testInfo) => {
  await ejecutarHU('HU-16', browser, testInfo, async (hu) => {
    const i1 = hu.requiere<{ id: number; numero: string }>('HU-15', 'hu15.factura');
    const proveedor = await hu.sesion('proveedor3');

    await hu.escenario('Validación del Invoice "en la medida de lo posible" antes del envío', async () => {
      await hu.paso(
        proveedor,
        `Abrir ${i1.numero} ("Cargada") y pulsar "Verificar"`,
        'El motor evalúa el texto del Invoice contra los datos del proveedor y de ULTRASIST (INT-001 a INT-004, advertencias) y las reglas XML del CFDI resultan "No aplica a proveedores internacionales".',
        async () => {
          await proveedor.goto(`/invoices/${i1.id}`);
          await verificar(proveedor);
          const resultados: string[] = [];
          for (const codigo of ['INT-001', 'INT-002', 'INT-003', 'INT-004']) {
            const regla = await resultadoRegla(proveedor, codigo);
            expect(['PASS', 'WARNING', 'NOT_APPLICABLE', 'NOT_EVALUATED']).toContain(regla.estado);
            resultados.push(`${codigo} ${regla.estado} (${regla.mensaje}; esperado "${regla.esperado}")`);
          }
          const int001 = await resultadoRegla(proveedor, 'INT-001');
          expect(int001.estado, 'El Invoice contiene el identificador fiscal 98-7654321').toBe('PASS');
          const int002 = await resultadoRegla(proveedor, 'INT-002');
          expect(int002.estado, 'El Invoice no contiene la razón social ULTRASIST').toBe('WARNING');
          // Revision visual: la etiqueta del resultado vive en una columna de 95 px de la tarjeta de la regla.
          const fin004 = proveedor.locator('#validations details.rule-card').filter({ hasText: 'FIN-004' });
          const etiqueta = await fin004.locator('.rule-result').boundingBox();
          const codigo = await fin004.locator('summary strong').boundingBox();
          if (etiqueta && codigo && etiqueta.width > 95) {
            hu.nota(
              `Defecto visual menor (no afecta los criterios): en la matriz de evidencia la etiqueta "NOT_APPLICABLE" mide ${Math.round(etiqueta.width)} px y excede su columna de 95 px y ${codigo.x - (etiqueta.x + etiqueta.width) <= 0 ? `se superpone ${Math.round(etiqueta.x + etiqueta.width - codigo.x)} px con` : `queda a ${Math.round(codigo.x - (etiqueta.x + etiqueta.width))} px de`} el código de la regla (FIN-004). Ver evidencia "reglas-int".`,
            );
          }
          const xml002 = await resultadoRegla(proveedor, 'XML-002');
          expect(xml002.estado).toBe('NOT_APPLICABLE');
          expect(xml002.mensaje).toBe('No aplica a proveedores internacionales');
          await hu.captura(proveedor, 'reglas-int', 'Matriz de evidencia: reglas INT sobre el texto del Invoice (datos del proveedor, de ULTRASIST y dirección).', {
            enfocar: proveedor.locator('#validations .rule-group').filter({ has: proveedor.locator('h3', { hasText: /^INT$/ }) }),
          });
          await hu.captura(proveedor, 'reglas-xml-no-aplican', 'Reglas XML del CFDI: "No aplica a proveedores internacionales".', {
            enfocar: proveedor.locator('#validations .rule-group').filter({ has: proveedor.locator('h3', { hasText: /^XML$/ }) }),
          });
          return `${resultados.join('; ')}. XML-002: ${xml002.estado} (${xml002.mensaje}).`;
        },
      );
    });

    await hu.escenario('Envío del Invoice al área de validación (PMO)', async () => {
      await hu.paso(
        proveedor,
        'Pulsar "Enviar a validación"',
        'Las advertencias INT no bloquean: la factura pasa a "Enviada" con el aviso "Factura enviada a validación".',
        async () => {
          await enviarAValidacion(proveedor);
          await expect(proveedor.locator('.alert-success')).toHaveText('Factura enviada a validación');
          await expect(proveedor.locator('.page-heading .status')).toHaveText('Enviada');
          await hu.captura(proveedor, 'invoice-enviado', `${i1.numero} en "Enviada" tras el envío.`);
          return `Aviso "${await texto(proveedor, '.alert-success')}"; estatus "${await texto(proveedor, '.page-heading .status')}"; advertencias: ${await texto(proveedor, '.summary-stat.warning strong')}.`;
        },
      );
      await hu.paso(
        proveedor,
        'Revisar "Datos del Invoice" y el seguimiento',
        'Se muestran los importes capturados (1,000.00 USD), el texto del Invoice "Legible" y el envío en el seguimiento.',
        async () => {
          const datos = proveedor.locator('#invoice-data');
          await expect(datos).toContainText('$1,000.00 USD');
          await expect(datos).toContainText('Legible');
          await expect(proveedor.locator('#history')).toContainText(/Envi/);
          await hu.captura(proveedor, 'datos-invoice', '"Datos del Invoice" capturados y seguimiento del envío.', { enfocar: datos });
          return `Datos del Invoice: ${(await datos.locator('dl').innerText()).replace(/\s+/g, ' ')}; seguimiento: ${(await proveedor.locator('#history ol').innerText()).replace(/\s+/g, ' ')}.`;
        },
      );
      guardarDato('hu16.enviada', i1);
    });
  });
});
