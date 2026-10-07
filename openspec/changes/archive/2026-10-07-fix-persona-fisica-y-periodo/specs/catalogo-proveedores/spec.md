## MODIFIED Requirements

### Requirement: Plantilla de Excel predefinida
El sistema SHALL generar y ofrecer al Administrador la plantilla vigente de carga masiva de proveedores en formato `.xlsx`. La plantilla SHALL contener:
- una hoja `Proveedores` con estos encabezados, en este orden, en la fila 1 y sin filas de datos: `Origen`, `Tipo de persona`, `Razón social`, `RFC`, `Identificador fiscal extranjero`, `País`, `Correo electrónico`, `Teléfono`, `Convenio de confidencialidad`, `Notas`;
- listas desplegables en `Origen` (`Nacional`, `Internacional`), `Tipo de persona` (`Física (con actividad empresarial)`, `Moral`) y `Convenio de confidencialidad` (`Sí`, `No`);
- formato de texto en `RFC`, `Identificador fiscal extranjero` y `Teléfono`;
- una hoja `Instrucciones` con la versión de la plantilla, la descripción de cada columna, un ejemplo por origen y la lista de códigos de país ISO 3166-1 alfa-2.

#### Scenario: Descarga de la plantilla
- **WHEN** el Administrador solicita `GET /suppliers/import/template`
- **THEN** recibe el archivo `plantilla_carga_proveedores_v1.xlsx`, cuya hoja `Proveedores` tiene en la fila 1 exactamente los encabezados vigentes y ninguna fila de datos

#### Scenario: Los ejemplos no se importan
- **WHEN** el Administrador carga la plantilla recién descargada sin capturar datos
- **THEN** la carga se rechaza con HTTP 400 y el mensaje "El archivo no contiene proveedores", y no se registra ningún proveedor

### Requirement: Mapeo de columnas al catálogo de proveedores
Cada columna de la hoja `Proveedores` SHALL mapearse a un campo del catálogo de proveedores:
- `Origen` → `origin` (`Nacional` → `NATIONAL`, `Internacional` → `INTERNATIONAL`);
- `Tipo de persona` → `supplier_type` (`Física (con actividad empresarial)` o `Física` → `PERSONA_FISICA`, `Moral` → `PERSONA_MORAL`);
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

#### Scenario: Persona física con actividad empresarial
- **WHEN** una fila trae `Tipo de persona` = "Física (con actividad empresarial)"
- **THEN** el proveedor queda con `supplier_type = PERSONA_FISICA`
