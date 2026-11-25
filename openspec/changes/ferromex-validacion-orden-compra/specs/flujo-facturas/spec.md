## MODIFIED Requirements

### Requirement: Alta de factura con datos validados
El alta de factura SHALL verificar, en este orden:
1. que el usuario esté vinculado a un proveedor, y que éste esté "Autorizado" (`ACTIVE`); si no tiene proveedor, HTTP 409 "Su usuario no está vinculado a un proveedor. Contacte al Administrador"; si el proveedor no está autorizado, HTTP 409 "Su proveedor no está autorizado para registrar facturas"; también al abrir el formulario;
2. para un proveedor nacional, los archivos del Paso 1 y sus datos extraídos (spec `registro-factura-extraccion`); para un proveedor internacional, los datos del Invoice capturados (spec `factura-internacional`).

Los errores de datos SHALL mostrarse en el mismo formulario con HTTP 400 (o el código que indique la spec de cada origen). Un número de factura repetido para el mismo proveedor SHALL rechazarse con un mensaje claro, sin HTTP 500. La factura creada SHALL quedar en "Borrador", sin contrato, proyecto ni líder de proyecto. El alta SHALL llevar a la revisión de los datos (nacional) o a la carga documental (internacional).

#### Scenario: Número de factura repetido
- **WHEN** un proveedor registra una factura cuyo número ya usó en otra factura propia
- **THEN** la respuesta es HTTP 409 con el mensaje "Ya existe una factura con ese número para el proveedor" y no se crea la factura

#### Scenario: Proveedor inactivo
- **WHEN** un proveedor cuyo registro está inactivo abre el formulario de alta o lo envía
- **THEN** la respuesta es HTTP 409 "Su proveedor no está autorizado para registrar facturas" y no se crea la factura

#### Scenario: Alta correcta
- **WHEN** un proveedor nacional autorizado registra el PDF de una factura propia
- **THEN** la factura queda en "Borrador" con `contract_id` nulo y la respuesta redirige a su revisión (`/invoices/{id}/data`)

#### Scenario: Usuario sin proveedor
- **WHEN** un usuario Proveedor sin proveedor abre el formulario de alta o lo envía
- **THEN** la respuesta es HTTP 409 "Su usuario no está vinculado a un proveedor. Contacte al Administrador" y no se crea la factura

#### Scenario: Proveedor manipulado en el formulario
- **WHEN** un proveedor envía el alta con el `supplier_id` de otro proveedor
- **THEN** la factura se crea para el proveedor del usuario

### Requirement: Borrador y Cargada según los archivos obligatorios
Una factura SHALL crearse en "Borrador" y su estatus SHALL recalcularse al crearla y en cada carga o reemplazo de documento, con el checklist de archivos mínimos vigente para el origen de su proveedor: "Cargada" si no falta ningún obligatorio y "Borrador" si falta alguno. El recálculo SHALL aplicar sólo a "Borrador" y "Cargada"; una factura en "Observaciones" SHALL conservar su estatus. Con los obligatorios completos, la carga documental SHALL mostrar "Factura cargada. Ya puede enviarla a validación".

#### Scenario: Falta el Vo.Bo.
- **WHEN** con la configuración inicial un proveedor nacional registra una factura con su PDF y su XML
- **THEN** la factura está en "Borrador" y la carga documental muestra "Falta 1 archivo obligatorio"

#### Scenario: Se completan los obligatorios
- **WHEN** a esa factura se le carga el Vo.Bo. del líder de proyecto
- **THEN** la factura pasa a "Cargada", se audita `STATUS_CHANGED` de `DRAFT` a `UPLOADED` y la carga documental muestra "Factura cargada. Ya puede enviarla a validación"

#### Scenario: Observaciones no se recalcula
- **WHEN** el proveedor reemplaza el PDF del CFDI de una factura en "Observaciones"
- **THEN** la factura sigue en "Observaciones"

