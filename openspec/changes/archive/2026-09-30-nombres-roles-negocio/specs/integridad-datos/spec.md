## ADDED Requirements

### Requirement: Nombres de los roles
Los roles del sistema SHALL ser exactamente `Administrador`, `Proveedor` y `PMO`, y `users.role` SHALL guardar esos nombres; la base de datos SHALL rechazar cualquier otro con el `CHECK role`. Ni el código ni la interfaz MUST usar nombres en inglés ni los nombres por defecto de la enumeración.

La migración `0014_business_role_names` SHALL renombrar `ADMIN` a `Administrador`, `PROVIDER` a `Proveedor` e `INTERNAL` a `PMO`, ampliar la columna a `VARCHAR(13)` y rehacer los `CHECK role` y `ck_users_provider_supplier` con los nombres nuevos. Los registros de auditoría previos MUST NOT modificarse. El downgrade SHALL restaurar los nombres, la longitud y los `CHECK` anteriores.

#### Scenario: Usuarios previos con los nombres anteriores
- **WHEN** se aplica la migración sobre usuarios `ADMIN`, `PROVIDER` e `INTERNAL`
- **THEN** quedan como `Administrador`, `Proveedor` y `PMO`, y conservan su proveedor

#### Scenario: Rol con nombre anterior
- **WHEN** se actualiza un usuario con rol `ADMIN` después de la migración
- **THEN** la base de datos rechaza la operación

## MODIFIED Requirements

### Requirement: Rol del usuario y su proveedor
La base de datos SHALL rechazar, con `CHECK ck_users_provider_supplier`, un usuario `Proveedor` activo sin `supplier_id` y un usuario `PMO` o `Administrador` con `supplier_id`. Un usuario `Proveedor` deshabilitado sin proveedor SHALL admitirse: es el estado en que la migración deja los registros previos.

La migración `0013_provider_user_supplier` SHALL, antes de crear el `CHECK`:
- deshabilitar cada usuario `Proveedor` activo sin proveedor, revocar sus sesiones y auditar `USER_DEACTIVATED_WITHOUT_SUPPLIER`;
- quitar el proveedor a cada usuario `PMO` o `Administrador` que lo tenga, auditando `USER_SUPPLIER_CLEARED` con el id anterior.

El downgrade SHALL retirar el `CHECK` sin revertir los datos.

#### Scenario: Proveedor activo sin proveedor por SQL
- **WHEN** se ejecuta `UPDATE users SET supplier_id = NULL` sobre un usuario Proveedor activo
- **THEN** la base de datos rechaza la operación

#### Scenario: Migración de un usuario huérfano
- **WHEN** existe el usuario Proveedor activo `jobhdev@gmail.com` sin proveedor y se aplica `0013_provider_user_supplier`
- **THEN** el usuario queda deshabilitado, sin sesiones vigentes y con la auditoría `USER_DEACTIVATED_WITHOUT_SUPPLIER`
