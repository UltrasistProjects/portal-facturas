## MODIFIED Requirements

### Requirement: Una plantilla por evento de estatus de factura
El sistema SHALL mantener exactamente una plantilla de correo por cada evento de notificación:
- `INVOICE_AUTHORIZED`, que se muestra como "Autorizada";
- `INVOICE_REJECTED`, que se muestra como "Rechazada";
- `INVOICE_OBSERVATIONS`, que se muestra como "Observaciones";
- `INVOICE_CANCELLED`, que se muestra como "Cancelada";
- `SUPPLIER_CREDENTIALS`, que se muestra como "Credenciales de acceso" y es el correo de usuario y contraseña temporal del proveedor autorizado (HU-03).

Cada plantilla SHALL tener asunto, cuerpo, número de versión, fecha de la última modificación y el Administrador que la hizo. Las cinco plantillas SHALL existir desde la instalación con su texto predeterminado, en la versión 1 y sin Administrador asociado. La interfaz MUST NOT permitir crear, eliminar ni desactivar plantillas.

#### Scenario: Instalación nueva
- **WHEN** se ejecuta `alembic upgrade head` sobre una base vacía
- **THEN** existen cinco plantillas, una por evento, en la versión 1, con el texto predeterminado y sin Administrador de la última modificación

#### Scenario: Evento inexistente
- **WHEN** el Administrador solicita `GET /admin/notification-templates/INVOICE_PAID`
- **THEN** la respuesta es HTTP 404

### Requirement: Consulta de las plantillas
`GET /admin/notification-templates` SHALL listar las cinco plantillas en el orden Autorizada, Rechazada, Observaciones, Cancelada y Credenciales de acceso. De cada una SHALL mostrar el nombre del evento, el destinatario, el asunto vigente y la fecha y el Administrador de la última modificación, o "Predeterminada" si nunca se ha modificado. El destinatario SHALL ser:
- "Recepción de Facturas" para Autorizada y Cancelada;
- "Proveedor (correo del catálogo)" para Rechazada, Observaciones y Credenciales de acceso.

La página de edición SHALL mostrar el destinatario como dato de solo lectura y la lista de variables de la plantilla, con su descripción y la marca de obligatoria. Las páginas MUST NOT usar scripts ni estilos en línea.

#### Scenario: Listado inicial
- **WHEN** el Administrador abre el listado en una instalación nueva
- **THEN** ve cinco filas en el orden Autorizada, Rechazada, Observaciones, Cancelada y Credenciales de acceso, con los destinatarios "Recepción de Facturas", "Proveedor (correo del catálogo)", "Proveedor (correo del catálogo)", "Recepción de Facturas" y "Proveedor (correo del catálogo)", y todas con la última modificación "Predeterminada"

#### Scenario: Destinatario de solo lectura
- **WHEN** el Administrador abre la edición de la plantilla Rechazada
- **THEN** la página muestra "Destinatario: Proveedor (correo del catálogo)" y el formulario no tiene ningún campo para cambiarlo

### Requirement: Variables por plantilla
Cada plantilla SHALL admitir únicamente las variables de su evento y SHALL exigir en el cuerpo sus variables obligatorias. Las cuatro plantillas de factura admiten `folio_interno`, `estatus` y `fecha_estatus`. Además:
- Autorizada: obligatorias `numero_factura`, `proveedor` y `monto`;
- Rechazada: obligatorias `numero_factura` y `observaciones`; disponibles `proveedor` y `monto`;
- Observaciones: obligatorias `numero_factura` y `observaciones`; disponibles `proveedor` y `monto`;
- Cancelada: obligatorias `numero_factura`, `proveedor` y `fecha_limite_cancelacion`; disponible `monto`.

La plantilla Credenciales de acceso admite sólo `proveedor`, `usuario`, `contrasena_temporal` y `url_portal`, y exige `usuario`, `contrasena_temporal` y `url_portal`.

#### Scenario: Variables de la plantilla Cancelada
- **WHEN** el Administrador abre la edición de la plantilla Cancelada
- **THEN** la página lista `numero_factura`, `folio_interno`, `proveedor`, `monto`, `estatus`, `fecha_estatus` y `fecha_limite_cancelacion`; marca como obligatorias `numero_factura`, `proveedor` y `fecha_limite_cancelacion`, y no lista `observaciones`

#### Scenario: Variable de otro evento
- **WHEN** el Administrador guarda la plantilla Rechazada con `{{fecha_limite_cancelacion}}` en el cuerpo
- **THEN** la respuesta es HTTP 400 con el error "Cuerpo: la variable {{fecha_limite_cancelacion}} no existe en esta plantilla" y la plantilla no cambia

#### Scenario: Variables de la plantilla de credenciales
- **WHEN** el Administrador guarda la plantilla Credenciales de acceso sin `{{contrasena_temporal}}` en el cuerpo, o con `{{numero_factura}}`
- **THEN** la respuesta es HTTP 400 con el error de la variable obligatoria ausente o de la variable que no existe en esta plantilla, y la plantilla no cambia

