# flujo-facturas Specification

## Purpose
Alta de factura validada, folio interno sin carrera, listado filtrado y paginado en SQL, indicadores agregados y reglas de estado centralizadas en el servicio de facturas.
## Requirements
### Requirement: Alta de factura con datos validados
El alta de factura SHALL verificar, en este orden:
1. que el usuario esté vinculado a un proveedor, y que éste esté "Autorizado" (`ACTIVE`); si no tiene proveedor, HTTP 409 "Su usuario no está vinculado a un proveedor. Contacte al Administrador"; si el proveedor no está autorizado, HTTP 409 "Su proveedor no está autorizado para registrar facturas"; también al abrir el formulario;
2. los datos del formulario con el esquema `InvoiceCreate`:
   - `invoice_number` de 1 a 100 caracteres;
   - `service_period` con formato `MM/AAAA` y mes entre 01 y 12;
   - `project_name` de 2 a 200 caracteres;
3. que el contrato pertenezca al proveedor y esté activo.

Los errores de datos SHALL mostrarse en el mismo formulario con HTTP 400. Un número de factura repetido para el mismo proveedor SHALL rechazarse con un mensaje claro, sin HTTP 500. La factura creada SHALL quedar en "Borrador" y el alta SHALL llevar a la carga documental.

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

### Requirement: Folio interno sin colisiones
El folio interno SHALL derivarse del identificador asignado por la base de datos a la factura, dentro de la misma transacción del alta, con el formato `FAC-{AAAA}-{id:05d}`. `AAAA` es el año de la fecha de creación en la zona horaria de negocio.

#### Scenario: Altas concurrentes
- **WHEN** dos altas de factura se procesan de forma concurrente
- **THEN** ambas se crean con folios distintos y ninguna falla por colisión de folio

#### Scenario: Año según zona de negocio
- **WHEN** una factura se crea el 31 de diciembre de 2026 a las 20:00 en `America/Mexico_City` (1 de enero de 2027 en UTC)
- **THEN** su folio comienza con `FAC-2026-`

### Requirement: Reglas de estado centralizadas en el servicio de facturas
Las reglas de flujo SHALL residir en `invoice_service`, en el servicio de envío y en el de revisión, y los routers MUST limitarse a invocarlas:
- el conjunto de estados editables (`DRAFT`, `UPLOADED`, `REQUIRES_CORRECTION`);
- el recálculo de "Borrador" y "Cargada";
- el envío y su resultado;
- la decisión del PMO y la prohibición de aceptar con bloqueos críticos;
- el resumen de validación, que SHALL reutilizar `calculate_score`.

#### Scenario: Aceptación con bloqueo crítico
- **WHEN** un usuario PMO envía la decisión `ACCEPTED` sobre una factura en `UNDER_REVIEW` con un resultado `FAIL` de severidad `CRITICAL`
- **THEN** la respuesta es HTTP 409 "No se puede aceptar con bloqueos criticos", la factura sigue en `UNDER_REVIEW` y no se registra revisión

#### Scenario: Carga en estado no editable
- **WHEN** un proveedor sube un documento a una factura en `UNDER_REVIEW`
- **THEN** la respuesta es HTTP 409 y no se almacena el archivo

#### Scenario: Carga en Cargada
- **WHEN** un proveedor reemplaza el XML de una factura "Cargada"
- **THEN** el documento se guarda y la factura sigue "Cargada"

#### Scenario: Resumen del detalle
- **WHEN** se muestra el detalle de una factura validada
- **THEN** los contadores de aprobadas, advertencias, errores y bloqueos coinciden con los calculados por `calculate_score` para los mismos resultados

### Requirement: Listado de facturas filtrado y paginado en la base de datos
El listado SHALL aplicar la búsqueda, el filtro por estado, el filtro por origen del proveedor (`NATIONAL` o `INTERNATIONAL`; un valor desconocido se ignora), el alcance por proveedor (rol Proveedor), el orden y la paginación (25 por página) en la consulta SQL, cargando el proveedor asociado sin consultas adicionales por fila. El orden SHALL ser `created_at DESC`, salvo en la bandeja del PMO (spec `revision-pmo`), donde las facturas "Enviada" se ordenan por `submitted_at` ascendente. La búsqueda SHALL comparar, sin distinguir mayúsculas, contra folio interno, número de factura, proyecto y razón social del proveedor, y SHALL tratar `%` y `_` como caracteres literales.

