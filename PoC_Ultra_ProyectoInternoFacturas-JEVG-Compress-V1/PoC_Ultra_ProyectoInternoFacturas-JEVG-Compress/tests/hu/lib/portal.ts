import { expect, type Locator, type Page } from '@playwright/test';

/** Pulsa un control que envia un formulario y espera a que cargue la pagina de respuesta (no la actual). */
export async function clicNavegando(page: Page, control: Locator): Promise<void> {
  const navegacion = page.waitForEvent('framenavigated', (frame) => frame === page.mainFrame());
  await control.click();
  await navegacion;
  await page.waitForLoadState('load');
}

/** Texto normalizado (espacios colapsados) de un locator o de la pagina. */
export async function texto(page: Page, selector: string): Promise<string> {
  return ((await page.locator(selector).first().innerText()) ?? '').replace(/\s+/g, ' ').trim();
}

/** Estatus que muestra el encabezado del detalle de una factura. */
export async function estatusFactura(page: Page, facturaId: number): Promise<string> {
  await page.goto(`/invoices/${facturaId}`);
  return texto(page, '.page-heading .status');
}

export async function idDesdeUrl(page: Page): Promise<number> {
  const coincidencia = page.url().match(/\/invoices\/(\d+)/);
  if (!coincidencia) throw new Error(`La URL no es de una factura: ${page.url()}`);
  return Number(coincidencia[1]);
}

/** Paso 1 del alta (HU-12/HU-15): llena el formulario y deja la pagina en la carga documental. El total del Invoice
 * no se captura: la pagina lo calcula (subtotal + impuestos) y el servidor lo vuelve a calcular. */
export async function llenarAltaFactura(
  page: Page,
  datos: { numero: string; periodo?: string; ordenCompra?: string; invoice?: { fecha: string; moneda: string; subtotal: string; impuestos: string } },
): Promise<void> {
  await page.locator('input[name=invoice_number]').fill(datos.numero);
  await page.locator('input[name=service_period]').fill(datos.periodo ?? '08/2026');
  await page.locator('input[name=purchase_order_number]').fill(datos.ordenCompra ?? `OC-${datos.numero}`);
  if (datos.invoice) {
    await page.locator('#invoice_date').fill(datos.invoice.fecha);
    await page.locator('#currency').selectOption(datos.invoice.moneda);
    await page.locator('#subtotal').fill(datos.invoice.subtotal);
    await page.locator('#tax').fill(datos.invoice.impuestos);
  }
}

export async function enviarAlta(page: Page): Promise<number> {
  await page.getByRole('button', { name: /Continuar a documentos/ }).click();
  await page.waitForURL(/\/invoices\/\d+\/documents/);
  return idDesdeUrl(page);
}

/** Carga un documento en la carga documental (HU-04/HU-12/HU-15) y espera la respuesta del servidor. */
export async function cargarDocumento(page: Page, tipo: string, archivo: string): Promise<void> {
  await page.locator('#document_type').selectOption(tipo);
  await page.locator('form.upload-form input[name=upload]').setInputFiles(archivo);
  await clicNavegando(page, page.getByRole('button', { name: 'Cargar documento' }));
}

/** Abre el expediente de un proveedor buscandolo por su razon social en el listado; devuelve su id. */
export async function abrirExpediente(page: Page, razonSocial: string): Promise<number> {
  await page.goto(`/suppliers?q=${encodeURIComponent(razonSocial)}`);
  const fila = page.locator('table tbody tr').filter({ hasText: razonSocial }).first();
  await clicNavegando(page, fila.locator('a[aria-label="Ver expediente"]'));
  const coincidencia = page.url().match(/\/suppliers\/(\d+)/);
  if (!coincidencia) throw new Error(`La URL no es de un expediente: ${page.url()}`);
  return Number(coincidencia[1]);
}

