# HU-01 · Carga masiva de proveedores

| Campo | Valor |
| --- | --- |
| ID | HU-01 |
| Rol | Administrador |
| Módulo | A. Administración y Configuración |
| Prioridad | Alta (alcance comprometido del MVP) |
| Origen | Documento de HUs (literal) — `HUs Portal Proveedores ULTRASIST_v2.docx` |
| Requisito funcional | RF-01 (ERS v1.3) |
| Regla de negocio | RN-HU01-01 |
| Change OpenSpec sugerido | `carga-masiva-proveedores` |
| Capacidad nueva | `catalogo-proveedores` |
| Capacidades modificadas | `integridad-datos`, `observabilidad` |
| Estado | Lista para `/opsx:propose`. Decisiones de negocio y arquitectura confirmadas en la revisión del 2026-09-24 (secciones 5 y 10) |
| Estimación | Por definir en el refinamiento |
| Versión / fecha | 1.2 · 2026-09-24 · Equipo Técnico |

## Cómo usar este documento con OpenSpec

Ejecutar `/opsx:propose carga-masiva-proveedores` con este documento como entrada. Cada sección alimenta un artefacto:

| Artefacto OpenSpec | Secciones de esta HU |
| --- | --- |
| `proposal.md` — Why | 1, 2 |
| `proposal.md` — What Changes | 3, 6 |
| `proposal.md` — Capabilities | Tabla de metadatos, 8, 9 |
| `proposal.md` — Impact | 11 |
| `specs/catalogo-proveedores/spec.md` | 8 (se copia tal cual bajo `## ADDED Requirements`) |
| `specs/integridad-datos/spec.md`, `specs/observabilidad/spec.md` | 9 (bloques listos para copiar) |
| `design.md` | 4, 5, 10 |
| `tasks.md` | 11, 13 |

---

## 1. Historia de usuario

**Texto literal (documento de HUs):**

> Yo como administrador requiero una opción para cargar de forma masiva los registros de los proveedores a través de un formato de Excel predefinido para tener cargado en el sistema el catálogo de los proveedores.

**Reformulación:**

- **Como** Administrador del portal,
- **quiero** cargar desde un archivo de Excel, con una plantilla que proporciona el propio sistema, los registros de muchos proveedores en una sola operación,
- **para** tener el catálogo de proveedores en el sistema sin capturarlos uno por uno, como base para autorizarlos (HU-02) y enviarles sus credenciales (HU-03).

**Regla de negocio asociada:**

> **RN-HU01-01.** Se deben mapear los datos requeridos dentro del catálogo de proveedores.

## 2. Contexto y motivación

El catálogo de proveedores es el requisito base del MVP (ERS §2.5): sin él no se puede autorizar proveedores ni enviar credenciales, y tampoco validar ni recibir facturas. Hoy el único medio de alta es un formulario individual, inviable para poblar el catálogo inicial. El Alcance del MVP (minuta del 21-sep-2026) incluye explícitamente, para el Administrador, "Administrar y cargar catálogos" y "Administrar proveedores y accesos al portal".

La carga también debe dejar en el catálogo los datos que consumen las HU posteriores:

- **Origen Nacional/Internacional:** lo requieren HU-04, HU-13, HU-15 y HU-16.
- **Correo:** HU-03 envía ahí las credenciales y RN-HU20-03 lo usa para las notificaciones.
- **Identificación fiscal:** el RFC para los proveedores nacionales y el identificador fiscal extranjero para los internacionales.

## 3. Alcance

### Dentro del alcance

- Descarga de la plantilla de Excel (`.xlsx`) predefinida, generada por el sistema.
- Carga y validación del archivo: tipo, tamaño, estructura de la plantilla y límites.
- Mapeo de cada columna a un campo del catálogo y normalización de valores (RN-HU01-01).
- Validación de cada fila con reglas distintas para proveedores Nacional e Internacional.
- Detección de duplicados, tanto dentro del archivo como contra el catálogo.
- Confirmación ante filas con errores: una ventana emergente deja elegir entre corregir primero (opción predeterminada) o registrar sólo las filas válidas.
- Registro atómico de las filas que se registran.
- Estatus inicial **"Registrado"**, sin acceso al portal.
- Resumen del resultado, auditoría y evento de log.
- Cambios de modelo: origen Nacional/Internacional, identificador fiscal extranjero, país y estatus `REGISTERED`.

