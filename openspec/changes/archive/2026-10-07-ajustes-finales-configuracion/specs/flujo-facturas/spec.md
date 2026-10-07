## ADDED Requirements

### Requirement: Archivos obligatorios en la transición a "Enviada"
El servicio de transición de estados (`transition_invoice`) SHALL verificar, en toda transición a "Enviada" (`UNDER_REVIEW`), que la factura tenga un documento vigente de cada tipo activo y Obligatorio para el origen de su proveedor en Archivos mínimos, con la configuración vigente en ese momento. Si falta alguno, SHALL rechazar la transición con un error de regla de negocio que se responde HTTP 409, nunca 500, con "Faltan archivos obligatorios: <nombres en el orden del catálogo>. Cárguelos antes de enviar". El estatus MUST NOT cambiar.

La verificación SHALL aplicar sólo a las transiciones futuras. Una factura "Enviada" o en un estatus posterior MUST NOT reevaluarse ni cambiar de estatus cuando cambian los archivos mínimos. Un tipo eliminado MUST NOT exigirse.

#### Scenario: Transición directa sin archivos
- **WHEN** se invoca la transición a "Enviada" de una factura nacional en "Observaciones" sin el Vo.Bo.
- **THEN** el servicio rechaza la transición con "Faltan archivos obligatorios: Vo.Bo. del líder de proyecto. Cárguelos antes de enviar", la respuesta HTTP sería 409 y la factura sigue en "Observaciones"

#### Scenario: Requisito agregado después del envío
- **WHEN** una factura está "Enviada" y el Administrador hace Obligatorio "Contrato" para su origen
- **THEN** la factura sigue "Enviada" y el PMO puede autorizarla

#### Scenario: Tipo eliminado
- **WHEN** el Administrador elimina "Vo.Bo. del líder de proyecto" y el proveedor envía una factura "Cargada" sin Vo.Bo. y sin fallas en las demás reglas
- **THEN** la factura pasa a "Enviada"

## MODIFIED Requirements

### Requirement: Alta de factura con datos validados
El alta de factura SHALL verificar, en este orden:
1. que el usuario esté vinculado a un proveedor, y que éste esté "Autorizado" (`ACTIVE`); si no tiene proveedor, HTTP 409 "Su usuario no está vinculado a un proveedor. Contacte al Administrador"; si el proveedor no está autorizado, HTTP 409 "Su proveedor no está autorizado para registrar facturas"; también al abrir el formulario;
2. los datos del formulario con el esquema `InvoiceCreate`:
   - `invoice_number` de 1 a 100 caracteres;
   - `service_period` con formato `MM/AAAA` y mes entre 01 y 12;
   - `project_name` de 2 a 200 caracteres;
3. que el contrato pertenezca al proveedor y esté activo.

Los errores de datos SHALL mostrarse en el mismo formulario con HTTP 400. Un número de factura repetido para el mismo proveedor SHALL rechazarse con un mensaje claro, sin HTTP 500. La factura creada SHALL quedar en "Borrador" y el alta SHALL llevar a la carga documental. La factura de un proveedor nacional SHALL nacer con la moneda de su contrato, hasta que el XML aporte una moneda activa del catálogo.

#### Scenario: Periodo inválido
- **WHEN** un proveedor crea una factura con `service_period = "13/2026"`
- **THEN** la respuesta es HTTP 400, el formulario muestra el error del periodo y no se crea la factura

#### Scenario: Número de factura repetido
- **WHEN** un proveedor crea una factura con un `invoice_number` que ya usó en otra factura propia
- **THEN** la respuesta es HTTP 409 con el mensaje "Ya existe una factura con ese número para el proveedor" y no se crea la factura

#### Scenario: Proveedor inactivo
- **WHEN** un proveedor cuyo registro está inactivo abre el formulario de alta o lo envía
- **THEN** la respuesta es HTTP 409 "Su proveedor no está autorizado para registrar facturas" y no se crea la factura

#### Scenario: Alta correcta
- **WHEN** un proveedor autorizado crea una factura con datos válidos y un contrato propio activo
- **THEN** la factura queda en "Borrador" y la respuesta redirige a su carga documental

#### Scenario: Usuario sin proveedor
- **WHEN** un usuario Proveedor sin proveedor abre el formulario de alta o lo envía
- **THEN** la respuesta es HTTP 409 "Su usuario no está vinculado a un proveedor. Contacte al Administrador" y no se crea la factura

