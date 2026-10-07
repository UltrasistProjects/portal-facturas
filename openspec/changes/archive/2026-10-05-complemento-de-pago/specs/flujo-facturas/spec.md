## MODIFIED Requirements

### Requirement: Modelo de estatus de la factura
El estatus de la factura SHALL pertenecer a este catálogo, con estas etiquetas en toda la interfaz:

| Clave | Etiqueta |
| --- | --- |
| `DRAFT` | Borrador |
| `UPLOADED` | Cargada |
| `UNDER_REVIEW` | Enviada |
| `ACCEPTED` | Autorizada |
| `REJECTED` | Rechazada |
| `REQUIRES_CORRECTION` | Observaciones |
| `CANCELLED` | Cancelada |
| `PAID` | Pagada |

Las únicas transiciones permitidas SHALL ser:
- `DRAFT → UPLOADED` y `UPLOADED → DRAFT`, que asigna el sistema según los archivos obligatorios;
- `UPLOADED → UNDER_REVIEW` y `REQUIRES_CORRECTION → UNDER_REVIEW`, por un envío que procede;
- `UNDER_REVIEW → ACCEPTED | REJECTED | REQUIRES_CORRECTION`, por la decisión del PMO;
- `ACCEPTED → PAID`, cuando el PMO o el Administrador marcan la factura como pagada (spec `pago-facturas`);
- de cualquier estatus distinto de `CANCELLED` y `PAID` a `CANCELLED`, por la cancelación del proveedor (HU-14).

"Autorizada" sólo admite el pago y la cancelación; "Rechazada" sólo admite la cancelación: los pasos de ClickBalance del PoC se retiraron (HU-20). "Cancelada" y "Pagada" son finales.

Cualquier otra transición SHALL rechazarse con HTTP 409 sin cambios. Cada transición SHALL auditarse como `STATUS_CHANGED` con el estatus anterior y el nuevo. Sólo la decisión del PMO SHALL asignar `REQUIRES_CORRECTION`.

#### Scenario: Etiquetas en el listado
- **WHEN** un usuario abre el listado de facturas
- **THEN** el filtro de estatus ofrece "Borrador", "Cargada", "Enviada", "Autorizada", "Rechazada", "Observaciones", "Cancelada" y "Pagada", y ninguna otra opción

#### Scenario: El PMO pide correcciones
- **WHEN** un usuario PMO envía la decisión `REQUIRES_CORRECTION` sobre una factura "Enviada"
- **THEN** la factura queda en "Observaciones"

#### Scenario: Una validación fallida no asigna Observaciones
- **WHEN** el proveedor envía una factura "Cargada" cuyo XML falla XML-002
- **THEN** la factura sigue "Cargada"

#### Scenario: Autorizada sólo admite el pago y la cancelación
- **WHEN** se intenta desde una factura "Autorizada" cualquier transición distinta del pago y de la cancelación
- **THEN** la respuesta es HTTP 409 y la factura sigue "Autorizada"

#### Scenario: Cancelada es final
- **WHEN** se intenta cualquier transición desde una factura "Cancelada"
- **THEN** la respuesta es HTTP 409 y la factura sigue "Cancelada"

#### Scenario: Pagada es final
- **WHEN** se intenta cualquier transición desde una factura "Pagada", incluida la cancelación
- **THEN** la respuesta es HTTP 409 y la factura sigue "Pagada"

#### Scenario: Migración de ClickBalance
- **WHEN** se aplica `0011_retire_clickbalance` sobre una base con facturas "Lista para ClickBalance" y "Cargada a ClickBalance"
- **THEN** quedan "Autorizada" y cada una tiene un registro `STATUS_MIGRATED` con el estatus anterior y el nuevo

