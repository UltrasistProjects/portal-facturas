## ADDED Requirements

### Requirement: Registro de la factura a partir de sus archivos
Para un proveedor nacional, el Paso 1 del registro ("Archivos", `GET /invoices/new` y `POST /invoices/new` multipart) SHALL pedir el PDF de la factura (obligatorio) y el XML (opcional), y SHALL NOT pedir contrato, número de factura, periodo, proyecto ni líder de proyecto.

Con los archivos válidos, el sistema SHALL:
1. verificar la extensión, el contenido y el tamaño de cada archivo (spec `almacenamiento-documentos`);
2. extraer los datos de la factura;
3. crear la factura en "Borrador" con:
   - número `Serie`+`Folio` del CFDI o, sin ellos, el número impreso;
   - periodo `MM/AAAA` del mes de la fecha de emisión;
   - UUID, fecha, importes y moneda del comprobante (la moneda sólo si está activa en el catálogo);
   - el número de orden de compra detectado en los conceptos;
4. guardar ambos documentos con sus datos extraídos;
5. recalcular "Borrador"/"Cargada" con los archivos obligatorios;
6. llevar al Paso 2 (`/invoices/{id}/data`).

Las verificaciones de proveedor autorizado y de usuario vinculado de `flujo-facturas` SHALL conservarse. Un UUID que ya tiene otra factura MUST NOT impedir el alta: no se asigna a la factura y FIN-004 lo reporta. Ninguna factura nueva SHALL tener contrato, proyecto ni líder de proyecto.

#### Scenario: Sólo PDF
- **WHEN** un proveedor nacional autorizado carga sólo el PDF de la factura 3668
- **THEN** la factura se crea en "Borrador" con número `3668`, periodo `01/2026`, UUID `A328F91A-DDDD-4624-89AC-877819F5B540` y moneda MXN, y la respuesta lleva al Paso 2

#### Scenario: PDF y XML
- **WHEN** el proveedor carga el PDF y el XML de la misma factura
- **THEN** los datos fiscales se toman del XML y ambos documentos quedan ligados a la factura

#### Scenario: PDF sin datos acompañado del XML
- **WHEN** el proveedor carga un PDF cuyo texto no es una representación impresa del CFDI junto con un XML válido
- **THEN** la factura se crea con los datos del XML

#### Scenario: PDF y XML de facturas distintas
- **WHEN** el UUID del PDF es distinto del UUID del XML
- **THEN** la respuesta es HTTP 409 "El PDF y el XML no corresponden a la misma factura" y no se crea la factura

#### Scenario: Sin PDF
- **WHEN** el proveedor envía el Paso 1 sólo con XML
- **THEN** la respuesta es HTTP 400 "Adjunte el PDF de la factura" y no se crea la factura

#### Scenario: Archivo que no es PDF
- **WHEN** el proveedor carga como PDF un archivo `factura.png`
- **THEN** la respuesta es HTTP 400 con el motivo y no se crea la factura ni se escribe ningún archivo en `storage/`

#### Scenario: PDF ilegible
- **WHEN** el PDF no tiene texto y el analizador documental no está disponible, y no se adjuntó XML
- **THEN** la respuesta es HTTP 422 "No pudimos leer los datos de la factura en el PDF. Adjunte el XML." y no se crea la factura

#### Scenario: Número de factura repetido
- **WHEN** el número extraído ya existe en otra factura del mismo proveedor
- **THEN** la respuesta es HTTP 409 "Ya existe una factura con ese número para el proveedor" y no se crea la factura

### Requirement: Extracción de los datos de la factura
El sistema SHALL obtener los datos de la sección 6.3 de la HU-24:
- **con XML:** del XML del CFDI. Además de los datos actuales, SHALL leer serie, folio, régimen fiscal del emisor, clave de unidad, unidad, número de identificación y objeto de impuesto de cada concepto, y el tipo de cada impuesto (traslado o retención);
- **sin XML:** del texto de la representación impresa del CFDI 4.0 en el PDF;
- **PDF sin texto:** del analizador documental configurado. El analizador de la demo SHALL responder que no está disponible y MUST NOT inventar datos.

