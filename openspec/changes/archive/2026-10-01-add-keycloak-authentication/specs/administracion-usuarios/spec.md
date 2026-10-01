## ADDED Requirements

### Requirement: Alta de usuarios en Keycloak
El formulario de alta de `/admin/users` MUST NOT pedir contraseña. Un alta válida SHALL, en una sola transacción, crear el usuario local sin contraseña y aprovisionarlo en Keycloak:
- crear el usuario, o enlazar uno existente con ese correo si no está enlazado a otro usuario local y sus roles reconocidos son ninguno o sólo el rol pedido;
- asignarle el realm role igual al rol elegido;
- registrar una contraseña temporal con la acción requerida `UPDATE_PASSWORD`;
- guardar el `sub` en `users.keycloak_sub`.

La contraseña temporal SHALL mostrarse al Administrador una única vez, en la respuesta del alta con `Cache-Control: no-store`, y MUST NOT persistirse ni escribirse en el log (opción D1-A del diseño).

Si el correo pertenece en Keycloak a un usuario con otro rol reconocido, la respuesta SHALL ser HTTP 409. Si Keycloak no responde, SHALL ser HTTP 503 y no se crea nada.

#### Scenario: Alta de un usuario PMO
- **WHEN** el Administrador da de alta `analista@ultrasist.com.mx` con rol PMO
- **THEN** existe el usuario local con `keycloak_sub` y sin `password_hash`, y en Keycloak un usuario con el rol `PMO` y la acción `UPDATE_PASSWORD`; la contraseña temporal se muestra una vez con `Cache-Control: no-store`

#### Scenario: Correo con otro rol en Keycloak
- **WHEN** el Administrador da de alta con rol PMO un correo que en Keycloak tiene el rol `Administrador`
- **THEN** la respuesta es HTTP 409 y no se crea el usuario local

#### Scenario: Keycloak no disponible en el alta
- **WHEN** Keycloak no responde durante un alta válida
- **THEN** la respuesta es HTTP 503 con "El servicio de identidad no está disponible. Intente más tarde." y no se crea el usuario local

### Requirement: Habilitación sincronizada con Keycloak
- **Deshabilitar** un usuario SHALL desactivarlo en el portal y revocar sus sesiones locales en cualquier caso. Después SHALL deshabilitarlo en Keycloak y cerrar allí sus sesiones. Si Keycloak falla, el usuario queda deshabilitado en el portal, se registra `IDP_SYNC_FAILED` y se avisa al Administrador.
- **Habilitar** un usuario SHALL habilitarlo primero en Keycloak y sólo después en el portal. Si Keycloak falla, la respuesta SHALL ser HTTP 503 y el usuario sigue deshabilitado.

#### Scenario: Deshabilitar con Keycloak disponible
- **WHEN** el Administrador deshabilita a un usuario con sesión abierta
- **THEN** el usuario queda inactivo en el portal y deshabilitado en Keycloak, y sus sesiones del portal y de Keycloak quedan cerradas

#### Scenario: Deshabilitar con Keycloak caído
- **WHEN** Keycloak no responde y el Administrador deshabilita a un usuario
- **THEN** el usuario queda inactivo en el portal con sus sesiones revocadas, `audit_logs` contiene `IDP_SYNC_FAILED` y la página avisa que Keycloak no se actualizó

#### Scenario: Habilitar con Keycloak caído
- **WHEN** Keycloak no responde y el Administrador habilita a un usuario
- **THEN** la respuesta es HTTP 503 y el usuario sigue deshabilitado

## MODIFIED Requirements

### Requirement: Usuario Proveedor vinculado a su proveedor
El alta de usuario en `/admin/users` (rol `Administrador`) SHALL exigir, con el rol `Proveedor`, un proveedor existente:
- sin él: HTTP 400 "Seleccione el proveedor del usuario";
- con un identificador que no existe: HTTP 400 "Proveedor inexistente".

Con los roles `PMO` y `Administrador`, SHALL ignorar el proveedor enviado y guardar el usuario sin proveedor.

Un alta rechazada SHALL volver a mostrar el formulario abierto con el error y los datos capturados. El formulario no tiene campo de contraseña. El selector MUST NOT ofrecer "Ninguno" como opción válida para Proveedor.

#### Scenario: Proveedor sin proveedor
- **WHEN** el Administrador da de alta `jobhdev@gmail.com` con rol Proveedor y sin proveedor
- **THEN** la respuesta es HTTP 400 "Seleccione el proveedor del usuario", no se crea el usuario ni en el portal ni en Keycloak, y el formulario conserva el nombre, el correo y el rol

#### Scenario: Proveedor inexistente
- **WHEN** el alta llega con rol Proveedor y `supplier_id = 999999`
- **THEN** la respuesta es HTTP 400 "Proveedor inexistente" y no se crea el usuario

#### Scenario: PMO con proveedor
- **WHEN** el alta llega con rol PMO y el id de un proveedor
- **THEN** el usuario se crea sin proveedor
