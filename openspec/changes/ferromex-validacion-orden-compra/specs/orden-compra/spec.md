## ADDED Requirements

### Requirement: Entidad Orden de compra
El sistema SHALL guardar cada orden de compra en `purchase_orders` con `convenio` (entero positivo, único), `rfc` (12 o 13 caracteres), `supplier_name` (hasta 150), `order_date`, `total` (> 0), `taxes` (≥ 0), `supplier_id` (proveedor del portal, opcional) y `data` (JSONB con `items`, al menos una partida). Cada partida SHALL conservar las etiquetas de SAP de la sección 6.2 de la HU-24 y traer `Txt.brv`, `Ctd.Pedido`, `Unidad.Pedido`, `Prc.Neto` y `Moneda`. Montos y cantidades de `data` SHALL guardarse como texto decimal con punto. La factura SHALL ligarse a su orden de compra con `invoices.purchase_order_id`, una llave foránea que impide borrar una orden de compra con facturas.

#### Scenario: Convenio repetido
- **WHEN** se inserta una segunda orden de compra con `convenio = 25704872`
- **THEN** la base de datos rechaza la operación

#### Scenario: Total no positivo
- **WHEN** se inserta una orden de compra con `total = 0`
- **THEN** la base de datos rechaza la operación

#### Scenario: Borrado de una orden de compra facturada
- **WHEN** se borra una orden de compra ligada a una factura
- **THEN** la base de datos rechaza la operación

#### Scenario: Partida sin Txt.brv
- **WHEN** se siembra una orden de compra cuya partida no trae `Txt.brv`
- **THEN** el servicio rechaza la orden antes de guardarla

### Requirement: Datos demo de órdenes de compra
La demo SHALL sembrar órdenes de compra de los proveedores demo, entre ellas:
- el convenio 25704872 del ejemplo de la solicitud: proveedor `GOHS60031745A`, Total 3,559.05, Impuestos 569.45 y una partida "LTH TIPO L-31 T-900 AR" de 1 PZA a 3,559.05 MXN con entrada de mercancía;
- una orden con una partida sin entrada de mercancía;
- una orden con dos partidas;
- una orden en USD del proveedor internacional demo, con entrada de mercancía.

El proveedor persona física demo SHALL ser el emisor del ejemplo: "SOCORRO PATRICIA GONZALEZ HERNANDEZ", RFC `GOHS60031745A`. Las facturas demo enviadas o posteriores SHALL estar ligadas a su orden de compra.

#### Scenario: Orden del ejemplo sembrada
- **WHEN** se siembra la demo
- **THEN** existe la orden de compra 25704872 con una partida cuyo `Docto Material` es `5000527117`

#### Scenario: Orden del proveedor internacional
- **WHEN** se siembra la demo
- **THEN** existe una orden de compra en USD ligada por `supplier_id` al proveedor internacional demo, con el total y los impuestos de su factura INV-2026-0042

### Requirement: Consulta de órdenes de compra
El menú "Órdenes de compra" SHALL mostrar a PMO y Administrador el listado `GET /purchase-orders`, paginado en SQL con 25 registros por página, del más reciente al más antiguo. Cada fila SHALL mostrar convenio, fecha, RFC, nombre, total, impuestos, número de partidas y número de facturas ligadas.

La búsqueda (`q`) SHALL comparar:
- un texto de sólo dígitos con el convenio exacto, además de con el RFC y el nombre;
- cualquier otro texto, sin distinguir mayúsculas, con el RFC y el nombre.

El detalle `GET /purchase-orders/{id}` SHALL mostrar el encabezado, cada partida con todas sus etiquetas de `DATA` y las facturas ligadas, con su folio y estatus. El Proveedor MUST NOT acceder al listado ni al detalle. Una orden inexistente SHALL responder HTTP 404.

#### Scenario: Búsqueda por convenio
- **WHEN** PMO busca `25704872`
- **THEN** el listado muestra sólo esa orden de compra

#### Scenario: Detalle con partidas
- **WHEN** el Administrador abre la orden 25704872
- **THEN** ve el encabezado y la partida con Material `E20080`, Txt.brv, cantidad, unidad, fecha de entrega, precio neto, moneda, grupo, almacén, documento de material y fecha contable

#### Scenario: Proveedor sin acceso
- **WHEN** un Proveedor abre `/purchase-orders`
- **THEN** la respuesta es HTTP 403