### Fuera del alcance

| Tema | Motivo / dónde se atiende |
| --- | --- |
| Autorizar proveedores (`Registrado → Autorizado`) | HU-02 |
| Crear usuarios del portal, generar contraseñas temporales y enviar correos | HU-03 |
| Actualizar proveedores existentes mediante la carga (upsert) | La HU pide *cargar* el catálogo, no mantenerlo (RD-03) |
| Alinear el alta individual (`POST /suppliers`) con el estatus `REGISTERED` y el origen | HU-02; hasta entonces el formulario conserva su comportamiento |
| Carga masiva de otros catálogos o de contratos | HU-07 |
| Expediente documental de proveedores internacionales (el Anexo A sólo cubre personas físicas y morales mexicanas) | HU-04 |
| Datos bancarios | RD-08 |
| Domicilio y código postal del proveedor | Ninguna HU del MVP los usa: HU-06 compara la dirección de ULTRASIST, no la del proveedor (RD-09) |

## 4. Situación actual del PoC

| Aspecto | Hoy | Brecha para HU-01 |
| --- | --- | --- |
| Alta de proveedores | Formulario individual `POST /suppliers` (sólo `ADMIN`) con razón social, RFC, tipo de persona y correo | No hay carga masiva ni plantilla |
| Clasificación | `supplier_type`: `PERSONA_FISICA` / `PERSONA_MORAL` | No existe el origen Nacional/Internacional |
| Identidad fiscal | `suppliers.rfc` es `VARCHAR(13)`, obligatorio y único | Un proveedor extranjero no tiene RFC propio. En el CFDI usa el genérico `XEXX010101000`, que violaría la unicidad |
| Estatus | `ACTIVE` / `INACTIVE`; el alta nace en `ACTIVE` | No hay estatus previo a la autorización (la minuta habla de proveedor "registrado" y luego "Aprobado/Autorizado") |
| Validación del RFC | Longitud de 12 a 13 caracteres y mayúsculas | No valida el patrón SAT ni la coherencia con el tipo de persona |
| Correo | Sin unicidad en `suppliers`; `users.email` es único y cada usuario pertenece a un solo proveedor | Si dos proveedores comparten correo, HU-03 no puede crear el usuario del segundo |
| Datos bancarios | `bank_information` en texto plano | La auditoría del 2026-09-22 lo señala como dato sensible; no debe alimentarse de forma masiva |
| Lectura de Excel | No hay dependencia para leer Excel | Hay que añadir `openpyxl` y `defusedxml` al lock y auditarlas con `pip-audit` |
| Regla SUP-001 | La validación de facturas exige `supplier.status == ACTIVE` | Sin cambio: un proveedor `REGISTERED` no pasa la validación, que es lo esperado |

## 5. Reglas de negocio

**Oficial:** RN-HU01-01, "Se deben mapear los datos requeridos dentro del catálogo de proveedores". Ninguna fuente enumera esos datos. RD-09 los fija a partir de lo que ya usa el catálogo y de lo que consumen las HU del MVP (sección 6.2).

**Reglas derivadas**, fundamentadas en las fuentes del proyecto. Las marcadas con ✔ se confirmaron en la revisión de la HU del 2026-09-24:

