import { expect, test } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
import { buscarCorreo, demoPassword, herramienta } from '../lib/estado';
import { CUENTAS } from '../lib/hu';
import { abrirExpediente, clicNavegando, enviarAlta, enviarAValidacion } from '../lib/portal';
import { APP_ROOT, EVIDENCIAS } from '../lib/rutas';
import {
  cerrarSesion,
  escribir,
  iniciarSesion,
  instalarCapa,
  loginKeycloak,
  menu,
  mostrarCorreo,
  mostrarExcel,
  senalar,
  subirDocumento,
  subirRequisitosAlta,
  tarjeta,
} from './comun';

// Recorrido del flujo completo en una sola pagina (un solo video): el Administrador da de alta y autoriza
// proveedores y crea un usuario PMO, un proveedor nuevo entra por primera vez, un proveedor con contrato registra y
// envia una factura, el PMO nuevo entra por primera vez, la autoriza y registra el pago, y el proveedor adjunta el
// Complemento de Pago. Los roles se cambian cerrando sesion. Requiere el portal con MAIL_BACKEND=file (ver
// tests/hu/README.md): los correos se muestran desde el buzon. Las cargas de archivos van paso a paso, con pausas.

const VIDEO = path.join(EVIDENCIAS, 'video', 'recorrido-flujo-completo.webm');

