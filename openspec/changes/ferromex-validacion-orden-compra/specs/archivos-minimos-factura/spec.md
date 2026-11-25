## MODIFIED Requirements

### Requirement: Catálogo de tipos de documento de factura
El sistema SHALL mantener un catálogo persistente de los tipos de documento que se cargan en una factura. Cada tipo SHALL tener:
- una clave inmutable, que es el valor que se guarda en `documents.document_type`;
- un nombre en español y una descripción opcional, que se muestran al proveedor;
- los formatos admitidos, entre `PDF` (`.pdf`), `PNG` (`.png`), `JPEG` (`.jpg`, `.jpeg`), `XML` (`.xml`) y `TXT` (`.txt`);
- si es un tipo del sistema o uno definido por el Administrador;
- si está activo;
- un nivel de exigencia para proveedores nacionales y otro para internacionales: `REQUIRED` ("Obligatorio"), `OPTIONAL` ("Opcional") o `NOT_APPLICABLE` ("No aplica").

El catálogo SHALL incluir estos tipos del sistema con estos valores iniciales en la rama `ferromex` (clave · nombre · formatos · Nacional · Internacional):
- `INVOICE_XML` · XML del CFDI · XML · Opcional · No aplica;
- `INVOICE_PDF` · PDF del CFDI · PDF · Obligatorio · No aplica;
- `FOREIGN_INVOICE` · Invoice (PDF) · PDF · No aplica · Obligatorio;
- `PURCHASE_ORDER` · Orden de compra · PDF, PNG, JPEG, TXT · No aplica · No aplica (la orden de compra es una entidad del portal, spec `orden-compra`);
- `APPROVAL` · Vo.Bo. del líder de proyecto · PDF, PNG, JPEG, TXT · Obligatorio · Obligatorio;
- `CONTRACT` · Contrato · PDF, PNG, JPEG, TXT · No aplica · No aplica;
- `CONTRACT_ANNEX` · Anexo del contrato · PDF, PNG, JPEG, TXT · No aplica · No aplica;
- `PAYMENT_COMPLEMENT_XML` · Complemento de pago (XML) · XML · Opcional · No aplica;
- `PAYMENT_COMPLEMENT_PDF` · Complemento de pago (PDF) · PDF · Opcional · No aplica;
- `ADDITIONAL` · Documentación adicional · PDF, PNG, JPEG, XML, TXT · Opcional · Opcional;
- `CANCELLATION_ACK` · Acuse de cancelación · PDF, XML · No aplica · No aplica (se carga sólo al cancelar la factura, HU-14).

La migración `0023_ferromex_purchase_orders` SHALL fijar esos niveles en `INVOICE_XML`, `PURCHASE_ORDER`, `CONTRACT` y `CONTRACT_ANNEX` sin cambiar los demás tipos ni los documentos ya cargados.

#### Scenario: Catálogo inicial tras la migración
- **WHEN** se aplica la migración `0023_ferromex_purchase_orders` sobre una base con facturas y documentos existentes
- **THEN** el catálogo contiene los 11 tipos del sistema con los niveles de esta rama (XML del CFDI Opcional · No aplica; Orden de compra, Contrato y Anexo del contrato No aplica · No aplica), y cada documento existente conserva su `document_type`

#### Scenario: Nombres en español
- **WHEN** un proveedor abre la carga documental de una factura
- **THEN** los tipos se muestran por su nombre del catálogo (por ejemplo "PDF del CFDI" y "Vo.Bo. del líder de proyecto"), no por su clave

#### Scenario: Nombres en el detalle de la factura
- **WHEN** se abre el detalle de una factura con documentos cargados
- **THEN** cada documento se muestra con el nombre de su tipo en el catálogo, aunque el tipo esté inactivo o ya no aplique al origen del proveedor

### Requirement: Carga documental según el origen del proveedor
La página de carga documental de una factura SHALL ofrecer sólo los tipos activos cuyo nivel para el origen del proveedor de la factura sea Obligatorio u Opcional, cada uno con su nombre y sus formatos. En una factura "Pagada" que requiere Complemento de Pago, SHALL ofrecer sólo "Complemento de pago (XML)" y "Complemento de pago (PDF)" (spec `pago-facturas`). `POST /invoices/{invoice_id}/documents` SHALL rechazar con HTTP 400, antes de escribir el archivo:
- un tipo que no se ofrece para esa factura, con el mensaje "El tipo de documento no aplica a esta factura". En una factura "Pagada", un tipo distinto del Complemento de pago se rechaza con HTTP 409, como indica la spec `pago-facturas`;
- un archivo cuya extensión no corresponde a los formatos del tipo, con el mensaje "Formato no admitido para <nombre>. Formatos admitidos: <formatos>";
- un XML del Complemento de pago que no es un CFDI de tipo `P` o que no relaciona el UUID de la factura (spec `pago-facturas`).