| ID | Regla | Fundamento |
| --- | --- | --- |
| RD-01 | El sistema genera la plantilla y reconoce el archivo por sus encabezados | ERS §3.3: "formato Excel predefinido para el alta masiva" |
| RD-02 ✔ | Si hay filas con errores, no se registra nada hasta que el Administrador elige en una ventana emergente: "No, corregir primero (Recomendado)", la opción preseleccionada, o "Agrega las filas válidas y omite el resto". Los errores de archivo nunca ofrecen el registro parcial | Revisión de la HU. La opción predeterminada respeta la spec `proteccion-http` (el estado no cambia ante un error de negocio) |
| RD-03 ✔ | Un proveedor que ya existe se omite y no se actualiza | La HU pide cargar el catálogo, no mantenerlo. Sobrescribir un correo desviaría las credenciales de HU-03, y omitir hace idempotente la recarga |
| RD-04 ✔ | Estatus inicial "Registrado" (`REGISTERED`), sin usuario ni correo. `ACTIVE` sigue siendo el estatus operativo hasta HU-02 | Minuta, "Acceso de proveedores": el acceso se habilita al autorizar; HU-02 y HU-03 |
| RD-05 ✔ | La carga incluye proveedores internacionales. El Nacional se identifica por su RFC y el Internacional por el par (país, identificador fiscal) | Minuta, "Proveedores extranjeros". En el CFDI el extranjero usa el RFC genérico `XEXX010101000`, que no identifica a nadie |
| RD-06 | Un correo corresponde a un solo proveedor y no puede usarlo otro proveedor ni otro usuario | `users.email` es único y `users.supplier_id` liga cada usuario a un proveedor; HU-03 crea ese usuario con el correo del proveedor |
| RD-07 | Máximo 1000 proveedores y 5 MB por archivo | La carga es aditiva e idempotente: un catálogo mayor se carga en varios archivos. El límite acota memoria y tiempo de respuesta |
| RD-08 | Los datos bancarios no se cargan | La Guía de Validación del PoC deja "banca" fuera de alcance, la auditoría técnica marca `bank_information` como dato sensible y el Anexo A acredita la CLABE con el estado de cuenta |
| RD-09 | Sólo se cargan los campos que ya usa el catálogo o que consumen las HU del MVP | Columna "Lo usa" de la sección 6.2 |
| RD-10 | Un duplicado dentro del archivo invalida todas sus apariciones | Con el registro parcial, conservar una de las filas repetidas sería una elección arbitraria entre datos distintos |

## 6. Plantilla de Excel (formato predefinido)

### 6.1 Estructura del libro

- **Archivo:** `plantilla_carga_proveedores_v1.xlsx`, generado por el sistema. No se versiona un binario en el repositorio.
- **Hoja `Proveedores`:** contiene los encabezados en la fila 1 y los datos desde la fila 2. La plantilla se entrega sin filas de datos, con listas desplegables en `Origen`, `Tipo de persona` y `Convenio de confidencialidad`, y con formato de texto en `RFC`, `Identificador fiscal extranjero` y `Teléfono` para que Excel no convierta los valores.
- **Hoja `Instrucciones`:** incluye la versión de la plantilla, la descripción de cada columna, un ejemplo por origen y la lista de códigos de país ISO 3166-1 alfa-2. Los ejemplos nunca se importan.

### 6.2 Columnas y mapeo al catálogo (RN-HU01-01)

| # | Encabezado | Obligatoria | Formato / valores | Campo del catálogo | ¿Nuevo? | Lo usa |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Origen | Sí | `Nacional` / `Internacional` | `origin` (`NATIONAL` / `INTERNATIONAL`) | Sí | HU-04, HU-13, HU-15, HU-16 |
| 2 | Tipo de persona | Sí | `Física` / `Moral` | `supplier_type` (`PERSONA_FISICA` / `PERSONA_MORAL`) | No | Expediente del Anexo A; longitud del RFC |
| 3 | Razón social | Sí | 2 a 250 caracteres | `business_name` | No | Listados; correos de HU-14 y RN-HU20-02 ("proveedor Y") |
| 4 | RFC | Nacional: sí. Internacional: vacío | Patrón SAT `^[A-ZÑ&]{3,4}[0-9]{6}[A-Z0-9]{3}$`; 12 caracteres para persona moral y 13 para física; fecha AAMMDD válida; no genérico | `rfc` (pasa a admitir `NULL`) | No | Identidad del proveedor nacional; HU-13 |
| 5 | Identificador fiscal extranjero | Internacional: sí. Nacional: vacío | 1 a 40 caracteres: letras, dígitos, espacio, `.`, `-`, `/` | `foreign_tax_id` | Sí | Identidad del proveedor internacional; HU-16 ("datos del proveedor") |
| 6 | País | Internacional: sí. Nacional: vacío o `MX` | Código ISO 3166-1 alfa-2; `MX` no válido para Internacional | `country` (Nacional → `MX`) | Sí | Identidad del proveedor internacional; HU-16 |
| 7 | Correo electrónico | Sí | Correo válido de hasta 255 caracteres, único | `email` | No | HU-03 (credenciales); RN-HU20-03 (notificaciones) |
| 8 | Teléfono | No | 7 a 30 caracteres: dígitos, espacio, `+`, `(`, `)`, `-` | `phone` | No | Contacto (campo actual del catálogo) |
| 9 | Convenio de confidencialidad | No | `Sí` / `No`; vacío equivale a `No` | `confidentiality_agreement` | No | Prerrequisito de los Lineamientos (1.iii) |
| 10 | Notas | No | Hasta 1000 caracteres | `notes` | No | Campo actual del catálogo |

