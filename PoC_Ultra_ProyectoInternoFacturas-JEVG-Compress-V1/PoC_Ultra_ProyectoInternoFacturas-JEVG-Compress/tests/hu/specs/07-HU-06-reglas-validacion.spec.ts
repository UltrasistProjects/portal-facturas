import { expect, test, type Page } from '@playwright/test';
import { guardarDato, leerEstado } from '../lib/estado';
import { ejecutarHU } from '../lib/hu';
import { abrirFactura, clicNavegando, resultadoRegla, texto, verificar } from '../lib/portal';

async function guardarReglas(admin: Page): Promise<string> {
  await clicNavegando(admin, admin.getByRole('button', { name: 'Guardar reglas' }));
  await expect(admin.locator('.alert-success')).toHaveText('Reglas de validación guardadas');
  return texto(admin, '.alert-success');
}

test('HU-06 · Configuración de reglas de validación', async ({ browser }, testInfo) => {
  await ejecutarHU('HU-06', browser, testInfo, async (hu) => {
    const { run } = leerEstado();
    const admin = await hu.sesion('admin');
    const direccion = `Av. Insurgentes Sur 1000, Col. Del Valle, Benito Juárez, CDMX (QA ${run})`;

    await hu.escenario('Consulta de los datos de ULTRASIST contra los que se comparan las facturas', async () => {
      await hu.paso(
        admin,
        'Abrir Administración › Reglas de validación',
        'Se muestran RFC, Razón social, Código postal y Dirección de ULTRASIST con su interruptor "Comparar", y la tabla de reglas XML.',
        async () => {
          await admin.goto('/admin/rules');
          await expect(admin.locator('h1')).toHaveText('Reglas de validación');
          await expect(admin.locator('#receiver_rfc')).toHaveValue('ULT940623AG0');
          await expect(admin.locator('#receiver_name')).toHaveValue('ULTRASIST');
          await expect(admin.locator('#receiver_postal_code')).toHaveValue('03930');
          await expect(admin.locator('#receiver_address')).toBeVisible();
          await expect(admin.locator('input[name=check_receiver_postal_code]')).toBeChecked();
          await hu.captura(admin, 'reglas-validacion', 'Datos de ULTRASIST (RFC, razón social, código postal, dirección) con sus interruptores "Comparar".');
          return `RFC "${await admin.locator('#receiver_rfc').inputValue()}", Razón social "${await admin.locator('#receiver_name').inputValue()}", C.P. "${await admin.locator('#receiver_postal_code').inputValue()}"; comparaciones activas.`;
        },
      );
    });

    await hu.escenario('Validación de los valores de referencia', async () => {
      await hu.paso(
        admin,
        'Capturar un RFC con formato inválido ("XYZ123") y un código postal inválido ("ABC12") y guardar',
        'El guardado se rechaza, se muestran juntos los errores y los valores vigentes no cambian.',
        async () => {
          await admin.goto('/admin/rules');
          await admin.locator('#receiver_rfc').fill('XYZ123');
          await admin.locator('#receiver_postal_code').fill('ABC12');
          await clicNavegando(admin, admin.getByRole('button', { name: 'Guardar reglas' }));
          const errores = admin.locator('.template-errors li');
          await expect(errores.first()).toBeVisible();
          const lista = await errores.allInnerTexts();
          await hu.captura(admin, 'errores-reglas', 'Errores de validación de las reglas (RFC y código postal).');
          await admin.goto('/admin/rules');
          await expect(admin.locator('#receiver_rfc')).toHaveValue('ULT940623AG0');
          await expect(admin.locator('#receiver_postal_code')).toHaveValue('03930');
          return `Errores: ${lista.join(' / ')}. Al recargar, RFC y C.P. siguen en ULT940623AG0 y 03930.`;
        },
      );
    });

    await hu.escenario('Alta y modificación de un valor de referencia (Dirección)', async () => {
      await hu.paso(
        admin,
        'Capturar la Dirección de ULTRASIST y guardar',
        'Se guardan las reglas ("Reglas de validación guardadas") y la dirección queda registrada con la nueva versión.',
        async () => {
          await admin.goto('/admin/rules');
          const version = await texto(admin, '.panel-header p');
          await admin.locator('#receiver_address').fill(direccion);
          const aviso = await guardarReglas(admin);
          await expect(admin.locator('#receiver_address')).toHaveValue(direccion);
          await hu.captura(admin, 'direccion-guardada', 'Reglas guardadas con la Dirección de ULTRASIST capturada.');
          return `Aviso "${aviso}"; dirección "${direccion}". Antes: "${version}"; ahora: "${await texto(admin, '.panel-header p')}".`;
        },
      );
      guardarDato('hu06.direccion', direccion);
    });

    await hu.escenario(
      'La validación de facturas internacionales usa los datos configurados (INT-004 / Dirección)',
      async () => {
        const internacional = await hu.sesion('proveedor3');
        await hu.paso(
          internacional,
          'El proveedor internacional pulsa "Verificar" en su factura INV-2026-0042',
          'INT-004 compara el texto del Invoice con la Dirección recién configurada (valor esperado = dirección guardada).',
          async () => {
            await abrirFactura(internacional, 'INV-2026-0042');
            await verificar(internacional);
            const regla = await resultadoRegla(internacional, 'INT-004');
            expect(regla.esperado).toBe(direccion);
            expect(['PASS', 'WARNING']).toContain(regla.estado);
            await hu.captura(internacional, 'int-004-direccion', 'INT-004 en el Invoice internacional con la Dirección configurada como valor esperado.', {
              enfocar: internacional.locator('#validations details.rule-card').filter({ hasText: 'INT-004' }),
            });
            return `INT-004: ${regla.estado} — "${regla.mensaje}" (esperado "${regla.esperado}").`;
          },
        );
      },
      { requiere: ['Alta y modificación de un valor de referencia (Dirección)'] },
    );

    const proveedor = await hu.sesion('proveedor1');
    await hu.escenario('La validación de facturas consume la configuración vigente (XML-010 / Código postal)', async () => {
      await hu.paso(admin, 'Cambiar el Código postal de ULTRASIST a 06600 y guardar', 'Las reglas se guardan con el C.P. 06600.', async () => {
        await admin.goto('/admin/rules');
        await admin.locator('#receiver_postal_code').fill('06600');
        const aviso = await guardarReglas(admin);
        await expect(admin.locator('#receiver_postal_code')).toHaveValue('06600');
        return `Aviso "${aviso}"; C.P. configurado 06600.`;
      });
      await hu.paso(
        proveedor,
        'El proveedor pulsa "Verificar" en su factura A-CORRECTA (XML con C.P. del receptor 03930)',
        'XML-010 resulta FAIL con esperado 06600 y detectado 03930: el motor usa el valor recién configurado.',
        async () => {
          await abrirFactura(proveedor, 'A-CORRECTA');
          await verificar(proveedor);
          const regla = await resultadoRegla(proveedor, 'XML-010');
          expect(regla.estado).toBe('FAIL');
          expect(regla.esperado).toBe('06600');
          expect(regla.detectado).toBe('03930');
          await hu.captura(proveedor, 'xml-010-fail', 'Tras cambiar el C.P. a 06600, "Verificar" marca XML-010 en FAIL (esperado 06600, detectado 03930).', {
            enfocar: proveedor.locator('#blocking'),
          });
          return `XML-010: ${regla.estado} — "${regla.mensaje}" (esperado ${regla.esperado}, detectado ${regla.detectado}).`;
        },
      );
      await hu.paso(admin, 'Restaurar el Código postal 03930 y guardar', 'Las reglas se guardan de nuevo con el C.P. 03930.', async () => {
        await admin.goto('/admin/rules');
        await admin.locator('#receiver_postal_code').fill('03930');
        return `Aviso "${await guardarReglas(admin)}"; C.P. 03930 restaurado.`;
      });
      await hu.paso(proveedor, 'El proveedor vuelve a pulsar "Verificar"', 'XML-010 resulta PASS (03930 = 03930).', async () => {
        await verificar(proveedor);
        const regla = await resultadoRegla(proveedor, 'XML-010');
        expect(regla.estado).toBe('PASS');
        await hu.captura(proveedor, 'xml-010-pass', 'Con el C.P. restaurado, XML-010 vuelve a PASS.', {
          enfocar: proveedor.locator('#validations details.rule-card').filter({ hasText: 'XML-010' }),
        });
        return `XML-010: ${regla.estado} — "${regla.mensaje}".`;
      });
    });

    await hu.escenario('Baja de una comparación: desactivar "Comparar" en el Código postal', async () => {
      await hu.paso(admin, 'Desmarcar "Comparar" del Código postal y guardar', 'Las reglas se guardan y XML-010 aparece "Desactivada".', async () => {
        await admin.goto('/admin/rules');
        await admin.locator('input[name=check_receiver_postal_code]').uncheck();
        const aviso = await guardarReglas(admin);
        const fila = admin.locator('table tbody tr').filter({ hasText: 'XML-010' });
        await expect(fila.locator('.status')).toHaveText('Desactivada');
        await hu.captura(admin, 'comparacion-desactivada', 'Tabla de reglas XML con XML-010 "Desactivada".', { enfocar: fila });
        return `Aviso "${aviso}"; XML-010 en estado "${await fila.locator('.status').innerText()}".`;
      });
      await hu.paso(
        proveedor,
        'El proveedor pulsa "Verificar" en A-CORRECTA',
        'XML-010 resulta NOT_APPLICABLE con el mensaje "Comparación desactivada en Reglas de Validación".',
        async () => {
          await verificar(proveedor);
          const regla = await resultadoRegla(proveedor, 'XML-010');
          expect(regla.estado).toBe('NOT_APPLICABLE');
          expect(regla.mensaje).toBe('Comparación desactivada en Reglas de Validación');
          await hu.captura(proveedor, 'xml-010-no-aplica', 'XML-010 "NOT_APPLICABLE": comparación desactivada en las Reglas de Validación.', {
            enfocar: proveedor.locator('#validations details.rule-card').filter({ hasText: 'XML-010' }),
          });
          return `XML-010: ${regla.estado} — "${regla.mensaje}".`;
        },
      );
      await hu.paso(admin, 'Volver a activar "Comparar" en el Código postal', 'XML-010 vuelve a "Activa".', async () => {
        await admin.goto('/admin/rules');
        await admin.locator('input[name=check_receiver_postal_code]').check();
        const aviso = await guardarReglas(admin);
        await expect(admin.locator('table tbody tr').filter({ hasText: 'XML-010' }).locator('.status')).toHaveText('Activa');
        return `Aviso "${aviso}"; XML-010 activa de nuevo.`;
      });
      await hu.paso(proveedor, 'El proveedor verifica de nuevo A-CORRECTA', 'XML-010 vuelve a PASS.', async () => {
        await verificar(proveedor);
        const regla = await resultadoRegla(proveedor, 'XML-010');
        expect(regla.estado).toBe('PASS');
        return `XML-010: ${regla.estado}.`;
      });
    });
  });
});
