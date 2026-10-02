import { expect, test } from '@playwright/test';
import path from 'node:path';
import { herramienta, leerEstado } from '../lib/estado';
import { ejecutarHU } from '../lib/hu';
import { clicNavegando, texto } from '../lib/portal';
import { DATOS } from '../lib/rutas';

/** Clave de moneda de tres letras derivada del identificador de la ejecucion (unica por ejecucion). */
function claveMoneda(run: string, desplazamiento: number): string {
  const base = run.slice(-6);
  let clave = 'Q';
  for (let i = 0; i < 2; i += 1) {
    const codigo = base.charCodeAt(base.length - 1 - i - desplazamiento * 2);
    clave += String.fromCharCode(65 + (codigo % 26));
  }
  return clave;
}

test('HU-07 · Administración de catálogos', async ({ browser }, testInfo) => {
  await ejecutarHU('HU-07', browser, testInfo, async (hu) => {
    const { run } = leerEstado();
    const admin = await hu.sesion('admin');
    const clave = claveMoneda(run, 0);
    const claveExcel = claveMoneda(run, 1) === clave ? `${clave.slice(0, 2)}Z` : claveMoneda(run, 1);
    const fila = () => admin.locator('table.catalog-table tbody tr').filter({ has: admin.locator('td.mono', { hasText: new RegExp(`^${clave}`) }) });

    await hu.escenario('Consulta de los catálogos de referencia', async () => {
      await hu.paso(
        admin,
        'Abrir Administración › Catálogos',
        'Se listan los catálogos administrables (monedas, usos de CFDI, formas y métodos de pago, regímenes fiscales y actividades económicas) con sus claves activas y totales.',
        async () => {
          await admin.goto('/admin/catalogs');
          await expect(admin.locator('h1')).toHaveText('Catálogos');
          const catalogos = await admin.locator('table tbody tr td:first-child strong').allInnerTexts();
          expect(catalogos).toEqual(['Monedas', 'Usos de CFDI', 'Formas de pago', 'Métodos de pago', 'Regímenes fiscales', 'Actividades económicas']);
          await hu.captura(admin, 'indice-catalogos', 'Índice de catálogos con claves activas y totales.');
          const resumen = await admin.locator('table tbody tr').evaluateAll((filas) =>
            filas.map((f) => {
              const celdas = [...f.querySelectorAll('td')].map((c) => (c as HTMLElement).innerText.trim());
              return `${celdas[0].replace(/\s+/g, ' (')}): ${celdas[1]} activas de ${celdas[2]}`;
            }),
          );
          return `Catálogos: ${resumen.join('; ')}.`;
        },
      );
      await hu.paso(admin, 'Abrir el catálogo de Monedas', 'Se muestran las claves vigentes (MXN, USD, EUR) con su estado.', async () => {
        await admin.goto('/admin/catalogs/CURRENCY');
        await expect(admin.locator('h1')).toHaveText('Monedas');
        for (const codigo of ['MXN', 'USD', 'EUR']) await expect(admin.locator('table.catalog-table')).toContainText(codigo);
        await hu.captura(admin, 'catalogo-monedas', 'Catálogo de Monedas con sus claves y estados.');
        return `Catálogo "Monedas": ${await texto(admin, 'section.panel:has(table.catalog-table) .panel-header p')}`;
      });
    });

    await hu.escenario('Crear una clave nueva', async () => {
      await hu.paso(
        admin,
        `Agregar la clave "${clave}" con la descripción "Moneda de prueba QA ${run}"`,
        'Se agrega la clave ("Clave agregada") y aparece activa en el listado.',
        async () => {
          await admin.goto('/admin/catalogs/CURRENCY');
          await admin.locator('#entry_code').fill(clave);
          await admin.locator('#entry_name').fill(`Moneda de prueba QA ${run}`);
          await clicNavegando(admin, admin.getByRole('button', { name: 'Agregar clave' }));
          await expect(admin.locator('.alert-success')).toHaveText('Clave agregada');
          await expect(fila()).toContainText(`Moneda de prueba QA ${run}`);
          await expect(fila().locator('.status')).toHaveText('Activa');
          await hu.captura(admin, 'clave-agregada', `Clave ${clave} agregada y activa.`, { completa: true });
          return `Aviso "${await texto(admin, '.alert-success')}"; fila: ${(await fila().innerText()).replace(/\s+/g, ' ')}.`;
        },
      );
      await hu.paso(admin, `Intentar agregar otra vez la clave "${clave}"`, 'Se rechaza porque la clave ya existe.', async () => {
        await admin.locator('#entry_code').fill(clave);
        await admin.locator('#entry_name').fill('Duplicada');
        await clicNavegando(admin, admin.getByRole('button', { name: 'Agregar clave' }));
        const error = admin.locator('.alert-danger');
        await expect(error).toBeVisible();
        await hu.captura(admin, 'clave-duplicada', `Intento de agregar de nuevo la clave ${clave}: rechazado.`, { completa: true });
        return `Rechazado: "${await texto(admin, '.alert-danger')}".`;
      });
    });

    await hu.escenario(
      'Actualizar la descripción y desactivar / reactivar la clave',
      async () => {
        await hu.paso(admin, `Editar la descripción de "${clave}"`, 'Se guarda ("Descripción actualizada").', async () => {
          await admin.goto(`/admin/catalogs/CURRENCY?q=${clave}`);
          await fila().locator('summary').click();
          await fila().locator('input[name=name]').fill(`Moneda QA ${run} (editada)`);
          await clicNavegando(admin, fila().getByRole('button', { name: 'Guardar' }));
          await expect(admin.locator('.alert-success')).toHaveText('Descripción actualizada');
          await expect(fila()).toContainText(`Moneda QA ${run} (editada)`);
          await hu.captura(admin, 'descripcion-actualizada', `Descripción de ${clave} actualizada.`, { completa: true });
          return `Aviso "${await texto(admin, '.alert-success')}"; nueva descripción "Moneda QA ${run} (editada)".`;
        });
        await hu.paso(admin, `Desactivar "${clave}"`, 'La clave queda "Inactiva" (nunca se borra).', async () => {
          await clicNavegando(admin, fila().getByRole('button', { name: 'Desactivar' }));
          await expect(admin.locator('.alert-success')).toHaveText('Estado de la clave actualizado');
          await expect(fila().locator('.status')).toHaveText('Inactiva');
          await hu.captura(admin, 'clave-inactiva', `Clave ${clave} desactivada: estado "Inactiva".`, { completa: true });
          return `Aviso "${await texto(admin, '.alert-success')}"; estado "${await fila().locator('.status').innerText()}".`;
        });
        await hu.paso(admin, `Reactivar "${clave}"`, 'La clave vuelve a "Activa".', async () => {
          await clicNavegando(admin, fila().getByRole('button', { name: 'Reactivar' }));
          await expect(fila().locator('.status')).toHaveText('Activa');
          return `Estado "${await fila().locator('.status').innerText()}".`;
        });
      },
      { requiere: ['Crear una clave nueva'] },
    );

    await hu.escenario('Clave en uso por las Reglas de Validación: no se puede desactivar', async () => {
      await hu.paso(
        admin,
        'Abrir el catálogo de Métodos de pago',
        'La clave PPD (método esperado en las Reglas de Validación) aparece "En uso" y su botón "Desactivar" está deshabilitado.',
        async () => {
          await admin.goto('/admin/catalogs/PAYMENT_METHOD');
          const ppd = admin.locator('table.catalog-table tbody tr').filter({ has: admin.locator('td.mono', { hasText: /^PPD/ }) });
          await expect(ppd.locator('.in-use')).toHaveText('En uso');
          await expect(ppd.getByRole('button', { name: 'Desactivar' })).toBeDisabled();
          await hu.captura(admin, 'clave-en-uso', 'PPD "En uso": su botón Desactivar está deshabilitado.', { completa: true });
          return `PPD marcada "${await ppd.locator('.in-use').innerText()}" con "Desactivar" deshabilitado.`;
        },
      );
    });

    await hu.escenario('Carga del catálogo desde Excel', async () => {
      const carpeta = path.join(DATOS, run);
      let plantilla = '';
      await hu.paso(
        admin,
        'Descargar la plantilla con las claves vigentes del catálogo de Monedas',
        'Se descarga un .xlsx con la hoja "Catalogo" (Clave, Descripción, Activo) y una fila por clave vigente.',
        async () => {
          await admin.goto('/admin/catalogs/CURRENCY');
          const total = Number((await texto(admin, 'section.panel:has(table.catalog-table) .panel-header p')).match(/de (\d+)/)?.[1]);
          const [descarga] = await Promise.all([admin.waitForEvent('download'), admin.getByRole('link', { name: /Descargar plantilla/ }).click()]);
          plantilla = path.join(carpeta, descarga.suggestedFilename());
          await descarga.saveAs(plantilla);
          const libro = herramienta('inspeccionar-xlsx', plantilla);
          expect(libro.hojas[0]).toBe('Catalogo');
          expect(libro.encabezados.slice(0, 3)).toEqual(['Clave', 'Descripción', 'Activo']);
          expect(libro.filas_datos).toBe(total);
          return `Descargado "${descarga.suggestedFilename()}": hoja ${libro.hojas[0]}, encabezados ${libro.encabezados.join(' | ')}, ${libro.filas_datos} claves (= ${total} del catálogo).`;
        },
      );
      await hu.paso(
        admin,
        `Agregar en el archivo la clave "${claveExcel}" y cargarlo`,
        'La carga se aplica ("Carga aplicada: …") y la clave nueva aparece activa en el catálogo.',
        async () => {
          const archivo = path.join(carpeta, `catalogo_monedas_${run}.xlsx`);
          herramienta('plantilla-catalogo', plantilla, archivo, claveExcel, `Moneda por Excel QA ${run}`);
          await admin.locator('#catalog-file').setInputFiles(archivo);
          await clicNavegando(admin, admin.getByRole('button', { name: /Cargar archivo/ }));
          const aviso = admin.locator('.alert-success');
          await expect(aviso).toContainText('Carga aplicada');
          const textoAviso = await texto(admin, '.alert-success');
          await hu.captura(admin, 'carga-excel-aplicada', `Resultado de la carga desde Excel con la clave ${claveExcel}.`);
          await admin.goto(`/admin/catalogs/CURRENCY?q=${claveExcel}`);
          const nueva = admin.locator('table.catalog-table tbody tr').filter({ has: admin.locator('td.mono', { hasText: new RegExp(`^${claveExcel}`) }) });
          await expect(nueva).toContainText(`Moneda por Excel QA ${run}`);
          await expect(nueva.locator('.status')).toHaveText('Activa');
          await hu.captura(admin, 'clave-desde-excel', `Clave ${claveExcel} registrada desde el archivo de Excel.`, { completa: true });
          return `Aviso "${textoAviso}"; ${claveExcel} activa con la descripción "Moneda por Excel QA ${run}".`;
        },
      );
    });
  });
});