Hay campos del catálogo que la plantilla no incluye:

- `status`: lo asigna el sistema (`REGISTERED`).
- `economic_proposal`: se acredita con un documento del expediente (Anexo A).
- `bank_information`: queda fuera por RD-08.

### 6.3 Límites

| Límite | Valor |
| --- | --- |
| Tamaño del archivo | 5 MB |
| Contenido descomprimido del `.xlsx` | 50 MB (defensa contra bombas de descompresión) |
| Filas de datos por carga | 1 a 1000; las filas completamente vacías no cuentan |
| Errores mostrados | Los primeros 200, ordenados por fila, más el conteo de los restantes |

## 7. Flujo de uso

1. El Administrador entra a **Proveedores › Carga masiva** (`GET /suppliers/import`). Un enlace en el listado de proveedores lleva a esta página.
2. Descarga la plantilla (`GET /suppliers/import/template`) y captura o pega los proveedores en la hoja `Proveedores`.
3. Selecciona el archivo (el campo acepta `.xlsx`) y pulsa **Cargar proveedores**. La página envía el archivo a `POST /suppliers/import` en modo `strict`.
4. **Nivel 1, archivo:** el sistema comprueba el tipo, el tamaño, la estructura, la plantilla y los límites. Si algo falla, muestra un mensaje único, no procesa filas y no ofrece el registro parcial.
5. **Nivel 2, filas:** el sistema valida todas las filas en una sola pasada y detecta los duplicados.
   - **Sin errores:** registra los proveedores nuevos y muestra el resumen (registrados y omitidos).
   - **Con errores y al menos una fila registrable:** no registra nada y abre una ventana emergente con el texto *"Algunas filas contienen errores o no se han podido leer correctamente. ¿Desea agregar las filas válidas?"* y dos botones:
     - **No, corregir primero (Recomendado)**: preseleccionado y resaltado. Cierra la ventana y muestra la lista "Fila N · Columna: mensaje"; el catálogo no cambia. Cerrar la ventana o pulsar Esc equivale a esta opción.
     - **Agrega las filas válidas y omite el resto**: reenvía el mismo archivo en modo `partial`. El sistema lo valida de nuevo, registra sólo las filas sin errores y muestra el resumen con las filas no registradas y sus errores.
   - **Con errores y ninguna fila registrable:** muestra la lista de errores, sin ventana emergente.
6. **Registro:** las filas que se registran entran en una sola transacción.
7. Los proveedores quedan en **"Registrado"**. El siguiente paso es autorizarlos (HU-02).

## 8. Criterios de aceptación — spec `catalogo-proveedores`

Los requisitos de esta sección siguen el formato de delta de OpenSpec. Se copian tal cual a `openspec/changes/carga-masiva-proveedores/specs/catalogo-proveedores/spec.md`, bajo el encabezado `## ADDED Requirements`.

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

## 9. Deltas sobre capacidades existentes

### 9.1 `integridad-datos`

Destino: `openspec/changes/carga-masiva-proveedores/specs/integridad-datos/spec.md`. El requisito modificado reproduce el bloque completo vigente con los cambios aplicados.

