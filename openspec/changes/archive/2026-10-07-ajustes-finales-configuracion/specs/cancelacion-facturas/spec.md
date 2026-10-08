## MODIFIED Requirements

### Requirement: Acuse obligatorio y confirmación
Antes de escribir el archivo, el sistema SHALL responder HTTP 409 con "La factura ya está cancelada" si la factura ya lo está, o con "Una factura pagada no se puede cancelar" si está "Pagada". En los demás casos SHALL rechazar con HTTP 400, sin cambiar la factura, en este orden:
- sin la confirmación: "Confirme la cancelación";
- sin archivo: "Cargue el <nombre del tipo>";
- con una extensión que no admite el tipo: "Formato no admitido para <nombre del tipo>. Formatos admitidos: <formatos>".

El acuse SHALL exigirse con el nombre y los formatos de su tipo en Archivos mínimos (`CANCELLATION_ACK`, inicialmente "Acuse de cancelación" con PDF y XML) mientras el tipo esté activo. Si el Administrador eliminó el tipo, la sección "Cancelar factura" MUST NOT mostrar el campo del archivo, y la cancelación SHALL proceder sólo con la confirmación, sin guardar ningún archivo.

El archivo SHALL pasar las validaciones de contenido, tamaño y nombre de almacenamiento de cualquier carga; un contenido que no corresponde a su extensión SHALL rechazarse con HTTP 400. El XML del acuse MUST NOT procesarse como CFDI. Un rechazo SHALL volver a mostrar el detalle con el error en la sección "Cancelar factura".

#### Scenario: Cancelar sin acuse
- **WHEN** el proveedor confirma la cancelación sin adjuntar el acuse
- **THEN** la respuesta es HTTP 400 con "Cargue el Acuse de cancelación" y la factura no cambia

#### Scenario: Sin confirmación
- **WHEN** el proveedor adjunta el acuse sin marcar la confirmación
- **THEN** la respuesta es HTTP 400 con "Confirme la cancelación" y no se escribe ningún archivo

#### Scenario: Formato no admitido
- **WHEN** el proveedor adjunta `acuse.png`
- **THEN** la respuesta es HTTP 400 con "Formato no admitido para Acuse de cancelación. Formatos admitidos: PDF, XML"

#### Scenario: Acuse XML del SAT
- **WHEN** el proveedor adjunta el acuse XML que entrega el SAT, que no es un CFDI
- **THEN** la cancelación procede y el acuse se guarda sin intentar leerlo como CFDI

#### Scenario: Cancelar una factura pagada
- **WHEN** el proveedor envía `POST /invoices/{id}/cancel` con su acuse sobre una factura "Pagada"
- **THEN** la respuesta es HTTP 409 con "Una factura pagada no se puede cancelar", no se escribe ningún archivo y la factura sigue "Pagada"

#### Scenario: Tipo del acuse eliminado
- **WHEN** el Administrador eliminó "Acuse de cancelación" y el proveedor confirma la cancelación de una factura "Cargada" sin archivo
- **THEN** la factura queda "Cancelada" y no se guarda ningún documento
