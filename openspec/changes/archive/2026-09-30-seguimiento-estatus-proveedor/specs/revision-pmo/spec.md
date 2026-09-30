## MODIFIED Requirements

### Requirement: Historial de revisión en el detalle
El detalle de la factura SHALL mostrar el historial en orden cronológico: a `INTERNAL` y `ADMIN` en la sección "Historial" y al `PROVIDER` en la sección "Seguimiento" (HU-17), con:
- cada envío a validación del proveedor (auditoría `INVOICE_SUBMITTED`): fecha y usuario;
- cada revisión del PMO (tabla `reviews`): fecha, decisión con la etiqueta de su estatus ("Autorizada", "Rechazada", "Observaciones" o "Comentario") y observaciones;
- la cancelación (auditoría `INVOICE_CANCELLED`): fecha, "Cancelada", usuario y "Fecha límite de aceptación: <fecha límite>" en la zona de negocio.

A `INTERNAL` y `ADMIN` SHALL mostrar el nombre del revisor. Al `PROVIDER` SHALL mostrar "PMO" en lugar del nombre del revisor (EP-02 DT-07) y MUST NOT mostrar las revisiones `COMMENT` (comentarios internos del PoC). Sin eventos, SHALL mostrar "Sin envíos ni revisiones".

#### Scenario: Factura devuelta y reenviada
- **WHEN** una factura se envió, el PMO la marcó con observaciones "Falta el Vo.Bo." y el proveedor la reenvió
- **THEN** el historial muestra, en ese orden, el primer envío, la revisión "Observaciones" con "Falta el Vo.Bo." y el nombre del revisor, y el segundo envío

#### Scenario: Seguimiento del proveedor
- **WHEN** el proveedor abre el detalle de esa misma factura
- **THEN** ve la sección "Seguimiento" con los mismos tres eventos, la revisión atribuida a "PMO" y sin el nombre del revisor

#### Scenario: Comentario interno
- **WHEN** la factura tiene una revisión `COMMENT` del PoC
- **THEN** el PMO la ve como "Comentario" y el proveedor no la ve

#### Scenario: Cancelación en el historial
- **WHEN** el proveedor canceló la factura el 25/09/2026 a las 10:30 (hora de negocio)
- **THEN** el historial termina con "Cancelada", el usuario del proveedor y "Fecha límite de aceptación: 28/09/2026 10:30"
