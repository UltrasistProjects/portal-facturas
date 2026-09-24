## ADDED Requirements

### Requirement: Alta de factura con datos validados
El alta de factura SHALL validar los datos del formulario con el esquema `InvoiceCreate` antes de persistir:
- `invoice_number` de 1 a 100 caracteres;
- `service_period` con formato `MM/AAAA` y mes entre 01 y 12;
- `project_name` de 2 a 200 caracteres.

Los errores SHALL mostrarse en el mismo formulario con HTTP 400. Un número de factura repetido para el mismo proveedor SHALL rechazarse con un mensaje claro, sin HTTP 500.

#### Scenario: Periodo inválido
- **WHEN** un proveedor crea una factura con `service_period = "13/2026"`
- **THEN** la respuesta es HTTP 400, el formulario muestra el error del periodo y no se crea la factura

#### Scenario: Número de factura repetido
- **WHEN** un proveedor crea una factura con un `invoice_number` que ya usó en otra factura propia
- **THEN** la respuesta es HTTP 409 con el mensaje "Ya existe una factura con ese número para el proveedor" y no se crea la factura

### Requirement: Folio interno sin colisiones
El folio interno SHALL derivarse del identificador asignado por la base de datos a la factura, dentro de la misma transacción del alta, con el formato `FAC-{AAAA}-{id:05d}`. `AAAA` es el año de la fecha de creación en la zona horaria de negocio.

#### Scenario: Altas concurrentes
- **WHEN** dos altas de factura se procesan de forma concurrente
- **THEN** ambas se crean con folios distintos y ninguna falla por colisión de folio

#### Scenario: Año según zona de negocio
- **WHEN** una factura se crea el 31 de diciembre de 2026 a las 20:00 en `America/Mexico_City` (1 de enero de 2027 en UTC)
- **THEN** su folio comienza con `FAC-2026-`

### Requirement: Reglas de estado centralizadas en el servicio de facturas
Las reglas de flujo SHALL residir en `invoice_service` y los routers MUST limitarse a invocarlas:
- el conjunto de estados editables (`DRAFT`, `REQUIRES_CORRECTION`, `VALIDATION_FAILED`);
- la prohibición de aceptar con bloqueos críticos;
- el siguiente estado de ClickBalance;
- el resumen de validación, que SHALL reutilizar `calculate_score`.

#### Scenario: Aceptación con bloqueo crítico
- **WHEN** un usuario INTERNAL envía la decisión `ACCEPTED` sobre una factura en `UNDER_REVIEW` con un resultado `FAIL` de severidad `CRITICAL`
- **THEN** la respuesta es HTTP 409 "No se puede aceptar con bloqueos criticos", la factura sigue en `UNDER_REVIEW` y no se registra revisión

#### Scenario: Carga en estado no editable
- **WHEN** un proveedor sube un documento a una factura en `UNDER_REVIEW`
- **THEN** la respuesta es HTTP 409 y no se almacena el archivo

#### Scenario: Resumen del detalle
- **WHEN** se muestra el detalle de una factura validada
- **THEN** los contadores de aprobadas, advertencias, errores y bloqueos coinciden con los calculados por `calculate_score` para los mismos resultados

### Requirement: Listado de facturas filtrado y paginado en la base de datos
El listado SHALL aplicar la búsqueda, el filtro por estado, el alcance por proveedor (rol PROVIDER), el orden por `created_at DESC` y la paginación (25 por página) en la consulta SQL, cargando el proveedor asociado sin consultas adicionales por fila. La búsqueda SHALL comparar, sin distinguir mayúsculas, contra folio interno, número de factura, proyecto y razón social del proveedor, y SHALL tratar `%` y `_` como caracteres literales.

#### Scenario: Búsqueda por razón social
- **WHEN** un usuario INTERNAL busca `tecnologia integral`
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

### Requirement: Indicadores del tablero agregados en la base de datos
El tablero SHALL calcular el conteo por estado con `COUNT ... GROUP BY status` y el monto total con `SUM` sobre centavos, respetando el alcance por proveedor. MUST NOT cargar todas las facturas en memoria.

#### Scenario: KPIs del proveedor
- **WHEN** un PROVIDER abre el tablero
- **THEN** los conteos y el monto total corresponden sólo a sus facturas y el monto es exacto al centavo

### Requirement: Límite transaccional en la capa HTTP
Los servicios (`run_validation`, `transition_invoice`, `audit` y los demás) MUST NOT ejecutar `commit`. Cada endpoint mutable SHALL confirmar o revertir su transacción completa.

#### Scenario: Fallo posterior a la validación
- **WHEN** `run_validation` termina y una operación posterior dentro del mismo endpoint falla
- **THEN** no persisten ni los resultados de validación ni los cambios de estado de esa petición

### Requirement: Registro de auditoría paginado
La vista `/admin/audit` SHALL paginar las entradas (50 por página, más recientes primero) y SHALL permitir llegar a cualquier entrada histórica.

#### Scenario: Entradas antiguas accesibles
- **WHEN** existen 600 entradas de auditoría y un ADMIN navega a la última página
- **THEN** ve las entradas más antiguas