### Requirement: Validación de la factura contra la orden de compra
Al verificar y al enviar una factura nacional, el motor SHALL evaluar `OC-001` a `OC-012` según la sección 6.4 de la HU-24, con la orden de compra vigente en ese momento:
- **Número de orden:** se toma de las descripciones de los conceptos (`OC` seguido de `/`, `-`, `:` o espacios y de 6 a 10 dígitos). Todos los conceptos que lo traen deben citar la misma orden.
- **Búsqueda de la orden:** por convenio exacto, entre las órdenes cuyo RFC es el del proveedor del usuario. Una orden de otro proveedor responde igual que una inexistente.
- **Partida de cada concepto:** la descripción del concepto debe contener el `Txt.brv` completo, sin distinguir mayúsculas, acentos, espacios ni signos. Si coinciden varias partidas, gana la de `Txt.brv` más largo; un empate es ambiguo. Cada partida se usa a lo más por un concepto.
- **Unidad:** coincide con `Unidad.Pedido` según la tabla de equivalencias de la sección 6.5 de la HU-24, con la clave o la descripción de la unidad de la factura.
- **Montos:** se comparan con una tolerancia de ±0.01. El precio unitario se compara con `Prc.Neto` y el importe con `Ctd.Pedido × Prc.Neto`.
- **IVA de la factura:** es la suma de los traslados `002` con tasa `0.160000` de los conceptos o, si ningún concepto trae impuestos, el total trasladado del comprobante.
- **Orden ya facturada:** cuenta toda otra factura ligada a la orden que no esté "Rechazada" ni "Cancelada".
- **Bloqueo:** el motor SHALL leer la orden con bloqueo de fila, para que dos envíos que citan la misma orden se ejecuten uno después del otro.

OC-007, OC-008, OC-009 y OC-011 SHALL generar un resultado por concepto, con `source_reference` "Concepto <n>". Si OC-001 u OC-002 fallan, OC-003 a OC-012 SHALL resultar `NOT_APPLICABLE` con "Sin orden de compra". Si OC-007 falla para un concepto, sus OC-008, OC-009 y OC-011 SHALL resultar `NOT_APPLICABLE`. Cada resultado SHALL guardar en su evidencia los valores de la orden leídos (convenio, RFC, nombre, total, impuestos y, por concepto, la partida usada). `CRITICAL` y `ERROR` SHALL impedir el envío. Al enviarse, la factura SHALL quedar ligada a su orden de compra; "Verificar" MUST NOT ligarla.

#### Scenario: Factura del ejemplo
- **WHEN** el proveedor `GOHS60031745A` envía la factura 3668 (concepto "LTH TIPO L-31T-900 AR BATERIA (OC/25704872)", 1.00 H87 - PZ, 3,559.05, IVA 569.45, MXN)
- **THEN** `OC-001` a `OC-012` resultan `PASS`, la factura pasa a "Enviada" y queda ligada a la orden 25704872

#### Scenario: Sin número de orden de compra
- **WHEN** ningún concepto trae el texto `OC/<número>`
- **THEN** `OC-001` resulta `FAIL` "No se encontró el número de orden de compra en los conceptos", `OC-002` a `OC-012` resultan `NOT_APPLICABLE` y el envío no procede

#### Scenario: Órdenes distintas en los conceptos
- **WHEN** un concepto cita `OC/25704872` y otro `OC/25704873`
- **THEN** `OC-001` resulta `FAIL` "Los conceptos citan órdenes de compra distintas: 25704872, 25704873"

#### Scenario: Orden de otro proveedor
- **WHEN** el concepto cita una orden de compra cuyo RFC es de otro proveedor
- **THEN** `OC-002` resulta `FAIL` "La orden de compra <n> no existe para el proveedor"

#### Scenario: Subtotal distinto
- **WHEN** el subtotal de la factura es 3,600.00 y el Total de la orden es 3,559.05
- **THEN** `OC-005` resulta `FAIL` con esperado 3,559.05 y detectado 3,600.00

#### Scenario: IVA distinto
- **WHEN** la suma del IVA tasa 0.160000 de los conceptos es 570.00 y los Impuestos de la orden son 569.45
- **THEN** `OC-006` resulta `FAIL`

#### Scenario: Concepto sin partida
- **WHEN** un concepto describe "BATERIA LTH L-40" y ninguna partida de la orden tiene un `Txt.brv` contenido en esa descripción
- **THEN** `OC-007` resulta `FAIL` para ese concepto y sus `OC-008`, `OC-009` y `OC-011` resultan `NOT_APPLICABLE`

#### Scenario: Txt.brv con espacios distintos
- **WHEN** el concepto dice "LTH TIPO L-31T-900 AR BATERIA" y la partida "LTH TIPO L-31 T-900 AR"
- **THEN** `OC-007` resulta `PASS` para ese concepto

#### Scenario: Partida más específica
- **WHEN** la orden tiene las partidas "BATERIA" y "BATERIA LTH 900" y el concepto describe "BATERIA LTH 900 REFORZADA"
- **THEN** `OC-007` resulta `PASS` con la partida "BATERIA LTH 900"

#### Scenario: Cantidad distinta
- **WHEN** el concepto factura 2 piezas y la partida tiene `Ctd.Pedido` 1
- **THEN** `OC-008` resulta `FAIL` "Concepto 1: cantidad 2 vs 1"

#### Scenario: Unidad equivalente
- **WHEN** el concepto tiene unidad "H87 - PZ" y la partida `Unidad.Pedido` "PZA"
- **THEN** `OC-008` resulta `PASS`

#### Scenario: Importe distinto
- **WHEN** el concepto tiene importe 3,600.00 y la partida `Prc.Neto` 3,559.05 con cantidad 1
- **THEN** `OC-009` resulta `FAIL` "Concepto 1: importe 3600.00 vs 3559.05"