#### Scenario: Búsqueda por razón social
- **WHEN** un usuario PMO busca `tecnologia integral` con "Todos los estados"
- **THEN** el listado muestra las facturas de "Tecnologia Integral del Centro SA de CV"

#### Scenario: Comodines literales
- **WHEN** se busca `%`
- **THEN** sólo se muestran facturas cuyos campos de búsqueda contienen el carácter `%`

#### Scenario: Paginación
- **WHEN** existen 30 facturas visibles y se solicita la página 2
- **THEN** se muestran las 5 facturas más antiguas y los controles de paginación indican 2 páginas

#### Scenario: Sin N+1
- **WHEN** se renderiza una página de 25 facturas
- **THEN** el número de consultas SQL emitidas es constante e independiente del número de facturas

#### Scenario: Alcance del proveedor
- **WHEN** un Proveedor consulta el listado con cualquier filtro
- **THEN** sólo aparecen facturas de su proveedor

#### Scenario: Filtro por origen
- **WHEN** un usuario PMO filtra por origen "Internacional" con "Todos los estados"
- **THEN** sólo aparecen facturas de proveedores internacionales

### Requirement: Indicadores del tablero agregados en la base de datos
El tablero SHALL calcular el conteo por estado con `COUNT ... GROUP BY status` y el monto total con `SUM` sobre centavos, respetando el alcance por proveedor. MUST NOT cargar todas las facturas en memoria.

SHALL mostrar el total de facturas y un indicador por cada estatus de seguimiento: "Enviadas", "Observaciones", "Autorizadas", "Rechazadas" y "Canceladas" (EP-01 DT-01). Cada indicador SHALL enlazar al listado filtrado por su estatus (`/invoices?status=<clave>`) y el total, al listado con "Todos los estados" (`/invoices?status=`).

#### Scenario: KPIs del proveedor
- **WHEN** un Proveedor abre el tablero
- **THEN** los conteos y el monto total corresponden sólo a sus facturas y el monto es exacto al centavo

#### Scenario: Indicador enlazado
- **WHEN** el proveedor con una factura rechazada pulsa el indicador "Rechazadas"
- **THEN** llega al listado filtrado por "Rechazada", que muestra sólo sus facturas rechazadas

### Requirement: Límite transaccional en la capa HTTP
Los servicios (`run_validation`, `transition_invoice`, `audit` y los demás) MUST NOT ejecutar `commit`. Cada endpoint mutable SHALL confirmar o revertir su transacción completa.

#### Scenario: Fallo posterior a la validación
- **WHEN** `run_validation` termina y una operación posterior dentro del mismo endpoint falla
- **THEN** no persisten ni los resultados de validación ni los cambios de estado de esa petición

### Requirement: Registro de auditoría paginado
La vista `/admin/audit` SHALL paginar las entradas (50 por página, más recientes primero) y SHALL permitir llegar a cualquier entrada histórica.

#### Scenario: Entradas antiguas accesibles
- **WHEN** existen 600 entradas de auditoría y un Administrador navega a la última página
- **THEN** ve las entradas más antiguas

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

Las únicas transiciones permitidas SHALL ser:
- `DRAFT → UPLOADED` y `UPLOADED → DRAFT`, que asigna el sistema según los archivos obligatorios;
- `UPLOADED → UNDER_REVIEW` y `REQUIRES_CORRECTION → UNDER_REVIEW`, por un envío que procede;
- `UNDER_REVIEW → ACCEPTED | REJECTED | REQUIRES_CORRECTION`, por la decisión del PMO;
- de cualquier estatus distinto de `CANCELLED` a `CANCELLED`, por la cancelación del proveedor (HU-14).

"Autorizada" y "Rechazada" no admiten otra decisión del PMO: los pasos de ClickBalance del PoC se retiraron (HU-20). "Cancelada" es final.

Cualquier otra transición SHALL rechazarse con HTTP 409 sin cambios. Cada transición SHALL auditarse como `STATUS_CHANGED` con el estatus anterior y el nuevo. Sólo la decisión del PMO SHALL asignar `REQUIRES_CORRECTION`.

#### Scenario: Etiquetas en el listado
- **WHEN** un usuario abre el listado de facturas
- **THEN** el filtro de estatus ofrece "Borrador", "Cargada", "Enviada", "Autorizada", "Rechazada", "Observaciones" y "Cancelada", y ninguna otra opción

