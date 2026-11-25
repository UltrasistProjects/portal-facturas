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
  menu,
  mostrarCorreo,
  senalar,
  subirDocumento,
  tarjeta,
} from './comun';

// Recorrido en video de la factura 3668 del documento de negocio (HU-24), como lo describe
// data/pruebas-factura-3668/INSTRUCTIVO.md: la proveedora SOCORRO PATRICIA GONZALEZ HERNANDEZ (cuenta demo
// proveedor2@poc.local) la registra solo con su PDF, el analista de cuentas por pagar la devuelve con Observaciones por el Vo.Bo., la proveedora
// corrige y reenvia, el analista de cuentas por pagar autoriza, el Administrador registra el pago y la proveedora adjunta el Complemento de Pago.
// Requiere una base recien reiniciada (scripts/reset_demo.py: el UUID de la 3668 es fijo y su orden admite una sola
// factura vigente) y el portal con MAIL_BACKEND=file y MAIL_FROM (ver tests/hu/README.md).

const VIDEO = path.join(EVIDENCIAS, 'video', 'recorrido-factura-3668.webm');
const SET = path.join(APP_ROOT, 'data', 'pruebas-factura-3668');
const FACTURA = path.join(SET, '1-factura');
const PAGO = path.join(SET, '2-pago');
const NUMERO = '3668';
const ORDEN = '25704872';
const VOBO = 'Vo.Bo. del líder de proyecto';
const PROVEEDORA = { correo: CUENTAS.proveedor2, nombre: 'SOCORRO PATRICIA GONZALEZ HERNANDEZ' };
const OBSERVACIONES = 'El Vo.Bo. cita la orden de compra 25704827; la factura es de la 25704872. Adjunte el Vo.Bo. corregido.';

const zonaDeCarga = (page: Page, id: string) => page.locator('label.dropzone').filter({ has: page.locator(`#${id}`) });

