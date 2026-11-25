import { expect, test, type Page } from '@playwright/test';
import path from 'node:path';
import { buscarCorreo, demoPassword } from '../lib/estado';
import { CUENTAS } from '../lib/hu';
import { clicNavegando, enviarAValidacion, idDesdeUrl } from '../lib/portal';
import { APP_ROOT, EVIDENCIAS } from '../lib/rutas';
import {
  capaDeVideo,
  cerrarSesion,
  escribir,
  guardarVideo,
  iniciarSesion,
  loginKeycloak,
  menu,
  mostrarCorreo,
  senalar,
  subirDocumento,
  tarjeta,
} from './comun';

// Recorrido en video de la HU-24 (rama ferromex): la factura se registra con su PDF (y su XML, si lo hay), el portal
// lee sus datos y los valida junto a la imagen del PDF (Validacion 1), y al enviarla la valida contra la orden de compra
// de SAP (Validacion 2). Usa los documentos de data/pruebas-ferromex y la factura 3668 de data/demo_documents, con las
// ordenes 45000451, 45000452 y 25704872 que siembra la demo. Requiere una base recien reiniciada
// (scripts/reset_demo.py) y el portal con MAIL_BACKEND=file (ver tests/hu/README.md): los UUID de los CFDI son fijos y
// cada orden admite una sola factura vigente.

const VIDEO = path.join(EVIDENCIAS, 'video', 'recorrido-orden-compra.webm');
const DATOS = path.join(APP_ROOT, 'data', 'pruebas-ferromex');
const DEMO = path.join(APP_ROOT, 'data', 'demo_documents');
const A1001 = path.join(DATOS, '3-factura-observaciones-autorizada');
const A1002 = path.join(DATOS, '4-factura-rechazada');
const VOBO = 'Vo.Bo. del líder de proyecto';

const PROVEEDOR = {
  nombre: 'Héctor Garza Villarreal',
  rfc: 'GAVH810417Q42',
  // Dominio reservado (.example): el correo no le llega a nadie; el portal lo deja en el buzon de archivos.
  correo: 'contacto@hgarzavillarreal.example',
  telefono: '8183456712',
  web: 'https://www.hgarzavillarreal.example',
  banco: 'Banco Demo, S.A. - Cuenta 0457812396 - CLABE 000580004578123964',
  clave: 'Garza#Mty2026',
};

// Requisitos de alta con su archivo y la fecha impresa en el documento (DATOS-A-CAPTURAR.txt). La propuesta economica
// es obligatoria porque el alta es por cotizacion o licitacion.
const EXPEDIENTE: Record<string, [string, string]> = {
  'Cédula fiscal': ['Constancia-Situacion-Fiscal', '2026-11-17'],
  'Comprobante de domicilio': ['Comprobante-Domicilio', '2026-11-04'],
  'Estado de cuenta bancario': ['Estado-Cuenta-Bancario', '2026-10-31'],
  'Identificación oficial': ['Identificacion-Oficial', '2025-03-12'],
  'Propuesta económica': ['Propuesta-Economica', '2026-09-15'],
};

const OBSERVACIONES = 'El Vo.Bo. corresponde al periodo 09/2026; adjunte el Vo.Bo. del periodo 10/2026.';

const zonaDeCarga = (page: Page, id: string) => page.locator('label.dropzone').filter({ has: page.locator(`#${id}`) });