#### Scenario: El PMO pide correcciones
- **WHEN** un usuario PMO envía la decisión `REQUIRES_CORRECTION` sobre una factura "Enviada"
- **THEN** la factura queda en "Observaciones"

#### Scenario: Una validación fallida no asigna Observaciones
- **WHEN** el proveedor envía una factura "Cargada" cuyo XML falla XML-002
- **THEN** la factura sigue "Cargada"

#### Scenario: Autorizada sólo admite la cancelación
- **WHEN** se intenta desde una factura "Autorizada" cualquier transición distinta de la cancelación
- **THEN** la respuesta es HTTP 409 y la factura sigue "Autorizada"

#### Scenario: Cancelada es final
- **WHEN** se intenta cualquier transición desde una factura "Cancelada"
- **THEN** la respuesta es HTTP 409 y la factura sigue "Cancelada"

#### Scenario: Migración de ClickBalance
- **WHEN** se aplica `0011_retire_clickbalance` sobre una base con facturas "Lista para ClickBalance" y "Cargada a ClickBalance"
- **THEN** quedan "Autorizada" y cada una tiene un registro `STATUS_MIGRATED` con el estatus anterior y el nuevo

### Requirement: Borrador y Cargada según los archivos obligatorios
Una factura SHALL crearse en "Borrador". Cada carga o reemplazo de documento SHALL recalcular su estatus con el checklist de archivos mínimos vigente para el origen de su proveedor: "Cargada" si no falta ningún obligatorio y "Borrador" si falta alguno. El recálculo SHALL aplicar sólo a "Borrador" y "Cargada"; una factura en "Observaciones" SHALL conservar su estatus. Con los obligatorios completos, la carga documental SHALL mostrar "Factura cargada. Ya puede enviarla a validación".

#### Scenario: Falta el Vo.Bo.
- **WHEN** con la configuración inicial un proveedor nacional carga en una factura nueva el XML del CFDI, el PDF del CFDI y la orden de compra
- **THEN** la factura está en "Borrador" y la carga documental muestra "Falta 1 archivo obligatorio"

#### Scenario: Se completan los obligatorios
- **WHEN** a esa factura se le carga el Vo.Bo. del líder de proyecto
- **THEN** la factura pasa a "Cargada", se audita `STATUS_CHANGED` de `DRAFT` a `UPLOADED` y la carga documental muestra "Factura cargada. Ya puede enviarla a validación"

#### Scenario: Observaciones no se recalcula
- **WHEN** el proveedor reemplaza el PDF del CFDI de una factura en "Observaciones"
- **THEN** la factura sigue en "Observaciones"

### Requirement: Envío a validación
`POST /invoices/{id}/submit` SHALL proceder sólo desde "Cargada" u "Observaciones". Antes de validar, SHALL recalcular "Borrador"/"Cargada"; si la factura queda en "Borrador", SHALL responder HTTP 409 "Faltan archivos obligatorios. Cárguelos antes de enviar" sin ejecutar el motor. Desde cualquier otro estatus SHALL responder HTTP 409 "La factura no puede enviarse en su estatus actual".

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

### Requirement: Verificación sin cambio de estatus
`POST /invoices/{id}/validation` ("Verificar") SHALL ejecutar el motor sobre una factura en "Borrador", "Cargada" u "Observaciones", guardar sus resultados y redirigir al detalle sin cambiar el estatus. En otro estatus SHALL responder HTTP 409. Mientras la factura esté en un estatus editable, el detalle SHALL listar en "Reglas que impiden el envío" cada resultado en `FAIL`.

#### Scenario: Verificar con fallas
- **WHEN** el proveedor verifica una factura "Cargada" cuyo subtotal excede el monto autorizado del contrato
- **THEN** la factura sigue "Cargada" y el detalle lista FIN-001 en "Reglas que impiden el envío"

#### Scenario: Verificar una factura enviada
- **WHEN** el proveedor verifica una factura "Enviada"
- **THEN** la respuesta es HTTP 409 y sus resultados no cambian

