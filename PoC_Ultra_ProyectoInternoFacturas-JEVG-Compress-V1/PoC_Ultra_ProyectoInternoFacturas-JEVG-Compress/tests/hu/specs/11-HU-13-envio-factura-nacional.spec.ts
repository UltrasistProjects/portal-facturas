import { expect, test } from '@playwright/test';
import { guardarDato, leerEstado } from '../lib/estado';
import { ejecutarHU } from '../lib/hu';
import { enviarAValidacion, registrarFacturaNacional, resultadoRegla, texto } from '../lib/portal';

test('HU-13 · Envío de factura por proveedor nacional', async ({ browser }, testInfo) => {
  await ejecutarHU('HU-13', browser, testInfo, async (hu) => {
    const { run, fixtures } = leerEstado();
    const n1 = hu.requiere<{ id: number; numero: string }>('HU-12', 'hu12.factura');
    const proveedor = await hu.sesion('proveedor1');
    const soporte = { pdf: fixtures.pdf_cfdi, ordenCompra: fixtures.orden_compra, vobo: fixtures.vobo };

    await hu.escenario('Envío de una factura cuyo XML coincide con las Reglas de Validación (RN-HU13-02)', async () => {
      await hu.paso(
        proveedor,
        `Abrir la factura ${n1.numero} ("Cargada", de HU-12) y pulsar "Enviar a validación"`,
        'El sistema valida el XML contra las Reglas de Validación; sin reglas en FAIL, la factura pasa a "Enviada" con el aviso "Factura enviada a validación".',
        async () => {
          await proveedor.goto(`/invoices/${n1.id}`);
          await expect(proveedor.locator('.page-heading .status')).toHaveText('Cargada');
          await hu.captura(proveedor, 'antes-de-enviar', `Detalle de ${n1.numero} en "Cargada" con el botón "Enviar a validación".`);
          await enviarAValidacion(proveedor);
          await expect(proveedor.locator('.alert-success')).toHaveText('Factura enviada a validación');
          await expect(proveedor.locator('.page-heading .status')).toHaveText('Enviada');
          await expect(proveedor.getByRole('link', { name: /Gestionar documentos/ })).toHaveCount(0);
          await hu.captura(proveedor, 'factura-enviada', `${n1.numero} enviada: estatus "Enviada" y sin opción de modificar documentos.`);
          return `Aviso "${await texto(proveedor, '.alert-success')}"; estatus "${await texto(proveedor, '.page-heading .status')}"; "Gestionar documentos" ya no se ofrece.`;
        },
      );
      await hu.paso(
        proveedor,
        'Revisar en la matriz de evidencia las comparaciones del XML con las Reglas de Validación',
        'XML-002 (RFC), XML-009 (razón social), XML-010 (código postal) y FIN-004 (UUID no duplicado) resultan PASS.',
        async () => {
          const reglas = [];
          for (const codigo of ['XML-002', 'XML-009', 'XML-010', 'FIN-004']) {
            const regla = await resultadoRegla(proveedor, codigo);
            expect(regla.estado, `${codigo}: ${regla.mensaje}`).toBe('PASS');
            reglas.push(`${codigo} ${regla.estado} (${regla.mensaje})`);
          }
          await hu.captura(proveedor, 'reglas-xml-pass', 'Matriz de evidencia: grupo XML (XML-001 a XML-010) en PASS frente a las Reglas de Validación.', {
            enfocar: proveedor.locator('#validations details.rule-card').filter({ hasText: 'XML-006' }),
          });
          await hu.captura(proveedor, 'fin-004-uuid-unico', 'Matriz de evidencia: FIN-004 "UUID no duplicado" en PASS.', {
            enfocar: proveedor.locator('#validations details.rule-card').filter({ hasText: 'FIN-004' }),
          });
          return reglas.join('; ') + '.';
        },
      );
      guardarDato('hu13.enviada', n1);
    });

    await hu.escenario('El XML no coincide con las Reglas de Validación: el envío no procede', async () => {
      const numero = `QA-${run}-N2`;
      let id = 0;
      await hu.paso(
        proveedor,
        `Registrar ${numero} con un XML cuyo código postal del receptor es 06600 (configurado: 03930)`,
        'La factura queda "Cargada" con sus 4 obligatorios.',
        async () => {
          id = await registrarFacturaNacional(proveedor, numero, { xml: fixtures.cfdi_cp, ...soporte });
          await proveedor.goto(`/invoices/${id}`);
          await expect(proveedor.locator('.page-heading .status')).toHaveText('Cargada');
          return `Factura #${id} "${numero}" en "${await texto(proveedor, '.page-heading .status')}".`;
        },
      );
      await hu.paso(
        proveedor,
        'Pulsar "Enviar a validación"',
        'El envío no procede: se muestra "El envío no procedió" y "Reglas que impiden el envío" con XML-010 (esperado 03930, detectado 06600); la factura sigue "Cargada".',
        async () => {
          await enviarAValidacion(proveedor);
          await expect(proveedor.locator('.alert-danger').filter({ hasText: 'El envío no procedió' })).toBeVisible();
          const fila = proveedor.locator('#blocking tbody tr').filter({ hasText: 'XML-010' });
          await expect(fila.locator('td').nth(2)).toHaveText('03930');
          await expect(fila.locator('td').nth(3)).toHaveText('06600');
          await expect(proveedor.locator('.page-heading .status')).toHaveText('Cargada');
          await hu.captura(proveedor, 'envio-rechazado-reglas', 'El envío no procedió: XML-010 con el valor esperado (03930) y el detectado (06600).', {
            enfocar: proveedor.locator('#blocking'),
          });
          return `"${await texto(proveedor, '.alert-danger')}"; bloqueo: ${(await fila.innerText()).replace(/\s+/g, ' ')}; estatus "${await texto(proveedor, '.page-heading .status')}".`;
        },
      );
      guardarDato('hu13.noEnviada', { id, numero });
    });

    await hu.escenario('Factura duplicada por el folio fiscal (UUID) del XML (RN-HU13-01)', async () => {
      const numero = `QA-${run}-N3`;
      let id = 0;
      await hu.paso(
        proveedor,
        `Registrar ${numero} con un XML que repite el UUID de ${n1.numero}`,
        'La factura queda "Cargada" con sus 4 obligatorios.',
        async () => {
          id = await registrarFacturaNacional(proveedor, numero, { xml: fixtures.cfdi_dup, ...soporte });
          await proveedor.goto(`/invoices/${id}`);
          await expect(proveedor.locator('.page-heading .status')).toHaveText('Cargada');
          return `Factura #${id} "${numero}" en "${await texto(proveedor, '.page-heading .status')}" (UUID ${fixtures.uuid_ok}).`;
        },
      );
      await hu.paso(
        proveedor,
        'Pulsar "Enviar a validación"',
        'El envío no procede por FIN-004 ("Posible factura duplicada por UUID"), sin revelar datos de la otra factura; la factura sigue "Cargada".',
        async () => {
          await enviarAValidacion(proveedor);
          await expect(proveedor.locator('.alert-danger').filter({ hasText: 'El envío no procedió' })).toBeVisible();
          const fila = proveedor.locator('#blocking tbody tr').filter({ hasText: 'FIN-004' });
          await expect(fila).toContainText('Posible factura duplicada por UUID');
          await expect(proveedor.locator('#blocking')).not.toContainText(n1.numero);
          await expect(proveedor.locator('.page-heading .status')).toHaveText('Cargada');
          await hu.captura(proveedor, 'envio-rechazado-duplicado', 'El envío no procedió: FIN-004, UUID ya registrado en otra factura.', {
            enfocar: proveedor.locator('#blocking'),
          });
          return `Bloqueo: ${(await fila.innerText()).replace(/\s+/g, ' ')}; no se muestra el número de la otra factura; estatus "${await texto(proveedor, '.page-heading .status')}".`;
        },
      );
    });
  });
});
