## ADDED Requirements

### Requirement: Plantilla de Excel predefinida
El sistema SHALL generar y ofrecer al Administrador la plantilla vigente de carga masiva de proveedores en formato `.xlsx`. La plantilla SHALL contener:
- una hoja `Proveedores` con estos encabezados, en este orden, en la fila 1 y sin filas de datos: `Origen`, `Tipo de persona`, `Razón social`, `RFC`, `Identificador fiscal extranjero`, `País`, `Correo electrónico`, `Teléfono`, `Convenio de confidencialidad`, `Notas`;
- listas desplegables en `Origen` (`Nacional`, `Internacional`), `Tipo de persona` (`Física`, `Moral`) y `Convenio de confidencialidad` (`Sí`, `No`);
- formato de texto en `RFC`, `Identificador fiscal extranjero` y `Teléfono`;
- una hoja `Instrucciones` con la versión de la plantilla, la descripción de cada columna, un ejemplo por origen y la lista de códigos de país ISO 3166-1 alfa-2.

#### Scenario: Descarga de la plantilla
- **WHEN** el Administrador solicita `GET /suppliers/import/template`
- **THEN** recibe el archivo `plantilla_carga_proveedores_v1.xlsx`, cuya hoja `Proveedores` tiene en la fila 1 exactamente los encabezados vigentes y ninguna fila de datos

#### Scenario: Los ejemplos no se importan
- **WHEN** el Administrador carga la plantilla recién descargada sin capturar datos
- **THEN** la carga se rechaza con HTTP 400 y el mensaje "El archivo no contiene proveedores", y no se registra ningún proveedor

### Requirement: Carga masiva exclusiva del Administrador
La página de carga (`GET /suppliers/import`), la descarga de la plantilla (`GET /suppliers/import/template`) y el procesamiento del archivo (`POST /suppliers/import`) SHALL estar disponibles únicamente para el rol `ADMIN`. El procesamiento MUST exigir un token CSRF válido.

#### Scenario: PMO sin acceso
- **WHEN** un usuario con rol `INTERNAL` solicita la página de carga, la plantilla o envía un archivo
- **THEN** la respuesta es HTTP 403 y no se registra ningún proveedor

#### Scenario: Proveedor sin acceso
- **WHEN** un usuario con rol `PROVIDER` solicita la página de carga, la plantilla o envía un archivo
- **THEN** la respuesta es HTTP 403 y no se registra ningún proveedor

#### Scenario: Envío sin token CSRF
- **WHEN** un Administrador envía `POST /suppliers/import` sin token CSRF o con uno inválido
- **THEN** la respuesta es HTTP 403 y el archivo no se procesa

### Requirement: Validación del archivo cargado
El sistema SHALL aceptar únicamente archivos con extensión `.xlsx`, de hasta 5 MB, cuyo contenido sea un libro de Excel válido. El sistema MUST leer el libro sin ejecutar macros ni evaluar fórmulas, MUST rechazar un libro cuyo contenido descomprimido supere 50 MB y MUST NOT expandir entidades XML declaradas en el libro. El libro SHALL contener la hoja `Proveedores` con los encabezados vigentes, comparados sin distinguir mayúsculas ni espacios en los extremos y sin columnas adicionales con encabezado. También SHALL tener entre 1 y 1000 filas de datos; las filas completamente vacías no cuentan. Cualquier incumplimiento SHALL rechazar el archivo completo con HTTP 400 y un mensaje que indique la causa, sin validar filas ni registrar proveedores.

#### Scenario: Extensión no permitida
- **WHEN** el Administrador carga `proveedores.csv`, `proveedores.xls` o `proveedores.xlsm`
- **THEN** la respuesta es HTTP 400 con el mensaje "Solo se aceptan archivos de Excel (.xlsx) generados con la plantilla"

#### Scenario: Contenido que no es un libro de Excel
- **WHEN** el Administrador carga un PDF renombrado como `proveedores.xlsx`
- **THEN** la respuesta es HTTP 400 con el mensaje "El archivo no es un libro de Excel válido"

#### Scenario: Plantilla distinta
- **WHEN** el archivo no tiene la hoja `Proveedores`, o sus encabezados difieren de los vigentes (falta una columna, cambia el orden o el nombre, o hay una columna adicional)
- **THEN** la respuesta es HTTP 400 con el mensaje "El archivo no corresponde a la plantilla vigente. Descargue la plantilla e intente de nuevo."

