## ADDED Requirements

### Requirement: Rol del usuario y su proveedor
La base de datos SHALL rechazar, con `CHECK ck_users_provider_supplier`, un usuario `PROVIDER` activo sin `supplier_id` y un usuario `INTERNAL` o `ADMIN` con `supplier_id`. Un usuario `PROVIDER` deshabilitado sin proveedor SHALL admitirse: es el estado en que la migración deja los registros previos.

La migración `0013_provider_user_supplier` SHALL, antes de crear el `CHECK`:
- deshabilitar cada usuario `PROVIDER` activo sin proveedor, revocar sus sesiones y auditar `USER_DEACTIVATED_WITHOUT_SUPPLIER`;
- quitar el proveedor a cada usuario `INTERNAL` o `ADMIN` que lo tenga, auditando `USER_SUPPLIER_CLEARED` con el id anterior.

El downgrade SHALL retirar el `CHECK` sin revertir los datos.

#### Scenario: Proveedor activo sin proveedor por SQL
- **WHEN** se ejecuta `UPDATE users SET supplier_id = NULL` sobre un usuario Proveedor activo
- **THEN** la base de datos rechaza la operación

#### Scenario: Migración de un usuario huérfano
- **WHEN** existe el usuario Proveedor activo `jobhdev@gmail.com` sin proveedor y se aplica `0013_provider_user_supplier`
- **THEN** el usuario queda deshabilitado, sin sesiones vigentes y con la auditoría `USER_DEACTIVATED_WITHOUT_SUPPLIER`
