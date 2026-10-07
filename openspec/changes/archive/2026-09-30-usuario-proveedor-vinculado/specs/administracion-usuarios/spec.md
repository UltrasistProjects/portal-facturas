## ADDED Requirements

### Requirement: Usuario Proveedor vinculado a su proveedor
El alta de usuario en `/admin/users` (rol `ADMIN`) SHALL exigir, con el rol `PROVIDER`, un proveedor existente: sin él, HTTP 400 "Seleccione el proveedor del usuario"; con un identificador que no existe, HTTP 400 "Proveedor inexistente". Con los roles `INTERNAL` y `ADMIN` SHALL ignorar el proveedor enviado y guardar el usuario sin proveedor. Un alta rechazada SHALL volver a mostrar el formulario abierto con el error y los datos capturados, salvo la contraseña. El selector MUST NOT ofrecer "Ninguno" como opción válida para Proveedor.

#### Scenario: Proveedor sin proveedor
- **WHEN** el Administrador da de alta `jobhdev@gmail.com` con rol Proveedor y sin proveedor
- **THEN** la respuesta es HTTP 400 "Seleccione el proveedor del usuario", no se crea el usuario y el formulario conserva el nombre, el correo y el rol

#### Scenario: Proveedor inexistente
- **WHEN** el alta llega con rol Proveedor y `supplier_id = 999999`
- **THEN** la respuesta es HTTP 400 "Proveedor inexistente" y no se crea el usuario

#### Scenario: Interno con proveedor
- **WHEN** el alta llega con rol Interno y el id de un proveedor
- **THEN** el usuario se crea sin proveedor

### Requirement: Habilitar un usuario Proveedor sin proveedor
Habilitar un usuario `PROVIDER` sin proveedor SHALL responder HTTP 409 "El usuario no está vinculado a un proveedor: dé de alta uno nuevo con su proveedor" sin cambiarlo. Deshabilitarlo SHALL seguir permitido.

#### Scenario: Reactivar un usuario migrado
- **WHEN** el Administrador intenta habilitar un usuario Proveedor que la migración deshabilitó por no tener proveedor
- **THEN** la respuesta es HTTP 409 con ese mensaje y el usuario sigue deshabilitado
