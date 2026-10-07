## MODIFIED Requirements

### Requirement: Estatus "Autorizado"
El estatus operativo `ACTIVE` de un proveedor SHALL mostrarse como "Autorizado" en el listado y en el expediente. La interfaz SHALL ofrecer como única transición de estatus el paso de "Registrado" (`REGISTERED`) a "Autorizado", mediante la autorización: masiva desde el listado o individual desde el expediente. Un proveedor SHALL pasar a "Autorizado" sólo con sus requisitos de alta exigibles completos (capacidad `requisitos-alta-proveedor`), evaluados con la configuración vigente. Un proveedor autorizado cumple la regla SUP-001.

La regla SHALL vivir en el servicio de autorización (`supplier_access_service.authorize`), que es el único código que asigna `ACTIVE`. Todo proveedor nuevo SHALL nacer "Registrado", incluso si quien lo crea no indica su estatus. La regla SHALL aplicar sólo a las autorizaciones siguientes: agregar, editar o eliminar un requisito de alta MUST NOT desactivar ni modificar a los proveedores ya autorizados.

#### Scenario: Etiqueta del estatus
- **WHEN** el Administrador abre el listado de proveedores de la demo
- **THEN** los proveedores con estatus `ACTIVE` se muestran como "Autorizado"

#### Scenario: Proveedor creado sin estatus
- **WHEN** el código crea un `Supplier` sin indicar su estatus
- **THEN** el proveedor queda "Registrado"

#### Scenario: Requisito nuevo después de autorizar
- **WHEN** un proveedor está "Autorizado" y el Administrador agrega un requisito Obligatorio para su tipo que el proveedor no tiene
- **THEN** el proveedor sigue "Autorizado" y su registro no cambia

#### Scenario: Requisito eliminado antes de autorizar
- **WHEN** a una persona moral "Registrado" sólo le falta "Poderes" y el Administrador elimina ese requisito
- **THEN** la siguiente autorización la pasa a "Autorizado"

#### Scenario: Un solo camino a Autorizado
- **WHEN** se inspecciona el código de `app/`
- **THEN** la única asignación de `SupplierStatus.ACTIVE` a un proveedor está en `supplier_access_service`
