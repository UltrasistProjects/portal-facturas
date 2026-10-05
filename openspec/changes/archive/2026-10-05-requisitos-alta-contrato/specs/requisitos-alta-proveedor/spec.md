## MODIFIED Requirements

### Requirement: Catálogo de requisitos de alta
El sistema SHALL mantener un catálogo persistente de los documentos que forman el expediente del proveedor (requisitos de alta). Cada requisito SHALL tener:
- una clave inmutable, que es el valor que se guarda en `documents.document_type` de los documentos del expediente;
- un nombre en español y una descripción opcional, que se muestran en el expediente;
- si es un requisito del sistema o uno definido por el Administrador;
- si está activo;
- un nivel para cada tipo de proveedor (persona moral, persona física e internacional): `REQUIRED` ("Obligatorio"), `OPTIONAL` ("Opcional") o `NOT_APPLICABLE` ("No aplica").

El tipo de proveedor SHALL determinarse así: un proveedor con `origin = INTERNATIONAL` es Internacional, sin importar su tipo de persona; uno nacional es Persona moral o Persona física según su `supplier_type`.

El catálogo SHALL incluir estos requisitos del sistema con estos valores (clave · nombre · persona moral · persona física · internacional):
- `INCORPORATION_ACT` · Acta constitutiva · Obligatorio · No aplica · No aplica;
- `POWER_OF_ATTORNEY` · Poderes · Obligatorio · No aplica · No aplica;
- `TAX_STATUS` · Cédula fiscal · Obligatorio · Obligatorio · No aplica;
- `LEGAL_REP_ID` · Identificación del representante legal · Obligatorio · No aplica · No aplica;
- `LEGAL_REP_ADDRESS_PROOF` · Comprobante de domicilio del representante legal · Obligatorio · No aplica · No aplica;
- `ADDRESS_PROOF` · Comprobante de domicilio · Obligatorio · Obligatorio · No aplica;
- `BANK_STATEMENT` · Estado de cuenta bancario · Obligatorio · Obligatorio · No aplica;
- `OFFICIAL_ID` · Identificación oficial · No aplica · Obligatorio · No aplica;
- `SAT_OPINION` · Opinión de cumplimiento · Opcional · Opcional · No aplica;
- `ECONOMIC_PROPOSAL` · Propuesta económica · Opcional · Opcional · No aplica;
- `DUE_DILIGENCE` · Debida diligencia · Opcional · No aplica · No aplica;
- `LOCATION` · Ubicación · Opcional · Opcional · No aplica;
- `SUPPLIER_CONTRACT` · Contrato · No aplica · No aplica · No aplica, fijo: el contrato firmado se carga en cada contrato (capacidad `requisitos-alta-contrato`).

#### Scenario: Catálogo inicial tras la migración
- **WHEN** se aplican las migraciones sobre una base con proveedores y documentos de expediente existentes
- **THEN** el catálogo contiene los 13 requisitos del sistema, activos y con los valores anteriores; ningún proveedor cambia de estatus y cada documento conserva su `document_type`

#### Scenario: Nombres en español
- **WHEN** el Administrador abre el expediente de un proveedor
- **THEN** los requisitos se muestran por su nombre del catálogo (por ejemplo "Cédula fiscal" y "Poderes"), no por su clave

#### Scenario: Contrato cargado antes en el expediente
- **WHEN** un proveedor tenía cargado un documento `SUPPLIER_CONTRACT` antes de la migración de `requisitos-alta-contrato`
- **THEN** su expediente ya no lista "Contrato" entre los requisitos, y "Otros documentos del expediente" lo lista y permite descargarlo

### Requirement: Configuración de los requisitos por tipo de proveedor
La página de configuración SHALL mostrar una fila por cada requisito activo, con su nombre, su descripción y un selector de nivel para Persona moral, otro para Persona física y otro para Internacional. Primero aparecen los requisitos del sistema, en el orden del catálogo, y después los del Administrador, por nombre.

Los tres niveles de `SUPPLIER_CONTRACT` SHALL ser fijos en No aplica: la página los muestra como texto con el ícono de candado y el motivo "Se carga en cada contrato", sin selectores. Una petición que intente cambiarlos SHALL rechazarse con HTTP 409 y el mensaje "Contrato tiene un nivel fijo para <tipo de proveedor en plural>" (por ejemplo, "personas morales"), sin guardar ningún cambio.

Al guardar, el sistema SHALL validar todos los niveles recibidos y actualizar en una sola transacción los que cambiaron. Un nivel distinto de `REQUIRED`, `OPTIONAL` o `NOT_APPLICABLE`, o la falta de un nivel editable de un requisito activo, SHALL rechazar el guardado completo con HTTP 400. Si ningún nivel cambió, el sistema SHALL informar "Sin cambios" sin modificar nada.