test('Recorrido del flujo completo del portal', async ({ page }) => {
  const run = `V${Date.now().toString(36).toUpperCase()}`;
  const carpeta = path.join(APP_ROOT, 'test-results', 'recorrido-datos', run);
  fs.mkdirSync(carpeta, { recursive: true });
  const fx = herramienta('fixtures', run, carpeta);
  const clave = demoPassword();
  const numero = `FAC-${run}`;
  const pmo = { nombre: `PMO de Proyectos ${run}`, correo: `pmo.${run.toLowerCase()}@ferromex-qa.example`, clave: `Pmo#${run}x7` };
  let facturaId = 0;

  let actual: [string, string] = ['', ''];
  await page.context().addInitScript(instalarCapa);
  page.on('domcontentloaded', () => {
    void page.evaluate(([etapa, texto]) => (window as any).__recorrido?.rotulo(etapa, texto), actual).catch(() => undefined);
  });
  const rotular = async (etapa: string, texto: string): Promise<void> => {
    actual = [etapa, texto];
    await page.evaluate(([e, t]) => (window as any).__recorrido?.rotulo(e, t), actual).catch(() => undefined);
  };

  await tarjeta(page, 'Portal de Proveedores FERROMEX', 'Recorrido del flujo completo', [
    '1. Administrador: alta y autorización de proveedores',
    '2. Administrador: alta del usuario PMO',
    '3. Proveedor nuevo: primer acceso y cambio de contraseña',
    '4. Proveedor: registro y envío de una factura',
    '5. PMO: primer acceso, revisión, autorización y pago',
    '6. Proveedor: Complemento de Pago',
  ], 7000);

  // ---------------------------------------------------------------- 1. Administrador: alta de proveedores
  await tarjeta(page, 'Parte 1 de 6 · Administrador', 'Alta y autorización de proveedores', [
    'Carga masiva con la plantilla de Excel',
    'Requisitos de alta en el expediente de cada proveedor',
    'Autorización masiva y envío automático de credenciales',
  ]);
  await rotular('Administrador', 'El portal redirige al inicio de sesión de Keycloak, el proveedor de identidad');
  await iniciarSesion(page, CUENTAS.admin, clave);
  await rotular('Administrador', 'Tablero con el resumen operativo de la recepción de facturas');
  await page.waitForTimeout(3000);

  await clicNavegando(page, menu(page, 'Proveedores'));
  await rotular('Administrador · Proveedores', 'Catálogo de proveedores: aquí empieza el alta');
  await page.waitForTimeout(2500);
  await senalar(page, page.getByRole('link', { name: /Carga masiva/ }), 1500);
  await clicNavegando(page, page.getByRole('link', { name: /Carga masiva/ }));
  await rotular('Administrador · Carga masiva', 'Instrucciones: se captura en la hoja "Proveedores", sin cambiar los encabezados');
  await senalar(page, page.locator('ol').filter({ hasText: 'Descargue la plantilla' }), 4500);
  await rotular('Administrador · Carga masiva', 'Se descarga la plantilla de Excel');
  await senalar(page, page.getByRole('link', { name: /Descargar plantilla/ }), 2000);
  const [descarga] = await Promise.all([page.waitForEvent('download'), page.getByRole('link', { name: /Descargar plantilla/ }).click()]);
  const plantilla = path.join(carpeta, descarga.suggestedFilename());
  await descarga.saveAs(plantilla);
  const nombreLlena = `carga_proveedores_${run}.xlsx`;
  const llena = path.join(carpeta, nombreLlena);
  const proveedores: { razon_social: string; rfc: string | null; id_fiscal: string | null; correo: string }[] =
    herramienta('plantilla-proveedores', plantilla, llena, run, 'validos').filas;
  await mostrarExcel(page, nombreLlena, herramienta('inspeccionar-xlsx', llena));

  await page.goto('/suppliers/import');
  await rotular('Administrador · Carga masiva', 'Se selecciona el archivo lleno: 2 proveedores nacionales y 1 internacional');
  await page.waitForTimeout(1200);
  await page.locator('#supplier-import-file').setInputFiles(llena);
  await senalar(page, page.locator('#supplier-import-file'), 2500);
  await senalar(page, page.locator('#supplier-import-submit'), 1500, false);
  await page.locator('#supplier-import-submit').click();
  await expect(page.locator('#supplier-import-summary-text')).toContainText('3 proveedores registrados');
  await rotular('Administrador · Carga masiva', 'Resultado: 3 filas leídas y 3 proveedores registrados, sin errores');
  await senalar(page, page.locator('#supplier-import-summary'), 4500);

  await page.goto(`/suppliers?q=${encodeURIComponent(run)}&status=REGISTERED`);
  await rotular('Administrador · Proveedores', 'Los 3 proveedores quedan "Registrado": todavía no tienen acceso al portal');
  await senalar(page, page.locator('table tbody'), 4500);

  for (const [i, proveedor] of proveedores.filter((p) => p.rfc).entries()) {
    await rotular('Administrador · Expediente', `Expediente de ${proveedor.razon_social}: faltan sus requisitos de alta obligatorios`);
    await abrirExpediente(page, proveedor.razon_social);
    await page.waitForTimeout(1500);
    await subirRequisitosAlta(
      page,
      fx.requisito_alta,
      (nombre, n, total) => rotular('Administrador · Expediente', `Requisito ${n} de ${total}: ${nombre}`),
      i === 0 ? 1 : 0.6,
    );
    await expect(page.locator('.requirements-summary')).toHaveText('Requisitos de alta completos');
    await rotular('Administrador · Expediente', 'Requisitos de alta completos: el proveedor ya se puede autorizar');
    await senalar(page, page.locator('.requirements-summary'), 2500);
  }

  await clicNavegando(page, menu(page, 'Proveedores'));
  await rotular('Administrador · Autorización masiva', 'Se filtran los proveedores "Registrado" y se seleccionan los nuevos');
  await page.locator('select[name=status]').selectOption('REGISTERED');
  await escribir(page.locator('input[name=q]'), run);
  await clicNavegando(page, page.getByRole('button', { name: 'Filtrar' }));
  for (const proveedor of proveedores) {
    await page.locator('table tbody tr').filter({ hasText: proveedor.razon_social }).locator('input.authorize-check').check();
    await page.waitForTimeout(500);
  }
  await expect(page.locator('#authorize-count')).toHaveText('3 seleccionados');
  await senalar(page, page.locator('#authorize-count'), 1800);
  await page.locator('#authorize-submit').click();
  await expect(page.locator('#authorize-confirm')).toBeVisible();
  await rotular('Administrador · Autorización masiva', 'Al confirmar, cada proveedor recibe por correo su usuario y una contraseña temporal');
  await page.waitForTimeout(3500);
  const desdeAutorizacion = new Date(Date.now() - 2000).toISOString();
  await Promise.all([page.waitForURL(/\/suppliers/), page.locator('#authorize-confirm-accept').click()]);
  await expect(page.locator('.authorization-summary .panel-header p')).toHaveText('3 autorizados · 0 omitidos · 0 no autorizados');
  await rotular('Administrador · Autorización masiva', 'Los 3 proveedores quedan "Autorizado" en una sola operación');
  await senalar(page, page.locator('.authorization-summary'), 4000);

  const nuevo = proveedores[0];
  const credenciales = buscarCorreo(nuevo.correo, 'Acceso al Portal de Proveedores FERROMEX', desdeAutorizacion);
  const temporal = credenciales?.texto.match(/Contraseña temporal: (\S+)/)?.[1];
  if (!credenciales || !temporal) throw new Error(`No se generó el correo de credenciales de ${nuevo.correo}`);
  await mostrarCorreo(page, `Correo que recibe el proveedor ${nuevo.razon_social}`, credenciales);

  // ---------------------------------------------------------------- 2. Administrador: alta del PMO
  await tarjeta(page, 'Parte 2 de 6 · Administrador', 'Alta del usuario PMO', [
    'Administración › Usuarios',
    'Usuario con rol PMO (sin proveedor)',
    'Contraseña temporal que se entrega por un medio seguro',
  ]);
  await page.goto('/');
  await clicNavegando(page, menu(page, 'Usuarios'));
  await rotular('Administrador · Usuarios', 'Usuarios del portal y su rol; las credenciales se gestionan en Keycloak');
  await page.waitForTimeout(3000);
  const crear = page.locator('details.admin-create');
  await crear.locator('summary').click();
  await rotular('Administrador · Nuevo usuario', 'Se capturan el nombre y el correo, y se elige el rol PMO');
  await senalar(page, crear, 1500);
  await escribir(page.locator('#user-name'), pmo.nombre);
  await escribir(page.locator('#user-email'), pmo.correo);
  await page.locator('#user-role').selectOption('PMO');
  await senalar(page, page.locator('#user-role'), 1800, false);
  await senalar(page, crear.locator('p.form-text'), 2500, false);
  await clicNavegando(page, crear.getByRole('button', { name: 'Crear usuario' }));
  await expect(page.locator('.alert-success')).toHaveText('Usuario creado');
  const temporalPmo = (await page.locator('.temporary-credentials code').innerText()).trim();
  await rotular('Administrador · Nuevo usuario', 'Usuario creado en Keycloak: la contraseña temporal se muestra una sola vez');
  await senalar(page, page.locator('.temporary-credentials'), 4500);
  await rotular('Administrador · Usuarios', 'El nuevo usuario aparece con el rol PMO y sin accesos todavía');
  await senalar(page, page.locator('table tbody tr').filter({ hasText: pmo.correo }), 3000);
  await rotular('Administrador', 'Cierra sesión');
  await cerrarSesion(page);

  // ---------------------------------------------------------------- 3. Proveedor nuevo: primer acceso
  await tarjeta(page, 'Parte 3 de 6 · Proveedor nuevo', 'Primer acceso al portal', [
    'Inicio de sesión con el usuario y la contraseña temporal del correo',
    'Cambio obligatorio de la contraseña temporal',
    'Entrada al portal con su propia contraseña',
  ]);
  await rotular('Proveedor nuevo', `Inicia sesión como ${nuevo.correo} con la contraseña temporal`);
  await loginKeycloak(page, nuevo.correo, temporal);
  await expect(page).toHaveURL(/required-action\?execution=UPDATE_PASSWORD/);
  await rotular('Proveedor nuevo', 'Keycloak exige cambiar la contraseña temporal: mínimo 8 caracteres con letra, número y carácter especial');
  await page.waitForTimeout(3500);
  const nueva = `Demo#${run}x9`;
  await escribir(page.locator('#password-new'), nueva);
  await escribir(page.locator('#password-confirm'), nueva);
  await page.locator('#kc-submit').click();
  await expect(page.locator('.sidebar-footer')).toContainText(nuevo.correo);
  await rotular('Proveedor nuevo', 'Ya entra al portal con su propia contraseña y el rol Proveedor');
  await senalar(page, page.locator('.sidebar-footer'), 3000, false);
  await cerrarSesion(page);

  // ---------------------------------------------------------------- 4. Proveedor: registro y envio de factura
  await tarjeta(page, 'Parte 4 de 6 · Proveedor', 'Registro y envío de una factura', [
    'Proveedor nacional con contrato activo (Tecnología Integral del Centro)',
    'Carga del XML y PDF del CFDI, la orden de compra y el Vo.Bo.',
    'Prevalidación automática contra las reglas y envío a validación',
  ]);
  await rotular('Proveedor', 'Inicia sesión un proveedor que ya opera con FERROMEX');
  await iniciarSesion(page, CUENTAS.proveedor1, clave);
  await rotular('Proveedor', 'Tablero del proveedor: sus facturas y avisos');
  await page.waitForTimeout(3000);
  await senalar(page, page.getByRole('link', { name: /Nueva factura/ }).first(), 1500);
  await clicNavegando(page, page.getByRole('link', { name: /Nueva factura/ }).first());
  await rotular('Proveedor · Nueva factura', 'Sólo se ofrecen los contratos activos del propio proveedor; el proyecto se toma del contrato');
  await senalar(page, page.locator('#contract'), 3000);
  await rotular('Proveedor · Nueva factura', 'Se capturan el número de factura, el periodo del servicio y la orden de compra');
  await escribir(page.locator('input[name=invoice_number]'), numero);
  await escribir(page.locator('input[name=service_period]'), '08/2026');
  await escribir(page.locator('input[name=purchase_order_number]'), `OC-${numero}`);
  await page.waitForTimeout(2000);
  facturaId = await enviarAlta(page);
  await rotular('Proveedor · Carga documental', 'Checklist de los 4 archivos obligatorios del proveedor nacional');
  await senalar(page, page.locator('.required-summary'), 3000);
  const documentos = [
    ['INVOICE_XML', fx.cfdi_ppd, 'XML del CFDI', 'XML del CFDI: de él salen los datos fiscales que se validan'],
    ['INVOICE_PDF', fx.pdf_cfdi, 'PDF del CFDI', 'PDF del CFDI: la representación impresa de la factura'],
    ['PURCHASE_ORDER', fx.orden_compra, 'Orden de compra', 'Orden de compra del servicio'],
    ['APPROVAL', fx.vobo, 'Vo.Bo. del líder de proyecto', 'Vo.Bo. del líder de proyecto'],
  ] as const;
  for (const [i, [tipo, archivo, etiqueta, descripcion]] of documentos.entries()) {
    await rotular('Proveedor · Carga documental', `Documento ${i + 1} de ${documentos.length} · ${descripcion}`);
    await subirDocumento(page, tipo, archivo, etiqueta);
  }
  await expect(page.locator('.required-summary')).toContainText('Archivos obligatorios completos');
  await rotular('Proveedor · Carga documental', 'Archivos obligatorios completos: la factura queda "Cargada"');
  await senalar(page, page.locator('.required-summary'), 3000);

  await page.goto(`/invoices/${facturaId}`);
  await expect(page.locator('.page-heading .status')).toHaveText('Cargada');
  await rotular('Proveedor · Envío', 'Al enviarla, el portal valida el XML del CFDI contra las Reglas de Validación');
  await senalar(page, page.locator('.page-heading'), 2500);
  await enviarAValidacion(page);
  await expect(page.locator('.page-heading .status')).toHaveText('Enviada');
  await rotular('Proveedor · Envío', 'Sin reglas que lo impidan, la factura pasa a "Enviada" y ya no se puede modificar');
  await senalar(page, page.locator('.page-heading .status'), 3000);
  await rotular('Proveedor · Prevalidación', 'Matriz de evidencia: cada regla con el valor esperado y el detectado en el XML');
  await senalar(page, page.locator('#validations'), 2500);
  const regla = page.locator('#validations details.rule-card').filter({ hasText: 'XML-002' }).first();
  await regla.locator('summary').click();
  await senalar(page, regla, 3500);
  await cerrarSesion(page);

  // ---------------------------------------------------------------- 5. PMO: primer acceso, revision, autorizacion y pago
  await tarjeta(page, 'Parte 5 de 6 · PMO', 'Revisión, autorización y registro del pago', [
    'Primer acceso del PMO creado en la parte 2',
    'Consulta de las facturas enviadas y su detalle',
    'Autorización con aviso a Recepción de Facturas y copia al proveedor',
    'Registro del pago y aviso al proveedor',
  ]);
  await rotular('PMO', `Primer acceso de ${pmo.correo} con la contraseña temporal que le entregó el Administrador`);
  await loginKeycloak(page, pmo.correo, temporalPmo);
  await expect(page).toHaveURL(/required-action\?execution=UPDATE_PASSWORD/);
  await rotular('PMO', 'Keycloak le pide definir su propia contraseña antes de entrar');
  await page.waitForTimeout(3000);
  await escribir(page.locator('#password-new'), pmo.clave);
  await escribir(page.locator('#password-confirm'), pmo.clave);
  await page.locator('#kc-submit').click();
  await expect(page.locator('.sidebar-footer')).toContainText(pmo.correo);
  await rotular('PMO', 'Tablero del PMO con el resumen de facturas');
  await senalar(page, page.locator('.sidebar-footer'), 2500, false);
  await clicNavegando(page, menu(page, 'Facturas'));
  await rotular('PMO · Facturas', 'Se filtran las facturas "Enviada", pendientes de decisión');
  await page.locator('select[name=status]').selectOption('UNDER_REVIEW');
  await escribir(page.locator('input[name=q]'), numero);
  await clicNavegando(page, page.getByRole('button', { name: 'Filtrar' }));
  const fila = page.locator('table tbody tr').filter({ hasText: numero }).first();
  await senalar(page, fila, 2500);
  await clicNavegando(page, fila.locator('a.icon-action'));
  await rotular('PMO · Detalle', 'Detalle de la factura: datos del CFDI, documentos y prevalidación');
  await page.waitForTimeout(3000);
  await senalar(page, page.locator('.document-list'), 3000);

  await clicNavegando(page, page.getByRole('link', { name: /Decidir/ }));
  await rotular('PMO · Decisión', 'Tres opciones: Autorizar, Observaciones o Rechazar (estas dos piden la causa)');
  await senalar(page, page.locator('#decision'), 3500);
  await page.locator('#decision').getByRole('button', { name: 'Autorizar' }).click();
  await expect(page.locator('#decision-confirm')).toBeVisible();
  await page.waitForTimeout(3000);
  const desdeAutorizada = new Date(Date.now() - 2000).toISOString();
  await clicNavegando(page, page.locator('#decision-confirm-accept'));
  await expect(page.locator('.page-heading .status')).toHaveText('Autorizada');
  await rotular('PMO · Decisión', 'Factura "Autorizada": se notifica a Recepción de Facturas con copia al proveedor');
  await senalar(page, page.locator('#decision-result'), 3500);
  const recepcion = ((await page.locator('#decision-result').innerText()).match(/[\w.+-]+@[\w.-]+\.\w+/g) ?? [])[0];
  const autorizada = recepcion ? buscarCorreo(recepcion, `Factura ${numero} autorizada para pago`, desdeAutorizada) : null;
  if (autorizada) await mostrarCorreo(page, 'Correo a Recepción de Facturas (Cc: proveedor)', autorizada);

  await page.goto(`/invoices/${facturaId}`);
  await rotular('PMO · Pago', 'Programar pago: la solicitud en JSON y su confirmación');
  await page.locator('.page-heading').getByRole('button', { name: /Programar pago/ }).click();
  await expect(page.locator('#payment')).toBeVisible();
  await senalar(page, page.locator('#payment .modal-content'), 4000);
  await page.waitForTimeout(1500);
  const desdePagada = new Date(Date.now() - 2000).toISOString();
  await clicNavegando(page, page.locator('#payment').getByRole('button', { name: /Confirmar y programar pago/ }));
  await expect(page.locator('.page-heading .status')).toHaveText('Programado para pago');
  await rotular('PMO · Pago', 'Factura "Programado para pago": el proveedor tiene un plazo para adjuntar el Complemento de Pago');
  await senalar(page, page.locator('.page-heading .status'), 2500);
  await senalar(page, page.locator('#complement'), 3000);
  const pagada = buscarCorreo(CUENTAS.proveedor1, `Factura ${numero} programada para pago`, desdePagada);
  if (pagada) await mostrarCorreo(page, 'Correo al proveedor: pago y aviso del Complemento de Pago', pagada);
  await page.goto('/');
  await cerrarSesion(page);

  // ---------------------------------------------------------------- 6. Proveedor: complemento de pago
  await tarjeta(page, 'Parte 6 de 6 · Proveedor', 'Complemento de Pago', [
    'Aviso de complementos pendientes en el tablero',
    'Carga del Complemento de Pago (CFDI de tipo P)',
    'Aviso automático a Recepción de Facturas',
  ]);
  await rotular('Proveedor', 'Inicia sesión el proveedor');
  await iniciarSesion(page, CUENTAS.proveedor1, clave);
  await rotular('Proveedor', 'El tablero le avisa que tiene un Complemento de Pago pendiente y su fecha límite');
  await senalar(page, page.locator('#pending-complements'), 4000);
  await page.goto(`/invoices/${facturaId}`);
  await rotular('Proveedor · Factura pagada', 'La factura aparece "Pagada" con el complemento pendiente');
  await senalar(page, page.locator('#complement'), 3000);
  await senalar(page, page.getByRole('link', { name: /Adjuntar Complemento de Pago/ }), 1500);
  await clicNavegando(page, page.getByRole('link', { name: /Adjuntar Complemento de Pago/ }));
  await rotular('Proveedor · Complemento', 'Se carga el XML del Complemento de Pago (CFDI de tipo P) que relaciona la factura');
  await page.waitForTimeout(2000);
  await subirDocumento(page, 'PAYMENT_COMPLEMENT_XML', fx.complemento_pago, 'Complemento de pago (XML)', false);
  await expect(page.locator('#complement-result')).toHaveText('Se notificó a Recepción de Facturas.');
  await rotular('Proveedor · Complemento', 'Complemento adjuntado: el portal avisa a Recepción de Facturas');
  await senalar(page, page.locator('#complement-result'), 3500);

  await page.goto(`/invoices/${facturaId}`);
  await rotular('Historial', 'El historial registra cada paso de la factura con su fecha y responsable');
  await senalar(page, page.locator('#history'), 5000);
  await clicNavegando(page, menu(page, 'Facturas'));
  await rotular('Proveedor · Mis facturas', 'El proveedor consulta en todo momento el estatus de sus facturas');
  await senalar(page, page.locator('table tbody tr').filter({ hasText: numero }).first(), 3500);
  await rotular('', '');
  await cerrarSesion(page);

  await tarjeta(page, 'Portal de Proveedores FERROMEX', 'Fin del recorrido', [
    `3 proveedores dados de alta y autorizados; usuario PMO creado`,
    `Factura ${numero}: registrada, prevalidada, autorizada, pagada y con su Complemento de Pago`,
    'Correos generados en cada paso: credenciales, autorización, pago y complemento',
  ], 6000);

  const video = page.video();
  await page.context().close();
  fs.mkdirSync(path.dirname(VIDEO), { recursive: true });
  await video?.saveAs(VIDEO);
});
