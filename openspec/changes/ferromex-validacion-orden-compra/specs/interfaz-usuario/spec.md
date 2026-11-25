## ADDED Requirements

### Requirement: Menú de navegación por rol
El menú lateral SHALL mostrar:
- a todos los roles, "Dashboard" y "Facturas";
- a PMO y Administrador, además, "Proveedores" y "Órdenes de compra" (`/purchase-orders`);
- sólo al Administrador, los grupos "Administracion", "Reglas de validación" y "Requisitos mínimos". "Requisitos mínimos" SHALL contener sólo "Archivos de factura" y "Alta de proveedor".

El menú MUST NOT mostrar "Contratos" ni "Alta de contrato".

#### Scenario: Menú del PMO
- **WHEN** un usuario PMO abre el portal
- **THEN** el menú muestra "Órdenes de compra" y no muestra "Contratos" ni el grupo "Requisitos mínimos"

#### Scenario: Menú del Administrador
- **WHEN** un Administrador abre el portal
- **THEN** el grupo "Requisitos mínimos" muestra "Archivos de factura" y "Alta de proveedor", sin "Alta de contrato"

#### Scenario: Menú del Proveedor
- **WHEN** un Proveedor abre el portal
- **THEN** el menú no muestra "Órdenes de compra" ni "Proveedores"

### Requirement: Pasos del asistente de registro
El asistente de registro de una factura nacional SHALL mostrar los pasos "Archivos", "Revisión" y "Envío", con el paso vigente resaltado y los anteriores marcados como completos. El de una factura internacional SHALL mostrar "Información", "Documentos" y "Envío".

#### Scenario: Paso 1 nacional
- **WHEN** un proveedor nacional abre `/invoices/new`
- **THEN** ve "1 Archivos" activo, seguido de "Revisión" y "Envío"

#### Scenario: Paso 2 nacional
- **WHEN** el proveedor abre la revisión de su factura
- **THEN** ve "Archivos" completo y "2 Revisión" activo
