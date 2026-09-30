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
- **WHEN** un usuario INTERNAL envía la decisión `REQUIRES_CORRECTION` sobre una factura "Enviada"
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
