## MODIFIED Requirements

### Requirement: Alta individual en "Registrado"
`POST /suppliers` SHALL crear el proveedor con estatus `REGISTERED`, sin usuario del portal y sin enviar correos.

El campo **Origen** (`origin`: `NATIONAL`, el valor por omisión, o `INTERNATIONAL`) SHALL decidir la identidad fiscal, con las reglas de la carga masiva:
- **Nacional:** RFC obligatorio, guardado en mayúsculas; sin identificador fiscal extranjero; país vacío o `MX`, que se guarda como `MX`.
- **Internacional:** identificador fiscal extranjero obligatorio, de hasta 40 caracteres (letras, dígitos, espacios, puntos, guiones o diagonales). Se guarda en mayúsculas y con los espacios internos colapsados. País obligatorio, con código ISO de dos letras distinto de `MX`. Sin RFC.

Una combinación incongruente o un valor inválido SHALL responder HTTP 400 con el motivo de cada campo, y nada se crea. Cada origen se compara sólo por su identidad:
- un RFC ya registrado SHALL responder HTTP 409 "Ya existe un proveedor con ese RFC.";
- un par (país, identificador fiscal extranjero) ya registrado SHALL responder HTTP 409 "Ya existe un proveedor con ese identificador fiscal extranjero en ese pais."; el mismo identificador en otro país es otro proveedor;
- si el correo, sin distinguir mayúsculas, ya lo usa otro proveedor o un usuario, la respuesta SHALL ser HTTP 409 "El correo ya lo usa otro proveedor o usuario.".

Un alta rechazada SHALL volver a mostrar el formulario con lo capturado, incluidos el origen y el país. El selector de país MUST NOT ofrecer México, que corresponde al origen Nacional. El origen y el tipo de persona no se editan después del alta.

**Campos según el origen y el tipo de persona.** Con JavaScript (`supplier_form.js`), el formulario de alta SHALL mostrar sólo los campos que aplican:
- el RFC, con el origen Nacional;
- el identificador fiscal extranjero y el país, con el Internacional;
- la fecha de constitución y el nombre y teléfono del representante legal, sólo con persona moral.

A la persona física MUST NOT pedírsele el representante legal: el servidor lo guarda vacío aunque llegue, y el expediente muestra "Representante legal: No aplica". Para la persona moral es obligatorio. En la interfaz, el tipo `PERSONA_FISICA` SHALL mostrarse como "Persona física (con actividad empresarial)".

Un campo que deja de aplicar SHALL ocultarse, limpiarse y deshabilitarse, de modo que el navegador no lo valida ni lo envía. Al volver a aplicar, SHALL recuperar su obligatoriedad. Sin JavaScript se muestran todos los campos y el servidor valida la combinación. La página de edición MUST NOT ofrecer el origen ni el tipo de persona: el servidor muestra sólo los campos que aplican, y la fecha de constitución y el representante legal de la persona moral son obligatorios sin depender del script.

#### Scenario: Proveedor nuevo registrado
- **WHEN** el Administrador da de alta un proveedor con el formulario
- **THEN** el proveedor queda "Registrado", no existe ningún usuario con su `supplier_id` y no se registra ningún envío de correo

#### Scenario: Correo en uso
- **WHEN** el Administrador da de alta un proveedor con el correo "Proveedor1@poc.local", que ya usa un usuario
- **THEN** la respuesta es HTTP 409 con el mensaje del correo en uso y no se crea el proveedor

#### Scenario: Alta nacional por omisión
- **WHEN** el alta llega sin origen y con un RFC válido
- **THEN** el proveedor es Nacional, con país `MX` y sin identificador fiscal extranjero

#### Scenario: Alta de proveedor internacional
- **WHEN** el Administrador da de alta un proveedor Internacional con el identificador " pco-00  01 " y el país "us"
- **THEN** el proveedor queda "Registrado" sin RFC, con el identificador "PCO-00 01" y el país "US"

#### Scenario: Identificador fiscal extranjero repetido
- **WHEN** ya existe un proveedor de "US" con el identificador "PCO-0001" y se da de alta otro con el mismo par
- **THEN** la respuesta es HTTP 409 "Ya existe un proveedor con ese identificador fiscal extranjero en ese pais."; con el país "CA", el alta procede

#### Scenario: Identidad fiscal incongruente
- **WHEN** el alta Internacional trae el país "MX", o el alta Nacional trae un identificador fiscal extranjero
- **THEN** la respuesta es HTTP 400 con "Pais: un proveedor internacional no puede tener pais MX" o "Identificador fiscal extranjero: debe quedar vacio para proveedores nacionales", y no se crea el proveedor

#### Scenario: Alta rechazada conserva lo capturado
- **WHEN** un alta Internacional con el país "CA" se rechaza por falta del identificador
- **THEN** el formulario vuelve con el origen Internacional y el país "CA" seleccionados, y el selector de país no ofrece México

#### Scenario: Campos que no aplican
- **WHEN** con JavaScript el Administrador elige el origen Internacional y el tipo persona física
- **THEN** el RFC, la fecha de constitución y el representante legal se ocultan, se limpian y no se envían, y el identificador fiscal y el país se vuelven obligatorios

#### Scenario: Edición sin selectores de identidad
- **WHEN** el Administrador abre el expediente de una persona moral para editarla
- **THEN** el formulario no tiene los campos de origen ni de tipo de persona, y la fecha de constitución y el representante legal son obligatorios

#### Scenario: Persona física sin representante legal
- **WHEN** el Administrador da de alta una persona física; aunque la petición traiga nombre y teléfono del representante legal
- **THEN** el proveedor queda sin representante legal, su expediente muestra "Representante legal: No aplica" y el tipo "Persona física (con actividad empresarial)"

#### Scenario: Persona moral sin representante legal
- **WHEN** el Administrador da de alta una persona moral sin el teléfono del representante legal
- **THEN** la respuesta es HTTP 400 con "Telefono del representante legal: es obligatorio para persona moral" y no se crea el proveedor
