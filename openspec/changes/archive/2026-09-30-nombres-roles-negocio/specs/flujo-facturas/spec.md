## MODIFIED Requirements

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
