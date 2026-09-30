# archivos-minimos-factura Specification

## Purpose
Catálogo de tipos de documento de factura y configuración de los archivos mínimos por origen del proveedor (HU-04, RF-04): acceso exclusivo del Administrador, matriz de niveles y niveles fijos, tipos de documento soporte del Administrador, carga documental y checklist según el origen, protección contra ediciones concurrentes y auditoría.
## Requirements
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

### Requirement: Configuración exclusiva del Administrador
La página `GET /admin/required-documents` y las operaciones `POST /admin/required-documents`, `POST /admin/required-documents/types`, `POST /admin/required-documents/types/{type_id}` y `POST /admin/required-documents/types/{type_id}/status` SHALL estar disponibles únicamente para el rol `Administrador`. Toda operación `POST` MUST exigir un token CSRF válido.

#### Scenario: PMO sin acceso
- **WHEN** un usuario con rol `PMO` solicita la página de configuración o envía cualquiera de sus operaciones
- **THEN** la respuesta es HTTP 403 y la configuración no cambia

#### Scenario: Proveedor sin acceso
- **WHEN** un usuario con rol `Proveedor` solicita la página de configuración o envía cualquiera de sus operaciones
- **THEN** la respuesta es HTTP 403 y la configuración no cambia

#### Scenario: Envío sin token CSRF
- **WHEN** un Administrador envía `POST /admin/required-documents` sin token CSRF o con uno inválido
- **THEN** la respuesta es HTTP 403 y la configuración no cambia

### Requirement: Configuración de los archivos mínimos por origen
La página de configuración SHALL mostrar una fila por cada tipo activo, con su nombre, sus formatos y un selector de nivel para Nacional y otro para Internacional. Primero aparecen los tipos del sistema, en el orden del catálogo, y después los del Administrador, por nombre.

Al guardar, el sistema SHALL validar todos los niveles recibidos y actualizar en una sola transacción los que cambiaron. Un nivel distinto de `REQUIRED`, `OPTIONAL` o `NOT_APPLICABLE`, o la falta del nivel de un tipo activo con nivel editable, SHALL rechazar el guardado completo con HTTP 400. Si ningún nivel cambió, el sistema SHALL informar "Sin cambios" sin modificar nada.

#### Scenario: Exigir un documento al proveedor internacional
- **WHEN** el Administrador cambia "Contrato" a Obligatorio en la columna Internacional y guarda
- **THEN** la página muestra "Configuración guardada" y la carga documental de una factura de un proveedor internacional muestra "Contrato" como Obligatorio

#### Scenario: Dejar de exigir la orden de compra al proveedor nacional
- **WHEN** el Administrador cambia "Orden de compra" a Opcional en la columna Nacional y guarda
- **THEN** la carga documental de una factura de un proveedor nacional muestra "Orden de compra" como Opcional

#### Scenario: Guardar sin cambios
- **WHEN** el Administrador guarda la configuración sin modificar ningún nivel
- **THEN** la página muestra "Sin cambios" y no se agrega ningún registro de auditoría

#### Scenario: Nivel inválido
- **WHEN** la petición trae `MANDATORY` como nivel de un tipo, junto con otros cambios válidos
- **THEN** la respuesta es HTTP 400 con el mensaje "Nivel de exigencia inválido" y no se guarda ningún cambio

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

### Requirement: Tipos de documento soporte definidos por el Administrador
El Administrador SHALL poder dar de alta tipos de documento soporte con un nombre de 3 a 80 caracteres, una descripción opcional de hasta 300 caracteres, al menos un formato y un nivel para cada origen, preseleccionado en "No aplica". El sistema SHALL:
- normalizar el nombre, recortando los espacios de los extremos y colapsando los internos repetidos;
- rechazar un nombre que ya use otro tipo, sin distinguir mayúsculas;
- asignar al tipo la clave `SOPORTE_<id>`, que no cambia.

El Administrador SHALL poder editar el nombre, la descripción y los formatos de estos tipos, y desactivarlos o reactivarlos. Un tipo inactivo MUST NOT ofrecerse en la carga documental ni exigirse en la prevalidación, y SHALL conservar sus niveles para cuando se reactive. Los tipos del sistema MUST NOT editarse ni desactivarse.

