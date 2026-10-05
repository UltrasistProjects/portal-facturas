# listados-paginados Specification

## Purpose
Paginación en SQL, búsqueda y retorno tras las altas y acciones en los listados de administración (proveedores, usuarios, contratos, claves de catálogo y bitácora de correos), para que ningún listado crezca sin límite en una página y un registro recién creado siempre quede a la vista.
## Requirements
### Requirement: Listados paginados en la base de datos
Los listados de proveedores (`/suppliers`), usuarios (`/admin/users`), contratos (`/contracts`), claves de catálogo (`/admin/catalogs/{catalogo}`) y la bitácora de envíos (`/admin/notifications`) SHALL paginar en la consulta SQL (`LIMIT/OFFSET`) con 25 registros por página y un orden total (con el `id` como desempate):
- proveedores: razón social;
- usuarios: nombre;
- contratos: del más reciente al más antiguo;
- claves: clave;
- envíos: del más reciente al más antiguo.

Con más de una página, SHALL mostrar "Página N de M · T registros" y los enlaces "Anterior" y "Siguiente", que conservan la búsqueda y los filtros. Una página fuera de rango SHALL mostrar la última existente. Los conteos que la pantalla muestra (por ejemplo, claves activas de un catálogo) SHALL calcularse en SQL sobre todo el conjunto, no sobre la página. El listado de facturas (25) y el Audit Log (50) conservan su paginación.

#### Scenario: Segunda página de usuarios
- **WHEN** hay 30 usuarios y el Administrador abre `/admin/users?page=2`
- **THEN** ve los 5 últimos por nombre y "Página 2 de 2 · 30 registros"

#### Scenario: Página fuera de rango
- **WHEN** el Administrador abre `/contracts?page=99` con 30 contratos
- **THEN** ve la página 2

#### Scenario: Conteo del catálogo
- **WHEN** un catálogo tiene 30 claves, 28 activas, y el Administrador abre su primera página
- **THEN** ve 25 claves y "28 activas de 30"

#### Scenario: Bitácora completa
- **WHEN** hay 30 envíos registrados
- **THEN** la primera página de `/admin/notifications` muestra los 25 más recientes y la segunda, los 5 más antiguos

### Requirement: Búsqueda en los listados
Los listados de proveedores, usuarios, contratos y claves SHALL ofrecer un campo de búsqueda (`q`) que compara, sin distinguir mayúsculas y tratando `%` y `_` como caracteres literales, contra:
- proveedores: razón social, RFC, identificador fiscal extranjero y correo;
- usuarios: nombre y correo;
- contratos: proyecto y razón social del proveedor;
- claves: clave y descripción.

La búsqueda SHALL combinarse con el filtro de estatus de proveedores. Sin resultados, SHALL mostrar "Sin resultados para la búsqueda".

#### Scenario: Buscar un usuario por correo
- **WHEN** el Administrador busca `JOBHDEV@` en `/admin/users`
- **THEN** ve sólo el usuario con el correo `jobhdev@gmail.com`

#### Scenario: Proveedor con filtro y búsqueda
- **WHEN** busca `demo` con el estatus "Registrado" en `/suppliers`
- **THEN** ve sólo los proveedores registrados cuya razón social, identificador o correo contiene "demo"

### Requirement: El alta muestra el registro creado
Tras crear un usuario o una clave de catálogo, el sistema SHALL redirigir al listado buscando el registro creado (correo del usuario o clave) con el aviso "Usuario creado" o "Clave agregada". El alta de un proveedor SHALL seguir llevando a su expediente, y el alta de un contrato SHALL llevar al expediente del contrato con el aviso "Contrato creado. Cargue sus requisitos para activarlo.".

#### Scenario: Usuario nuevo visible
- **WHEN** hay 40 usuarios y el Administrador crea "Joshua Bolaños Hernández" con `jobhdev@gmail.com`
- **THEN** llega a `/admin/users?q=jobhdev%40gmail.com&ok=created`, ve "Usuario creado" y el usuario en la lista

#### Scenario: Contrato nuevo
- **WHEN** hay 40 contratos y el Administrador crea el contrato del proyecto "Portal Proveedores 2027"
- **THEN** llega a `/contracts/{contract_id}` del contrato creado y ve "Contrato creado. Cargue sus requisitos para activarlo."

### Requirement: Las acciones conservan la página
Habilitar o deshabilitar un usuario, registrar una enmienda de contrato, editar la descripción de una clave y desactivarla o reactivarla SHALL regresar al listado con la misma búsqueda, filtro y página desde la que se hizo la acción. Sólo se conservan `q`, `status` y `page`; cualquier otro valor del formulario se ignora.

#### Scenario: Deshabilitar en la página 2
- **WHEN** el Administrador deshabilita un usuario desde `/admin/users?q=demo&page=2`
- **THEN** regresa a `/admin/users?q=demo&page=2`
