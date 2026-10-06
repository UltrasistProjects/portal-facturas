# cancelacion-facturas Specification

## Purpose
Cancelación de la factura por el proveedor (HU-14, RF-09): acuse de cancelación obligatorio, estatus final "Cancelada" con la fecha límite de 72 horas para que Recepción de Facturas acepte la cancelación ante el SAT, correo a ese buzón con su reenvío y la visualización de la factura cancelada en el detalle.
## Requirements
### Requirement: Cancelación exclusiva del proveedor
El detalle de una factura que no está "Cancelada" ni "Pagada" SHALL ofrecer al rol `Proveedor` la sección "Cancelar factura" con el campo del "Acuse de cancelación" (PDF o XML) y la confirmación "Confirmo que la factura se canceló y adjunto su acuse". `POST /invoices/{invoice_id}/cancel` SHALL exigir CSRF y el rol `Proveedor` (HTTP 403 para `PMO` y `Administrador`); una factura de otro proveedor SHALL responder HTTP 404. Los demás roles MUST NOT ver la sección.

#### Scenario: Sección para el proveedor
- **WHEN** el proveedor abre el detalle de su factura "Enviada"
- **THEN** ve "Cancelar factura" con el campo del acuse y la confirmación

#### Scenario: Sin cancelación en una factura pagada
- **WHEN** el proveedor abre el detalle de su factura "Pagada"
- **THEN** no ve la sección "Cancelar factura"

#### Scenario: PMO sin cancelación
- **WHEN** el PMO abre el detalle de una factura o envía `POST /invoices/{id}/cancel`
- **THEN** no ve la sección y la petición responde HTTP 403 sin cambios

#### Scenario: Factura de otro proveedor
- **WHEN** un proveedor envía la cancelación de una factura de otro proveedor
- **THEN** la respuesta es HTTP 404 y la factura no cambia

### Requirement: Acuse obligatorio y confirmación
Antes de escribir el archivo, el sistema SHALL responder HTTP 409 con "La factura ya está cancelada" si la factura ya lo está, o con "Una factura pagada no se puede cancelar" si está "Pagada". En los demás casos SHALL rechazar con HTTP 400, sin cambiar la factura, en este orden:
- sin la confirmación: "Confirme la cancelación";
- sin archivo: "Cargue el Acuse de cancelación";
- con una extensión distinta de PDF o XML: "Formato no admitido para Acuse de cancelación. Formatos admitidos: PDF, XML".

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

### Requirement: Registro de la cancelación
Con el acuse y la confirmación válidos, el sistema SHALL bloquear la fila de la factura y, en una sola transacción:
- responder HTTP 409 con "La factura ya está cancelada" si ya lo está, o con "Una factura pagada no se puede cancelar" si está "Pagada";
- guardar el acuse como documento vigente de tipo `CANCELLATION_ACK`;
- pasar la factura a "Cancelada" (`CANCELLED`) desde cualquier otro estatus, auditando `STATUS_CHANGED`;
- registrar `cancelled_at`, `cancelled_by` y `cancellation_deadline = cancelled_at + 72 horas`;
- auditar `INVOICE_CANCELLED` con el estatus anterior, el id del acuse y la fecha límite.

"Cancelada" SHALL ser final: la factura MUST NOT admitir documentos, verificación, envío, decisión del PMO ni otra cancelación, y MUST NOT aparecer en la bandeja del PMO.

#### Scenario: Cancelar una factura enviada
- **WHEN** el proveedor cancela con su acuse PDF una factura "Enviada" el 25/09/2026 a las 10:30 (hora de negocio)
- **THEN** la factura queda "Cancelada" con `cancelled_by` del proveedor y fecha límite 28/09/2026 10:30, el acuse aparece en sus documentos y la factura ya no está en la bandeja del PMO

#### Scenario: Cancelar una factura autorizada
- **WHEN** el proveedor cancela una factura "Autorizada"
- **THEN** la factura queda "Cancelada"

#### Scenario: Cancelación repetida
- **WHEN** el proveedor envía la cancelación de una factura ya "Cancelada"
- **THEN** la respuesta es HTTP 409 con "La factura ya está cancelada" y no se agrega ningún documento

#### Scenario: Pago y cancelación simultáneos
- **WHEN** el PMO marca como pagada una factura "Autorizada" mientras el proveedor la cancela
- **THEN** sólo una de las dos operaciones se aplica y la otra recibe HTTP 409, sin documentos ni correos de la operación rechazada

#### Scenario: Factura cancelada no se edita ni se envía
- **WHEN** el proveedor intenta cargar un documento o enviar una factura "Cancelada"
- **THEN** la respuesta es HTTP 409 y la factura no cambia

### Requirement: Correo de cancelación a Recepción de Facturas
Después de confirmar la cancelación, el sistema SHALL enviar el correo `INVOICE_CANCELLED` al buzón "Recepción de Facturas" y a las copias del evento, con `numero_factura`, `proveedor`, `fecha_limite_cancelacion`, `folio_interno`, `monto` (total con su moneda) y `fecha_estatus` (`cancelled_at`), registrado en la bitácora con la entidad `Invoice` y el id de la factura. Un envío fallido MUST NOT revertir la cancelación. El detalle SHALL mostrar al proveedor "Se notificó a Recepción de Facturas" o "No se pudo notificar a Recepción de Facturas", sin las direcciones del buzón.

#### Scenario: Aviso con la fecha límite
- **WHEN** con `MAIL_BACKEND=file` el proveedor "Tecnologia Integral del Centro SA de CV" cancela la factura "A-2001" el 25/09/2026 a las 10:30 (hora de negocio)
- **THEN** el buzón de salida tiene un correo para `recepcionfacturas@ultrasist.com.mx` con el asunto "Cancelación de la factura A-2001 de Tecnologia Integral del Centro SA de CV" y el texto "Por favor acepte la “Cancelación” antes del 28/09/2026 10:30.", y el proveedor ve "Se notificó a Recepción de Facturas"

#### Scenario: Servidor de correo caído
- **WHEN** el servidor SMTP rechaza la conexión y el proveedor cancela
- **THEN** la factura queda "Cancelada", la bitácora registra el envío como `FAILED`, el proveedor ve "No se pudo notificar a Recepción de Facturas" y el PMO ve "Reenviar notificación" en el detalle

### Requirement: Factura cancelada en el detalle
El detalle de una factura "Cancelada" SHALL mostrar a todos los roles "Cancelada el <fecha>. Recepción de Facturas debe aceptar la cancelación antes del <fecha límite>." con las fechas en la zona de negocio (`dd/mm/aaaa HH:MM`), y el acuse en la lista de documentos con el nombre "Acuse de cancelación", visible y descargable. MUST NOT mostrar la sección "Cancelar factura", el panel "Decisión" ni las acciones de documentos y envío.

#### Scenario: Aviso de factura cancelada
- **WHEN** el PMO abre el detalle de una factura cancelada el 25/09/2026 a las 10:30
- **THEN** ve "Cancelada el 25/09/2026 10:30. Recepción de Facturas debe aceptar la cancelación antes del 28/09/2026 10:30." y el "Acuse de cancelación" entre los documentos

