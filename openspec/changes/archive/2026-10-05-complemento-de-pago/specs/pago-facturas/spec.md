## ADDED Requirements

### Requirement: Marcar una factura como pagada
Para los roles `PMO` y `Administrador`, el detalle de una factura "Autorizada" (`ACCEPTED`) SHALL mostrar el panel "Pago" con la casilla obligatoria "Confirmo que la factura <número> fue pagada. Se notificará al proveedor." y el botón "Marcar como pagada". En otro estatus, o para el rol `Proveedor`, el panel MUST NOT mostrarse.

`POST /invoices/{invoice_id}/payment` SHALL exigir CSRF y los roles `PMO` o `Administrador`. El rol `Proveedor` SHALL recibir HTTP 403. El sistema SHALL bloquear la fila de la factura antes de comprobar su estatus. Si la factura está "Pagada", SHALL responder HTTP 409 con "La factura ya fue pagada". Si está en otro estatus distinto de "Autorizada", SHALL responder HTTP 409 con "Sólo una factura autorizada se puede marcar como pagada". En los dos casos nada cambia y no se envía correo. Si la factura está "Autorizada" y la petición no trae la confirmación, SHALL responder HTTP 400 con "Confirme que la factura fue pagada" en el panel "Pago", sin cambios. Si la factura está "Autorizada" y trae la confirmación, el sistema SHALL hacer lo siguiente en una sola transacción:
- pasar la factura a "Pagada" (`PAID`) y auditar `STATUS_CHANGED`;
- registrar `paid_at` y `paid_by`;
- determinar si la factura requiere Complemento de Pago y, si lo requiere, registrar `payment_complement_due_at = paid_at + 72 horas`;
- auditar `INVOICE_PAID` con `paid_at`, si requiere complemento y su fecha límite.

Después SHALL redirigir (303) al detalle con el resultado del correo "Pagada".

#### Scenario: Marcar como pagada
- **WHEN** el PMO marca como pagada una factura "Autorizada"
- **THEN** la factura queda "Pagada" con `paid_by` del PMO, `audit_logs` tiene `STATUS_CHANGED` de `ACCEPTED` a `PAID` y un registro `INVOICE_PAID`, y el detalle ya no muestra el panel "Pago"

#### Scenario: Sin confirmación
- **WHEN** el PMO pulsa "Marcar como pagada" sin marcar la casilla de confirmación
- **THEN** la respuesta es HTTP 400 con "Confirme que la factura fue pagada", la factura sigue "Autorizada" y no se envía correo

#### Scenario: Factura no autorizada
- **WHEN** el Administrador envía `POST /invoices/{id}/payment` sobre una factura "Enviada"
- **THEN** la respuesta es HTTP 409 con "Sólo una factura autorizada se puede marcar como pagada" y la factura sigue "Enviada"

#### Scenario: Dos pagos simultáneos
- **WHEN** dos usuarios PMO marcan como pagada la misma factura "Autorizada" al mismo tiempo
- **THEN** uno de los dos marca la factura como pagada, el otro recibe HTTP 409 con "La factura ya fue pagada" y sale un solo correo "Pagada"

#### Scenario: Proveedor
- **WHEN** un usuario `Proveedor` envía `POST /invoices/{id}/payment` sobre su propia factura "Autorizada"
- **THEN** la respuesta es HTTP 403 y la factura sigue "Autorizada"

#### Scenario: Sin token CSRF
- **WHEN** el PMO envía `POST /invoices/{id}/payment` sin token CSRF
- **THEN** la respuesta es HTTP 403 y la factura no cambia

### Requirement: Factura que requiere Complemento de Pago
Una factura SHALL requerir Complemento de Pago si y sólo si su proveedor es nacional (`NATIONAL`) y el método de pago (`MetodoPago`) de su XML del CFDI vigente es `PPD`. El método de pago SHALL leerse de los datos que el motor de validación extrajo del XML (`payment_method`). Si no hay XML vigente o no tiene método de pago, la factura no lo requiere. El requisito SHALL determinarse una sola vez, al marcar la factura como pagada, y SHALL quedar fijo en `payment_complement_due_at`. Un cambio posterior en el catálogo o en las Reglas de Validación MUST NOT cambiarlo.

Si al marcar la factura como pagada ya tiene un XML del Complemento de Pago vigente y válido, el sistema SHALL registrar también `payment_complement_received_at` con la fecha de esa carga, y el complemento no queda pendiente.

#### Scenario: Nacional PPD
- **WHEN** el PMO marca como pagada el 01/10/2026 a las 10:00 (hora de negocio) la factura nacional "A-1024", cuyo XML trae `MetodoPago="PPD"`
- **THEN** la factura requiere Complemento de Pago con fecha límite 04/10/2026 10:00

