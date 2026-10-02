## MODIFIED Requirements

### Requirement: Catálogo de tipos de documento de factura
El sistema SHALL mantener un catálogo persistente de los tipos de documento que se cargan en una factura. Cada tipo SHALL tener:
- una clave inmutable, que es el valor que se guarda en `documents.document_type`;
- un nombre en español y una descripción opcional, que se muestran al proveedor;
- los formatos admitidos, entre `PDF` (`.pdf`), `PNG` (`.png`), `JPEG` (`.jpg`, `.jpeg`), `XML` (`.xml`) y `TXT` (`.txt`);
- si es un tipo del sistema o uno definido por el Administrador;
- si está activo;
- un nivel de exigencia para proveedores nacionales y otro para internacionales: `REQUIRED` ("Obligatorio"), `OPTIONAL` ("Opcional") o `NOT_APPLICABLE` ("No aplica").

El catálogo SHALL incluir estos tipos del sistema con estos valores iniciales (clave · nombre · formatos · Nacional · Internacional):
- `INVOICE_XML` · XML del CFDI · XML · Obligatorio · No aplica;
- `INVOICE_PDF` · PDF del CFDI · PDF · Obligatorio · No aplica;
- `FOREIGN_INVOICE` · Invoice (PDF) · PDF · No aplica · Obligatorio;
- `PURCHASE_ORDER` · Orden de compra · PDF, PNG, JPEG, TXT · Obligatorio · Obligatorio;
- `APPROVAL` · Vo.Bo. del líder de proyecto · PDF, PNG, JPEG, TXT · Obligatorio · Obligatorio;
- `CONTRACT` · Contrato · PDF, PNG, JPEG, TXT · Opcional · Opcional;
- `CONTRACT_ANNEX` · Anexo del contrato · PDF, PNG, JPEG, TXT · Opcional · Opcional;
- `PAYMENT_COMPLEMENT_XML` · Complemento de pago (XML) · XML · Opcional · No aplica;
- `PAYMENT_COMPLEMENT_PDF` · Complemento de pago (PDF) · PDF · Opcional · No aplica;
- `ADDITIONAL` · Documentación adicional · PDF, PNG, JPEG, XML, TXT · Opcional · Opcional;
- `CANCELLATION_ACK` · Acuse de cancelación · PDF, XML · No aplica · No aplica (se carga sólo al cancelar la factura, HU-14).

#### Scenario: Catálogo inicial tras la migración
- **WHEN** se aplica la migración sobre una base con facturas y documentos existentes
- **THEN** el catálogo contiene los 11 tipos del sistema, activos y con sus valores iniciales, y cada documento existente conserva su `document_type`

#### Scenario: Nombres en español
- **WHEN** un proveedor abre la carga documental de una factura
- **THEN** los tipos se muestran por su nombre del catálogo (por ejemplo "Orden de compra" y "Vo.Bo. del líder de proyecto"), no por su clave

#### Scenario: Nombres en el detalle de la factura
- **WHEN** se abre el detalle de una factura con documentos cargados
- **THEN** cada documento se muestra con el nombre de su tipo en el catálogo, aunque el tipo esté inactivo o ya no aplique al origen del proveedor

### Requirement: Archivos fijos por origen
Estos niveles SHALL ser fijos:
- `INVOICE_XML` e `INVOICE_PDF`: Obligatorio para Nacional y No aplica para Internacional;
- `FOREIGN_INVOICE`: No aplica para Nacional y Obligatorio para Internacional;
- `CANCELLATION_ACK`: No aplica para ambos orígenes, con el motivo "Se carga al cancelar la factura".

La página de configuración SHALL mostrar esos niveles como texto con el ícono de candado y su motivo, sin selector. Una petición que intente cambiarlos SHALL rechazarse con HTTP 409 sin guardar ningún cambio.

#### Scenario: Niveles fijos en la pantalla
- **WHEN** el Administrador abre la configuración
- **THEN** la fila "XML del CFDI" muestra "Obligatorio" con candado en Nacional y "No aplica" con candado en Internacional, con el motivo "El proveedor nacional factura con CFDI", y no tiene selectores

#### Scenario: Petición manipulada
- **WHEN** la petición trae `OPTIONAL` como nivel Nacional de `INVOICE_XML`, junto con otros cambios válidos
- **THEN** la respuesta es HTTP 409 con el mensaje "XML del CFDI tiene un nivel fijo para proveedores nacionales" y no se guarda ningún cambio

#### Scenario: Acuse de cancelación fuera de la carga documental
- **WHEN** el proveedor abre la carga documental de una factura
- **THEN** no se ofrece "Acuse de cancelación" y la prevalidación no lo exige