Son esenciales el UUID, el RFC emisor, el RFC receptor, la fecha, el subtotal, el total, la moneda y al menos un concepto. La extracción SHALL guardar los datos y su fuente (`xml`, `pdf_text` u `ocr`) en `metadata_json` del documento del que salieron.

#### Scenario: Conceptos de la factura 3668
- **WHEN** se extraen los datos del PDF de la factura 3668
- **THEN** se obtiene un concepto con cantidad 1.00, clave de unidad `H87`, unidad `PZ`, no. de identificación `L-31T-900`, descripción "LTH TIPO L-31T-900 AR BATERIA (OC/25704872)", precio unitario 3,559.05, objeto de impuesto `02`, importe 3,559.05 e IVA tasa 0.160000 por 569.45

#### Scenario: Emisor y receptor de la factura 3668
- **WHEN** se extraen los datos del PDF de la factura 3668
- **THEN** el emisor es `GOHS60031745A` · SOCORRO PATRICIA GONZALEZ HERNANDEZ · régimen `612`, y el receptor `IME010718PU3` · INTERMODAL MEXICO · régimen `601` · uso `G03` · C.P. `11700`

#### Scenario: Maqueta del documento de negocio
- **WHEN** se extraen los datos del PDF de la factura 3668 con la maqueta del ejemplo: el RFC del emisor y el del cliente sin la etiqueta "RFC", el "RFC PROVEEDOR DE CERTIFICACIÓN" entre los datos del timbre, la columna "Objeto Imp." con "02 - Sí objeto de impuesto." y el detalle del concepto debajo de su renglón
- **THEN** se obtienen los mismos datos que de su XML, y el RFC del proveedor de certificación no se toma como RFC del emisor ni del cliente

#### Scenario: Totales de la factura 3668
- **WHEN** se extraen los datos del PDF de la factura 3668
- **THEN** el subtotal es 3,559.05, el IVA trasladado 569.45, el total 4,128.50, la moneda `MXN`, la forma de pago `99`, el método `PPD` y la fuente `pdf_text`

#### Scenario: Datos ampliados del XML
- **WHEN** se lee el XML de la factura 3668
- **THEN** se obtienen el folio `3668`, el régimen del emisor `612` y, en el concepto, `ClaveUnidad` `H87`, `Unidad` `PZ`, `NoIdentificacion` `L-31T-900`, `ObjetoImp` `02` y un traslado `002` de tasa `0.160000`

#### Scenario: Analizador de demo
- **WHEN** se pide al analizador de la demo extraer una factura
- **THEN** responde que no está disponible, sin devolver datos

### Requirement: Revisión de los datos junto a la imagen de la factura
El Paso 2 ("Revisión", `GET /invoices/{id}/data`) SHALL estar disponible sólo para el Proveedor de la factura, sobre facturas nacionales en "Borrador", "Cargada" u "Observaciones". Una factura en otro estatus SHALL redirigir a su detalle, y una factura internacional, a su carga documental. La página SHALL mostrar:
- a la izquierda, las páginas del PDF de la factura como imagen;
- a la derecha, los datos extraídos con su fuente: factura (serie y folio, UUID, fecha, tipo, moneda, forma y método de pago), proveedor (RFC, nombre y régimen), cliente (RFC, nombre, régimen, uso de CFDI y C.P.), conceptos (cantidad, unidad, descripción, precio unitario, objeto de impuesto, importe e IVA) con la orden de compra detectada, y totales;
- junto a cada dato validado, el resultado de la Validación 1 (`PRV-001` a `PRV-003` y las reglas XML con las Reglas de Validación vigentes): ✓ si pasa y ✗ con el valor esperado si falla;
- el checklist de archivos de la factura con su carga, y los botones "Verificar" y "Enviar a validación".

La Validación 1 SHALL calcularse con los archivos vigentes en cada apertura de la página y MUST NOT cambiar el estatus ni los resultados guardados de la factura.

#### Scenario: Revisión de la factura 3668
- **WHEN** el proveedor abre el Paso 2 de la factura 3668
- **THEN** ve la imagen de la página 1 a la izquierda y, a la derecha, los datos con `PRV-001`, `PRV-002`, `PRV-003`, `XML-002`, `XML-005`, `XML-009` y `XML-011` en `PASS`