#### Scenario: Demasiadas filas
- **WHEN** la hoja `Proveedores` contiene 1001 filas de datos
- **THEN** la respuesta es HTTP 400 con el mensaje "El archivo excede el máximo de 1000 proveedores por carga" y no se valida ninguna fila

#### Scenario: Archivo demasiado grande
- **WHEN** el archivo pesa más de 5 MB
- **THEN** la respuesta es HTTP 400 con el mensaje "El archivo excede 5 MB"

#### Scenario: Bomba de descompresión
- **WHEN** el archivo pesa menos de 5 MB pero su contenido descomprimido supera 50 MB
- **THEN** la respuesta es HTTP 400 con el mensaje "El contenido del archivo excede el tamaño permitido" y el libro no se abre

#### Scenario: Entidades XML
- **WHEN** una parte XML del libro declara entidades anidadas (ataque "billion laughs")
- **THEN** la respuesta es HTTP 400 con el mensaje "El archivo no es un libro de Excel válido" y las entidades no se expanden

### Requirement: Mapeo de columnas al catálogo de proveedores
Cada columna de la hoja `Proveedores` SHALL mapearse a un campo del catálogo de proveedores:
- `Origen` → `origin` (`Nacional` → `NATIONAL`, `Internacional` → `INTERNATIONAL`);
- `Tipo de persona` → `supplier_type` (`Física` → `PERSONA_FISICA`, `Moral` → `PERSONA_MORAL`);
- `Razón social` → `business_name`;
- `RFC` → `rfc`;
- `Identificador fiscal extranjero` → `foreign_tax_id`;
- `País` → `country`;
- `Correo electrónico` → `email`;
- `Teléfono` → `phone`;
- `Convenio de confidencialidad` → `confidentiality_agreement` (`Sí` → verdadero; `No` o vacío → falso);
- `Notas` → `notes`.

Antes de validar, el sistema SHALL normalizar cada valor:
- recortar los espacios de los extremos y colapsar los espacios internos repetidos;
- convertir `RFC`, `Identificador fiscal extranjero` y `País` a mayúsculas, y `Correo electrónico` a minúsculas;
- interpretar los valores de lista sin distinguir mayúsculas ni acentos;
- convertir a texto sin decimales los números enteros capturados en columnas de texto;
- asignar `country = "MX"` a los proveedores nacionales.

#### Scenario: Fila nacional normalizada
- **WHEN** una fila trae `Origen` = "Nacional", `Tipo de persona` = "Moral", `Razón social` = "  Servicios   Digitales del Norte SA de CV ", `RFC` = "sdn200315ab1" y `Correo electrónico` = "Contacto@SDN.mx", y la carga concluye
- **THEN** el proveedor queda con `origin = NATIONAL`, `supplier_type = PERSONA_MORAL`, `business_name = "Servicios Digitales del Norte SA de CV"`, `rfc = "SDN200315AB1"`, `country = "MX"` y `email = "contacto@sdn.mx"`

#### Scenario: Fila internacional normalizada
- **WHEN** una fila trae `Origen` = "INTERNACIONAL", `Tipo de persona` = "moral", `Razón social` = "Northwind Consulting LLC", `Identificador fiscal extranjero` = "12-3456789", `País` = "us" y `Correo electrónico` = "billing@northwind.example", y la carga concluye
- **THEN** el proveedor queda con `origin = INTERNATIONAL`, `supplier_type = PERSONA_MORAL`, `rfc` nulo, `foreign_tax_id = "12-3456789"` y `country = "US"`

#### Scenario: Valores de lista sin acentos ni mayúsculas
- **WHEN** una fila trae `Tipo de persona` = "FISICA" y `Convenio de confidencialidad` = "si"
- **THEN** el proveedor queda con `supplier_type = PERSONA_FISICA` y `confidentiality_agreement` verdadero

#### Scenario: Teléfono capturado como número
- **WHEN** la celda `Teléfono` contiene el número 5512345678
- **THEN** el proveedor queda con `phone = "5512345678"`