#### Scenario: Nacional PUE
- **WHEN** el PMO marca como pagada una factura nacional cuyo XML trae `MetodoPago="PUE"`
- **THEN** la factura no requiere Complemento de Pago y `payment_complement_due_at` es nulo

#### Scenario: Internacional
- **WHEN** el PMO marca como pagada una factura de un proveedor internacional
- **THEN** la factura no requiere Complemento de Pago

### Requirement: Correo "Pagada" al proveedor
Después de confirmar el pago, el sistema SHALL enviar con el servicio de notificaciones el correo `INVOICE_PAID` al correo del proveedor en el catálogo y a las copias del evento. El envío SHALL registrarse en la bitácora con la entidad `Invoice` y el id de la factura. Las variables SHALL ser `numero_factura`, `folio_interno`, `proveedor`, `monto` (total con su moneda), `fecha_estatus` (`paid_at`) y `aviso_complemento`.

`aviso_complemento` SHALL valer, sólo si la factura requiere Complemento de Pago y todavía no lo tiene adjuntado: "Es importante que adjunte su “Complemento de Pago” a dicha factura pagada antes del <fecha límite>. Mientras no lo adjunte, el portal no le permitirá enviar nuevas facturas a validación.", con la fecha en la zona de negocio. En cualquier otro caso SHALL ser vacía. Un envío fallido MUST NOT revertir el pago. La redirección SHALL llevar el id del envío, y el detalle SHALL mostrar "Correo enviado a <destinatarios>" o "No se pudo enviar el correo: <error>".

#### Scenario: Pagada de un proveedor nacional PPD
- **WHEN** con `MAIL_BACKEND=file` el PMO marca como pagada la factura nacional PPD "A-1024" del proveedor con correo "contacto@proveedor.mx"
- **THEN** el buzón de salida tiene un correo para "contacto@proveedor.mx" con el asunto "Factura A-1024 pagada", el texto "Su factura número A-1024 ha sido pagada." y el texto "Es importante que adjunte su “Complemento de Pago” a dicha factura pagada antes del", y el detalle muestra "Correo enviado a contacto@proveedor.mx"

#### Scenario: Pagada de un proveedor internacional
- **WHEN** el Administrador marca como pagada la factura "INV-2026-0042" de un proveedor internacional
- **THEN** el proveedor recibe el correo "Factura INV-2026-0042 pagada" con "Su factura número INV-2026-0042 ha sido pagada." y sin el texto "Complemento de Pago"

#### Scenario: Pagada de un proveedor nacional PUE
- **WHEN** el PMO marca como pagada una factura nacional con `MetodoPago="PUE"`
- **THEN** el correo "Pagada" no contiene el texto "Complemento de Pago" ni deja líneas vacías repetidas en su lugar

#### Scenario: Servidor de correo caído
- **WHEN** el servidor SMTP rechaza la conexión y el PMO marca como pagada una factura
- **THEN** la factura queda "Pagada", la bitácora registra el envío `INVOICE_PAID` como `FAILED` y el detalle muestra "No se pudo enviar el correo" con el error y "Reenviar notificación"

### Requirement: Carga del Complemento de Pago en la factura pagada
En una factura "Pagada" que requiere Complemento de Pago, la carga documental (`GET` y `POST /invoices/{invoice_id}/documents`) SHALL estar disponible para el proveedor de la factura. La carga SHALL ofrecer y aceptar sólo "Complemento de pago (XML)" (`PAYMENT_COMPLEMENT_XML`) y "Complemento de pago (PDF)" (`PAYMENT_COMPLEMENT_PDF`). Otro tipo SHALL rechazarse con HTTP 409 "En una factura pagada sólo se puede cargar el Complemento de Pago". En una factura "Pagada" que no requiere complemento, la carga SHALL responder HTTP 409 "La factura no requiere Complemento de Pago". La carga MUST NOT cambiar el estatus de la factura ni ejecutar el motor de validación. Un reemplazo SHALL conservar el documento anterior, como en cualquier carga.

Antes de guardar el XML del complemento, el sistema SHALL verificar que sea un CFDI con `TipoDeComprobante="P"`. Si no lo es, SHALL responder HTTP 400 con "El XML no es un Complemento de Pago (CFDI de tipo P)". También SHALL verificar que algún `DoctoRelacionado` tenga en `IdDocumento` el UUID de la factura, sin distinguir mayúsculas. Si ninguno lo tiene, SHALL responder HTTP 400 con "El Complemento de Pago no relaciona la factura <UUID>". En los dos casos MUST NOT escribirse ningún archivo. Las mismas verificaciones SHALL aplicar al XML del complemento cargado en una factura que no está "Pagada". El UUID del complemento SHALL guardarse en los metadatos del documento.