/** Carga desde el expediente abierto un archivo por cada requisito de alta obligatorio pendiente (HU-21). */
export async function cargarRequisitosAlta(page: Page, archivo: string): Promise<string[]> {
  const pendientes = (
    await page
      .locator('.requirements-panel .document-row')
      .filter({ hasText: 'Obligatorio · Pendiente' })
      .locator('strong')
      .allInnerTexts()
  ).map((nombre) => nombre.trim());
  for (const nombre of pendientes) {
    const formulario = page.locator('details.admin-create').filter({ hasText: 'Agregar o reemplazar documento del expediente' });
    if (!(await formulario.evaluate((el) => (el as HTMLDetailsElement).open))) await formulario.locator('summary').click();
    await formulario.locator('#supplier-document-type').selectOption({ label: `${nombre} (obligatorio)` });
    await formulario.locator('input[name=upload]').setInputFiles(archivo);
    await clicNavegando(page, formulario.getByRole('button', { name: 'Guardar documento' }));
  }
  return pendientes;
}

export async function resumenObligatorios(page: Page): Promise<string> {
  return texto(page, '.required-summary');
}

/** Pulsa "Enviar a validación" en el detalle o la carga documental. */
export async function enviarAValidacion(page: Page): Promise<void> {
  await clicNavegando(page, page.getByRole('button', { name: /Enviar a validación/ }).first());
}

export interface ResultadoRegla {
  estado: string;
  mensaje: string;
  esperado: string;
  detectado: string;
}

/** Resultado de una regla en la "Matriz de evidencia" del detalle de la factura. */
export async function resultadoRegla(page: Page, codigo: string): Promise<ResultadoRegla> {
  const tarjeta = page
    .locator('#validations details.rule-card')
    .filter({ has: page.locator('summary strong', { hasText: new RegExp(`^${codigo}$`) }) })
    .first();
  await expect(tarjeta, `La regla ${codigo} no aparece en la matriz de evidencia`).toHaveCount(1);
  const valores = await tarjeta.locator('.evidence-grid strong').allTextContents();
  return {
    estado: (await tarjeta.locator('.rule-result').innerText()).trim(),
    mensaje: (await tarjeta.locator('.rule-message').innerText()).trim(),
    esperado: (valores[0] ?? '').trim(),
    detectado: (valores[1] ?? '').trim(),
  };
}

/** Abre el detalle de una factura buscandola por su numero en el listado del usuario. */
export async function abrirFactura(page: Page, numero: string): Promise<number> {
  await page.goto(`/invoices?status=&q=${encodeURIComponent(numero)}`);
  await page.locator('table tbody tr').filter({ hasText: numero }).first().locator('a.icon-action').click();
  await page.waitForURL(/\/invoices\/\d+$/);
  return idDesdeUrl(page);
}

/** "Verificar" (proveedor): ejecuta el motor y vuelve al detalle. */
export async function verificar(page: Page): Promise<void> {
  await clicNavegando(page, page.getByRole('button', { name: /Verificar/ }).first());
  await expect(page.locator('#validations')).toBeVisible();
}

/** Registra una factura nacional y carga sus 4 obligatorios (XML, PDF, orden de compra y Vo.Bo.). */
export async function registrarFacturaNacional(
  page: Page,
  numero: string,
  archivos: { xml: string; pdf: string; ordenCompra: string; vobo: string },
): Promise<number> {
  await page.goto('/invoices/new');
  await llenarAltaFactura(page, { numero });
  const id = await enviarAlta(page);
  await cargarDocumento(page, 'INVOICE_XML', archivos.xml);
  await cargarDocumento(page, 'INVOICE_PDF', archivos.pdf);
  await cargarDocumento(page, 'PURCHASE_ORDER', archivos.ordenCompra);
  await cargarDocumento(page, 'APPROVAL', archivos.vobo);
  await expect(page.locator('.required-summary')).toContainText('Archivos obligatorios completos');
  return id;
}