#### Scenario: Factura emitida a otro cliente
- **WHEN** el RFC receptor es `ULT940623AG0`
- **THEN** el dato RFC del cliente muestra ✗ con el valor esperado configurado y `XML-002` resulta `FAIL`

#### Scenario: Revisión de otro proveedor
- **WHEN** un proveedor abre el Paso 2 de una factura de otro proveedor
- **THEN** la respuesta es HTTP 404

#### Scenario: Revisión de una factura enviada
- **WHEN** el proveedor abre el Paso 2 de una factura "Enviada"
- **THEN** la respuesta redirige al detalle de la factura

### Requirement: Reemplazo del PDF o del XML
Al cargar en una factura nacional editable un nuevo PDF del CFDI o un nuevo XML del CFDI (`POST /invoices/{id}/documents`), el sistema SHALL volver a extraer los datos con el archivo nuevo y el otro vigente, con las mismas reglas del Paso 1: HTTP 409 si los UUID difieren, HTTP 422 si no hay datos legibles y HTTP 409 si el número resultante ya existe en otra factura del proveedor. Un rechazo MUST NOT escribir el archivo ni cambiar la factura.

Si procede, SHALL actualizar número, periodo, UUID, fecha, importes, moneda y orden de compra detectada, y auditar `INVOICE_DATA_EXTRACTED` con los valores anteriores y los nuevos de los campos que cambiaron. Desde el Paso 2 (`next=data`), la carga SHALL regresar al Paso 2.

#### Scenario: XML agregado después del PDF
- **WHEN** una factura registrada sólo con PDF recibe el XML de la misma factura
- **THEN** los datos pasan a tomarse del XML y la respuesta regresa al Paso 2

#### Scenario: XML de otra factura
- **WHEN** una factura registrada con el PDF de la factura 3668 recibe un XML con otro UUID
- **THEN** la respuesta es HTTP 409 "El PDF y el XML no corresponden a la misma factura" y la factura conserva sus datos y documentos

### Requirement: Validación de los datos del proveedor
`PRV-001` a `PRV-003` SHALL evaluarse según la sección 6.4 de la HU-24 en la Validación 1 y otra vez al verificar y al enviar:
- PRV-001 (`CRITICAL`): el RFC emisor es el RFC del proveedor del usuario;
- PRV-002 (`ERROR`): el nombre del emisor coincide con la razón social del proveedor, sin distinguir mayúsculas, acentos, espacios ni signos;
- PRV-003 (`ERROR`): la factura trae el régimen fiscal del emisor y es una clave activa del catálogo de regímenes fiscales.

Para un proveedor internacional las tres SHALL resultar `NOT_APPLICABLE` con "No aplica a proveedores internacionales".

#### Scenario: RFC emisor de otro proveedor
- **WHEN** el RFC emisor de la factura no es el RFC del proveedor del usuario
- **THEN** `PRV-001` resulta `FAIL` (`CRITICAL`) con "El RFC emisor <rfc> no corresponde al proveedor <rfc>" y el envío no procede

#### Scenario: Nombre con acentos y mayúsculas distintos
- **WHEN** el emisor es "Socorro Patricia González Hernández" y el proveedor "SOCORRO PATRICIA GONZALEZ HERNANDEZ"
- **THEN** `PRV-002` resulta `PASS`

#### Scenario: Razón social con signos
- **WHEN** el emisor es "TECNOLOGIA INTEGRAL DEL CENTRO, S.A. DE C.V." y el proveedor "Tecnologia Integral del Centro SA de CV"
- **THEN** `PRV-002` resulta `PASS`

#### Scenario: Sin régimen fiscal del emisor
- **WHEN** la factura no trae el régimen fiscal del emisor
- **THEN** `PRV-003` resulta `FAIL` "Falta el régimen fiscal del emisor"

#### Scenario: Régimen inactivo
- **WHEN** la factura trae el régimen `612` y el Administrador lo desactivó en el catálogo
- **THEN** `PRV-003` resulta `FAIL` "Régimen fiscal 612 no válido"