### Requirement: Validación de cada fila
El sistema SHALL validar todas las filas de datos en una sola pasada y reportar cada error con el número de fila de Excel, el encabezado de la columna y un mensaje en español, con el formato "Fila N · Columna: mensaje". Son errores bloqueantes:
- `Origen`, `Tipo de persona`, `Razón social` (2 a 250 caracteres) o `Correo electrónico` (correo válido de hasta 255 caracteres) ausentes o inválidos;
- en una fila `Nacional`:
  - `RFC` ausente, fuera del patrón `^[A-ZÑ&]{3,4}[0-9]{6}[A-Z0-9]{3}$` o con sus seis dígitos fuera de una fecha AAMMDD válida;
  - `RFC` de longitud distinta de 12 para persona moral o de 13 para persona física;
  - `RFC` genérico (`XAXX010101000`, `XEXX010101000`);
  - `Identificador fiscal extranjero` capturado;
  - `País` distinto de vacío o `MX`;
- en una fila `Internacional`:
  - `Identificador fiscal extranjero` ausente o fuera de 1 a 40 caracteres entre letras, dígitos, espacio, `.`, `-` y `/`;
  - `País` ausente, fuera de ISO 3166-1 alfa-2 o igual a `MX`;
  - `RFC` capturado;
- `Teléfono` capturado fuera de 7 a 30 caracteres entre dígitos, espacio, `+`, `(`, `)` y `-`;
- `Notas` de más de 1000 caracteres;
- `Convenio de confidencialidad` distinto de `Sí`, `No` o vacío;
- cualquier celda que contenga una fórmula o un valor de tipo fecha.

#### Scenario: Errores de varias filas en una sola respuesta
- **WHEN** el archivo tiene datos en las filas 2 a 4 de Excel, la fila 2 no tiene `Correo electrónico` y la fila 4 tiene `RFC` = "ABC123"
- **THEN** la respuesta en modo `strict` es HTTP 400, incluye los errores "Fila 2 · Correo electrónico: es obligatorio" y "Fila 4 · RFC: tiene un formato inválido", y no se registra ningún proveedor

#### Scenario: RFC incongruente con el tipo de persona
- **WHEN** una fila `Nacional` con `Tipo de persona` = "Moral" trae el RFC de 13 caracteres "GOMA850612H45"
- **THEN** se reporta "Fila N · RFC: una persona moral debe tener un RFC de 12 caracteres"

#### Scenario: RFC genérico en un proveedor nacional
- **WHEN** una fila `Nacional` trae `RFC` = "XEXX010101000"
- **THEN** se reporta "Fila N · RFC: no se permite un RFC genérico; un proveedor extranjero se registra con Origen Internacional"

#### Scenario: Proveedor internacional incompleto
- **WHEN** una fila `Internacional` no tiene `Identificador fiscal extranjero` y sí tiene `RFC`
- **THEN** se reportan "Fila N · Identificador fiscal extranjero: es obligatorio para proveedores internacionales" y "Fila N · RFC: debe quedar vacío para proveedores internacionales"

#### Scenario: País no válido
- **WHEN** una fila `Internacional` trae `País` = "USA"
- **THEN** se reporta "Fila N · País: use el código ISO de dos letras (p. ej. US)"

#### Scenario: Celda con fórmula
- **WHEN** la celda `Correo electrónico` de una fila contiene la fórmula `=A2&"@proveedor.mx"`
- **THEN** se reporta "Fila N · Correo electrónico: la celda contiene una fórmula; capture el valor"

### Requirement: Detección de duplicados
El sistema SHALL detectar duplicados dentro del archivo y contra el catálogo, comparando correos sin distinguir mayúsculas:
- el mismo `RFC`, el mismo par (`País`, `Identificador fiscal extranjero`) o el mismo `Correo electrónico` en más de una fila SHALL ser un error bloqueante en todas sus apariciones, indicando las filas involucradas; ninguna de ellas se registra, ni siquiera en modo `partial`;
- una fila cuyo `RFC` (Nacional) o par (`País`, `Identificador fiscal extranjero`) (Internacional) ya existe en el catálogo SHALL omitirse sin modificar al proveedor existente y SHALL informarse como omitida, sin bloquear la carga;
- una fila nueva cuyo `Correo electrónico` ya pertenece a otro proveedor o a un usuario del portal SHALL ser un error bloqueante.

#### Scenario: RFC repetido en el archivo
- **WHEN** las filas 3 y 7 traen `RFC` = "SDN200315AB1"
- **THEN** se reportan "Fila 3 · RFC: repetido en las filas 3 y 7" y "Fila 7 · RFC: repetido en las filas 3 y 7", y ninguna de las dos filas se registra en ningún modo