#### Scenario: Alta de un tipo soporte
- **WHEN** el Administrador da de alta "Reporte de horas" con formato PDF, Obligatorio para Internacional y No aplica para Nacional
- **THEN** existe un tipo activo con clave `SOPORTE_<id>` que aparece en la configuración; la carga documental de una factura internacional lo muestra como Obligatorio y la de una nacional no lo ofrece

#### Scenario: Nombre repetido
- **WHEN** el Administrador da de alta un tipo con el nombre "  orden   de COMPRA "
- **THEN** la respuesta es HTTP 409 con el mensaje "Ya existe un tipo de documento con ese nombre" y no se crea ningún tipo

#### Scenario: Sin formatos
- **WHEN** el Administrador da de alta un tipo sin seleccionar ningún formato
- **THEN** la respuesta es HTTP 400 con el mensaje "Seleccione al menos un formato" y no se crea ningún tipo

#### Scenario: Cambio de formatos
- **WHEN** el Administrador edita "Reporte de horas" para admitir PDF y PNG
- **THEN** la siguiente carga de `horas.png` como "Reporte de horas" se acepta, y los documentos ya cargados de ese tipo no cambian

#### Scenario: Desactivación y reactivación
- **WHEN** el Administrador desactiva "Reporte de horas", que era Obligatorio para Internacional
- **THEN** la carga documental ya no lo ofrece, la prevalidación ya no lo exige y los documentos ya cargados de ese tipo siguen listados y descargables en el detalle de la factura; al reactivarlo vuelve a ser Obligatorio para Internacional

#### Scenario: Tipo del sistema
- **WHEN** el Administrador envía la edición o la desactivación de "Orden de compra"
- **THEN** la respuesta es HTTP 409 con el mensaje "Los tipos de documento del sistema no se pueden editar ni desactivar" y el tipo no cambia

### Requirement: Carga documental según el origen del proveedor
La página de carga documental de una factura SHALL ofrecer sólo los tipos activos cuyo nivel para el origen del proveedor de la factura sea Obligatorio u Opcional, cada uno con su nombre y sus formatos. `POST /invoices/{invoice_id}/documents` SHALL rechazar con HTTP 400, antes de escribir el archivo:
- un tipo que no se ofrece para esa factura, con el mensaje "El tipo de documento no aplica a esta factura";
- un archivo cuya extensión no corresponde a los formatos del tipo, con el mensaje "Formato no admitido para <nombre>. Formatos admitidos: <formatos>".

Las verificaciones existentes de contenido, tamaño y estado editable SHALL mantenerse.

#### Scenario: Tipos ofrecidos a un proveedor nacional
- **WHEN** con la configuración inicial se abre la carga documental de una factura de un proveedor nacional
- **THEN** se ofrecen XML del CFDI, PDF del CFDI, Orden de compra, Vo.Bo. del líder de proyecto, Contrato, Anexo del contrato, Complemento de pago (XML), Complemento de pago (PDF) y Documentación adicional, y no se ofrece Invoice (PDF)

#### Scenario: Tipos ofrecidos a un proveedor internacional
- **WHEN** con la configuración inicial se abre la carga documental de una factura de un proveedor internacional
- **THEN** se ofrecen Invoice (PDF), Orden de compra, Vo.Bo. del líder de proyecto, Contrato, Anexo del contrato y Documentación adicional, y no se ofrecen el XML ni el PDF del CFDI ni los complementos de pago

#### Scenario: Tipo que no aplica
- **WHEN** se envía un documento con `document_type = INVOICE_XML` a una factura de un proveedor internacional
- **THEN** la respuesta es HTTP 400 con el mensaje "El tipo de documento no aplica a esta factura" y no se escribe ningún archivo en `storage/`

#### Scenario: Tipo inexistente
- **WHEN** se envía un documento con `document_type = OTRO`
- **THEN** la respuesta es HTTP 400 con el mensaje "El tipo de documento no aplica a esta factura" y no se escribe ningún archivo en `storage/`