La primera carga válida del XML del complemento SHALL registrar `payment_complement_received_at`. Cada carga válida del XML SHALL auditarse como `PAYMENT_COMPLEMENT_UPLOADED`, con el id del documento y el UUID del complemento. El detalle de la factura SHALL mostrar al proveedor el enlace "Adjuntar Complemento de Pago" mientras el complemento esté pendiente o vencido.

#### Scenario: Adjuntar el complemento a tiempo
- **WHEN** el proveedor carga en su factura "Pagada" "A-1024" un XML de tipo `P` cuyo `DoctoRelacionado` trae el UUID de "A-1024"
- **THEN** el documento se guarda como "Complemento de pago (XML)", la factura sigue "Pagada", `payment_complement_received_at` queda registrado y `audit_logs` tiene `PAYMENT_COMPLEMENT_UPLOADED`

#### Scenario: XML que no es complemento
- **WHEN** el proveedor carga como Complemento de pago (XML) un CFDI de ingreso (`TipoDeComprobante="I"`)
- **THEN** la respuesta es HTTP 400 con "El XML no es un Complemento de Pago (CFDI de tipo P)" y no se escribe ningún archivo en `storage/`

#### Scenario: Complemento de otra factura
- **WHEN** el proveedor carga un complemento cuyo `DoctoRelacionado` relaciona otro UUID
- **THEN** la respuesta es HTTP 400 con "El Complemento de Pago no relaciona la factura <UUID de la factura>" y el complemento sigue pendiente

#### Scenario: Otro tipo en una factura pagada
- **WHEN** el proveedor carga una orden de compra en su factura "Pagada"
- **THEN** la respuesta es HTTP 409 con "En una factura pagada sólo se puede cargar el Complemento de Pago" y no se escribe ningún archivo

#### Scenario: Factura pagada sin complemento requerido
- **WHEN** el proveedor abre la carga documental de una factura "Pagada" de método PUE
- **THEN** la respuesta es HTTP 409 con "La factura no requiere Complemento de Pago"

#### Scenario: PDF del complemento
- **WHEN** el proveedor carga sólo el PDF del complemento en su factura "Pagada" PPD
- **THEN** el documento se guarda, el complemento sigue pendiente y no se envía correo a Recepción de Facturas

### Requirement: Correo de complemento adjuntado a Recepción de Facturas
Después de confirmar cada carga válida del XML del Complemento de Pago en una factura "Pagada", el sistema SHALL enviar el correo `PAYMENT_COMPLEMENT` al buzón "Recepción de Facturas" y a las copias del evento. Las variables SHALL ser `numero_factura`, `proveedor`, `folio_interno`, `monto` y `fecha_estatus` (fecha de la carga). El envío SHALL registrarse en la bitácora con la entidad `Invoice` y el id de la factura. Un envío fallido MUST NOT revertir la carga. La carga documental SHALL mostrar al proveedor "Se notificó a Recepción de Facturas" o "No se pudo notificar a Recepción de Facturas", sin las direcciones del buzón.

#### Scenario: Aviso a Recepción
- **WHEN** con `MAIL_BACKEND=file` el proveedor "Servicios Digitales del Norte SA de CV" adjunta el complemento de la factura "A-1024"
- **THEN** el buzón de salida tiene un correo para `recepcionfacturas@ultrasist.com.mx` con el asunto "Complemento de pago de la factura A-1024" y el texto "El Complemento de Pago ha sido adjuntado a la factura A-1024 del proveedor Servicios Digitales del Norte SA de CV.", y el proveedor ve "Se notificó a Recepción de Facturas"

#### Scenario: Reemplazo del complemento
- **WHEN** el proveedor reemplaza el XML del complemento de una factura cuyo complemento ya estaba adjuntado
- **THEN** sale otro correo a Recepción de Facturas y `payment_complement_received_at` conserva la fecha de la primera carga

#### Scenario: Servidor de correo caído
- **WHEN** el servidor SMTP rechaza la conexión y el proveedor adjunta el complemento
- **THEN** el complemento queda adjuntado, la bitácora registra el envío como `FAILED` y el proveedor ve "No se pudo notificar a Recepción de Facturas"

### Requirement: Complementos pendientes y vencidos
Un complemento SHALL estar pendiente cuando la factura está "Pagada", tiene `payment_complement_due_at` y no tiene `payment_complement_received_at`. Un complemento pendiente SHALL estar vencido cuando `payment_complement_due_at` ya pasó. El detalle de la factura SHALL mostrar a todos los roles el bloque "Complemento de pago" con uno de estos textos y las fechas en la zona de negocio:
- "No requerido", si la factura "Pagada" no lo requiere;
- "Pendiente: adjúntelo antes del <fecha límite>";
- "Vencido desde el <fecha límite>. El proveedor no puede enviar nuevas facturas a validación.";
- "Adjuntado el <fecha>".

