import { expect, test, type Page } from '@playwright/test';
import { guardarDato, leerEstado } from '../lib/estado';
import { ejecutarHU } from '../lib/hu';
import { abrirFactura, clicNavegando, resultadoRegla, texto, verificar } from '../lib/portal';

type Origen = 'national' | 'international';

/** Fila de una regla en la tabla de activas o en la de eliminadas (con ?eliminados=1). */
function filaRegla(admin: Page, codigo: string) {
  return admin.locator('table tbody tr').filter({ has: admin.locator('td.mono', { hasText: codigo }) });
}

/** Edita el valor esperado de una regla (activa o eliminada) y guarda; devuelve el aviso. */
async function editarRegla(admin: Page, origen: Origen, codigo: string, valor: string): Promise<string> {
  await admin.goto(`/admin/rules/${origen}?eliminados=1`);
  await clicNavegando(admin, filaRegla(admin, codigo).getByRole('link', { name: 'Editar' }));
  const formulario = admin.locator('details.admin-create[open]').filter({ hasText: codigo });
  await formulario.locator('[name=parameter]').fill(valor);
  await clicNavegando(admin, formulario.getByRole('button', { name: 'Guardar regla' }));
  return texto(admin, '.alert');
}

async function eliminarRegla(admin: Page, origen: Origen, codigo: string): Promise<string> {
  await admin.goto(`/admin/rules/${origen}`);
  const confirmar = filaRegla(admin, codigo).locator('details.delete-confirm');
  await confirmar.locator('summary').click();
  await clicNavegando(admin, confirmar.getByRole('button', { name: 'Sí, eliminar' }));
  await expect(admin.locator('.alert-success')).toHaveText('Regla eliminada');
  return texto(admin, '.alert-success');
}

/** Restaura la regla si esta eliminada; no hace nada si ya esta activa. */
async function restaurarRegla(admin: Page, origen: Origen, codigo: string): Promise<string> {
  await admin.goto(`/admin/rules/${origen}?eliminados=1`);
  const restaurar = admin.locator('#eliminados tbody tr').filter({ hasText: codigo }).getByRole('button', { name: 'Restaurar' });
  if ((await restaurar.count()) === 0) return 'ya estaba activa';
  await clicNavegando(admin, restaurar);
  await expect(admin.locator('.alert-success')).toHaveText('Regla restaurada');
  return texto(admin, '.alert-success');
}