#### Scenario: Formato no admitido por el tipo
- **WHEN** se envía `factura.png` como `INVOICE_PDF` a una factura de un proveedor nacional
- **THEN** la respuesta es HTTP 400 con el mensaje "Formato no admitido para PDF del CFDI. Formatos admitidos: PDF" y no se escribe ningún archivo en `storage/`

### Requirement: Checklist de archivos mínimos
La página de carga documental SHALL listar los tipos ofrecidos, primero los obligatorios y después los opcionales, cada grupo en el orden del catálogo. De cada tipo SHALL mostrar su nivel, sus formatos, su descripción si la tiene y su estado: el nombre y el tamaño del documento vigente, o "Pendiente". La página SHALL indicar "Falta 1 archivo obligatorio", "Faltan N archivos obligatorios" o "Archivos obligatorios completos". Los documentos de tipos que ya no se ofrecen MUST NOT contarse y SHALL seguir listados y descargables en el detalle de la factura.

#### Scenario: Obligatorios pendientes
- **WHEN** con la configuración inicial una factura de un proveedor nacional sólo tiene cargados el XML y el PDF del CFDI
- **THEN** el checklist muestra "Orden de compra" y "Vo.Bo. del líder de proyecto" como "Obligatorio · Pendiente" y la página indica "Faltan 2 archivos obligatorios"

#### Scenario: Obligatorios completos
- **WHEN** esa factura tiene además la orden de compra y el Vo.Bo.
- **THEN** la página indica "Archivos obligatorios completos"

#### Scenario: Documento de un tipo que dejó de aplicar
- **WHEN** una factura nacional tiene cargada su orden de compra y el Administrador cambia "Orden de compra" a No aplica en la columna Nacional
- **THEN** la carga documental ya no ofrece ni lista la orden de compra, y el detalle de la factura la sigue listando y permite descargarla

### Requirement: Protección contra ediciones concurrentes
La página de configuración SHALL incluir la huella `config_version` de la configuración que muestra: el SHA-256 de la clave, los niveles y el estado activo de todos los tipos. Si al guardar la huella recibida falta o no coincide con la de la configuración vigente, el sistema SHALL responder HTTP 409 sin guardar ningún cambio.

#### Scenario: Dos Administradores editan a la vez
- **WHEN** los Administradores A y B abren la configuración, A guarda un cambio y después B guarda el suyo
- **THEN** B recibe HTTP 409 con el mensaje "La configuración cambió mientras la editaba. Recargue la página." y sólo persiste el cambio de A

### Requirement: Auditoría de la configuración de archivos mínimos
Cada cambio guardado SHALL generar un registro de auditoría con el `user_id` del Administrador:
- `INVOICE_DOCUMENT_REQUIREMENTS_UPDATED` al guardar la configuración, con el nivel anterior y el nuevo de cada tipo y origen que cambió;
- `INVOICE_DOCUMENT_TYPE_CREATED` al dar de alta un tipo, con su clave, nombre, formatos y niveles;
- `INVOICE_DOCUMENT_TYPE_UPDATED` al editar un tipo, con los valores anteriores y nuevos de los campos que cambiaron;
- `INVOICE_DOCUMENT_TYPE_STATUS_CHANGED` al desactivar o reactivar un tipo.

Una operación rechazada o un guardado sin cambios MUST NOT generar registros de auditoría.

#### Scenario: Cambio de nivel auditado
- **WHEN** el Administrador cambia "Orden de compra" de Obligatorio a Opcional en la columna Internacional y guarda
- **THEN** `audit_logs` contiene un registro `INVOICE_DOCUMENT_REQUIREMENTS_UPDATED` con su `user_id`, `old_value = {"PURCHASE_ORDER": {"international": "REQUIRED"}}` y `new_value = {"PURCHASE_ORDER": {"international": "OPTIONAL"}}`

#### Scenario: Alta auditada
- **WHEN** el Administrador da de alta "Reporte de horas"
- **THEN** `audit_logs` contiene un registro `INVOICE_DOCUMENT_TYPE_CREATED` con la clave `SOPORTE_<id>`, el nombre, los formatos y los dos niveles

#### Scenario: Operación rechazada sin auditoría
- **WHEN** una operación de configuración se rechaza con HTTP 400, 403 o 409
- **THEN** no se agrega ningún registro a `audit_logs`