#### Scenario: Proveedor existente omitido
- **WHEN** el catálogo ya tiene un proveedor con RFC "SDN200315AB1", y el archivo trae ese RFC con otra razón social y otro correo junto con dos proveedores nuevos válidos
- **THEN** se registran los dos proveedores nuevos, la fila del RFC existente aparece como "Omitido: ya existe en el catálogo" y el proveedor existente conserva su razón social y su correo

#### Scenario: Correo en uso
- **WHEN** una fila nueva trae un `Correo electrónico` que ya pertenece a otro proveedor o a un usuario del portal
- **THEN** se reporta "Fila N · Correo electrónico: ya está registrado para otro proveedor o usuario" y esa fila no se registra en ningún modo

### Requirement: Confirmación ante filas con errores
`POST /suppliers/import` SHALL aceptar el campo `mode` con valor `strict` (predeterminado) o `partial`.

En modo `strict`, si alguna fila tiene errores, el sistema MUST NOT registrar ningún proveedor. SHALL responder HTTP 400 con los primeros 200 errores ordenados por fila, el número de errores no mostrados, el número de filas que se registrarían y el SHA-256 del archivo.

Si al menos una fila se registraría, la página SHALL abrir una ventana emergente con el texto "Algunas filas contienen errores o no se han podido leer correctamente. ¿Desea agregar las filas válidas?" y dos opciones:
- "No, corregir primero (Recomendado)", preseleccionada, resaltada y con el foco;
- "Agrega las filas válidas y omite el resto".

Elegir la primera opción, cerrar la ventana o pulsar Esc SHALL cerrar la ventana, mostrar la lista de errores y dejar el catálogo sin cambios.

Elegir la segunda SHALL reenviar el mismo archivo con `mode = partial` y `expected_sha256` igual al SHA-256 recibido. El sistema SHALL validarlo de nuevo y registrar sólo las filas sin errores. Si el SHA-256 del archivo no coincide con `expected_sha256`, o si falta, el sistema SHALL responder HTTP 409 sin registrar nada.

Los errores de archivo MUST NOT ofrecer el registro parcial.

#### Scenario: Filas con errores abren la confirmación
- **WHEN** el Administrador carga en modo `strict` un archivo con 8 filas nuevas válidas y 2 filas con errores
- **THEN** la respuesta es HTTP 400, no se registra ningún proveedor y la página abre la ventana emergente con el texto y las dos opciones, con "No, corregir primero (Recomendado)" preseleccionada

#### Scenario: Corregir primero
- **WHEN** en la ventana emergente el Administrador elige "No, corregir primero (Recomendado)" o pulsa Esc
- **THEN** la ventana se cierra, la página muestra la lista de errores y el catálogo no cambia

#### Scenario: Agregar las filas válidas
- **WHEN** en la ventana emergente el Administrador elige "Agrega las filas válidas y omite el resto"
- **THEN** el mismo archivo se reenvía con `mode = partial`, la respuesta es HTTP 200, se registran los 8 proveedores válidos y las 2 filas con errores aparecen como no registradas junto con sus errores

#### Scenario: Ninguna fila registrable
- **WHEN** todas las filas tienen errores, o las filas sin errores ya existen en el catálogo
- **THEN** la página muestra la lista de errores sin abrir la ventana emergente

#### Scenario: Archivo distinto al validado
- **WHEN** llega una petición en modo `partial` cuyo archivo no coincide con `expected_sha256`
- **THEN** la respuesta es HTTP 409 con "El archivo cambió desde la validación. Vuelva a cargarlo." y no se registra ningún proveedor

#### Scenario: Errores de archivo sin registro parcial
- **WHEN** el archivo se rechaza por tipo, tamaño, plantilla o límite de filas
- **THEN** la página muestra el mensaje del error sin abrir la ventana emergente

#### Scenario: Más de 200 errores
- **WHEN** el archivo produce 350 errores
- **THEN** la página muestra los 200 primeros ordenados por fila y el aviso "y 150 errores más"

### Requirement: Registro atómico de la carga
El sistema SHALL registrar en una sola transacción todas las filas que se registran: las filas nuevas de un archivo sin errores en modo `strict`, o las filas nuevas sin errores en modo `partial`. Si la base de datos rechaza algún registro por unicidad, por ejemplo ante una carga concurrente, el sistema SHALL revertir la transacción completa y responder HTTP 409 sin HTTP 500.

#### Scenario: Archivo sin errores
- **WHEN** el Administrador carga en modo `strict` un archivo cuyas filas no tienen errores
- **THEN** los proveedores nuevos se registran en ese mismo paso, sin ventana emergente, y la respuesta es HTTP 200