El tablero y el listado de facturas del rol `Proveedor` SHALL mostrar, si tiene complementos pendientes o vencidos, el aviso "Tiene complementos de pago pendientes" con cada factura, su fecha límite y un enlace a su carga documental. Los vencidos SHALL aparecer primero y marcados como vencidos.

#### Scenario: Complemento pendiente en el detalle
- **WHEN** el PMO abre el detalle de una factura "Pagada" PPD sin complemento cuya fecha límite es mañana
- **THEN** el bloque "Complemento de pago" muestra "Pendiente: adjúntelo antes del" con la fecha límite

#### Scenario: Aviso en el tablero del proveedor
- **WHEN** el proveedor tiene una factura con el complemento vencido y otra con el complemento pendiente, y abre el tablero
- **THEN** ve "Tiene complementos de pago pendientes" con las dos facturas, primero la vencida, marcada como vencida

#### Scenario: Complemento adjuntado
- **WHEN** el proveedor adjunta el complemento y abre el tablero
- **THEN** el aviso ya no lista esa factura y su detalle muestra "Adjuntado el <fecha>"

### Requirement: Bloqueo del envío por complementos vencidos
`POST /invoices/{invoice_id}/submit` SHALL verificar, después de comprobar que la factura está en un estatus que se puede enviar y antes de recalcular "Borrador"/"Cargada" y ejecutar el motor, si el proveedor de la factura tiene complementos vencidos. Si los tiene, la respuesta SHALL ser HTTP 409 con "No puede enviar facturas a validación: tiene complementos de pago vencidos de las facturas <números>. Adjúntelos para continuar.", con los números de factura en orden de fecha límite. El estatus de la factura MUST NOT cambiar y no se registran resultados de validación. Un complemento pendiente pero no vencido MUST NOT bloquear el envío. El bloqueo SHALL levantarse en cuanto el proveedor adjunta todos sus complementos vencidos. El bloqueo MUST NOT impedir el alta de facturas, la carga de documentos ni "Verificar".

#### Scenario: Envío bloqueado
- **WHEN** el proveedor tiene la factura "A-1024" pagada hace 73 horas sin complemento y envía a validación su factura "Cargada" "A-1030"
- **THEN** la respuesta es HTTP 409 con "No puede enviar facturas a validación: tiene complementos de pago vencidos de las facturas A-1024. Adjúntelos para continuar.", "A-1030" sigue "Cargada" y no se registran resultados de validación

#### Scenario: Dentro del plazo
- **WHEN** la factura "A-1024" se pagó hace 71 horas sin complemento y el proveedor envía "A-1030"
- **THEN** el envío se procesa con normalidad

#### Scenario: Bloqueo levantado
- **WHEN** el proveedor bloqueado adjunta el complemento de "A-1024" y vuelve a enviar "A-1030"
- **THEN** el envío se procesa con normalidad

#### Scenario: Reenvío desde Observaciones bloqueado
- **WHEN** el proveedor con un complemento vencido reenvía una factura en "Observaciones"
- **THEN** la respuesta es HTTP 409 con el mensaje de complementos vencidos y la factura sigue en "Observaciones"

#### Scenario: Sólo los complementos del proveedor
- **WHEN** otro proveedor tiene un complemento vencido y este proveedor envía su factura
- **THEN** el envío se procesa con normalidad

#### Scenario: Alta permitida
- **WHEN** el proveedor con un complemento vencido da de alta una factura y carga sus documentos
- **THEN** la factura se crea y sus documentos se guardan

### Requirement: Factura pagada es final
"Pagada" SHALL ser final. La factura MUST NOT admitir verificación, envío, decisión del PMO, cancelación ni más cargas que las del Complemento de Pago. MUST NOT aparecer en la bandeja del PMO. El detalle de una factura "Pagada" SHALL mostrar a todos los roles "Pagada el <fecha>" en la zona de negocio. MUST NOT mostrar el panel "Decisión", el panel "Pago", la sección "Cancelar factura" ni las acciones "Verificar" y "Enviar a validación".

#### Scenario: Envío de una factura pagada
- **WHEN** el proveedor envía `POST /invoices/{id}/submit` sobre su factura "Pagada"
- **THEN** la respuesta es HTTP 409 "La factura no puede enviarse en su estatus actual" y la factura sigue "Pagada"

#### Scenario: Detalle de una factura pagada
- **WHEN** el proveedor abre el detalle de su factura pagada el 01/10/2026 a las 10:00
- **THEN** ve "Pagada el 01/10/2026 10:00", el bloque "Complemento de pago" y no ve "Cancelar factura"