```markdown
## MODIFIED Requirements

### Requirement: Restricciones CHECK sobre estados, montos y vigencias
La base de datos SHALL rechazar:
- valores de estado, rol, tipo de proveedor, origen de proveedor, severidad, estado de regla, decisión de revisión o estado de procesamiento que no pertenezcan a su enumeración;
- montos negativos en factura;
- `authorized_amount <= 0` en contratos y `new_amount <= 0` en enmiendas;
- `end_date < start_date` en contratos;
- `validation_score` fuera de 0..100;
- `confidence` fuera de 0..1.

`suppliers.status` SHALL ser una enumeración tipada (`REGISTERED`, `ACTIVE`, `INACTIVE`), `suppliers.origin` SHALL ser una enumeración tipada (`NATIONAL`, `INTERNATIONAL`) y `contracts.status` SHALL ser una enumeración tipada (`ACTIVE`, `INACTIVE`).

#### Scenario: Estado inválido por SQL directo
- **WHEN** se ejecuta `UPDATE invoices SET status = 'APROBADA'`
- **THEN** la base de datos rechaza la operación

#### Scenario: Estatus de proveedor fuera de catálogo
- **WHEN** se ejecuta `UPDATE suppliers SET status = 'PENDIENTE'`
- **THEN** la base de datos rechaza la operación

#### Scenario: Monto negativo
- **WHEN** se intenta guardar una factura con `total = -1.00`
- **THEN** la base de datos rechaza la operación

#### Scenario: Vigencia invertida
- **WHEN** se intenta crear un contrato con `end_date` anterior a `start_date`
- **THEN** la base de datos rechaza la operación y el formulario muestra el error sin HTTP 500

#### Scenario: Score fuera de rango
- **WHEN** se intenta guardar `validation_score = 101`
- **THEN** la base de datos rechaza la operación

## ADDED Requirements

### Requirement: Identidad fiscal única de proveedores
La base de datos SHALL imponer unicidad sobre `suppliers.rfc` (se permiten múltiples `NULL`) y sobre `(suppliers.country, suppliers.foreign_tax_id)`. Una restricción `CHECK` SHALL exigir coherencia con el origen: un proveedor `NATIONAL` MUST tener `rfc` no nulo, `foreign_tax_id` nulo y `country = 'MX'`; un proveedor `INTERNATIONAL` MUST tener `rfc` nulo, `foreign_tax_id` no nulo y `country` distinto de `'MX'`. Los proveedores existentes antes del cambio SHALL quedar como `NATIONAL` con `country = 'MX'`.

#### Scenario: Varios internacionales sin RFC
- **WHEN** existen varios proveedores `INTERNATIONAL` con `rfc = NULL`
- **THEN** la restricción de unicidad no los rechaza

#### Scenario: Identificador fiscal repetido en el mismo país
- **WHEN** se inserta un segundo proveedor con `country = 'US'` y `foreign_tax_id = '12-3456789'`
- **THEN** la base de datos rechaza la operación

#### Scenario: Mismo identificador fiscal en países distintos
- **WHEN** se insertan dos proveedores con `foreign_tax_id = '12-3456789'`, uno con `country = 'US'` y otro con `country = 'CA'`
- **THEN** ambos se aceptan

#### Scenario: Proveedor nacional sin RFC
- **WHEN** se ejecuta `UPDATE suppliers SET rfc = NULL` sobre un proveedor `NATIONAL`
- **THEN** la base de datos rechaza la operación

#### Scenario: Proveedores previos al cambio
- **WHEN** se aplica la migración sobre una base con proveedores existentes
- **THEN** todos quedan con `origin = 'NATIONAL'` y `country = 'MX'` y conservan su RFC y su estatus
```

### 9.2 `observabilidad`

Destino: `openspec/changes/carga-masiva-proveedores/specs/observabilidad/spec.md`.