### Requirement: Envío a validación
`POST /invoices/{id}/submit` SHALL proceder sólo desde "Cargada" u "Observaciones". Desde cualquier otro estatus SHALL responder HTTP 409 "La factura no puede enviarse en su estatus actual". Después SHALL verificar los complementos de pago vencidos del proveedor (spec `pago-facturas`): si los tiene, SHALL responder HTTP 409 con el mensaje de complementos vencidos sin recalcular ni ejecutar el motor. Antes de validar, SHALL recalcular "Borrador"/"Cargada"; si la factura queda en "Borrador", SHALL responder HTTP 409 "Faltan archivos obligatorios. Cárguelos antes de enviar" sin ejecutar el motor.

El envío SHALL ejecutar el motor de validación con la configuración vigente en ese momento y guardar sus resultados:
- si ningún resultado es `FAIL`, la factura SHALL pasar a "Enviada", registrar `submitted_at`, auditar `INVOICE_SUBMITTED` y redirigir al detalle con el aviso "Factura enviada a validación";
- si algún resultado es `FAIL`, cualquiera que sea su severidad, el estatus SHALL NOT cambiar y la respuesta SHALL ser HTTP 409 con el detalle de la factura, el aviso "El envío no procedió" y cada regla en `FAIL` con su código, mensaje, valor esperado y valor detectado.

Un resultado `WARNING` SHALL NOT impedir el envío. La factura SHALL leerse con bloqueo de fila, de modo que dos envíos simultáneos, o un envío y una carga de documentos, se ejecuten uno después del otro.

#### Scenario: Envío exitoso
- **WHEN** el proveedor envía una factura "Cargada" cuyo XML coincide con las Reglas de Validación
- **THEN** la factura pasa a "Enviada" con `submitted_at`, se audita `INVOICE_SUBMITTED` y el detalle muestra "Factura enviada a validación"

#### Scenario: Código postal distinto
- **WHEN** el Código Postal configurado es `03930` y el proveedor envía una factura "Cargada" cuyo XML trae `DomicilioFiscalReceptor="06600"`
- **THEN** la respuesta es HTTP 409, la factura sigue "Cargada" y la página muestra XML-010 con el valor esperado `03930` y el detectado `06600`

#### Scenario: Reglas cambiadas después de verificar
- **WHEN** el proveedor verifica una factura sin fallas, el Administrador cambia la forma de pago esperada a `03` y el proveedor envía la factura con un XML de forma de pago `99`
- **THEN** el envío evalúa XML-004 contra `03`, no procede y la factura sigue "Cargada"

#### Scenario: Envío desde Borrador
- **WHEN** el proveedor envía una factura a la que le falta el Vo.Bo.
- **THEN** la respuesta es HTTP 409 "Faltan archivos obligatorios. Cárguelos antes de enviar", la factura sigue en "Borrador" y no se registran resultados de validación

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

### Requirement: Indicadores del tablero agregados en la base de datos
El tablero SHALL calcular el conteo por estado con `COUNT ... GROUP BY status` y el monto total con `SUM` sobre centavos, respetando el alcance por proveedor. MUST NOT cargar todas las facturas en memoria.

SHALL mostrar el total de facturas y un indicador por cada estatus de seguimiento: "Enviadas", "Observaciones", "Autorizadas", "Pagadas", "Rechazadas" y "Canceladas" (EP-01 DT-01). Cada indicador SHALL enlazar al listado filtrado por su estatus (`/invoices?status=<clave>`) y el total, al listado con "Todos los estados" (`/invoices?status=`).

#### Scenario: KPIs del proveedor
- **WHEN** un Proveedor abre el tablero
- **THEN** los conteos y el monto total corresponden sólo a sus facturas y el monto es exacto al centavo

#### Scenario: Indicador enlazado
- **WHEN** el proveedor con una factura rechazada pulsa el indicador "Rechazadas"
- **THEN** llega al listado filtrado por "Rechazada", que muestra sólo sus facturas rechazadas

#### Scenario: Indicador de pagadas
- **WHEN** el PMO marca como pagada una factura y abre el tablero
- **THEN** el indicador "Pagadas" cuenta esa factura y el de "Autorizadas" ya no la cuenta
