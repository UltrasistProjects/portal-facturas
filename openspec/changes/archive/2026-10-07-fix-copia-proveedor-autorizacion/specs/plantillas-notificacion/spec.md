## MODIFIED Requirements

### Requirement: Consulta de las plantillas
`GET /admin/notification-templates` SHALL listar las siete plantillas en el orden Autorizada, Rechazada, Observaciones, Cancelada, Pagada, Complemento de pago adjuntado y Credenciales de acceso. De cada una SHALL mostrar el nombre del evento, el destinatario, el asunto vigente y la fecha y el Administrador de la última modificación, o "Predeterminada" si nunca se ha modificado. El destinatario SHALL ser:
- "Recepción de Facturas con copia al proveedor" para Autorizada;
- "Recepción de Facturas" para Cancelada y Complemento de pago adjuntado;
- "Proveedor (correo del catálogo)" para Rechazada, Observaciones, Pagada y Credenciales de acceso.

La página de edición SHALL mostrar el destinatario como dato de solo lectura y la lista de variables de la plantilla, con su descripción y la marca de obligatoria. Las páginas MUST NOT usar scripts ni estilos en línea.

#### Scenario: Listado inicial
- **WHEN** el Administrador abre el listado en una instalación nueva
- **THEN** ve siete filas en el orden Autorizada, Rechazada, Observaciones, Cancelada, Pagada, Complemento de pago adjuntado y Credenciales de acceso, con los destinatarios "Recepción de Facturas con copia al proveedor", "Proveedor (correo del catálogo)", "Proveedor (correo del catálogo)", "Recepción de Facturas", "Proveedor (correo del catálogo)", "Recepción de Facturas" y "Proveedor (correo del catálogo)", y todas con la última modificación "Predeterminada"

#### Scenario: Destinatario de solo lectura
- **WHEN** el Administrador abre la edición de la plantilla Rechazada
- **THEN** la página muestra "Destinatario: Proveedor (correo del catálogo)" y el formulario no tiene ningún campo para cambiarlo