```markdown
## MODIFIED Requirements

### Requirement: Registro de eventos técnicos del flujo
El sistema SHALL registrar:
- subida de documento: `invoice_id` o `supplier_id`, tipo documental, extensión y tamaño en bytes;
- inicio y fin de validación, con `invoice_id`, duración en milisegundos, score, número de bloqueos y estado resultante;
- decisión de revisión, con `invoice_id` y decisión;
- todo fallo de parseo de XML o de apertura de PDF, con el tipo y el mensaje técnico de la excepción, registrado **antes** de devolver el mensaje genérico al usuario;
- carga masiva de proveedores: evento `supplier.bulk_import` con `mode` (`strict` o `partial`), `result` (`imported`, `partial`, `rejected` o `conflict`), filas leídas (`rows`), proveedores registrados (`registered`), proveedores omitidos (`skipped`), filas con errores (`invalid`), tamaño del archivo en bytes (`size_bytes`) y duración en milisegundos (`duration_ms`).

#### Scenario: Validación registrada
- **WHEN** se ejecuta la prevalidación de una factura
- **THEN** el log contiene un evento `validation.started` y un evento `validation.completed` con `duration_ms`, `score` y `blockers`

#### Scenario: PDF dañado
- **WHEN** se sube un PDF que PyMuPDF no puede abrir
- **THEN** el usuario ve "El PDF no puede abrirse o esta danado" y el log contiene un evento `pdf.analysis_failed` con el tipo y el mensaje de la excepción original

#### Scenario: Carga masiva registrada
- **WHEN** el Administrador carga un archivo válido con 3 proveedores nuevos
- **THEN** el log contiene un evento `supplier.bulk_import` con `mode = "strict"`, `result = "imported"`, `rows = 3`, `registered = 3`, `skipped = 0`, `invalid = 0`, `size_bytes` y `duration_ms`

#### Scenario: Carga parcial registrada
- **WHEN** el Administrador agrega las filas válidas de un archivo con 2 filas con errores
- **THEN** el log contiene un evento `supplier.bulk_import` con `mode = "partial"`, `result = "partial"` e `invalid = 2`
```

## 10. Notas de diseño (insumo para `design.md`)

| # | Decisión | Alternativas descartadas y motivo |
| --- | --- | --- |
| D1 | Leer y generar el Excel con `openpyxl` (`read_only=True`; se detectan fórmulas sin evaluarlas) y proteger el XML con `defusedxml` | `pandas`: dependencia pesada (numpy) para una tarea tabular simple. `python-calamine`: sólo lee y no genera la plantilla con listas desplegables. CSV: no es "Excel predefinido" y da problemas de codificación con acentos y la Ñ |
| D2 | Validar en tres fases: (1) archivo; (2) filas, con un esquema Pydantic `SupplierImportRow` que reutiliza validadores de campo compartidos; (3) duplicados en lote, con una consulta por RFC, otra por (país, identificador) y otra por correos en `suppliers` y `users` | Validar fila por fila contra la base (N+1): con 1000 filas son miles de consultas |
| D3 | Modo `strict` por omisión y registro parcial sólo con confirmación explícita (RD-02); los existentes se omiten (RD-03) | Registro parcial automático: deja el catálogo a medias sin que el Administrador lo decida. Upsert: sobrescribir un correo desvía las credenciales de HU-03 |
| D4 | Identidad fiscal por origen: `rfc` admite `NULL` y se añaden `foreign_tax_id` y `country` con unicidad compuesta y un `CHECK` de coherencia | RFC genérico `XEXX010101000`: choca con la unicidad. Tabla aparte para extranjeros: duplica consultas y flujos |
| D5 | Nuevo estatus `REGISTERED`; `ACTIVE` conserva su significado hasta que HU-02 defina la transición a "Autorizado". La regla SUP-001 ya rechaza cualquier estatus distinto de `ACTIVE` | Crear el proveedor en `ACTIVE`: se saltaría la autorización que exige la minuta |
| D6 | Declarar las rutas `/suppliers/import*` antes de `/suppliers/{supplier_id}` | Si no, `import` coincide con la ruta de detalle (parámetro `int`) y responde 422 |
| D7 | No conservar el archivo: la auditoría guarda su SHA-256 y su tamaño | Guardarlo en `storage/` retiene datos personales que acabarían en respaldos y paquetes, el riesgo que señaló la auditoría técnica. La trazabilidad por proveedor ya la da `SUPPLIER_CREATED` |
| D8 | Procesar en memoria sin pasar por `LocalFileStorage`; los límites (5 MB, 50 MB, 1000 filas) quedan como constantes de un solo módulo | Reutilizar `max_upload_mb` (20 MB): es un límite demasiado alto para un Excel de 1000 filas (~100 KB) |
| D9 | Una revisión Alembic nueva: columnas `origin`, `foreign_tax_id` y `country`; `rfc` que admite `NULL`; `CHECK` de enumeraciones y de coherencia; unicidad compuesta; relleno de los existentes como `NATIONAL`/`MX`. El downgrade lanza `NotImplementedError` si existen proveedores `INTERNATIONAL` o `REGISTERED` (revertir perdería datos) | Editar `0001_postgresql_baseline`: prohibido por la regla "Una revisión por cambio de modelo" |
| D10 | La unicidad del correo se valida en la carga (contra `suppliers` y `users`) sin añadir una restricción en `suppliers.email` | `users.email` ya es único y es donde HU-03 materializa el acceso. Una restricción nueva obligaría a cambiar también el alta individual, que está fuera del alcance |
| D11 | Confirmación sin estado en el servidor. Un script estático (`app/static/js/`, porque la CSP `default-src 'self'` prohíbe scripts en línea) envía el formulario con `fetch` y `Accept: application/json`. La ventana es un modal de Bootstrap, que ya viene incluido. El archivo permanece en el navegador: al confirmar se reenvía con `mode = partial` y `expected_sha256`, y el servidor lo valida de nuevo. Los datos del archivo se pintan con `textContent`, nunca con `innerHTML` | Guardar el archivo o las filas validadas en `storage/temp` con un token: deja datos personales en disco, obliga a limpiar las cargas abandonadas y contradice D7. Confiar en las filas validadas que devuelve el cliente: permitiría registrar datos sin validar |