#### Scenario: Diferencia de redondeo
- **WHEN** el importe del concepto es 3,559.06 y la partida espera 3,559.05
- **THEN** `OC-009` resulta `PASS`

#### Scenario: Moneda distinta
- **WHEN** la factura está en USD y la partida en MXN
- **THEN** `OC-010` resulta `FAIL`

#### Scenario: Mercancía no entregada
- **WHEN** la partida usada no tiene `Docto Material` o `Fecha Conta`
- **THEN** `OC-011` resulta `FAIL` "Concepto 1: la partida no tiene entrada de mercancía" y el envío no procede

#### Scenario: Orden ya facturada
- **WHEN** la orden 25704872 ya tiene una factura "Enviada" y se envía otra factura que la cita
- **THEN** `OC-012` resulta `FAIL` con el folio de la primera y el envío no procede

#### Scenario: Orden con factura cancelada
- **WHEN** la única factura de la orden está "Cancelada" y se envía otra factura que la cita
- **THEN** `OC-012` resulta `PASS`

#### Scenario: Verificar no liga la orden
- **WHEN** el proveedor verifica una factura sin fallas
- **THEN** los resultados `OC-*` quedan guardados y la factura no tiene `purchase_order_id`

### Requirement: Factura internacional contra la orden de compra
El registro del Invoice internacional SHALL pedir el número de orden de compra (6 a 10 dígitos) en lugar del contrato. Al verificar y al enviar el Invoice, el motor SHALL evaluar las reglas `OC-*` según la sección 6.7 de la HU-24, buscando la orden por convenio y por el proveedor del usuario (`supplier_id`):
- OC-004 compara la razón social del proveedor con el nombre de la orden, con severidad `WARNING`;
- OC-005 y OC-006 comparan el subtotal y los impuestos capturados;
- OC-010 compara la moneda capturada con la de todas las partidas;
- OC-011 exige la entrada de mercancía de todas las partidas, en un solo resultado;
- OC-003 y OC-007 a OC-009 resultan `NOT_APPLICABLE`.

#### Scenario: Invoice que cuadra con su orden
- **WHEN** el proveedor internacional demo envía un Invoice con la orden de compra sembrada, subtotal, impuestos y moneda iguales a los de la orden, y la orden tiene entrada de mercancía
- **THEN** `OC-001`, `OC-002`, `OC-004`, `OC-005`, `OC-006`, `OC-010`, `OC-011` y `OC-012` resultan `PASS`, `OC-003` y `OC-007` a `OC-009` resultan `NOT_APPLICABLE` y la factura pasa a "Enviada" ligada a la orden

#### Scenario: Orden de otro proveedor
- **WHEN** el proveedor internacional captura el número de una orden de compra de otro proveedor
- **THEN** `OC-002` resulta `FAIL` "La orden de compra <n> no existe para el proveedor"

#### Scenario: Sin número de orden de compra
- **WHEN** el proveedor internacional guarda los datos del Invoice sin número de orden de compra
- **THEN** el formulario muestra "Capture el número de orden de compra" con HTTP 400

### Requirement: Orden de compra en el detalle de la factura
El detalle de una factura SHALL mostrar, en lugar del contrato y del proyecto, la orden de compra:
- el convenio ligado, con enlace al detalle de la orden para PMO y Administrador;
- o, si la factura aún no está ligada, el número detectado y la leyenda "sin ligar".

Cuando la factura tiene orden ligada, el detalle SHALL mostrar el encabezado de la orden y sus partidas con todas las etiquetas de `DATA`. La sección "Conciliación contractual" MUST NOT mostrarse.

#### Scenario: Detalle del PMO
- **WHEN** el PMO abre una factura "Enviada" ligada a la orden 25704872
- **THEN** ve el convenio 25704872 con enlace a `/purchase-orders/{id}` y la partida "LTH TIPO L-31 T-900 AR", y no ve "Contrato" ni "Conciliación contractual"

### Requirement: Contratos conservados sin uso
Las tablas `contracts`, `contract_amendments` y `contract_document_types`, y las columnas `invoices.contract_id` y `documents.contract_id`, SHALL conservarse con sus datos y restricciones. Ninguna ruta, servicio, regla ni plantilla del portal SHALL leerlas o escribirlas, y ningún módulo fuera de `app/models` y `alembic/` SHALL importar sus modelos. Las facturas creadas a partir de este cambio SHALL tener `contract_id` nulo.

#### Scenario: Datos de contratos después de la migración
- **WHEN** se migra una base con contratos, enmiendas y facturas ligadas a contratos
- **THEN** las tablas y sus filas siguen presentes, las facturas conservan su `contract_id` y `/contracts` responde HTTP 404

#### Scenario: Factura nueva
- **WHEN** un proveedor registra una factura después de la migración
- **THEN** la factura tiene `contract_id` nulo

#### Scenario: Requisitos del contrato retirados
- **WHEN** el Administrador abre `/admin/contract-requirements`
- **THEN** la respuesta es HTTP 404 y el menú no muestra "Alta de contrato" ni "Contratos"