Las verificaciones existentes de contenido, tamaño y estado editable SHALL mantenerse. La única excepción al estado editable es la carga del Complemento de Pago en una factura "Pagada" que lo requiere. El reemplazo del PDF o del XML del CFDI de una factura nacional SHALL volver a extraer sus datos (spec `registro-factura-extraccion`).

#### Scenario: Tipos ofrecidos a un proveedor nacional
- **WHEN** con la configuración inicial se abre la carga documental de una factura de un proveedor nacional
- **THEN** se ofrecen XML del CFDI, PDF del CFDI, Vo.Bo. del líder de proyecto, Complemento de pago (XML), Complemento de pago (PDF) y Documentación adicional, y no se ofrecen Invoice (PDF), Orden de compra, Contrato ni Anexo del contrato

#### Scenario: Tipos ofrecidos a un proveedor internacional
- **WHEN** con la configuración inicial se abre la carga documental de una factura de un proveedor internacional
- **THEN** se ofrecen Invoice (PDF), Vo.Bo. del líder de proyecto y Documentación adicional, y no se ofrecen el XML ni el PDF del CFDI, los complementos de pago, la orden de compra, el contrato ni el anexo

#### Scenario: Tipos ofrecidos en una factura pagada
- **WHEN** el proveedor abre la carga documental de su factura nacional PPD "Pagada"
- **THEN** sólo se ofrecen Complemento de pago (XML) y Complemento de pago (PDF), y la página no indica archivos obligatorios faltantes

#### Scenario: Tipo que no aplica
- **WHEN** se envía un documento con `document_type = INVOICE_XML` a una factura de un proveedor internacional
- **THEN** la respuesta es HTTP 400 con el mensaje "El tipo de documento no aplica a esta factura" y no se escribe ningún archivo en `storage/`

#### Scenario: Orden de compra como archivo
- **WHEN** con la configuración inicial se envía un documento con `document_type = PURCHASE_ORDER` a una factura nacional
- **THEN** la respuesta es HTTP 400 con el mensaje "El tipo de documento no aplica a esta factura"

#### Scenario: Tipo inexistente
- **WHEN** se envía un documento con `document_type = OTRO`
- **THEN** la respuesta es HTTP 400 con el mensaje "El tipo de documento no aplica a esta factura" y no se escribe ningún archivo en `storage/`

#### Scenario: Formato no admitido por el tipo
- **WHEN** se envía `factura.png` como `INVOICE_PDF` a una factura de un proveedor nacional
- **THEN** la respuesta es HTTP 400 con el mensaje "Formato no admitido para PDF del CFDI. Formatos admitidos: PDF" y no se escribe ningún archivo en `storage/`

### Requirement: Checklist de archivos mínimos
La página de carga documental y la revisión de la factura nacional SHALL listar los tipos ofrecidos, primero los obligatorios y después los opcionales, cada grupo en el orden del catálogo. De cada tipo SHALL mostrar su nivel, sus formatos, su descripción si la tiene y su estado: el nombre y el tamaño del documento vigente, o "Pendiente". La página SHALL indicar "Falta 1 archivo obligatorio", "Faltan N archivos obligatorios" o "Archivos obligatorios completos". Los documentos de tipos que ya no se ofrecen MUST NOT contarse y SHALL seguir listados y descargables en el detalle de la factura.

#### Scenario: Obligatorios pendientes
- **WHEN** con la configuración inicial una factura de un proveedor nacional sólo tiene cargados el XML y el PDF del CFDI
- **THEN** el checklist muestra "Vo.Bo. del líder de proyecto" como "Obligatorio · Pendiente" y la página indica "Falta 1 archivo obligatorio"

#### Scenario: Obligatorios completos
- **WHEN** esa factura tiene además el Vo.Bo.
- **THEN** la página indica "Archivos obligatorios completos"

#### Scenario: Documento de un tipo que dejó de aplicar
- **WHEN** una factura nacional tenía cargada su orden de compra como archivo antes de la migración `0023_ferromex_purchase_orders`
- **THEN** la carga documental ya no ofrece ni lista la orden de compra, y el detalle de la factura la sigue listando y permite descargarla