test('Recorrido: validación de la factura contra la orden de compra', async ({ page }) => {
  const clave = demoPassword();
  const rotular = await capaDeVideo(page);

  /** Paso 1 de la factura nacional: PDF obligatorio y XML opcional; deja la pagina en la Revision. */
  const registrarArchivos = async (etapa: string, pdf: string, xml?: string): Promise<number> => {
    await senalar(page, page.getByRole('link', { name: /Nueva factura/ }).first(), 1500);
    await clicNavegando(page, page.getByRole('link', { name: /Nueva factura/ }).first());
    await rotular(etapa, 'Paso 1 · Archivos: ya no se captura la factura; basta con su PDF y, si se tiene, su XML');
    await senalar(page, page.locator('.steps'), 2500);
    await rotular(etapa, `Archivo 1 de ${xml ? 2 : 1} · PDF de la factura (obligatorio)`);
    await page.locator('#pdf').setInputFiles(pdf);
    await senalar(page, zonaDeCarga(page, 'pdf'), 2500, false);
    if (xml) {
      await rotular(etapa, 'Archivo 2 de 2 · XML del CFDI (opcional): si se carga, los datos fiscales se toman del XML');
      await page.locator('#xml').setInputFiles(xml);
      await senalar(page, zonaDeCarga(page, 'xml'), 2500, false);
    } else {
      await rotular(etapa, 'Sin XML: el portal leerá los datos del texto del PDF');
      await senalar(page, zonaDeCarga(page, 'xml'), 3000, false);
    }
    await clicNavegando(page, page.getByRole('button', { name: /Continuar a la revisión/ }));
    await expect(page).toHaveURL(/\/invoices\/\d+\/data/);
    return idDesdeUrl(page);
  };

  /** Abre una factura desde el listado del usuario, filtrando por estatus y numero. */
  const abrirDesdeListado = async (numero: string, estatus?: string): Promise<void> => {
    await clicNavegando(page, menu(page, 'Facturas'));
    if (estatus) await page.locator('select[name=status]').selectOption(estatus);
    await escribir(page.locator('input[name=q]'), numero);
    await clicNavegando(page, page.getByRole('button', { name: 'Filtrar' }));
    const fila = page.locator('table tbody tr').filter({ hasText: numero }).first();
    await senalar(page, fila, 2000);
    await clicNavegando(page, fila.locator('a.icon-action'));
  };

  // Por el codigo exacto: con hasText, 'OC-001' tambien coincide con DOC-001 del grupo de documentos.
  const grupoOrdenCompra = () =>
    page.locator('#validations .rule-group').filter({ has: page.locator('summary strong', { hasText: /^OC-001$/ }) });

  /** Cierra la sesion desde el tablero; el rotulo ya no arrastra el texto del paso anterior. */
  const salir = async (etapa: string): Promise<void> => {
    await page.goto('/');
    await rotular(etapa, 'Cierra sesión');
    await cerrarSesion(page);
  };

  await tarjeta(page, 'Portal de Proveedores FERROMEX', 'Validación de la factura contra la orden de compra', [
    '1. Administrador: órdenes de compra y alta del proveedor',
    '2. Proveedor: primer acceso y registro de la factura A-1001',
    '3. Analista de cuentas por pagar: revisión contra la orden de compra y Observaciones',
    '4. Proveedor: corrige el Vo.Bo. y reenvía',
    '5. Analista de cuentas por pagar: autorización y programación del pago',
    '6. Proveedor: Complemento de Pago y una factura que no cuadra',
    '7. Factura 3668 registrada sólo con su PDF',
    '8. Analista de cuentas por pagar: consulta de las órdenes de compra',
  ], 8000);

  // ---------------------------------------------------------------- 1. Administrador: ordenes de compra y alta
  await tarjeta(page, 'Parte 1 de 8 · Administrador', 'Órdenes de compra y alta del proveedor', [
    'Las órdenes de compra de SAP ya están cargadas en el portal',
    'Alta del proveedor Héctor Garza Villarreal y su expediente',
    'Autorización y envío automático de credenciales',
  ]);
  await rotular('Administrador', 'Inicio de sesión del Administrador');
  await iniciarSesion(page, CUENTAS.admin, clave);
  await page.waitForTimeout(2000);
  await clicNavegando(page, menu(page, 'Órdenes de compra'));
  await rotular('Administrador · Órdenes de compra', 'Convenios de SAP: encabezado, partidas y entrada de mercancía');
  await senalar(page, page.locator('table thead'), 3000);
  await escribir(page.locator('input[name=q]'), PROVEEDOR.rfc);
  await clicNavegando(page, page.getByRole('button', { name: 'Buscar' }));
  await rotular('Administrador · Órdenes de compra', `El proveedor ${PROVEEDOR.rfc} tiene dos órdenes, aunque todavía no está dado de alta`);
  await senalar(page, page.locator('table tbody'), 3500);
  await clicNavegando(page, page.getByRole('link', { name: '45000451', exact: true }));
  await rotular('Administrador · Orden 45000451', 'Total de la orden y sus impuestos: contra ellos se validará la factura');
  await senalar(page, page.locator('.metadata-grid'), 3500);
  await rotular('Administrador · Orden 45000451', 'Partida con su precio y su entrada de mercancía (documento de material y fecha contable)');
  await senalar(page, page.locator('#items'), 4500);
  await rotular('Administrador · Orden 45000451', 'Todavía no tiene facturas ligadas');
  await senalar(page, page.locator('#invoices'), 2500);

  await clicNavegando(page, menu(page, 'Proveedores'));
  await rotular('Administrador · Proveedores', 'Alta del proveedor nacional, persona física');
  const alta = page.locator('details.admin-create');
  await alta.locator('summary').click();
  await senalar(page, alta, 1500);
  await page.locator('#supplier-origin').selectOption('NATIONAL');
  await escribir(page.locator('#supplier-business-name'), PROVEEDOR.nombre);
  await escribir(page.locator('#supplier-rfc'), PROVEEDOR.rfc);
  await page.locator('#supplier-type').selectOption('PERSONA_FISICA');
  await escribir(page.locator('#supplier-email'), PROVEEDOR.correo);
  await rotular('Administrador · Alta', 'El correo es el usuario del proveedor: ahí recibirá sus credenciales');
  await senalar(page, page.locator('#supplier-email'), 2000, false);
  await rotular('Administrador · Alta', 'Datos del proveedor: contacto, clasificación, actividad e información bancaria');
  await escribir(page.locator('#supplier-phone'), PROVEEDOR.telefono);
  await page.locator('#supplier-classification').selectOption({ label: 'Externo' });
  await page.locator('#supplier-main-activity').selectOption('54');
  await escribir(page.locator('#supplier-website'), PROVEEDOR.web);
  await escribir(page.locator('#supplier-contact-name'), PROVEEDOR.nombre);
  await escribir(page.locator('#supplier-contact-phone'), PROVEEDOR.telefono);
  await escribir(page.locator('#supplier-bank-information'), PROVEEDOR.banco);
  await page.locator('#supplier-confidentiality').check();
  await page.locator('#supplier-economic-proposal').check();
  await senalar(page, page.getByRole('button', { name: 'Crear proveedor' }), 1500);
  await clicNavegando(page, page.getByRole('button', { name: 'Crear proveedor' }));
  await expect(page).toHaveURL(/\/suppliers\/\d+/);
  await rotular('Administrador · Expediente', 'El proveedor queda "Registrado": faltan sus requisitos de alta');
  await senalar(page, page.locator('.requirements-summary'), 3000);
  const pendientes = (
    await page.locator('.requirements-panel .document-row').filter({ hasText: 'Obligatorio · Pendiente' }).locator('strong').allInnerTexts()
  ).map((nombre) => nombre.trim()).filter((nombre) => nombre in EXPEDIENTE);
  for (const [i, nombre] of pendientes.entries()) {
    const [archivo, fecha] = EXPEDIENTE[nombre];
    await rotular('Administrador · Expediente', `Requisito ${i + 1} de ${pendientes.length}: ${nombre}, con la fecha del documento`);
    const formulario = page.locator('details.admin-create').filter({ hasText: 'Agregar o reemplazar documento del expediente' });
    if (!(await formulario.evaluate((el) => (el as HTMLDetailsElement).open))) await formulario.locator('summary').click();
    await senalar(page, formulario, 900);
    await formulario.locator('#supplier-document-type').selectOption({ label: `${nombre} (obligatorio)` });
    await formulario.locator('input[name=document_date]').fill(fecha);
    await formulario.locator('input[name=upload]').setInputFiles(path.join(DATOS, '1-proveedor', `${archivo}-${PROVEEDOR.rfc}.pdf`));
    await senalar(page, formulario.locator('input[name=upload]'), 1400, false);
    await clicNavegando(page, formulario.getByRole('button', { name: 'Guardar documento' }));
    await senalar(page, page.locator('.requirements-panel .document-row').filter({ hasText: nombre }), 1500);
  }
  await expect(page.locator('.requirements-summary')).toHaveText('Requisitos de alta completos');
  await rotular('Administrador · Expediente', 'Requisitos de alta completos: ya se puede autorizar');
  await senalar(page, page.locator('.requirements-summary'), 2500);
  await senalar(page, page.locator('#authorize-submit'), 1500);
  await page.locator('#authorize-submit').click();
  await expect(page.locator('#authorize-confirm')).toBeVisible();
  await rotular('Administrador · Autorización', 'Al confirmar, el proveedor recibe por correo su usuario y una contraseña temporal');
  await page.waitForTimeout(3000);
  const desdeAlta = new Date(Date.now() - 2000).toISOString();
  await Promise.all([page.waitForURL(/\/suppliers\?authorization=/), page.locator('#authorize-confirm-accept').click()]);
  await expect(page.locator('.authorization-summary .panel-header p')).toHaveText('1 autorizados · 0 omitidos · 0 no autorizados');
  await rotular('Administrador · Autorización', 'Proveedor "Autorizado"');
  await senalar(page, page.locator('.authorization-summary'), 3000);
  const credenciales = buscarCorreo(PROVEEDOR.correo, 'Acceso al Portal de Proveedores FERROMEX', desdeAlta);
  const temporal = credenciales?.texto.match(/Contraseña temporal: (\S+)/)?.[1];
  if (!credenciales || !temporal) throw new Error(`No se generó el correo de credenciales de ${PROVEEDOR.correo}`);
  await mostrarCorreo(page, `Correo que recibe ${PROVEEDOR.nombre}`, credenciales);
  await salir('Administrador');

  // ---------------------------------------------------------------- 2. Proveedor: primer acceso y A-1001
  await tarjeta(page, 'Parte 2 de 8 · Proveedor', 'Primer acceso y registro de la factura A-1001', [
    'Cambio obligatorio de la contraseña temporal',
    'Paso 1 · Archivos: PDF y XML de la factura',
    'Paso 2 · Revisión: datos leídos junto a la imagen del PDF',
    'Paso 3 · Envío: validación contra la orden de compra 45000451',
  ]);
  await rotular('Proveedor', `Primer acceso de ${PROVEEDOR.correo} con la contraseña temporal del correo`);
  await loginKeycloak(page, PROVEEDOR.correo, temporal);
  await expect(page).toHaveURL(/required-action\?execution=UPDATE_PASSWORD/);
  await rotular('Proveedor', 'Keycloak pide definir una contraseña propia antes de entrar');
  await page.waitForTimeout(2500);
  await escribir(page.locator('#password-new'), PROVEEDOR.clave);
  await escribir(page.locator('#password-confirm'), PROVEEDOR.clave);
  await page.locator('#kc-submit').click();
  await expect(page.locator('.sidebar-footer')).toContainText(PROVEEDOR.correo);
  await rotular('Proveedor', 'Tablero del proveedor');
  await page.waitForTimeout(2500);

  const idA = await registrarArchivos(
    'Proveedor · Factura A-1001',
    path.join(A1001, `CFDI-A1001-${PROVEEDOR.rfc}.pdf`),
    path.join(A1001, `CFDI-A1001-${PROVEEDOR.rfc}.xml`),
  );
  await rotular('Proveedor · Revisión', 'Paso 2 · Revisión: la imagen de la factura junto a los datos que leyó el portal');
  await senalar(page, page.locator('.review-pages'), 4000);
  await senalar(page, page.locator('.review-source'), 2000);
  await rotular('Proveedor · Revisión', 'Validación 1: el emisor coincide con el proveedor (RFC, nombre y régimen fiscal)');
  await senalar(page, page.locator('#supplier-data'), 3500);
  await rotular('Proveedor · Revisión', 'El receptor coincide con FERROMEX: RFC, nombre, régimen, uso de CFDI y código postal');
  await senalar(page, page.locator('#client-data'), 3500);
  await rotular('Proveedor · Revisión', 'La orden de compra se detecta en el concepto: «OC/45000451»');
  await senalar(page, page.locator('#concepts'), 4000);
  await senalar(page, page.locator('#totals'), 2000);
  await rotular('Proveedor · Revisión', `Se carga el ${VOBO}`);
  await subirDocumento(page, 'APPROVAL', path.join(A1001, 'VoBo-A1001-v1-con-error-periodo-09-2026.pdf'), VOBO);
  await expect(page.locator('.required-summary')).toContainText('Archivos obligatorios completos');
  await rotular('Proveedor · Envío', 'Paso 3 · Al enviar, el portal valida la factura contra su orden de compra');
  await senalar(page, page.locator('.next-action'), 2500);
  await enviarAValidacion(page);
  await expect(page.locator('.page-heading .status')).toHaveText('Enviada');
  await rotular('Proveedor · Envío', 'Factura "Enviada" y ligada a la orden de compra 45000451');
  await senalar(page, page.locator('.page-heading'), 2000);
  await senalar(page, page.locator('#purchase-order-number'), 2500);
  await rotular('Proveedor · Validación 2', 'Reglas de la orden de compra: proveedor, montos, partidas y entrada de mercancía, todas correctas');
  await senalar(page, grupoOrdenCompra(), 5000);
  await salir('Proveedor');

  // ---------------------------------------------------------------- 3. Analista de cuentas por pagar: revision y Observaciones
  await tarjeta(page, 'Parte 3 de 8 · Analista CxP', 'Revisión contra la orden de compra y Observaciones', [
    'Detalle de la factura con su orden de compra y sus partidas',
    'Revisión del Vo.Bo.: cita el periodo 09/2026, no el 10/2026 del servicio',
    'Observaciones con aviso por correo al proveedor',
  ]);
  await rotular('Analista CxP', 'Inicia sesión el analista de cuentas por pagar');
  await iniciarSesion(page, CUENTAS.pmo, clave);
  await rotular('Analista CxP · Facturas', 'Facturas "Enviada", pendientes de decisión');
  await abrirDesdeListado('A-1001', 'UNDER_REVIEW');
  await rotular('Analista CxP · Detalle', 'La factura muestra la orden de compra contra la que se validó, con sus partidas');
  await senalar(page, page.locator('#purchase-order'), 4500);
  await senalar(page, grupoOrdenCompra(), 3000);
  const verVobo = await page.locator(`a[aria-label="Ver ${VOBO}"]`).first().getAttribute('href');
  await rotular('Analista CxP · Vo.Bo.', 'El analista de cuentas por pagar abre el Vo.Bo.: cita el periodo 09/2026, pero el servicio facturado es de 10/2026');
  await page.goto(verVobo as string);
  await senalar(page, page.locator('.document-viewer'), 6000, false);
  await page.goto(`/invoices/${idA}#decision`);
  await rotular('Analista CxP · Decisión', 'Observaciones: la factura regresa al proveedor con la causa');
  const decision = page.locator('#decision');
  await senalar(page, decision, 2000);
  await decision.getByRole('button', { name: 'Observaciones' }).click();
  await escribir(page.locator('#observations'), OBSERVACIONES);
  await page.waitForTimeout(1500);
  const desdeObservaciones = new Date(Date.now() - 2000).toISOString();
  await clicNavegando(page, decision.getByRole('button', { name: 'Observaciones' }));
  await expect(page.locator('.page-heading .status')).toHaveText('Observaciones');
  await rotular('Analista CxP · Decisión', 'Factura en "Observaciones": se avisa al proveedor por correo');
  await senalar(page, page.locator('#decision-result'), 3000);
  const conObservaciones = buscarCorreo(PROVEEDOR.correo, 'Factura A-1001 con observaciones', desdeObservaciones);
  if (conObservaciones) await mostrarCorreo(page, 'Correo al proveedor con las observaciones del analista de cuentas por pagar', conObservaciones);
  await salir('Analista CxP');

  // ---------------------------------------------------------------- 4. Proveedor: corrige y reenvia
  await tarjeta(page, 'Parte 4 de 8 · Proveedor', 'Corrección del Vo.Bo. y reenvío', [
    'Observaciones del analista de cuentas por pagar en el detalle de la factura',
    'Reemplazo del Vo.Bo. por el del periodo correcto',
    'Reenvío: se vuelve a validar contra la orden de compra',
  ]);
  await rotular('Proveedor', 'Inicia sesión el proveedor con su propia contraseña');
  await iniciarSesion(page, PROVEEDOR.correo, PROVEEDOR.clave);
  await abrirDesdeListado('A-1001');
  await rotular('Proveedor · Observaciones', 'El detalle muestra las observaciones del analista de cuentas por pagar');
  await senalar(page, page.locator('#decision-cause'), 4000);
  await senalar(page, page.getByRole('link', { name: /Revisión/ }).first(), 1500, false);
  await clicNavegando(page, page.getByRole('link', { name: /Revisión/ }).first());
  await rotular('Proveedor · Corrección', 'Se reemplaza el Vo.Bo. por el del periodo 10/2026');
  await subirDocumento(page, 'APPROVAL', path.join(A1001, 'VoBo-A1001-v2-corregido.pdf'), VOBO);
  await expect(page.locator('.document-row').filter({ hasText: VOBO })).toContainText('VoBo-A1001-v2-corregido.pdf');
  await enviarAValidacion(page);
  await expect(page.locator('.page-heading .status')).toHaveText('Enviada');
  await rotular('Proveedor · Reenvío', 'La factura vuelve a "Enviada" con el Vo.Bo. corregido');
  await senalar(page, page.locator('.page-heading'), 3000);
  await salir('Proveedor');

  // ---------------------------------------------------------------- 5. Analista de cuentas por pagar: autorizacion y pago
  await tarjeta(page, 'Parte 5 de 8 · Analista CxP', 'Autorización y programación del pago', [
    'Autorización con aviso a Recepción de Facturas y copia al proveedor',
    'Programación del pago (JSON) y aviso del Complemento de Pago',
  ]);
  await rotular('Analista CxP', 'Inicia sesión el analista de cuentas por pagar');
  await iniciarSesion(page, CUENTAS.pmo, clave);
  await abrirDesdeListado('A-1001', 'UNDER_REVIEW');
  await rotular('Analista CxP · Detalle', 'El Vo.Bo. ya es el del periodo correcto');
  await senalar(page, page.locator('.document-list'), 3000);
  await page.goto(`/invoices/${idA}#decision`);
  await rotular('Analista CxP · Decisión', 'El analista de cuentas por pagar autoriza la factura para su pago');
  await page.locator('#decision').getByRole('button', { name: 'Autorizar' }).click();
  await expect(page.locator('#decision-confirm')).toBeVisible();
  await page.waitForTimeout(2500);
  const desdeAutorizada = new Date(Date.now() - 2000).toISOString();
  await clicNavegando(page, page.locator('#decision-confirm-accept'));
  await expect(page.locator('.page-heading .status')).toHaveText('Autorizada');
  await rotular('Analista CxP · Decisión', 'Factura "Autorizada": se notifica a Recepción de Facturas con copia al proveedor');
  await senalar(page, page.locator('#decision-result'), 3500);
  const recepcion = ((await page.locator('#decision-result').innerText()).match(/[\w.+-]+@[\w.-]+\.\w+/g) ?? [])[0];
  const autorizada = recepcion ? buscarCorreo(recepcion, 'Factura A-1001 autorizada para pago', desdeAutorizada) : null;
  if (autorizada) await mostrarCorreo(page, 'Correo a Recepción de Facturas (Cc: proveedor)', autorizada);
  await page.goto(`/invoices/${idA}`);
  await rotular('Analista CxP · Pago', 'Programar pago: la solicitud en JSON y su confirmación');
  await page.locator('.page-heading').getByRole('button', { name: /Programar pago/ }).click();
  await expect(page.locator('#payment')).toBeVisible();
  await senalar(page, page.locator('#payment .modal-content'), 4000);
  await page.waitForTimeout(1200);
  const desdePagada = new Date(Date.now() - 2000).toISOString();
  await clicNavegando(page, page.locator('#payment').getByRole('button', { name: /Confirmar y programar pago/ }));
  await expect(page.locator('.page-heading .status')).toHaveText('Programado para pago');
  await rotular('Analista CxP · Pago', 'Factura "Programado para pago": el proveedor tiene 72 horas para adjuntar el Complemento de Pago');
  await senalar(page, page.locator('#complement'), 3000);
  const pagada = buscarCorreo(PROVEEDOR.correo, 'Factura A-1001 programada para pago', desdePagada);
  if (pagada) await mostrarCorreo(page, 'Correo al proveedor: pago programado y aviso del Complemento de Pago', pagada);
  await salir('Analista CxP');

  // ---------------------------------------------------------------- 6. Proveedor: complemento y A-1002
  await tarjeta(page, 'Parte 6 de 8 · Proveedor', 'Complemento de Pago y una factura que no cuadra', [
    'Carga del Complemento de Pago de la factura A-1001',
    'Factura A-1002 por 52,000.00 contra la orden 45000452 de 45,000.00',
    'El envío no procede: el portal lista las diferencias',
  ]);
  await rotular('Proveedor', 'Inicia sesión el proveedor');
  await iniciarSesion(page, PROVEEDOR.correo, PROVEEDOR.clave);
  await rotular('Proveedor', 'El tablero avisa del Complemento de Pago pendiente y su fecha límite');
  await senalar(page, page.locator('#pending-complements'), 3500);
  await clicNavegando(page, page.locator('#pending-complements').getByRole('link', { name: 'Factura A-1001' }));
  await rotular('Proveedor · Complemento', 'Se carga el XML del Complemento de Pago, que relaciona el UUID de A-1001');
  await subirDocumento(page, 'PAYMENT_COMPLEMENT_XML', path.join(A1001, `REP-P1001-${PROVEEDOR.rfc}.xml`), 'Complemento de pago (XML)', false);
  await expect(page.locator('#complement-result')).toHaveText('Se notificó a Recepción de Facturas.');
  await rotular('Proveedor · Complemento', 'Complemento adjuntado: el portal avisa a Recepción de Facturas');
  await senalar(page, page.locator('#complement-result'), 3000);
  await page.goto('/');

  const idB = await registrarArchivos(
    'Proveedor · Factura A-1002',
    path.join(A1002, `CFDI-A1002-${PROVEEDOR.rfc}.pdf`),
    path.join(A1002, `CFDI-A1002-${PROVEEDOR.rfc}.xml`),
  );
  await rotular('Proveedor · Revisión', 'Los datos del proveedor y del cliente son correctos; la orden detectada es la 45000452');
  await senalar(page, page.locator('.review-pages'), 2500);
  await senalar(page, page.locator('#concepts'), 3500);
  await rotular('Proveedor · Revisión', 'La factura es por 52,000.00 + IVA, pero la orden de compra es por 45,000.00 + IVA');
  await senalar(page, page.locator('#totals'), 3500);
  await rotular('Proveedor · Revisión', `Se carga el ${VOBO}`);
  await subirDocumento(page, 'APPROVAL', path.join(A1002, 'VoBo-A1002.pdf'), VOBO);
  await rotular('Proveedor · Envío', 'Se envía a validación');
  await enviarAValidacion(page);
  await expect(page.locator('.alert-danger').filter({ hasText: 'El envío no procedió' })).toBeVisible();
  await expect(page.locator('#blocking')).toContainText('OC-005');
  await rotular('Proveedor · Envío', 'El envío no procede: la factura no cuadra con su orden de compra');
  await senalar(page, page.locator('.alert-danger').filter({ hasText: 'El envío no procedió' }), 2500);
  await rotular('Proveedor · Envío', 'Subtotal, IVA e importe del concepto distintos de la orden 45000452');
  await senalar(page, page.locator('#blocking'), 6000);
  await page.goto(`/invoices/${idB}`);
  await rotular('Proveedor · Envío', 'La factura sigue "Cargada": no llega al analista de cuentas por pagar hasta que cuadre con su orden');
  await senalar(page, page.locator('.page-heading .status'), 3000);
  await salir('Proveedor');

  // ---------------------------------------------------------------- 7. Factura 3668 solo con PDF
  await tarjeta(page, 'Parte 7 de 8 · Proveedor', 'Factura 3668 registrada sólo con su PDF', [
    'SOCORRO PATRICIA GONZALEZ HERNANDEZ, persona física',
    'Sin XML: el portal lee los datos del texto del PDF',
    'Validación contra la orden de compra 25704872',
  ]);
  await rotular('Proveedor', 'Inicia sesión otra proveedora del portal');
  await iniciarSesion(page, CUENTAS.proveedor2, clave);
  await page.waitForTimeout(1500);
  await registrarArchivos('Proveedor · Factura 3668', path.join(DEMO, 'factura_3668.pdf'));
  await rotular('Proveedor · Revisión', 'Datos tomados del texto del PDF');
  await senalar(page, page.locator('.review-source'), 2500);
  await senalar(page, page.locator('.review-pages'), 3500);
  await rotular('Proveedor · Revisión', 'UUID, moneda, forma y método de pago leídos del PDF');
  await senalar(page, page.locator('.review-data .panel').first(), 3500);
  await rotular('Proveedor · Revisión', 'Emisor y receptor validados también sin XML');
  await senalar(page, page.locator('#supplier-data'), 2500);
  await senalar(page, page.locator('#client-data'), 2500);
  await rotular('Proveedor · Revisión', 'Concepto «LTH TIPO L-31T-900 AR BATERIA (OC/25704872)»: orden de compra 25704872');
  await senalar(page, page.locator('#concepts'), 4000);
  await rotular('Proveedor · Revisión', `Se carga el ${VOBO}`);
  await subirDocumento(page, 'APPROVAL', path.join(DEMO, 'vobo_demo.txt'), VOBO);
  await enviarAValidacion(page);
  await expect(page.locator('.page-heading .status')).toHaveText('Enviada');
  await rotular('Proveedor · Envío', 'Factura "Enviada" y ligada a la orden 25704872');
  await senalar(page, page.locator('#purchase-order-number'), 2500);
  await rotular('Proveedor · Validación 2', 'Las reglas de la orden de compra salen correctas con los datos del PDF');
  await senalar(page, grupoOrdenCompra(), 5000);
  await salir('Proveedor');

  // ---------------------------------------------------------------- 8. Analista de cuentas por pagar: ordenes de compra
  await tarjeta(page, 'Parte 8 de 8 · Analista CxP', 'Consulta de las órdenes de compra', [
    'Cada orden muestra las facturas ligadas y su estatus',
    'Una orden admite una sola factura vigente',
  ]);
  await rotular('Analista CxP', 'Inicia sesión el analista de cuentas por pagar');
  await iniciarSesion(page, CUENTAS.pmo, clave);
  await clicNavegando(page, menu(page, 'Órdenes de compra'));
  await rotular('Analista CxP · Órdenes de compra', 'La columna Facturas cuenta las facturas ligadas a cada orden');
  await senalar(page, page.locator('table'), 3500);
  await clicNavegando(page, page.getByRole('link', { name: '45000451', exact: true }));
  await rotular('Analista CxP · Orden 45000451', 'La factura A-1001 quedó ligada a su orden y ya está "Programado para pago"');
  await senalar(page, page.locator('#invoices'), 4000);
  await clicNavegando(page, menu(page, 'Órdenes de compra'));
  await clicNavegando(page, page.getByRole('link', { name: '25704872', exact: true }));
  await rotular('Analista CxP · Orden 25704872', 'La factura 3668, registrada sólo con su PDF, está ligada y "Enviada"');
  await senalar(page, page.locator('#items'), 3000);
  await senalar(page, page.locator('#invoices'), 4000);
  await salir('Analista CxP');

  await tarjeta(page, 'Portal de Proveedores FERROMEX', 'Fin del recorrido', [
    'Factura A-1001: registrada por sus archivos, con Observaciones, autorizada, programada para pago y con su Complemento de Pago',
    'Factura A-1002: el envío no procede porque no cuadra con su orden de compra',
    'Factura 3668: registrada sólo con su PDF y validada contra la orden 25704872',
  ], 7000);

  await guardarVideo(page, VIDEO);
});