test('HU-06 · Configuración de reglas de validación', async ({ browser }, testInfo) => {
  await ejecutarHU('HU-06', browser, testInfo, async (hu) => {
    const { run } = leerEstado();
    const admin = await hu.sesion('admin');
    const direccion = `Av. Insurgentes Sur 1000, Col. Del Valle, Benito Juárez, CDMX (QA ${run})`;

    await hu.escenario('Reglas separadas por origen: Nacionales e Internacionales', async () => {
      await hu.paso(
        admin,
        'Abrir Reglas de validación › Nacionales',
        'Se listan las reglas del CFDI (XML-002 a XML-010) con su valor esperado, severidad y las acciones Editar y Eliminar; XML-007 se administra en el catálogo de monedas.',
        async () => {
          await admin.goto('/admin/rules/national');
          await expect(admin.locator('h1')).toHaveText('Reglas de validación — Nacionales');
          await expect(filaRegla(admin, 'XML-002')).toContainText('ULT940623AG0');
          await expect(filaRegla(admin, 'XML-009')).toContainText('ULTRASIST');
          await expect(filaRegla(admin, 'XML-010')).toContainText('03930');
          await expect(admin.locator('td.mono', { hasText: 'INT-' })).toHaveCount(0);
          await hu.captura(admin, 'reglas-nacionales', 'Reglas de validación — Nacionales: valores esperados, severidad y acciones.', { completa: true });
          const codigos = await admin.locator('table tbody td.mono').allInnerTexts();
          return `Reglas nacionales: ${codigos.join(', ')}.`;
        },
      );
      await hu.paso(
        admin,
        'Abrir Reglas de validación › Internacionales',
        'Se listan sólo las reglas del Invoice (INT-001 a INT-003); ninguna regla del CFDI.',
        async () => {
          await admin.goto('/admin/rules/international');
          await expect(admin.locator('h1')).toHaveText('Reglas de validación — Internacionales');
          await expect(filaRegla(admin, 'INT-002')).toContainText('ULTRASIST');
          await expect(admin.locator('td.mono', { hasText: 'XML-' })).toHaveCount(0);
          await hu.captura(admin, 'reglas-internacionales', 'Reglas de validación — Internacionales.', { completa: true });
          const codigos = await admin.locator('table tbody td.mono').allInnerTexts();
          return `Reglas internacionales: ${codigos.join(', ')}.`;
        },
      );
    });

    await hu.escenario('Validación de los valores de referencia', async () => {
      await hu.paso(
        admin,
        'Editar XML-002 con un RFC de formato inválido ("XYZ123") y guardar',
        'El guardado se rechaza con el error del RFC y el valor vigente no cambia.',
        async () => {
          await editarRegla(admin, 'national', 'XML-002', 'XYZ123');
          const errores = admin.locator('.template-errors li');
          await expect(errores.first()).toContainText('RFC: no es un RFC de persona moral válido');
          const lista = await errores.allInnerTexts();
          await hu.captura(admin, 'errores-reglas', 'Error de validación del RFC en XML-002.');
          await admin.goto('/admin/rules/national');
          await expect(filaRegla(admin, 'XML-002')).toContainText('ULT940623AG0');
          return `Errores: ${lista.join(' / ')}. Al recargar, XML-002 sigue esperando ULT940623AG0.`;
        },
      );
    });

    await hu.escenario('Alta de un valor de referencia internacional (INT-004 / Dirección)', async () => {
      await hu.paso(
        admin,
        'Capturar la Dirección de ULTRASIST en INT-004 (nace eliminada) y restaurarla',
        'La regla guarda la dirección ("Regla actualizada") y al restaurarla queda activa ("Regla restaurada").',
        async () => {
          const editado = await editarRegla(admin, 'international', 'INT-004', direccion);
          const restaurado = await restaurarRegla(admin, 'international', 'INT-004');
          await admin.goto('/admin/rules/international');
          await expect(filaRegla(admin, 'INT-004')).toContainText(direccion);
          await hu.captura(admin, 'direccion-guardada', 'INT-004 activa con la Dirección de ULTRASIST.', { enfocar: filaRegla(admin, 'INT-004') });
          return `Edición: "${editado}"; restauración: "${restaurado}"; INT-004 espera "${direccion}".`;
        },
      );
      guardarDato('hu06.direccion', direccion);
    });

    await hu.escenario(
      'La validación de facturas internacionales usa las reglas internacionales (INT-004 / Dirección)',
      async () => {
        const internacional = await hu.sesion('proveedor3');
        await hu.paso(
          internacional,
          'El proveedor internacional pulsa "Verificar" en su factura INV-2026-0042',
          'INT-004 compara el texto del Invoice con la Dirección configurada en la regla internacional.',
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
      { requiere: ['Alta de un valor de referencia internacional (INT-004 / Dirección)'] },
    );

    const proveedor = await hu.sesion('proveedor1');
    await hu.escenario('La validación de facturas consume la configuración vigente (XML-010 / Código postal)', async () => {
      await hu.paso(admin, 'Cambiar el Código postal esperado de XML-010 a 06600', 'La regla se guarda con el C.P. 06600 ("Regla actualizada").', async () => {
        const aviso = await editarRegla(admin, 'national', 'XML-010', '06600');
        await expect(admin.locator('.alert-success')).toHaveText('Regla actualizada');
        await expect(filaRegla(admin, 'XML-010')).toContainText('06600');
        return `Aviso "${aviso}"; XML-010 espera 06600.`;
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
      await hu.paso(admin, 'Restaurar el Código postal 03930 en XML-010', 'La regla vuelve a esperar 03930.', async () => {
        return `Aviso "${await editarRegla(admin, 'national', 'XML-010', '03930')}"; C.P. 03930 restaurado.`;
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

    await hu.escenario('Una factura nacional sólo usa las reglas nacionales', async () => {
      await hu.paso(admin, 'Cambiar la Razón social de la regla internacional INT-002 a "OTRA RAZON QA"', 'Sólo cambia la regla internacional; XML-009 sigue esperando "ULTRASIST".', async () => {
        const aviso = await editarRegla(admin, 'international', 'INT-002', 'OTRA RAZON QA');
        await admin.goto('/admin/rules/national');
        await expect(filaRegla(admin, 'XML-009')).toContainText('ULTRASIST');
        return `Aviso "${aviso}"; XML-009 (nacional) sigue en ULTRASIST.`;
      });
      await hu.paso(proveedor, 'El proveedor pulsa "Verificar" en A-CORRECTA', 'XML-009 resulta PASS con el valor esperado nacional "ULTRASIST".', async () => {
        await verificar(proveedor);
        const regla = await resultadoRegla(proveedor, 'XML-009');
        expect(regla.estado).toBe('PASS');
        expect(regla.esperado).toBe('ULTRASIST');
        return `XML-009: ${regla.estado} (esperado "${regla.esperado}").`;
      });
      await hu.paso(admin, 'Restaurar "ULTRASIST" en INT-002', 'La regla internacional vuelve a su valor inicial.', async () => {
        return `Aviso "${await editarRegla(admin, 'international', 'INT-002', 'ULTRASIST')}".`;
      });
    });

    await hu.escenario('Eliminación lógica y restauración de una regla (XML-010)', async () => {
      await hu.paso(admin, 'Eliminar XML-010 y confirmar', 'El portal responde "Regla eliminada" y la regla deja de listarse entre las activas.', async () => {
        const aviso = await eliminarRegla(admin, 'national', 'XML-010');
        await expect(filaRegla(admin, 'XML-010')).toHaveCount(0);
        await hu.captura(admin, 'regla-eliminada', 'XML-010 eliminada: ya no aparece entre las reglas activas.');
        return `Aviso "${aviso}".`;
      });
      await hu.paso(
        proveedor,
        'El proveedor pulsa "Verificar" en A-CORRECTA',
        'XML-010 resulta NOT_APPLICABLE con el mensaje "Regla inactiva en Reglas de Validación".',
        async () => {
          await verificar(proveedor);
          const regla = await resultadoRegla(proveedor, 'XML-010');
          expect(regla.estado).toBe('NOT_APPLICABLE');
          expect(regla.mensaje).toBe('Regla inactiva en Reglas de Validación');
          await hu.captura(proveedor, 'xml-010-no-aplica', 'XML-010 "NOT_APPLICABLE": regla eliminada en las Reglas de Validación.', {
            enfocar: proveedor.locator('#validations details.rule-card').filter({ hasText: 'XML-010' }),
          });
          return `XML-010: ${regla.estado} — "${regla.mensaje}".`;
        },
      );
      await hu.paso(admin, 'Mostrar eliminados y restaurar XML-010', 'La regla aparece entre las eliminadas y al restaurarla vuelve a las activas ("Regla restaurada").', async () => {
        await admin.goto('/admin/rules/national?eliminados=1');
        const eliminada = admin.locator('#eliminados tbody tr').filter({ hasText: 'XML-010' });
        await expect(eliminada).toHaveCount(1);
        await hu.captura(admin, 'regla-en-eliminados', 'XML-010 en "Reglas eliminadas" con "Restaurar".', { enfocar: eliminada });
        const aviso = await restaurarRegla(admin, 'national', 'XML-010');
        await expect(filaRegla(admin, 'XML-010')).toHaveCount(1);
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
