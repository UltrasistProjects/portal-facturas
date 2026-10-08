## MODIFIED Requirements

### Requirement: Reglas de estado centralizadas en el servicio de facturas
Las reglas de flujo SHALL residir en `invoice_service`, en el servicio de envío y en el de revisión, y los routers MUST limitarse a invocarlas:
- el conjunto de estados editables (`DRAFT`, `UPLOADED`, `REQUIRES_CORRECTION`);
- el recálculo de "Borrador" y "Cargada";
- el envío y su resultado;
- la decisión del PMO y la prohibición de aceptar con bloqueos críticos;
- el resumen de validación, que SHALL reutilizar `calculate_score`.

#### Scenario: Aceptación con bloqueo crítico
- **WHEN** un usuario INTERNAL envía la decisión `ACCEPTED` sobre una factura en `UNDER_REVIEW` con un resultado `FAIL` de severidad `CRITICAL`
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

Las únicas transiciones permitidas SHALL ser:
- `DRAFT → UPLOADED` y `UPLOADED → DRAFT`, que asigna el sistema según los archivos obligatorios;
- `UPLOADED → UNDER_REVIEW` y `REQUIRES_CORRECTION → UNDER_REVIEW`, por un envío que procede;
- `UNDER_REVIEW → ACCEPTED | REJECTED | REQUIRES_CORRECTION`, por la decisión del PMO.

"Autorizada" y "Rechazada" son estatus finales en el MVP: los pasos de ClickBalance del PoC se retiraron (HU-20).

Cualquier otra transición SHALL rechazarse con HTTP 409 sin cambios. Cada transición SHALL auditarse como `STATUS_CHANGED` con el estatus anterior y el nuevo. Sólo la decisión del PMO SHALL asignar `REQUIRES_CORRECTION`.

#### Scenario: Etiquetas en el listado
- **WHEN** un usuario abre el listado de facturas
- **THEN** el filtro de estatus ofrece "Borrador", "Cargada", "Enviada", "Autorizada", "Rechazada" y "Observaciones", y ninguna otra opción

#### Scenario: El PMO pide correcciones
- **WHEN** un usuario INTERNAL envía la decisión `REQUIRES_CORRECTION` sobre una factura "Enviada"
- **THEN** la factura queda en "Observaciones"

#### Scenario: Una validación fallida no asigna Observaciones
- **WHEN** el proveedor envía una factura "Cargada" cuyo XML falla XML-002
- **THEN** la factura sigue "Cargada"

#### Scenario: Autorizada es final
- **WHEN** se intenta cualquier transición desde una factura "Autorizada"
- **THEN** la respuesta es HTTP 409 y la factura sigue "Autorizada"

#### Scenario: Migración de ClickBalance
- **WHEN** se aplica `0011_retire_clickbalance` sobre una base con facturas "Lista para ClickBalance" y "Cargada a ClickBalance"
- **THEN** quedan "Autorizada" y cada una tiene un registro `STATUS_MIGRATED` con el estatus anterior y el nuevo
