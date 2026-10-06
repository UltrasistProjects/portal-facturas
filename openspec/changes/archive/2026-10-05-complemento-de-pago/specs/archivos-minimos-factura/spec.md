## MODIFIED Requirements

### Requirement: Archivos fijos por origen
Estos niveles SHALL ser fijos:
- `INVOICE_XML` e `INVOICE_PDF`: Obligatorio para Nacional y No aplica para Internacional;
- `FOREIGN_INVOICE`: No aplica para Nacional y Obligatorio para Internacional;
- `CANCELLATION_ACK`: No aplica para ambos orígenes, con el motivo "Se carga al cancelar la factura";
- `PAYMENT_COMPLEMENT_XML` y `PAYMENT_COMPLEMENT_PDF` ("Complemento de pago"): Opcional para Nacional y No aplica para Internacional, con el motivo "Se carga después del pago de la factura".

La página de configuración SHALL mostrar esos niveles como texto con el ícono de candado y su motivo, sin selector. Una petición que intente cambiarlos SHALL rechazarse con HTTP 409 sin guardar ningún cambio.

#### Scenario: Niveles fijos en la pantalla
- **WHEN** el Administrador abre la configuración
- **THEN** la fila "XML del CFDI" muestra "Obligatorio" con candado en Nacional y "No aplica" con candado en Internacional, con el motivo "El proveedor nacional factura con CFDI", y no tiene selectores

#### Scenario: Complemento de pago en la configuración
- **WHEN** el Administrador abre la configuración
- **THEN** las filas "Complemento de pago (XML)" y "Complemento de pago (PDF)" muestran "Opcional" con candado en Nacional y "No aplica" con candado en Internacional, con el motivo "Se carga después del pago de la factura"

#### Scenario: Petición manipulada
- **WHEN** la petición trae `OPTIONAL` como nivel Nacional de `INVOICE_XML`, junto con otros cambios válidos
- **THEN** la respuesta es HTTP 409 con el mensaje "XML del CFDI tiene un nivel fijo para proveedores nacionales" y no se guarda ningún cambio

#### Scenario: Complemento exigido por petición manipulada
- **WHEN** la petición trae `REQUIRED` como nivel Nacional de `PAYMENT_COMPLEMENT_XML`
- **THEN** la respuesta es HTTP 409 con el mensaje "Complemento de pago (XML) tiene un nivel fijo para proveedores nacionales" y no se guarda ningún cambio

#### Scenario: Acuse de cancelación fuera de la carga documental
- **WHEN** el proveedor abre la carga documental de una factura
- **THEN** no se ofrece "Acuse de cancelación" y la prevalidación no lo exige

### Requirement: Carga documental según el origen del proveedor
La página de carga documental de una factura SHALL ofrecer sólo los tipos activos cuyo nivel para el origen del proveedor de la factura sea Obligatorio u Opcional, cada uno con su nombre y sus formatos. En una factura "Pagada" que requiere Complemento de Pago, SHALL ofrecer sólo "Complemento de pago (XML)" y "Complemento de pago (PDF)" (spec `pago-facturas`). `POST /invoices/{invoice_id}/documents` SHALL rechazar con HTTP 400, antes de escribir el archivo:
- un tipo que no se ofrece para esa factura, con el mensaje "El tipo de documento no aplica a esta factura". En una factura "Pagada", un tipo distinto del Complemento de pago se rechaza con HTTP 409, como indica la spec `pago-facturas`;
- un archivo cuya extensión no corresponde a los formatos del tipo, con el mensaje "Formato no admitido para <nombre>. Formatos admitidos: <formatos>";
- un XML del Complemento de pago que no es un CFDI de tipo `P` o que no relaciona el UUID de la factura (spec `pago-facturas`).

Las verificaciones existentes de contenido, tamaño y estado editable SHALL mantenerse. La única excepción al estado editable es la carga del Complemento de Pago en una factura "Pagada" que lo requiere.

#### Scenario: Tipos ofrecidos a un proveedor nacional
- **WHEN** con la configuración inicial se abre la carga documental de una factura de un proveedor nacional
- **THEN** se ofrecen XML del CFDI, PDF del CFDI, Orden de compra, Vo.Bo. del líder de proyecto, Contrato, Anexo del contrato, Complemento de pago (XML), Complemento de pago (PDF) y Documentación adicional, y no se ofrece Invoice (PDF)

#### Scenario: Tipos ofrecidos a un proveedor internacional
- **WHEN** con la configuración inicial se abre la carga documental de una factura de un proveedor internacional
- **THEN** se ofrecen Invoice (PDF), Orden de compra, Vo.Bo. del líder de proyecto, Contrato, Anexo del contrato y Documentación adicional, y no se ofrecen el XML ni el PDF del CFDI ni los complementos de pago

#### Scenario: Tipos ofrecidos en una factura pagada
- **WHEN** el proveedor abre la carga documental de su factura nacional PPD "Pagada"
- **THEN** sólo se ofrecen Complemento de pago (XML) y Complemento de pago (PDF), y la página no indica archivos obligatorios faltantes

#### Scenario: Tipo que no aplica
- **WHEN** se envía un documento con `document_type = INVOICE_XML` a una factura de un proveedor internacional
- **THEN** la respuesta es HTTP 400 con el mensaje "El tipo de documento no aplica a esta factura" y no se escribe ningún archivo en `storage/`

#### Scenario: Tipo inexistente
- **WHEN** se envía un documento con `document_type = OTRO`
- **THEN** la respuesta es HTTP 400 con el mensaje "El tipo de documento no aplica a esta factura" y no se escribe ningún archivo en `storage/`

#### Scenario: Formato no admitido por el tipo
- **WHEN** se envía `factura.png` como `INVOICE_PDF` a una factura de un proveedor nacional
- **THEN** la respuesta es HTTP 400 con el mensaje "Formato no admitido para PDF del CFDI. Formatos admitidos: PDF" y no se escribe ningún archivo en `storage/`
