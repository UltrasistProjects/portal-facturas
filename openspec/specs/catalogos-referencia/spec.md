# catalogos-referencia Specification

## Purpose
Catálogos de referencia (HU-07, RF-12): monedas, usos de CFDI, formas y métodos de pago y regímenes fiscales; acceso exclusivo del Administrador, alta, edición, desactivación con protección de claves en uso, carga desde Excel y auditoría.
## Requirements
### Requirement: Administración exclusiva del Administrador
Las rutas `/admin/catalogs*` SHALL estar disponibles únicamente para el rol `Administrador`, y sus `POST` MUST exigir un token CSRF válido. El menú Administración SHALL mostrar la opción "Catálogos" sólo al rol `Administrador`. Un catálogo desconocido en la ruta SHALL responder HTTP 404. Las páginas MUST NOT usar scripts ni estilos en línea.

#### Scenario: PMO sin acceso
- **WHEN** un usuario `PMO` solicita `/admin/catalogs`, la página de un catálogo, la plantilla, o envía un alta, una edición, un cambio de estado o una carga
- **THEN** la respuesta es HTTP 403 y ningún catálogo cambia

#### Scenario: Catálogo inexistente
- **WHEN** el Administrador solicita `/admin/catalogs/COUNTRY`
- **THEN** la respuesta es HTTP 404

### Requirement: Catálogos de referencia
El sistema SHALL mantener cinco catálogos de claves, cada una con clave única dentro del catálogo, descripción y estado (activa o inactiva):
- `CURRENCY`, "Monedas": clave de tres letras;
- `CFDI_USE`, "Usos de CFDI": una o dos letras y dos dígitos;
- `PAYMENT_FORM`, "Formas de pago": dos dígitos;
- `PAYMENT_METHOD`, "Métodos de pago": tres letras;
- `TAX_REGIME`, "Regímenes fiscales": tres dígitos.

Desde la instalación SHALL contener, activas:
- las monedas `MXN`, `USD` y `EUR`;
- los 24 usos de CFDI, las 22 formas de pago, los 2 métodos de pago y los 19 regímenes fiscales del catálogo del SAT para CFDI 4.0.

`GET /admin/catalogs` SHALL listar los cinco catálogos con el número de claves activas y totales. La página de cada catálogo SHALL listar sus claves ordenadas por clave, con su estado, y marcar "En uso" las que usan las Reglas de Validación.

#### Scenario: Instalación nueva
- **WHEN** se ejecuta `alembic upgrade head` sobre una base vacía
- **THEN** existen 3 monedas, 24 usos de CFDI, 22 formas de pago, 2 métodos de pago y 19 regímenes fiscales, todas activas

#### Scenario: Claves en uso
- **WHEN** el Administrador abre el catálogo de formas de pago en una instalación nueva
- **THEN** la clave `99` aparece marcada "En uso"

### Requirement: Alta y edición de claves
El Administrador SHALL poder dar de alta una clave con su descripción y editar la descripción de una clave existente. La clave SHALL convertirse a mayúsculas, cumplir el formato de su catálogo y no repetirse en él; la descripción SHALL tener de 1 a 150 caracteres. Una clave MUST NOT cambiarse ni borrarse. Un error de validación SHALL responder HTTP 400 y una clave repetida HTTP 409, ambos con el mensaje en la página.

#### Scenario: Alta de una moneda
- **WHEN** el Administrador da de alta la moneda "cad" con la descripción "Dólar canadiense"
- **THEN** el catálogo de monedas contiene `CAD` activa y la siguiente prevalidación acepta la moneda `CAD` en XML-007

#### Scenario: Clave con formato inválido
- **WHEN** el Administrador da de alta la forma de pago "9A"
- **THEN** la respuesta es HTTP 400 con "Clave: debe tener dos dígitos" y la clave no se crea

#### Scenario: Clave repetida
- **WHEN** el Administrador da de alta el método de pago `PUE`, que ya existe
- **THEN** la respuesta es HTTP 409 con "La clave PUE ya existe en este catálogo"

### Requirement: Desactivación con protección de claves en uso
El Administrador SHALL poder desactivar y reactivar claves. Una clave inactiva MUST NOT ofrecerse en las Reglas de Validación, en el alta de contrato ni en el registro de la factura internacional y, en el caso de las monedas, MUST NOT aceptarse en XML-007. El sistema MUST NOT desactivar una clave que usa el valor esperado de una regla activa de Reglas de Validación, de cualquier origen (régimen de XML-011, método de pago de XML-003, forma de pago de XML-004 o uso de CFDI de XML-005), ni la última moneda activa: responde HTTP 409 con el motivo. Una clave que sólo usa una regla eliminada no está en uso.

#### Scenario: Clave en uso
- **WHEN** el Administrador intenta desactivar el uso de CFDI `G03`, permitido en XML-005 activa
- **THEN** la respuesta es HTTP 409 con "La clave G03 está en uso en Reglas de Validación." y sigue activa

#### Scenario: Clave de una regla eliminada
- **WHEN** XML-011 está eliminada con el régimen `601` y el Administrador desactiva `601`
- **THEN** `601` queda inactiva

#### Scenario: Desactivar una moneda
- **WHEN** el Administrador desactiva la moneda `EUR`
- **THEN** `EUR` queda inactiva, deja de ofrecerse en el alta de contrato y una factura con `Moneda="EUR"` falla XML-007 en su siguiente prevalidación

### Requirement: Carga de un catálogo desde Excel
Para cada catálogo, el Administrador SHALL poder:
- descargar una plantilla `.xlsx` con la hoja "Catalogo", las columnas "Clave", "Descripción" y "Activo" y las claves vigentes;
- cargarla modificada con `POST /admin/catalogs/{catalogo}/import`.