### Requirement: Acciones exclusivas del proveedor
El alta (`GET` y `POST /invoices/new`), la carga documental (`GET` y `POST /invoices/{id}/documents`), "Verificar" y el envío SHALL estar disponibles sólo para el rol Proveedor, sobre facturas de su proveedor. Los roles PMO y Administrador SHALL recibir HTTP 403 y SHALL conservar el listado, el detalle y la descarga de documentos. La interfaz SHALL mostrar "Nueva factura", "Gestionar documentos", "Verificar" y "Enviar a validación" sólo al proveedor.

#### Scenario: Alta por un usuario PMO
- **WHEN** un usuario PMO envía `POST /invoices/new`
- **THEN** la respuesta es HTTP 403 y no se crea la factura

#### Scenario: Envío por el Administrador
- **WHEN** un Administrador envía `POST /invoices/{id}/submit` sobre una factura "Cargada"
- **THEN** la respuesta es HTTP 403 y la factura sigue "Cargada"

#### Scenario: Consulta del PMO
- **WHEN** un usuario PMO abre el detalle de una factura "Cargada"
- **THEN** la página responde HTTP 200 sin los botones "Verificar", "Gestionar documentos" ni "Enviar a validación"

#### Scenario: Factura de otro proveedor
- **WHEN** un proveedor envía `POST /invoices/{id}/submit` sobre una factura de otro proveedor
- **THEN** la respuesta es HTTP 404

### Requirement: Contratos del proveedor en el formulario de alta
El formulario de alta SHALL recibir sólo los contratos activos del proveedor del usuario y SHALL NOT contener datos de contratos de otros proveedores. El proveedor de la factura SHALL ser el del usuario; un `supplier_id` enviado en el formulario SHALL ignorarse. Sin contratos activos, el formulario SHALL indicarlo y SHALL NOT ofrecer el botón para continuar.

#### Scenario: HTML sin contratos ajenos
- **WHEN** `proveedor1@poc.local` abre el formulario de alta y existe un contrato activo de otro proveedor
- **THEN** el HTML no contiene el identificador, el proyecto ni el monto de ese contrato

#### Scenario: Proveedor manipulado en el formulario
- **WHEN** un proveedor envía el alta con el `supplier_id` de otro proveedor y un contrato propio
- **THEN** la factura se crea para el proveedor del usuario

#### Scenario: Contrato ajeno
- **WHEN** un proveedor envía el alta con el identificador de un contrato de otro proveedor
- **THEN** la respuesta es HTTP 400 "Contrato no corresponde al proveedor" y no se crea la factura

#### Scenario: Contrato inactivo
- **WHEN** un proveedor envía el alta con un contrato propio inactivo
- **THEN** la respuesta es HTTP 400 "El contrato no está activo" y no se crea la factura

### Requirement: Migración al modelo de estatus
La revisión `0010_invoice_status_model` SHALL reasignar cada factura en `DRAFT`, `UPLOADED`, `VALIDATING`, `VALIDATION_FAILED`, `PREVALIDATED` o `REQUIRES_CORRECTION`:
- a `REQUIRES_CORRECTION`, si su última revisión con decisión distinta de `COMMENT` es `REQUIRES_CORRECTION`;
- en otro caso, a `UPLOADED` si tiene completos los archivos obligatorios vigentes para el origen de su proveedor, y a `DRAFT` si no.

Cada factura cuyo estatus cambia SHALL recibir un registro de auditoría `STATUS_MIGRATED` con el estatus anterior y el nuevo. Los demás estatus SHALL conservarse. El downgrade SHALL restaurar el catálogo anterior sin revertir los estatus.

#### Scenario: Prevalidada completa
- **WHEN** se migra una factura `PREVALIDATED` con sus obligatorios completos
- **THEN** queda en `UPLOADED` y existe un registro `STATUS_MIGRATED` de `PREVALIDATED` a `UPLOADED`

#### Scenario: Validación fallida sin Vo.Bo.
- **WHEN** se migra una factura `REQUIRES_CORRECTION` sin revisión del PMO y sin Vo.Bo.
- **THEN** queda en `DRAFT`

#### Scenario: Devuelta por el PMO
- **WHEN** se migra una factura `PREVALIDATED` cuya última decisión del PMO fue `REQUIRES_CORRECTION`
- **THEN** queda en `REQUIRES_CORRECTION`

#### Scenario: Estatus del PMO intactos
- **WHEN** se migra una factura `ACCEPTED`
- **THEN** conserva su estatus y no recibe registro `STATUS_MIGRATED`

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

