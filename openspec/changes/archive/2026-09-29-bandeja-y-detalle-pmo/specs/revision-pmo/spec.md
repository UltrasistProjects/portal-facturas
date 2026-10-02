## ADDED Requirements

### Requirement: Bandeja del PMO
Para los roles `INTERNAL` y `ADMIN`, `GET /invoices` sin el parámetro `status` SHALL mostrar sólo las facturas "Enviada" (`UNDER_REVIEW`). Siempre que el filtro de estatus de `INTERNAL` o `ADMIN` sea "Enviada", por omisión o elegido, el listado SHALL ordenarse por `submitted_at` ascendente y después por `id`, también en las páginas siguientes. Con cualquier otro estatus o con "Todos los estados" (`status` vacío), SHALL ordenarse por `created_at` descendente, como hoy. El formulario de filtros SHALL enviar siempre `status` y mostrar seleccionado "Enviada" cuando se abre la bandeja. El listado del rol `PROVIDER` MUST NOT cambiar: sin `status` muestra todas sus facturas, ordenadas por `created_at` descendente.

#### Scenario: Bandeja inicial
- **WHEN** hay tres facturas "Enviada" enviadas el 1, 2 y 3 de septiembre y el PMO abre "Facturas"
- **THEN** ve sólo facturas "Enviada", la enviada el 1 de septiembre primero, y el filtro de estatus muestra "Enviada"

#### Scenario: Segunda página de la bandeja
- **WHEN** hay 30 facturas "Enviada" y el PMO pasa a la página 2 de la bandeja
- **THEN** ve las 5 enviadas más recientemente, en orden de envío ascendente

#### Scenario: Todos los estados
- **WHEN** el PMO elige "Todos los estados" y filtra
- **THEN** ve facturas de cualquier estatus, las creadas más recientemente primero

#### Scenario: Proveedor sin bandeja
- **WHEN** un proveedor abre "Facturas" sin filtros
- **THEN** ve todas sus facturas en cualquier estatus, las más recientes primero

### Requirement: Columnas del listado para el PMO
Para `INTERNAL` y `ADMIN`, cada fila del listado SHALL mostrar el proveedor y su identificador fiscal, el folio interno y el número de factura, el origen ("Nacional" o "Internacional"), el proyecto, la fecha de envío (o "—" si no se ha enviado), el monto con su moneda, el score, el número de advertencias (`WARNING`) de la última validación y el estatus. El conteo de advertencias SHALL obtenerse con una sola consulta agregada para toda la página, de modo que el número de consultas no dependa del número de facturas.

#### Scenario: Fila de una factura internacional enviada
- **WHEN** una factura internacional "Enviada" por `$1,000.00 USD` tiene dos resultados `WARNING` y el PMO abre la bandeja
- **THEN** su fila muestra "Internacional", la fecha de envío, "$1,000.00 USD" y "2 advertencias"

#### Scenario: Consultas constantes
- **WHEN** el PMO renderiza una página de 25 facturas con resultados de validación
- **THEN** el número de consultas SQL es el mismo que con una página de 5 facturas

### Requirement: Datos del proveedor en el detalle
El detalle de la factura SHALL mostrar a `INTERNAL` y `ADMIN` un bloque "Proveedor" con la razón social, el origen, el identificador fiscal (RFC, o país e identificador extranjero), el correo y el estatus del proveedor.

#### Scenario: Proveedor internacional
- **WHEN** el PMO abre el detalle de la demo INV-2026-0042
- **THEN** el bloque "Proveedor" muestra "Global Data Services Inc. (DEMO)", "Internacional", "US 98-7654321", "proveedor3@poc.local" y "Autorizado"

### Requirement: Historial de revisión en el detalle
El detalle de la factura SHALL mostrar a `INTERNAL` y `ADMIN` la sección "Historial", en orden cronológico, con:
- cada envío a validación del proveedor (auditoría `INVOICE_SUBMITTED`): fecha y usuario;
- cada revisión del PMO (tabla `reviews`): fecha, decisión con la etiqueta de su estatus ("Autorizada", "Rechazada", "Observaciones" o "Comentario"), observaciones y revisor.

Sin eventos, SHALL mostrar "Sin envíos ni revisiones". El rol `PROVIDER` MUST NOT ver esta sección en esta versión (HU-17 define su seguimiento).

#### Scenario: Factura devuelta y reenviada
- **WHEN** una factura se envió, el PMO la marcó con observaciones "Falta el Vo.Bo." y el proveedor la reenvió
- **THEN** el historial muestra, en ese orden, el primer envío, la revisión "Observaciones" con "Falta el Vo.Bo." y el nombre del revisor, y el segundo envío

#### Scenario: Proveedor
- **WHEN** el proveedor abre el detalle de su factura
- **THEN** no ve la sección "Historial"