### Requirement: Vista previa con datos de ejemplo
`POST /admin/notification-templates/{codigo}/preview` SHALL validar el borrador con las mismas reglas del guardado. Si es válido, SHALL responder HTTP 200 con el formulario y, debajo, el asunto y el cuerpo compuestos con estos datos de ejemplo:
- `numero_factura` = "A-1024";
- `folio_interno` = "FAC-2026-00042";
- `proveedor` = "Servicios Digitales del Norte SA de CV";
- `monto` = "$116,000.00 MXN";
- `estatus` = el nombre del evento;
- `fecha_estatus` = "25/09/2026 10:30";
- `observaciones` = "El subtotal del XML no coincide con el de la orden de compra.";
- `fecha_limite_cancelacion` = "28/09/2026 10:30";
- `usuario` = "contacto@serviciosdelnorte.mx";
- `contrasena_temporal` = "Ejemplo#Temporal2026";
- `url_portal` = "https://proveedores.ultrasist.com.mx/login".

Si el borrador no es válido, SHALL responder HTTP 400 con los errores y sin vista previa. La vista previa MUST NOT guardar la plantilla, cambiar su versión ni generar registros de auditoría. SHALL funcionar sin JavaScript y mostrar el texto compuesto escapado.

#### Scenario: Vista previa del texto predeterminado
- **WHEN** el Administrador pide la vista previa de la plantilla Autorizada con su texto predeterminado
- **THEN** la respuesta es HTTP 200, el asunto es "Factura A-1024 autorizada para pago" y el cuerpo contiene "La factura número A-1024 del proveedor Servicios Digitales del Norte SA de CV por el monto $116,000.00 MXN ha sido Autorizada para su pago."

#### Scenario: Vista previa de las credenciales
- **WHEN** el Administrador pide la vista previa de la plantilla Credenciales de acceso con su texto predeterminado
- **THEN** el cuerpo contiene "Usuario: contacto@serviciosdelnorte.mx", "Contraseña temporal: Ejemplo#Temporal2026" y "https://proveedores.ultrasist.com.mx/login"

#### Scenario: La vista previa no guarda
- **WHEN** el Administrador modifica el cuerpo de la plantilla Rechazada, pide la vista previa y vuelve a abrir la plantilla
- **THEN** la plantilla conserva su texto y su versión anteriores, y no se agregó ningún registro a `audit_logs`

#### Scenario: Texto escapado
- **WHEN** el cuerpo contiene `<b>Urgente</b>` y el Administrador pide la vista previa
- **THEN** la página muestra el texto `<b>Urgente</b>` tal cual, y su HTML contiene `&lt;b&gt;Urgente&lt;/b&gt;`

#### Scenario: Borrador inválido
- **WHEN** el Administrador pide la vista previa de un borrador sin una variable obligatoria
- **THEN** la respuesta es HTTP 400 con el error correspondiente y la página no muestra la vista previa

### Requirement: Textos predeterminados conforme a las reglas de negocio
Los textos predeterminados SHALL cumplir las reglas de validación de su plantilla y SHALL reproducir la redacción de las reglas de negocio. Los asuntos SHALL ser:
- Autorizada: "Factura {{numero_factura}} autorizada para pago";
- Rechazada: "Factura {{numero_factura}} rechazada";
- Observaciones: "Factura {{numero_factura}} con observaciones";
- Cancelada: "Cancelación de la factura {{numero_factura}} de {{proveedor}}";
- Credenciales de acceso: "Acceso al Portal de Proveedores ULTRASIST".

El cuerpo SHALL contener:
- Autorizada (RN-HU20-02): "La factura número {{numero_factura}} del proveedor {{proveedor}} por el monto {{monto}} ha sido Autorizada para su pago.";
- Rechazada (RN-HU20-03): "La factura número {{numero_factura}} ha sido “Rechazada” por la siguiente causa:", seguido de `{{observaciones}}`;
- Observaciones (RN-HU20-03): "La factura número {{numero_factura}} tiene “Observaciones” por la siguiente causa:", seguido de `{{observaciones}}`;
- Cancelada (HU-14): "La factura número {{numero_factura}} del proveedor {{proveedor}} ha sido cancelada. Por favor acepte la “Cancelación” antes del {{fecha_limite_cancelacion}}.";
- Credenciales de acceso (HU-03): las líneas "Portal: {{url_portal}}", "Usuario: {{usuario}}" y "Contraseña temporal: {{contrasena_temporal}}".

#### Scenario: Textos predeterminados válidos
- **WHEN** se validan los cinco textos predeterminados con las reglas de su plantilla
- **THEN** ninguno produce errores

#### Scenario: Texto predeterminado de Cancelada
- **WHEN** se compone un correo `INVOICE_CANCELLED` con la plantilla predeterminada, `numero_factura = "A-1024"`, `proveedor = "Servicios Digitales del Norte SA de CV"` y la fecha límite 2026-09-28 16:30 UTC
- **THEN** el cuerpo contiene "La factura número A-1024 del proveedor Servicios Digitales del Norte SA de CV ha sido cancelada. Por favor acepte la “Cancelación” antes del 28/09/2026 10:30."
