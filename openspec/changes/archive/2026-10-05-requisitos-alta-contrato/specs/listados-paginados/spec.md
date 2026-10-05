## MODIFIED Requirements

### Requirement: El alta muestra el registro creado
Tras crear un usuario o una clave de catálogo, el sistema SHALL redirigir al listado buscando el registro creado (correo del usuario o clave) con el aviso "Usuario creado" o "Clave agregada". El alta de un proveedor SHALL seguir llevando a su expediente, y el alta de un contrato SHALL llevar al expediente del contrato con el aviso "Contrato creado. Cargue sus requisitos para activarlo.".

#### Scenario: Usuario nuevo visible
- **WHEN** hay 40 usuarios y el Administrador crea "Joshua Bolaños Hernández" con `jobhdev@gmail.com`
- **THEN** llega a `/admin/users?q=jobhdev%40gmail.com&ok=created`, ve "Usuario creado" y el usuario en la lista

#### Scenario: Contrato nuevo
- **WHEN** hay 40 contratos y el Administrador crea el contrato del proyecto "Portal Proveedores 2027"
- **THEN** llega a `/contracts/{contract_id}` del contrato creado y ve "Contrato creado. Cargue sus requisitos para activarlo."