test('Recorrido: flujo completo de la factura 3668', async ({ page }) => {
  const clave = demoPassword();
  const rotular = await capaDeVideo(page);

  /** Abre la factura 3668 desde el listado del usuario, filtrando por estatus si se indica. */
  const abrirFactura = async (estatus?: string): Promise<void> => {
    await clicNavegando(page, menu(page, 'Facturas'));
    if (estatus) await page.locator('select[name=status]').selectOption(estatus);
    await escribir(page.locator('input[name=q]'), NUMERO);
    await clicNavegando(page, page.getByRole('button', { name: 'Filtrar' }));
    const fila = page.locator('table tbody tr').filter({ hasText: NUMERO }).first();
    await senalar(page, fila, 2000);
    await clicNavegando(page, fila.locator('a.icon-action'));
  };

  /** Abre la orden 25704872 desde el menu Órdenes de compra. */
  const abrirOrden = async (): Promise<void> => {
    await clicNavegando(page, menu(page, 'Órdenes de compra'));
    await escribir(page.locator('input[name=q]'), ORDEN);
    await clicNavegando(page, page.getByRole('button', { name: 'Buscar' }));
    await senalar(page, page.locator('table tbody'), 2500);
    await clicNavegando(page, page.getByRole('link', { name: ORDEN, exact: true }));
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

  await tarjeta(page, 'Portal de Proveedores FERROMEX', 'Factura 3668: de la carga del PDF al Complemento de Pago', [
    '1. Administrador: la orden de compra 25704872 de SAP',
    '2. Proveedora: registro de la factura sólo con su PDF',
    '3. Analista de cuentas por pagar: revisión contra la orden de compra y Observaciones',
    '4. Proveedora: corrige el Vo.Bo. y reenvía',
    '5. Analista de cuentas por pagar: autorización',
    '6. Administrador: programación del pago',
    '7. Proveedora: Complemento de Pago',
    '8. Analista de cuentas por pagar: la orden de compra con su factura programada para pago',
  ], 8000);

  // ---------------------------------------------------------------- 1. Administrador: la orden de compra
  await tarjeta(page, 'Parte 1 de 8 · Administrador', 'La orden de compra 25704872 de SAP', [
    'Las órdenes de compra llegan de SAP: en el portal no se capturan',
    'Encabezado: proveedora, total e impuestos',
    'Partida con su entrada de mercancía',
  ]);
  await rotular('Administrador', 'Inicio de sesión del Administrador');
  await iniciarSesion(page, CUENTAS.admin, clave);
  await page.waitForTimeout(1500);
  await rotular('Administrador · Órdenes de compra', `Búsqueda del convenio ${ORDEN}`);
  await abrirOrden();
  await rotular('Administrador · Orden 25704872', `Orden de ${PROVEEDORA.nombre}: total $3,559.05 e impuestos $569.45`);
  await senalar(page, page.locator('.metadata-grid'), 4000);
  await rotular('Administrador · Orden 25704872', 'Partida «LTH TIPO L-31 T-900 AR», 1 PZA, con entrada de mercancía (documento de material y fecha contable)');
  await senalar(page, page.locator('#items'), 5000);
  await rotular('Administrador · Orden 25704872', 'Todavía no tiene facturas ligadas');
  await senalar(page, page.locator('#invoices'), 2500);
  await salir('Administrador');

  // ---------------------------------------------------------------- 2. Proveedora: registro solo con el PDF
  await tarjeta(page, 'Parte 2 de 8 · Proveedora', 'Registro de la factura 3668 sólo con su PDF', [
    `${PROVEEDORA.nombre}, persona física`,
    'Paso 1 · Archivos: sólo el PDF, sin XML',
    'Paso 2 · Revisión: los datos que leyó el portal junto a la imagen del PDF',
    'Paso 3 · Envío: validación contra la orden de compra 25704872',
  ]);
  await rotular('Proveedora', 'Inicia sesión la proveedora');
  await iniciarSesion(page, PROVEEDORA.correo, clave);
  await page.waitForTimeout(1500);
  await senalar(page, page.getByRole('link', { name: /Nueva factura/ }).first(), 1500);
  await clicNavegando(page, page.getByRole('link', { name: /Nueva factura/ }).first());
  await rotular('Proveedora · Factura 3668', 'Paso 1 · Archivos: la factura no se captura, se carga su PDF');
  await senalar(page, page.locator('.steps'), 2500);
  await rotular('Proveedora · Factura 3668', 'PDF de la factura 3668, tal como lo emitió la proveedora');
  await page.locator('#pdf').setInputFiles(path.join(FACTURA, `CFDI-${NUMERO}-GOHS60031745A.pdf`));
  await senalar(page, zonaDeCarga(page, 'pdf'), 2500, false);
  await rotular('Proveedora · Factura 3668', 'Sin XML: el portal leerá los datos del texto del PDF');
  await senalar(page, zonaDeCarga(page, 'xml'), 3000, false);
  await clicNavegando(page, page.getByRole('button', { name: /Continuar a la revisión/ }));
  await expect(page).toHaveURL(/\/invoices\/\d+\/data/);
  const id = await idDesdeUrl(page);

  await rotular('Proveedora · Revisión', 'Paso 2 · Revisión: la imagen de la factura junto a los datos que leyó el portal');
  await senalar(page, page.locator('.review-pages'), 5000);
  await rotular('Proveedora · Revisión', 'Datos tomados del texto del PDF: no hubo que adjuntar el XML');
  await senalar(page, page.locator('.review-source'), 2500);
  await rotular('Proveedora · Revisión', 'Folio 3668, UUID, fecha, moneda, forma de pago 99 y método PPD');
  await senalar(page, page.locator('.review-data .panel').first(), 4000);
  await rotular('Proveedora · Revisión', 'El emisor coincide con la proveedora: RFC, nombre y régimen fiscal 612');
  await senalar(page, page.locator('#supplier-data'), 3500);
  await rotular('Proveedora · Revisión', 'El cliente es INTERMODAL MEXICO: RFC, nombre, régimen, uso de CFDI y código postal');
  await senalar(page, page.locator('#client-data'), 3500);
  await rotular('Proveedora · Revisión', 'La orden de compra se detecta en el concepto: «LTH TIPO L-31T-900 AR BATERIA (OC/25704872)»');
  await senalar(page, page.locator('#concepts'), 4500);
  await rotular('Proveedora · Revisión', 'Subtotal $3,559.05 + IVA $569.45 = $4,128.50');
  await senalar(page, page.locator('#totals'), 2500);
  await rotular('Proveedora · Revisión', `Se carga el ${VOBO}`);
  await subirDocumento(page, 'APPROVAL', path.join(FACTURA, 'VoBo-3668-v1-orden-equivocada.pdf'), VOBO);
  await expect(page.locator('.required-summary')).toContainText('Archivos obligatorios completos');
  await rotular('Proveedora · Envío', 'Paso 3 · Al enviar, el portal valida la factura contra su orden de compra');
  await senalar(page, page.locator('.next-action'), 2500);
  await enviarAValidacion(page);
  await expect(page.locator('.page-heading .status')).toHaveText('Enviada');
  await rotular('Proveedora · Envío', 'Factura "Enviada" y ligada a la orden de compra 25704872');
  await senalar(page, page.locator('.page-heading'), 2000);
  await senalar(page, page.locator('#purchase-order-number'), 2500);
  await rotular('Proveedora · Validación', 'Reglas de la orden de compra: proveedora, montos, partida y entrada de mercancía, todas correctas');
  await senalar(page, grupoOrdenCompra(), 5000);
  await salir('Proveedora');

  // ---------------------------------------------------------------- 3. Analista de cuentas por pagar: revision y Observaciones
  await tarjeta(page, 'Parte 3 de 8 · Analista CxP', 'Revisión contra la orden de compra y Observaciones', [
    'Detalle de la factura con su orden de compra y su partida',
    'Revisión del Vo.Bo.: cita la orden 25704827, no la 25704872',
    'Observaciones con aviso por correo a la proveedora',
  ]);
  await rotular('Analista CxP', 'Inicia sesión el analista de cuentas por pagar');
  await iniciarSesion(page, CUENTAS.pmo, clave);
  await rotular('Analista CxP · Facturas', 'Facturas "Enviada", pendientes de decisión');
  await abrirFactura('UNDER_REVIEW');
  await rotular('Analista CxP · Detalle', 'La factura muestra la orden de compra contra la que se validó, con su partida');
  await senalar(page, page.locator('#purchase-order'), 4500);
  await senalar(page, grupoOrdenCompra(), 3000);
  const verVobo = await page.locator(`a[aria-label="Ver ${VOBO}"]`).first().getAttribute('href');
  await rotular('Analista CxP · Vo.Bo.', 'El analista de cuentas por pagar abre el Vo.Bo.: cita la orden 25704827, con dos dígitos invertidos');
  await page.goto(verVobo as string);
  await senalar(page, page.locator('.document-viewer'), 6500, false);
  await page.goto(`/invoices/${id}#decision`);
  await rotular('Analista CxP · Decisión', 'Observaciones: la factura regresa a la proveedora con la causa');
  const decision = page.locator('#decision');
  await senalar(page, decision, 2000);
  await decision.getByRole('button', { name: 'Observaciones' }).click();
  await escribir(page.locator('#observations'), OBSERVACIONES);
  await page.waitForTimeout(1500);
  const desdeObservaciones = new Date(Date.now() - 2000).toISOString();
  await clicNavegando(page, decision.getByRole('button', { name: 'Observaciones' }));
  await expect(page.locator('.page-heading .status')).toHaveText('Observaciones');
  await rotular('Analista CxP · Decisión', 'Factura en "Observaciones": se avisa a la proveedora por correo');
  await senalar(page, page.locator('#decision-result'), 3000);
  const conObservaciones = buscarCorreo(PROVEEDORA.correo, `Factura ${NUMERO} con observaciones`, desdeObservaciones);
  if (conObservaciones) await mostrarCorreo(page, 'Correo a la proveedora con las observaciones del analista de cuentas por pagar', conObservaciones);
  await salir('Analista CxP');

  // ---------------------------------------------------------------- 4. Proveedora: corrige y reenvia
  await tarjeta(page, 'Parte 4 de 8 · Proveedora', 'Corrección del Vo.Bo. y reenvío', [
    'Observaciones del analista de cuentas por pagar en el detalle de la factura',
    'Reemplazo del Vo.Bo. por el que cita la orden 25704872',
    'Reenvío: se vuelve a validar contra la orden de compra',
  ]);
  await rotular('Proveedora', 'Inicia sesión la proveedora');
  await iniciarSesion(page, PROVEEDORA.correo, clave);
  await abrirFactura();
  await rotular('Proveedora · Observaciones', 'El detalle muestra las observaciones del analista de cuentas por pagar');
  await senalar(page, page.locator('#decision-cause'), 4000);
  await senalar(page, page.getByRole('link', { name: /Revisión/ }).first(), 1500, false);
  await clicNavegando(page, page.getByRole('link', { name: /Revisión/ }).first());
  await rotular('Proveedora · Corrección', 'Se reemplaza el Vo.Bo. por el corregido');
  await subirDocumento(page, 'APPROVAL', path.join(FACTURA, 'VoBo-3668-v2-corregido.pdf'), VOBO);
  await expect(page.locator('.document-row').filter({ hasText: VOBO })).toContainText('VoBo-3668-v2-corregido.pdf');
  await enviarAValidacion(page);
  await expect(page.locator('.page-heading .status')).toHaveText('Enviada');
  await rotular('Proveedora · Reenvío', 'La factura vuelve a "Enviada"; la orden sigue ligada a esta misma factura');
  await senalar(page, page.locator('.page-heading'), 2500);
  await senalar(page, page.locator('#purchase-order-number'), 2000);
  await salir('Proveedora');

  // ---------------------------------------------------------------- 5. Analista de cuentas por pagar: autorizacion
  await tarjeta(page, 'Parte 5 de 8 · Analista CxP', 'Autorización', [
    'El Vo.Bo. ya cita la orden correcta',
    'Autorización con aviso a Recepción de Facturas y copia a la proveedora',
  ]);
  await rotular('Analista CxP', 'Inicia sesión el analista de cuentas por pagar');
  await iniciarSesion(page, CUENTAS.pmo, clave);
  await abrirFactura('UNDER_REVIEW');
  await rotular('Analista CxP · Detalle', 'El Vo.Bo. ya es el corregido');
  await senalar(page, page.locator('.document-list'), 3000);
  await rotular('Analista CxP · Historial', 'El historial conserva el primer envío, las Observaciones y el reenvío');
  await senalar(page, page.locator('#history'), 3500);
  await page.goto(`/invoices/${id}#decision`);
  await rotular('Analista CxP · Decisión', 'El analista de cuentas por pagar autoriza la factura para su pago');
  await page.locator('#decision').getByRole('button', { name: 'Autorizar' }).click();
  await expect(page.locator('#decision-confirm')).toBeVisible();
  await page.waitForTimeout(2500);
  const desdeAutorizada = new Date(Date.now() - 2000).toISOString();
  await clicNavegando(page, page.locator('#decision-confirm-accept'));
  await expect(page.locator('.page-heading .status')).toHaveText('Autorizada');
  await rotular('Analista CxP · Decisión', 'Factura "Autorizada": se notifica a Recepción de Facturas con copia a la proveedora');
  await senalar(page, page.locator('#decision-result'), 3500);
  const recepcion = ((await page.locator('#decision-result').innerText()).match(/[\w.+-]+@[\w.-]+\.\w+/g) ?? [])[0];
  const autorizada = recepcion ? buscarCorreo(recepcion, `Factura ${NUMERO} autorizada para pago`, desdeAutorizada) : null;
  if (autorizada) await mostrarCorreo(page, 'Correo a Recepción de Facturas (Cc: proveedora)', autorizada);
  await salir('Analista CxP');

  // ---------------------------------------------------------------- 6. Administrador: pago
  await tarjeta(page, 'Parte 6 de 8 · Administrador', 'Programación del pago', [
    'Se programa el pago de la factura: la solicitud en JSON',
    'Es PPD: la proveedora debe adjuntar su Complemento de Pago en 72 horas',
    'El portal lo sabe aunque la factura se registró sin XML',
  ]);
  await rotular('Administrador', 'Inicia sesión el Administrador');
  await iniciarSesion(page, CUENTAS.admin, clave);
  await abrirFactura('ACCEPTED');
  await rotular('Administrador · Pago', 'Programar pago: la solicitud en JSON y su confirmación');
  await page.locator('.page-heading').getByRole('button', { name: /Programar pago/ }).click();
  await expect(page.locator('#payment')).toBeVisible();
  await senalar(page, page.locator('#payment .modal-content'), 4000);
  await page.waitForTimeout(1500);
  const desdePagada = new Date(Date.now() - 2000).toISOString();
  await clicNavegando(page, page.locator('#payment').getByRole('button', { name: /Confirmar y programar pago/ }));
  await expect(page.locator('.page-heading .status')).toHaveText('Programado para pago');
  await rotular('Administrador · Pago', 'Factura "Programado para pago": el método de pago PPD se leyó del PDF, así que se pide el Complemento de Pago');
  await senalar(page, page.locator('#complement'), 4000);
  const pagada = buscarCorreo(PROVEEDORA.correo, `Factura ${NUMERO} programada para pago`, desdePagada);
  if (pagada) await mostrarCorreo(page, 'Correo a la proveedora: pago programado y aviso del Complemento de Pago', pagada);
  await salir('Administrador');

  // ---------------------------------------------------------------- 7. Proveedora: complemento de pago
  await tarjeta(page, 'Parte 7 de 8 · Proveedora', 'Complemento de Pago', [
    'El tablero avisa del complemento pendiente y su fecha límite',
    'Carga del XML y del PDF del complemento P-3701',
    'El XML relaciona el UUID de la factura 3668',
  ]);
  await rotular('Proveedora', 'Inicia sesión la proveedora');
  await iniciarSesion(page, PROVEEDORA.correo, clave);
  await rotular('Proveedora', 'El tablero avisa del Complemento de Pago pendiente y su fecha límite');
  await senalar(page, page.locator('#pending-complements'), 3500);
  await clicNavegando(page, page.locator('#pending-complements').getByRole('link', { name: `Factura ${NUMERO}` }));
  await rotular('Proveedora · Complemento', 'Archivo 1 de 2 · XML del Complemento de Pago: relaciona el UUID de la factura 3668');
  await subirDocumento(page, 'PAYMENT_COMPLEMENT_XML', path.join(PAGO, 'REP-P-3701-GOHS60031745A.xml'), 'Complemento de pago (XML)', false);
  await expect(page.locator('#complement-result')).toHaveText('Se notificó a Recepción de Facturas.');
  await rotular('Proveedora · Complemento', 'Complemento adjuntado: el portal avisa a Recepción de Facturas');
  await senalar(page, page.locator('#complement-result'), 3000);
  await rotular('Proveedora · Complemento', 'Archivo 2 de 2 · PDF del Complemento de Pago');
  await subirDocumento(page, 'PAYMENT_COMPLEMENT_PDF', path.join(PAGO, 'REP-P-3701-GOHS60031745A.pdf'), 'Complemento de pago (PDF)', false);
  await page.goto(`/invoices/${id}`);
  await rotular('Proveedora · Complemento', 'La factura queda "Programado para pago" con su Complemento de Pago adjuntado');
  await senalar(page, page.locator('#complement'), 3500);
  await senalar(page, page.locator('#history'), 3500);
  await salir('Proveedora');

  // ---------------------------------------------------------------- 8. Analista de cuentas por pagar: la orden con su factura
  await tarjeta(page, 'Parte 8 de 8 · Analista CxP', 'La orden de compra con su factura programada para pago', [
    'Cada orden muestra las facturas ligadas y su estatus',
    'Una orden admite una sola factura vigente',
  ]);
  await rotular('Analista CxP', 'Inicia sesión el analista de cuentas por pagar');
  await iniciarSesion(page, CUENTAS.pmo, clave);
  await abrirOrden();
  await rotular('Analista CxP · Orden 25704872', 'La factura 3668 quedó ligada a su orden y ya está "Programado para pago"');
  await senalar(page, page.locator('#invoices'), 4500);
  await salir('Analista CxP');

  await tarjeta(page, 'Portal de Proveedores FERROMEX', 'Fin del recorrido', [
    'La factura 3668 se registró sólo con su PDF: el portal leyó sus datos del texto',
    'Se validó contra la orden de compra 25704872 de SAP',
    'Pasó por Observaciones, se autorizó, se pagó y tiene su Complemento de Pago',
  ], 7000);

  await guardarVideo(page, VIDEO);
});