El archivo SHALL validarse con las reglas de la carga masiva de proveedores: sólo `.xlsx`, hasta 5 MB, contenido descomprimido acotado, sin DTD ni entidades XML, encabezados exactos, de 1 a 1000 filas, y celdas sin fórmulas ni fechas.

Cada fila SHALL cumplir:
- clave con el formato del catálogo, sin repetirse en el archivo;
- descripción de 1 a 150 caracteres;
- "Activo" igual a "Sí" o "No"; vacío equivale a "Sí";
- no desactivar una clave en uso por las Reglas de Validación.

El archivo no puede dejar el catálogo de monedas sin claves activas.

Con cualquier error, la respuesta SHALL ser HTTP 400 con los errores por fila (hasta 200 mostrados) y nada se aplica. Sin errores, el sistema SHALL agregar las claves nuevas y actualizar la descripción y el estado de las existentes en una sola transacción. Las claves que no vienen en el archivo MUST NOT cambiar. El resultado SHALL mostrar las claves agregadas, actualizadas y sin cambios.

#### Scenario: Plantilla con el contenido vigente
- **WHEN** el Administrador descarga la plantilla del catálogo de métodos de pago
- **THEN** recibe un `.xlsx` con la hoja "Catalogo" y las filas `PPD` y `PUE` con su descripción y "Sí"

#### Scenario: Carga con claves nuevas y actualizadas
- **WHEN** el Administrador carga en monedas un archivo con `USD` y la descripción "Dólar estadounidense", y `JPY` "Yen japonés"
- **THEN** la respuesta muestra "1 agregada, 1 actualizada, 0 sin cambios", `JPY` queda activa y `MXN` y `EUR` no cambian

#### Scenario: Fila con errores
- **WHEN** el archivo de formas de pago tiene una fila con la clave "9A" y otra que desactiva la clave `99`, en uso
- **THEN** la respuesta es HTTP 400 con un error por cada fila y ninguna clave cambia

#### Scenario: Archivo que no es la plantilla
- **WHEN** el Administrador carga un `.xlsx` sin la hoja "Catalogo"
- **THEN** la respuesta es HTTP 400 con "El archivo no corresponde a la plantilla del catálogo. Descargue la plantilla e intente de nuevo."

### Requirement: Auditoría de los catálogos
El sistema SHALL registrar:
- `CATALOG_ENTRY_CREATED`, con catálogo, clave y descripción;
- `CATALOG_ENTRY_UPDATED`, con la descripción anterior y la nueva;
- `CATALOG_ENTRY_STATUS_CHANGED`, con el estado anterior y el nuevo;
- `CATALOG_IMPORTED`, por cada carga aplicada, con el catálogo y las claves agregadas y actualizadas.

Las operaciones rechazadas y las que no cambian nada MUST NOT generar registros.

#### Scenario: Auditoría de una carga
- **WHEN** el Administrador carga un archivo de monedas que agrega `JPY`
- **THEN** `audit_logs` contiene `CATALOG_IMPORTED` con su `user_id`, `catalog = "CURRENCY"` y `created = ["JPY"]`

### Requirement: Moneda de contratos y facturas del catálogo
La moneda de un contrato y la de una factura SHALL ser una clave del catálogo de monedas:
- el alta de contrato SHALL ofrecer un selector con las monedas activas, con `MXN` preseleccionada si está activa;
- el servidor SHALL rechazar con HTTP 400 y "Moneda: la clave no está activa en el catálogo" una moneda de contrato o de factura internacional inactiva o inexistente, también en una petición directa, sin crear ni cambiar nada;
- la moneda del XML de una factura nacional se guarda sólo si está activa (capacidad `motor-validacion`).

La migración `0021_currency_catalog_mapping` SHALL normalizar `invoices.currency` y `contracts.currency`: recorta espacios, convierte a mayúsculas y aplica los alias `MN` y `MXP` → `MXN`, `DLS`, `DLL` y `US` → `USD`, y `EU` → `EUR`, siempre que el resultado sea una clave del catálogo. Cada valor cambiado SHALL auditarse como `CURRENCY_NORMALIZED`, con el valor anterior y el nuevo y sin usuario. Un valor que no se puede mapear MUST NOT descartarse ni cambiarse: SHALL conservarse y registrarse en el log de la migración. `scripts/reporte_monedas.py` SHALL listar, sin modificar nada, las facturas (folio, proveedor, estatus y moneda) y los contratos (id, proyecto y moneda) cuya moneda no es una clave del catálogo.

#### Scenario: Contrato con moneda del catálogo
- **WHEN** el Administrador abre el alta de contrato
- **THEN** el campo Moneda es un selector con `MXN`, `USD` y `EUR`, y `MXN` está preseleccionada

#### Scenario: Contrato con moneda inválida por petición directa
- **WHEN** una petición directa crea un contrato con `currency = "XYZ"` o con una moneda desactivada
- **THEN** la respuesta es HTTP 400 con "Moneda: la clave no está activa en el catálogo" y no se crea el contrato

#### Scenario: Normalización de monedas existentes
- **WHEN** se aplica la migración sobre una base con un contrato en `"usd "` y una factura en `MN`
- **THEN** el contrato queda en `USD`, la factura en `MXN` y `audit_logs` tiene un `CURRENCY_NORMALIZED` por cada uno

#### Scenario: Moneda que no se puede mapear
- **WHEN** se aplica la migración sobre una base con una factura en `PES`
- **THEN** la factura conserva `PES`, el log de la migración la menciona y `scripts/reporte_monedas.py` la lista con su folio