#### Scenario: Hacer opcional un requisito
- **WHEN** el Administrador cambia "Poderes" a Opcional en la columna Persona moral y guarda
- **THEN** la página muestra "Configuración guardada", y el expediente de una persona moral "Registrado" sin poderes muestra "Poderes" como "Opcional · Pendiente" y no lo cuenta entre los obligatorios pendientes

#### Scenario: Exigir un requisito al proveedor internacional
- **WHEN** el Administrador cambia "Estado de cuenta bancario" a Obligatorio en la columna Internacional y guarda
- **THEN** el expediente de un proveedor internacional muestra "Estado de cuenta bancario" como Obligatorio, y el proveedor no puede autorizarse sin ese documento

#### Scenario: Contrato con nivel fijo
- **WHEN** el Administrador abre la configuración
- **THEN** la fila "Contrato" muestra "No aplica" con candado en las tres columnas y el motivo "Se carga en cada contrato", sin selectores

#### Scenario: Petición manipulada sobre el Contrato
- **WHEN** la petición trae `OPTIONAL` como nivel de Persona moral de `SUPPLIER_CONTRACT`, junto con otros cambios válidos
- **THEN** la respuesta es HTTP 409 con el mensaje "Contrato tiene un nivel fijo para personas morales" y no se guarda ningún cambio

#### Scenario: Guardar sin cambios
- **WHEN** el Administrador guarda la configuración sin modificar ningún nivel
- **THEN** la página muestra "Sin cambios" y no se agrega ningún registro de auditoría

#### Scenario: Nivel inválido
- **WHEN** la petición trae `MANDATORY` como nivel de un requisito, junto con otros cambios válidos
- **THEN** la respuesta es HTTP 400 con el mensaje "Nivel de exigencia inválido" y no se guarda ningún cambio

### Requirement: Requisitos que aplican a cada proveedor
Los requisitos que aplican a un proveedor SHALL ser los requisitos activos cuyo nivel para su tipo de proveedor es Obligatorio u Opcional. Los requisitos exigibles SHALL ser los Obligatorios y, si el alta es por cotización o licitación (`economic_proposal`), también "Propuesta económica" cuando su nivel no es No aplica. Un requisito SHALL cumplirse con un documento vigente (`is_current`) de su tipo en el expediente del proveedor (`invoice_id` nulo); la antigüedad del documento no afecta el cumplimiento.

`POST /suppliers/{supplier_id}/documents` SHALL rechazar con HTTP 400 y el mensaje "El documento no aplica a este proveedor", antes de escribir el archivo, un tipo que no aplica al proveedor: con nivel No aplica para su tipo, inactivo o inexistente. Las verificaciones existentes de permisos, contenido y tamaño SHALL mantenerse.

#### Scenario: Persona moral nacional
- **WHEN** con la configuración inicial se abre el expediente de una persona moral nacional
- **THEN** se piden como obligatorios Acta constitutiva, Poderes, Cédula fiscal, Identificación del representante legal, Comprobante de domicilio del representante legal, Comprobante de domicilio y Estado de cuenta bancario; se ofrecen como opcionales Opinión de cumplimiento, Propuesta económica, Debida diligencia y Ubicación; no se ofrecen Identificación oficial ni Contrato

#### Scenario: Persona física nacional
- **WHEN** con la configuración inicial se abre el expediente de una persona física nacional
- **THEN** se piden como obligatorios Identificación oficial, Cédula fiscal, Comprobante de domicilio y Estado de cuenta bancario, y no se ofrecen Acta constitutiva, Poderes ni Contrato

#### Scenario: Proveedor internacional con la configuración inicial
- **WHEN** con la configuración inicial se abre el expediente de un proveedor internacional
- **THEN** el panel muestra "Sin requisitos de alta configurados para proveedores internacionales" y el proveedor puede autorizarse sin documentos

#### Scenario: Alta por cotización
- **WHEN** una persona moral tiene `economic_proposal` y "Propuesta económica" es Opcional para Persona moral
- **THEN** su expediente muestra "Propuesta económica" como Obligatorio, con la nota "Alta por cotización o licitación", y el proveedor no puede autorizarse sin ella

#### Scenario: Documento que no aplica
- **WHEN** se envía un documento con `document_type = SUPPLIER_CONTRACT` al expediente de una persona moral
- **THEN** la respuesta es HTTP 400 con el mensaje "El documento no aplica a este proveedor" y no se escribe ningún archivo en `storage/`