**Riesgos y mitigaciones**

- **Excel convierte valores** (números largos, fechas) → formato de texto en la plantilla, conversión de enteros a texto y errores explícitos ante fechas y fórmulas.
- **Hojas con formato aplicado a columnas completas**, cuya dimensión declarada llega a 1 048 576 filas → lectura en modo streaming que se detiene al superar 1000 filas con datos, sin fiarse de la dimensión declarada.
- **Archivos editados en LibreOffice o Google Sheets**, que pueden perder las listas desplegables → la validación del servidor no depende de ellas. Se prueba con LibreOffice Calc.
- **Catálogo con más de 1000 proveedores** → se divide en varios archivos; la carga es aditiva e idempotente.
- **Carga concurrente** → la unicidad en base de datos decide y el sistema responde 409 sin registrar nada.
- **El catálogo cambia entre la validación y la confirmación** (otro Administrador registra una de las filas) → la segunda validación la trata como existente y la omite; el resumen refleja lo que realmente se registró.
- **El archivo en disco cambia antes de confirmar** → `expected_sha256` lo detecta y el sistema responde 409.
- **Navegador sin JavaScript** → la página muestra un aviso `<noscript>`. Es una herramienta interna del Administrador y la app ya depende de `app.js` y de Bootstrap.

## 11. Impacto

| Área | Cambio |
| --- | --- |
| `app/core/constants.py` | `SupplierStatus.REGISTERED`, enumeración `SupplierOrigin`, etiquetas en español del estatus de proveedor y límites de la carga |
| `app/models/__init__.py` | `Supplier`: `origin`, `foreign_tax_id` y `country`; `rfc` admite `NULL`; restricciones de unicidad y `CHECK` |
| `alembic/versions/` | Nueva revisión posterior a `0001_postgresql_baseline` |
| `app/schemas/__init__.py` | `SupplierImportRow` y validadores de RFC, correo y país compartidos |
| `app/services/` | Nuevo `supplier_import_service.py` (lectura, validación y registro) y generación de la plantilla |
| `app/routers/suppliers.py` | `GET /suppliers/import`, `GET /suppliers/import/template` y `POST /suppliers/import` (modos `strict` y `partial`, respuestas JSON) |
| `app/templates/suppliers/` | Nueva `import.html` con el modal de confirmación; enlace desde `list.html`; estatus "Registrado" en el listado y el detalle |
| `app/static/js/` | Nuevo script de la carga: envío con `fetch`, modal, reenvío en modo `partial` y pintado del resumen y los errores |
| `requirements.txt` / `requirements.lock` | `openpyxl` y `defusedxml` con hashes; `pip-audit` sin hallazgos |
| `scripts/seed_db.py` | Los proveedores demo se crean con `origin = NATIONAL` |
| `tests/` | Nuevo `test_carga_masiva_proveedores.py`, con libros generados en memoria y un escenario por requisito; ajustes en `test_integridad.py` y `test_migraciones.py` |
| `README.md` | Sección de uso de la carga masiva y formato de la plantilla |