### Requirement: Envío a validación
`POST /invoices/{id}/submit` SHALL proceder sólo desde "Cargada" u "Observaciones". Desde cualquier otro estatus SHALL responder HTTP 409 "La factura no puede enviarse en su estatus actual". Después SHALL verificar los complementos de pago vencidos del proveedor (spec `pago-facturas`): si los tiene, SHALL responder HTTP 409 con el mensaje de complementos vencidos sin recalcular ni ejecutar el motor. Antes de validar, SHALL recalcular "Borrador"/"Cargada". Si la factura queda en "Borrador", SHALL responder HTTP 409 "Faltan archivos obligatorios: <nombres>. Cárguelos antes de enviar" sin ejecutar el motor, con los nombres de los tipos obligatorios faltantes en el orden del catálogo.

El envío SHALL ejecutar el motor de validación con la configuración vigente y la orden de compra vigente en ese momento, incluidas la Validación 1 (`PRV-*` y `XML-*`) y la Validación 2 (`OC-*`), y guardar sus resultados:
- si ningún resultado es `FAIL`, la factura SHALL pasar a "Enviada" mediante el servicio de transición, que verifica los archivos obligatorios ("Archivos obligatorios en la transición a 'Enviada'"). Después SHALL ligarse a la orden de compra resuelta por el motor (`purchase_order_id`), registrar `submitted_at`, auditar `INVOICE_SUBMITTED` y redirigir al detalle con el aviso "Factura enviada a validación";
- si algún resultado es `FAIL`, cualquiera que sea su severidad, el estatus SHALL NOT cambiar, la factura SHALL NOT ligarse a la orden y la respuesta SHALL ser HTTP 409 con el detalle de la factura, el aviso "El envío no procedió" y cada regla en `FAIL` con su código, mensaje, valor esperado y valor detectado.

Un resultado `WARNING` SHALL NOT impedir el envío. La factura SHALL leerse con bloqueo de fila, de modo que dos envíos simultáneos, o un envío y una carga de documentos, se ejecuten uno después del otro.

#### Scenario: Envío exitoso
- **WHEN** el proveedor envía una factura "Cargada" cuyos datos coinciden con las Reglas de Validación y con su orden de compra
- **THEN** la factura pasa a "Enviada" con `submitted_at`, queda ligada a su orden, se audita `INVOICE_SUBMITTED` y el detalle muestra "Factura enviada a validación"

#### Scenario: Código postal distinto
- **WHEN** XML-010 espera `11700` y el proveedor envía una factura "Cargada" cuyo XML trae `DomicilioFiscalReceptor="06600"`
- **THEN** la respuesta es HTTP 409, la factura sigue "Cargada" y la página muestra XML-010 con el valor esperado `11700` y el detectado `06600`

#### Scenario: Diferencia contra la orden de compra
- **WHEN** el proveedor envía una factura "Cargada" cuyo subtotal no coincide con el total de su orden de compra
- **THEN** la respuesta es HTTP 409, la factura sigue "Cargada" sin `purchase_order_id` y la página muestra OC-005 con el total de la orden como esperado y el subtotal como detectado

#### Scenario: Reglas cambiadas después de verificar
- **WHEN** el proveedor verifica una factura sin fallas, el Administrador cambia la forma de pago esperada de XML-004 a `03` y el proveedor envía la factura con un XML de forma de pago `99`
- **THEN** el envío evalúa XML-004 contra `03`, no procede y la factura sigue "Cargada"

#### Scenario: Envío desde Borrador
- **WHEN** el proveedor envía una factura a la que le falta el Vo.Bo.
- **THEN** la respuesta es HTTP 409 "Faltan archivos obligatorios: Vo.Bo. del líder de proyecto. Cárguelos antes de enviar", la factura sigue en "Borrador" y no se registran resultados de validación

#### Scenario: Envío por petición directa con varios faltantes
- **WHEN** "Documentación adicional" es Obligatoria para Nacional y una petición directa envía una factura nacional que sólo tiene el PDF del CFDI
- **THEN** la respuesta es HTTP 409 "Faltan archivos obligatorios: Vo.Bo. del líder de proyecto, Documentación adicional. Cárguelos antes de enviar"