#### Scenario: Carga concurrente
- **WHEN** dos Administradores cargan al mismo tiempo archivos que incluyen el mismo RFC nuevo
- **THEN** una carga concluye; la otra responde HTTP 409 con "Otro proceso registró proveedores de este archivo mientras se procesaba. Vuelva a cargarlo." sin registrar ningún proveedor, y al volver a cargarla esa fila aparece como omitida

### Requirement: Estatus inicial sin acceso al portal
Los proveedores registrados por la carga masiva SHALL quedar con estatus `REGISTERED`, que se muestra como "Registrado". La carga MUST NOT crear usuarios del portal, generar contraseñas ni enviar correos.

#### Scenario: Proveedor recién cargado
- **WHEN** la carga registra al proveedor con RFC "SDN200315AB1"
- **THEN** su estatus es `REGISTERED`, el listado y el detalle de proveedores lo muestran como "Registrado", no existe ningún usuario con su `supplier_id` y no se envía ningún correo

### Requirement: Resumen del resultado de la carga
Tras una carga concluida, el sistema SHALL responder HTTP 200 con un resumen que indique las filas leídas, los proveedores registrados y los proveedores omitidos por existir ya en el catálogo. De cada omitido SHALL mostrar la fila, el RFC o identificador fiscal y la razón social. En modo `partial`, el resumen SHALL indicar además las filas no registradas por errores, junto con esos errores.

#### Scenario: Carga con proveedores nuevos y existentes
- **WHEN** el archivo trae 10 filas válidas, 8 de proveedores nuevos y 2 de proveedores que ya existen
- **THEN** la página muestra "10 filas leídas · 8 proveedores registrados · 2 omitidos" y lista los 2 omitidos con su fila, RFC o identificador fiscal y razón social

#### Scenario: Recarga del mismo archivo
- **WHEN** el Administrador vuelve a cargar el mismo archivo
- **THEN** la página muestra "10 filas leídas · 0 proveedores registrados · 10 omitidos" y el catálogo no cambia

#### Scenario: Resumen de una carga parcial
- **WHEN** el Administrador elige agregar las filas válidas de un archivo con 10 filas: 6 nuevas, 2 ya existentes y 2 con errores
- **THEN** la página muestra "10 filas leídas · 6 proveedores registrados · 2 omitidos · 2 con errores" y lista las filas omitidas y las filas con errores

### Requirement: Auditoría de la carga masiva
Cada carga concluida SHALL generar un registro de auditoría `SUPPLIER_BULK_IMPORTED` con estos datos: el Administrador que la ejecutó, el modo (`strict` o `partial`), el SHA-256 y el tamaño del archivo, las filas leídas, los proveedores registrados y omitidos, y las filas no registradas por errores. También SHALL generar un registro `SUPPLIER_CREATED` por cada proveedor registrado, con `{"source": "bulk_import", "import_sha256": "<sha256>"}`. Una carga que no registra nada por errores MUST NOT generar registros de auditoría. El log de aplicación MUST NOT contener RFC, identificadores fiscales, correos, razones sociales ni el nombre original del archivo.

#### Scenario: Auditoría de una carga concluida
- **WHEN** una carga en modo `strict` registra 8 proveedores y omite 2
- **THEN** `audit_logs` contiene un registro `SUPPLIER_BULK_IMPORTED` con el `user_id` del Administrador y `mode = "strict"`, `sha256`, `size_bytes`, `rows = 10`, `created = 8`, `skipped = 2` e `invalid = 0`, además de 8 registros `SUPPLIER_CREATED` con `source = "bulk_import"` y el mismo `import_sha256`

#### Scenario: Auditoría de una carga parcial
- **WHEN** una carga en modo `partial` registra 6 proveedores, omite 2 y deja 2 filas con errores sin registrar
- **THEN** el registro `SUPPLIER_BULK_IMPORTED` tiene `mode = "partial"`, `created = 6`, `skipped = 2` e `invalid = 2`

#### Scenario: Carga rechazada sin auditoría
- **WHEN** una carga no registra nada porque tiene errores de archivo, o errores de filas en modo `strict`
- **THEN** no se agrega ningún registro a `audit_logs`

#### Scenario: Log sin datos del archivo
- **WHEN** se procesa una carga, aceptada o rechazada, y se busca en el log los RFC, identificadores fiscales, correos y razones sociales del archivo, y su nombre original
- **THEN** no hay coincidencias
