# Dependencias entre Historias de Usuario (HUs)

| HU | HU parent |
| --- | --- |
| HU-01 Carga masiva de proveedores | — |
| HU-02 Autorización masiva de proveedores | HU-01 Carga masiva de proveedores |
| HU-03 Envío de credenciales al proveedor | HU-02 Autorización masiva de proveedores |
| HU-04 Definición de archivos requeridos por tipo de proveedor | — |
| HU-05 Configuración de plantillas de estatus de factura | — |
| HU-06 Configuración de reglas de validación | — |
| HU-07 Administración de catálogos | — |
| HU-08 Configuración de correos de notificación | — |
| HU-10 Cambio de contraseña en primer inicio de sesión | HU-03 Envío de credenciales al proveedor |
| HU-12 Registro de factura | HU-04 Definición de archivos requeridos por tipo de proveedor |
| HU-12 Registro de factura | HU-10 Cambio de contraseña en primer inicio de sesión |
| HU-13 Envío de factura por proveedor nacional | HU-12 Registro de factura |
| HU-13 Envío de factura por proveedor nacional | HU-06 Configuración de reglas de validación |
| HU-14 Cancelación de factura | HU-12 Registro de factura |
| HU-14 Cancelación de factura | HU-15 Registro de factura por proveedor internacional |
| HU-14 Cancelación de factura | HU-08 Configuración de correos de notificación |
| HU-15 Registro de factura por proveedor internacional | HU-04 Definición de archivos requeridos por tipo de proveedor |
| HU-15 Registro de factura por proveedor internacional | HU-10 Cambio de contraseña en primer inicio de sesión |
| HU-16 Envío de factura por proveedor internacional | HU-15 Registro de factura por proveedor internacional |
| HU-16 Envío de factura por proveedor internacional | HU-06 Configuración de reglas de validación |
| HU-17 Consulta de estatus de factura | HU-20 Cambio de estatus de factura |
| HU-18 Consulta de facturas por PMO | HU-13 Envío de factura por proveedor nacional |
| HU-18 Consulta de facturas por PMO | HU-16 Envío de factura por proveedor internacional |
| HU-19 Visualización de detalle de factura por PMO | HU-18 Consulta de facturas por PMO |
| HU-20 Cambio de estatus de factura | HU-19 Visualización de detalle de factura por PMO |
| HU-21 Requisitos de alta del proveedor | HU-01 Carga masiva de proveedores |
| HU-21 Requisitos de alta del proveedor | HU-02 Autorización masiva de proveedores |
| HU-22 Requisitos de alta del contrato | HU-21 Requisitos de alta del proveedor |
| HU-22 Requisitos de alta del contrato | HU-02 Autorización masiva de proveedores |
