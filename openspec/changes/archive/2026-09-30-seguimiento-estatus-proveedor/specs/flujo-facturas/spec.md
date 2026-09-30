## ADDED Requirements

### Requirement: Causa de la decisión en el detalle
En una factura "Rechazada" u "Observaciones", el detalle SHALL mostrar a todos los roles, antes de los resultados de la validación, el aviso "Motivo del rechazo" o "Observaciones del PMO" con las observaciones de la última revisión con decisión (no `COMMENT`) de la factura: el mismo texto que llevó el correo de la decisión (HU-20). Si la factura no tiene revisiones, SHALL usar `invoices.comments`. En "Observaciones", el aviso SHALL indicar al proveedor "Corrija lo indicado y vuelva a enviar la factura" con el enlace a "Gestionar documentos". En los demás estatus MUST NOT mostrarse un aviso de observaciones: las de rondas anteriores quedan en el historial.

#### Scenario: Factura rechazada
- **WHEN** el PMO rechazó la factura con "El RFC del receptor no corresponde" y el proveedor abre su detalle
- **THEN** ve "Motivo del rechazo" con "El RFC del receptor no corresponde"

#### Scenario: Observaciones por corregir
- **WHEN** el proveedor abre una factura en "Observaciones" con "Falta el Vo.Bo. firmado"
- **THEN** ve "Observaciones del PMO" con ese texto, "Corrija lo indicado y vuelva a enviar la factura" y el enlace a la carga documental

#### Scenario: Observaciones de una ronda anterior
- **WHEN** el proveedor reenvió una factura que tenía observaciones y la abre en "Enviada"
- **THEN** no ve un aviso de observaciones; la revisión anterior aparece en "Seguimiento"

## MODIFIED Requirements

### Requirement: Indicadores del tablero agregados en la base de datos
El tablero SHALL calcular el conteo por estado con `COUNT ... GROUP BY status` y el monto total con `SUM` sobre centavos, respetando el alcance por proveedor. MUST NOT cargar todas las facturas en memoria.

SHALL mostrar el total de facturas y un indicador por cada estatus de seguimiento: "Enviadas", "Observaciones", "Autorizadas", "Rechazadas" y "Canceladas" (EP-01 DT-01). Cada indicador SHALL enlazar al listado filtrado por su estatus (`/invoices?status=<clave>`) y el total, al listado con "Todos los estados" (`/invoices?status=`).

#### Scenario: KPIs del proveedor
- **WHEN** un PROVIDER abre el tablero
- **THEN** los conteos y el monto total corresponden sólo a sus facturas y el monto es exacto al centavo

#### Scenario: Indicador enlazado
- **WHEN** el proveedor con una factura rechazada pulsa el indicador "Rechazadas"
- **THEN** llega al listado filtrado por "Rechazada", que muestra sólo sus facturas rechazadas