## 12. Dependencias

- **Depende de:** ninguna HU (RF-01 es requisito base). Técnicamente depende de la migración a PostgreSQL, ya archivada (`2026-09-24-migrar-a-postgresql`).
- **Habilita** (con lo que cada HU recibe de esta):

| HU | Qué recibe de HU-01 | Qué le toca decidir a esa HU |
| --- | --- | --- |
| HU-02 | Proveedores en `REGISTERED` | La transición a "Autorizado" (renombrar `ACTIVE` o agregar un estatus) y alinear el alta individual |
| HU-03 | Un correo único por proveedor | — |
| HU-04 | El origen Nacional/Internacional | El expediente de los proveedores internacionales (el Anexo A no los cubre) |
| HU-13 | El RFC del proveedor nacional | — |
| HU-15, HU-16 | El identificador fiscal y el país | Agregar el domicilio del proveedor si su validación lo requiere |
| HU-20 (RN-HU20-03) | El correo del proveedor | — |

## 13. Definición de terminado

- [ ] Change `carga-masiva-proveedores` creado con proposal, specs, design y tasks; `openspec validate carga-masiva-proveedores --strict` sin errores.
- [ ] Cada escenario de las secciones 8 y 9 tiene al menos una prueba automatizada que pasa sobre la base PostgreSQL temporal de la sesión.
- [ ] La cobertura no baja del umbral vigente (`--cov-fail-under=93`).
- [ ] Revisión Alembic nueva; `alembic check` sin diferencias; downgrade conforme a D9.
- [ ] `openpyxl` y `defusedxml` en `requirements.txt` y en `requirements.lock` con hashes; `pip-audit` sin hallazgos.
- [ ] `scripts/check.py` en verde (ruff, pytest, `alembic check`, `pip-audit`).
- [ ] Plantilla probada manualmente en Microsoft Excel y LibreOffice Calc: descarga, captura y carga de 1000 filas en 10 s o menos.
- [ ] Ventana de confirmación probada manualmente: "No, corregir primero (Recomendado)" preseleccionada y con el foco, Esc equivale a corregir primero, y "Agrega las filas válidas y omite el resto" registra sólo las filas válidas.
- [ ] README actualizado y datos demo (`seed_db.py`) coherentes con el nuevo modelo.
- [ ] Change archivado y specs sincronizadas (`/opsx:archive`).

## 14. Trazabilidad

| Elemento | Referencia |
| --- | --- |
| Alcance del MVP (minuta del 21-sep-2026) | Rol Administrador: "Administrar y cargar catálogos"; "Administrar proveedores y accesos al portal". Acceso de proveedores: el acceso se habilita al pasar de "registrado" a "Aprobado". Proveedores extranjeros |
| Validación de HUs | HU-01 "Dentro del MVP" (sección 2); RN01 mapeada a HU-01 (sección 5) |
| ERS v1.3 | §3.1 HU-01; §3.2 RF-01; §3.3 "Carga de archivos: formato Excel predefinido"; §3.5 RN-HU01-01; §4.1 matriz HU-01 ↔ RF-01 ↔ RN-HU01-01 |
| Lineamientos de facturación 2024 v1.4.1 | 1.iii convenio de confidencialidad; Anexo A (tipo de persona física/moral; la CLABE se acredita con el estado de cuenta) |
| Guía de Validación Funcional del PoC | Fuera de alcance: "banca" |
| Auditoría técnica 2026-09-22 | `bank_information` en texto plano como dato sensible; riesgo de distribuir datos personales en respaldos y paquetes |
| OpenSpec | Capacidad nueva `catalogo-proveedores`; deltas en `integridad-datos` y `observabilidad`; regla de estado sin cambios de `proteccion-http` |
