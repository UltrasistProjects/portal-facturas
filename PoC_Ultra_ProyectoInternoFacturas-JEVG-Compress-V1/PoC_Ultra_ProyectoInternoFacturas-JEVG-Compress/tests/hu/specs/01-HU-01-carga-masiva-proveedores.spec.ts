import { expect, test } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
import { guardarDato, herramienta, leerEstado } from '../lib/estado';
import { ejecutarHU } from '../lib/hu';
import { texto } from '../lib/portal';
import { DATOS } from '../lib/rutas';

test('HU-01 · Carga masiva de proveedores', async ({ browser }, testInfo) => {
  await ejecutarHU('HU-01', browser, testInfo, async (hu) => {
    const { run } = leerEstado();
    const carpeta = path.join(DATOS, run);
    const admin = await hu.sesion('admin');
    let plantilla = '';
    let proveedores: { razon_social: string; rfc: string | null; id_fiscal: string | null; correo: string }[] = [];

    await hu.escenario('Acceso al módulo y descarga de la plantilla predefinida', async () => {
      await hu.paso(
        admin,
        'Abrir Proveedores › Carga masiva',
        'Se muestra la página "Carga masiva de proveedores" con el formulario de carga (.xlsx) y "Descargar plantilla".',
        async () => {
          await admin.goto('/suppliers');
          await expect(admin.locator('h1')).toHaveText('Proveedores');
          await hu.captura(admin, 'listado-proveedores-inicial', 'Listado de proveedores antes de la carga, con el botón "Carga masiva".');
          await admin.getByRole('link', { name: /Carga masiva/ }).click();
          await expect(admin.locator('h1')).toHaveText('Carga masiva de proveedores');
          await expect(admin.locator('#supplier-import-file')).toHaveAttribute('accept', '.xlsx');
          await hu.captura(admin, 'pagina-carga-masiva', 'Página de carga masiva: instrucciones, campo de archivo .xlsx y "Descargar plantilla".');
          return `Página "${await texto(admin, 'h1')}" con el campo de archivo (accept=.xlsx) y el botón "Cargar proveedores".`;
        },
      );
      await hu.paso(
        admin,
        'Descargar la plantilla de Excel',
        'Se descarga plantilla_carga_proveedores_v1.xlsx con la hoja "Proveedores" (10 columnas del catálogo) e "Instrucciones".',
        async () => {
          const [descarga] = await Promise.all([
            admin.waitForEvent('download'),
            admin.getByRole('link', { name: /Descargar plantilla/ }).click(),
          ]);
          plantilla = path.join(carpeta, descarga.suggestedFilename());
          await descarga.saveAs(plantilla);
          const libro = herramienta('inspeccionar-xlsx', plantilla);
          expect(descarga.suggestedFilename()).toBe('plantilla_carga_proveedores_v1.xlsx');
          expect(libro.hojas).toEqual(['Proveedores', 'Instrucciones']);
          expect(libro.encabezados).toEqual([
            'Origen', 'Tipo de persona', 'Razón social', 'RFC', 'Identificador fiscal extranjero', 'País',
            'Correo electrónico', 'Teléfono', 'Convenio de confidencialidad', 'Notas',
          ]);
          expect(libro.filas_datos).toBe(0);
          return `Descargado "${descarga.suggestedFilename()}": hojas ${libro.hojas.join(', ')}; encabezados: ${libro.encabezados.join(' | ')}; sin filas de datos.`;
        },
      );
    });

    const conErrores = path.join(carpeta, `carga_proveedores_${run}_con_errores.xlsx`);
    const validos = path.join(carpeta, `carga_proveedores_${run}_validos.xlsx`);
    let filaValidaConErrores = { rfc: '', razon_social: '' };

    await hu.escenario(
      'Archivo con filas con errores: "No, corregir primero"',
      async () => {
        const filas = herramienta('plantilla-proveedores', plantilla, conErrores, run, 'errores').filas;
        filaValidaConErrores = filas[0];
        await hu.paso(
          admin,
          'Cargar la plantilla llena con 1 fila válida y 3 filas con errores (RFC inválido, sin identificador fiscal, correo inválido)',
          'Se abre la ventana "Algunas filas contienen errores o no se han podido leer correctamente. ¿Desea agregar las filas válidas?".',
          async () => {
            await admin.locator('#supplier-import-file').setInputFiles(conErrores);
            await admin.locator('#supplier-import-submit').click();
            const modal = admin.locator('#supplier-import-confirm');
            await expect(modal).toBeVisible();
            await expect(modal).toContainText('Algunas filas contienen errores o no se han podido leer correctamente. ¿Desea agregar las filas válidas?');
            await expect(admin.locator('#supplier-import-fix')).toBeFocused();
            await hu.captura(admin, 'modal-filas-con-errores', 'Ventana de confirmación con "No, corregir primero (Recomendado)" preseleccionado.');
            return `Ventana mostrada: "${await texto(admin, '#supplier-import-confirm .modal-body')}"; botón con foco: "No, corregir primero (Recomendado)".`;
          },
        );
        await hu.paso(
          admin,
          'Elegir "No, corregir primero (Recomendado)"',
          'Se cierra la ventana, se listan los errores por fila y columna, y el catálogo no cambia.',
          async () => {
            await admin.locator('#supplier-import-fix').click();
            const errores = admin.locator('#supplier-import-errors');
            await expect(errores).toBeVisible();
            const items = await errores.locator('ul.import-errors li').allInnerTexts();
            expect(items.length).toBeGreaterThanOrEqual(3);
            expect(items.join('\n')).toMatch(/Fila 3/);
            await hu.captura(admin, 'errores-por-fila', 'Lista de errores "Fila N · Columna: mensaje" tras elegir corregir primero.', { enfocar: errores });
            await admin.goto(`/suppliers?q=${encodeURIComponent(filaValidaConErrores.rfc)}`);
            await expect(admin.locator('table tbody')).toContainText('Sin resultados para la búsqueda.');
            await hu.captura(admin, 'catalogo-sin-cambios', `Búsqueda del RFC de la fila válida (${filaValidaConErrores.rfc}): sin resultados, el catálogo no cambió.`);
            return `Errores listados (${items.length}): ${items.join(' / ')}. La búsqueda del RFC ${filaValidaConErrores.rfc} no devuelve proveedores.`;
          },
        );
      },
    );

    await hu.escenario('Archivo con filas con errores: "Agrega las filas válidas y omite el resto"', async () => {
      await hu.paso(
        admin,
        'Volver a cargar el mismo archivo y elegir "Agrega las filas válidas y omite el resto"',
        'Se registra sólo la fila válida y el resumen lista las filas no registradas con sus errores.',
        async () => {
          await admin.goto('/suppliers/import');
          await admin.locator('#supplier-import-file').setInputFiles(conErrores);
          await admin.locator('#supplier-import-submit').click();
          await expect(admin.locator('#supplier-import-confirm')).toBeVisible();
          await admin.locator('#supplier-import-partial').click();
          const resumen = admin.locator('#supplier-import-summary');
          await expect(resumen).toBeVisible();
          await expect(admin.locator('#supplier-import-summary-text')).toContainText('1 proveedor registrado');
          await expect(admin.locator('#supplier-import-errors-title')).toHaveText('Filas no registradas por errores');
          await hu.captura(admin, 'resumen-carga-parcial', 'Resumen de la carga parcial: 1 proveedor registrado y las filas no registradas por errores.', { completa: true });
          return `Resumen: "${await texto(admin, '#supplier-import-summary-text')}"; sección "${await texto(admin, '#supplier-import-errors-title')}" con ${await admin.locator('ul.import-errors li').count()} errores.`;
        },
      );
    });

    await hu.escenario('Archivo válido: registro y mapeo de los datos al catálogo (RN-HU01-01)', async () => {
      proveedores = herramienta('plantilla-proveedores', plantilla, validos, run, 'validos').filas;
      await hu.paso(
        admin,
        'Cargar la plantilla con 3 proveedores válidos (2 nacionales y 1 internacional)',
        'Se registran los 3 proveedores y se muestra el resumen "3 proveedores registrados".',
        async () => {
          await admin.goto('/suppliers/import');
          await admin.locator('#supplier-import-file').setInputFiles(validos);
          await admin.locator('#supplier-import-submit').click();
          await expect(admin.locator('#supplier-import-summary')).toBeVisible();
          await expect(admin.locator('#supplier-import-summary-text')).toContainText('3 proveedores registrados');
          await expect(admin.locator('#supplier-import-errors')).toBeHidden();
          await hu.captura(admin, 'resumen-carga-exitosa', 'Resultado de la carga del archivo válido: 3 proveedores registrados, sin errores.');
          return `Resumen: "${await texto(admin, '#supplier-import-summary-text')}".`;
        },
      );
      await hu.paso(
        admin,
        'Consultar el catálogo filtrado por estatus "Registrado"',
        'Los 3 proveedores aparecen con estatus "Registrado" (sin acceso al portal), con su RFC o identificador fiscal y tipo de persona.',
        async () => {
          await admin.goto(`/suppliers?q=${encodeURIComponent(`${run}`)}&status=REGISTERED`);
          const filas = admin.locator('table tbody tr');
          for (const proveedor of proveedores) {
            const fila = filas.filter({ hasText: proveedor.razon_social });
            await expect(fila).toHaveCount(1);
            await expect(fila).toContainText(proveedor.rfc ?? (proveedor.id_fiscal as string));
            await expect(fila).toContainText(proveedor.correo);
            await expect(fila.locator('.status')).toHaveText('Registrado');
          }
          await hu.captura(admin, 'catalogo-registrados', `Catálogo filtrado (búsqueda "${run}", estatus Registrado) con los proveedores cargados.`);
          return `Encontrados ${proveedores.length} proveedores en "Registrado": ${proveedores.map((p) => `${p.razon_social} (${p.rfc ?? p.id_fiscal})`).join('; ')}.`;
        },
      );
      await hu.paso(
        admin,
        'Abrir el expediente del proveedor internacional',
        'El expediente muestra el origen Internacional, el identificador fiscal extranjero, el correo y el estatus "Registrado" (mapeo de columnas).',
        async () => {
          const internacional = proveedores.find((p) => p.id_fiscal) as (typeof proveedores)[number];
          await admin
            .locator('table tbody tr')
            .filter({ hasText: internacional.razon_social })
            .getByRole('link', { name: 'Ver expediente' })
            .click();
          await expect(admin.locator('h1')).toHaveText(internacional.razon_social);
          await expect(admin.locator('.page-heading p')).toContainText(`${internacional.id_fiscal} · Internacional · Persona Moral`);
          await expect(admin.locator('.page-heading .status')).toHaveText('Registrado');
          await expect(admin.locator('.data-list').first()).toContainText(internacional.correo);
          await hu.captura(admin, 'expediente-internacional', 'Expediente del proveedor internacional cargado: identificador, origen, tipo, correo y estatus.');
          return `Expediente: "${await texto(admin, '.page-heading p')}", estatus "${await texto(admin, '.page-heading .status')}", correo ${internacional.correo}.`;
        },
      );
      guardarDato('hu01.proveedores', proveedores);
    });
  });
});