#### Scenario: Reenvío desde Observaciones
- **WHEN** el proveedor envía una factura en "Observaciones" que ya no tiene fallas
- **THEN** la factura pasa a "Enviada" ligada a su orden de compra

#### Scenario: Envío de una factura ya enviada
- **WHEN** el proveedor envía una factura "Enviada"
- **THEN** la respuesta es HTTP 409 "La factura no puede enviarse en su estatus actual" y no se ejecuta el motor

#### Scenario: Advertencias no bloquean
- **WHEN** el proveedor envía una factura "Cargada" sin resultados `FAIL` y con DAT-001 en `WARNING`
- **THEN** la factura pasa a "Enviada"

#### Scenario: Complemento de pago vencido
- **WHEN** el proveedor tiene un complemento de pago vencido y envía una factura "Cargada"
- **THEN** la respuesta es HTTP 409 con el mensaje de complementos vencidos, la factura sigue "Cargada" y no se ejecuta el motor

### Requirement: Verificación sin cambio de estatus
`POST /invoices/{id}/validation` ("Verificar") SHALL ejecutar el motor, incluidas las reglas `OC-*`, sobre una factura en "Borrador", "Cargada" u "Observaciones", guardar sus resultados y redirigir al detalle sin cambiar el estatus ni ligar la orden de compra. En otro estatus SHALL responder HTTP 409. Mientras la factura esté en un estatus editable, el detalle SHALL listar en "Reglas que impiden el envío" cada resultado en `FAIL`.

#### Scenario: Verificar con fallas
- **WHEN** el proveedor verifica una factura "Cargada" cuyo subtotal no coincide con el total de su orden de compra
- **THEN** la factura sigue "Cargada" y el detalle lista OC-005 en "Reglas que impiden el envío"

#### Scenario: Verificar una factura enviada
- **WHEN** el proveedor verifica una factura "Enviada"
- **THEN** la respuesta es HTTP 409 y sus resultados no cambian

### Requirement: Acciones exclusivas del proveedor
El alta (`GET` y `POST /invoices/new`), la revisión (`GET /invoices/{id}/data`), la carga documental (`GET` y `POST /invoices/{id}/documents`), "Verificar" y el envío SHALL estar disponibles sólo para el rol Proveedor, sobre facturas de su proveedor. Los roles PMO y Administrador SHALL recibir HTTP 403 y SHALL conservar el listado, el detalle y la descarga de documentos. La interfaz SHALL mostrar "Nueva factura", "Revisión", "Gestionar documentos", "Verificar" y "Enviar a validación" sólo al proveedor.

#### Scenario: Alta por un usuario PMO
- **WHEN** un usuario PMO envía `POST /invoices/new`
- **THEN** la respuesta es HTTP 403 y no se crea la factura

#### Scenario: Revisión por el Administrador
- **WHEN** un Administrador abre `/invoices/{id}/data`
- **THEN** la respuesta es HTTP 403

#### Scenario: Envío por el Administrador
- **WHEN** un Administrador envía `POST /invoices/{id}/submit` sobre una factura "Cargada"
- **THEN** la respuesta es HTTP 403 y la factura sigue "Cargada"

#### Scenario: Consulta del PMO
- **WHEN** un usuario PMO abre el detalle de una factura "Cargada"
- **THEN** la página responde HTTP 200 sin los botones "Verificar", "Gestionar documentos" ni "Enviar a validación"

#### Scenario: Factura de otro proveedor
- **WHEN** un proveedor envía `POST /invoices/{id}/submit` sobre una factura de otro proveedor
- **THEN** la respuesta es HTTP 404

## REMOVED Requirements

### Requirement: Contratos del proveedor en el formulario de alta
**Reason**: Se retira el módulo de contratos en la rama `ferromex`; el formulario de alta ya no ofrece contratos (HU-24).
**Migration**: La orden de compra se obtiene de los conceptos de la factura (nacional) o se captura en el Invoice (internacional), y se valida con `OC-001` a `OC-012` (spec `orden-compra`). El proveedor de la factura sigue siendo el del usuario ("Alta de factura con datos validados").