#### Scenario: Moneda inicial de la factura nacional
- **WHEN** un proveedor nacional crea una factura sobre un contrato en `USD`
- **THEN** la factura nace con `currency = USD`

### Requirement: Envío a validación
`POST /invoices/{id}/submit` SHALL proceder sólo desde "Cargada" u "Observaciones". Desde cualquier otro estatus SHALL responder HTTP 409 "La factura no puede enviarse en su estatus actual". Después SHALL verificar los complementos de pago vencidos del proveedor (spec `pago-facturas`): si los tiene, SHALL responder HTTP 409 con el mensaje de complementos vencidos sin recalcular ni ejecutar el motor. Antes de validar, SHALL recalcular "Borrador"/"Cargada". Si la factura queda en "Borrador", SHALL responder HTTP 409 "Faltan archivos obligatorios: <nombres>. Cárguelos antes de enviar" sin ejecutar el motor, con los nombres de los tipos obligatorios faltantes en el orden del catálogo.

El envío SHALL ejecutar el motor de validación con la configuración vigente en ese momento y guardar sus resultados:
- si ningún resultado es `FAIL`, la factura SHALL pasar a "Enviada" mediante el servicio de transición, que verifica los archivos obligatorios ("Archivos obligatorios en la transición a 'Enviada'"); después SHALL registrar `submitted_at`, auditar `INVOICE_SUBMITTED` y redirigir al detalle con el aviso "Factura enviada a validación";
- si algún resultado es `FAIL`, cualquiera que sea su severidad, el estatus SHALL NOT cambiar y la respuesta SHALL ser HTTP 409 con el detalle de la factura, el aviso "El envío no procedió" y cada regla en `FAIL` con su código, mensaje, valor esperado y valor detectado.

Un resultado `WARNING` SHALL NOT impedir el envío. La factura SHALL leerse con bloqueo de fila, de modo que dos envíos simultáneos, o un envío y una carga de documentos, se ejecuten uno después del otro.

#### Scenario: Envío exitoso
- **WHEN** el proveedor envía una factura "Cargada" cuyo XML coincide con las Reglas de Validación
- **THEN** la factura pasa a "Enviada" con `submitted_at`, se audita `INVOICE_SUBMITTED` y el detalle muestra "Factura enviada a validación"

#### Scenario: Código postal distinto
- **WHEN** XML-010 espera `03930` y el proveedor envía una factura "Cargada" cuyo XML trae `DomicilioFiscalReceptor="06600"`
- **THEN** la respuesta es HTTP 409, la factura sigue "Cargada" y la página muestra XML-010 con el valor esperado `03930` y el detectado `06600`

#### Scenario: Reglas cambiadas después de verificar
- **WHEN** el proveedor verifica una factura sin fallas, el Administrador cambia la forma de pago esperada de XML-004 a `03` y el proveedor envía la factura con un XML de forma de pago `99`
- **THEN** el envío evalúa XML-004 contra `03`, no procede y la factura sigue "Cargada"

#### Scenario: Envío desde Borrador
- **WHEN** el proveedor envía una factura a la que le falta el Vo.Bo.
- **THEN** la respuesta es HTTP 409 "Faltan archivos obligatorios: Vo.Bo. del líder de proyecto. Cárguelos antes de enviar", la factura sigue en "Borrador" y no se registran resultados de validación

#### Scenario: Envío por petición directa con varios faltantes
- **WHEN** una petición directa envía una factura nacional que sólo tiene el XML del CFDI
- **THEN** la respuesta es HTTP 409 "Faltan archivos obligatorios: PDF del CFDI, Orden de compra, Vo.Bo. del líder de proyecto. Cárguelos antes de enviar"

#### Scenario: Reenvío desde Observaciones
- **WHEN** el proveedor envía una factura en "Observaciones" que ya no tiene fallas
- **THEN** la factura pasa a "Enviada"

#### Scenario: Envío de una factura ya enviada
- **WHEN** el proveedor envía una factura "Enviada"
- **THEN** la respuesta es HTTP 409 "La factura no puede enviarse en su estatus actual" y no se ejecuta el motor

#### Scenario: Advertencias no bloquean
- **WHEN** el proveedor envía una factura "Cargada" sin resultados `FAIL` y con DAT-001 en `WARNING`
- **THEN** la factura pasa a "Enviada"

#### Scenario: Complemento de pago vencido
- **WHEN** el proveedor tiene un complemento de pago vencido y envía una factura "Cargada"
- **THEN** la respuesta es HTTP 409 con el mensaje de complementos vencidos, la factura sigue "Cargada" y no se ejecuta el motor
