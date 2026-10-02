## MODIFIED Requirements

### Requirement: Listado de facturas filtrado y paginado en la base de datos
El listado SHALL aplicar la búsqueda, el filtro por estado, el filtro por origen del proveedor (`NATIONAL` o `INTERNATIONAL`; un valor desconocido se ignora), el alcance por proveedor (rol PROVIDER), el orden y la paginación (25 por página) en la consulta SQL, cargando el proveedor asociado sin consultas adicionales por fila. El orden SHALL ser `created_at DESC`, salvo en la bandeja del PMO (spec `revision-pmo`), donde las facturas "Enviada" se ordenan por `submitted_at` ascendente. La búsqueda SHALL comparar, sin distinguir mayúsculas, contra folio interno, número de factura, proyecto y razón social del proveedor, y SHALL tratar `%` y `_` como caracteres literales.

#### Scenario: Búsqueda por razón social
- **WHEN** un usuario INTERNAL busca `tecnologia integral` con "Todos los estados"
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
- **WHEN** un PROVIDER consulta el listado con cualquier filtro
- **THEN** sólo aparecen facturas de su proveedor

#### Scenario: Filtro por origen
- **WHEN** un usuario INTERNAL filtra por origen "Internacional" con "Todos los estados"
- **THEN** sólo aparecen facturas de proveedores internacionales
