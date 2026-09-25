## ADDED Requirements

### Requirement: Una plantilla por evento de estatus de factura
El sistema SHALL mantener exactamente una plantilla de correo por cada evento de notificación de la factura:
- `INVOICE_AUTHORIZED`, que se muestra como "Autorizada";
- `INVOICE_REJECTED`, que se muestra como "Rechazada";
- `INVOICE_OBSERVATIONS`, que se muestra como "Observaciones";
- `INVOICE_CANCELLED`, que se muestra como "Cancelada".

Cada plantilla SHALL tener asunto, cuerpo, número de versión, fecha de la última modificación y el Administrador que la hizo. Las cuatro plantillas SHALL existir desde la instalación con su texto predeterminado, en la versión 1 y sin Administrador asociado. La interfaz MUST NOT permitir crear, eliminar ni desactivar plantillas.

#### Scenario: Instalación nueva
- **WHEN** se ejecuta `alembic upgrade head` sobre una base vacía
- **THEN** existen cuatro plantillas, una por evento, en la versión 1, con el texto predeterminado y sin Administrador de la última modificación

#### Scenario: Evento inexistente
- **WHEN** el Administrador solicita `GET /admin/notification-templates/INVOICE_PAID`
- **THEN** la respuesta es HTTP 404

### Requirement: Configuración exclusiva del Administrador
Las rutas `GET /admin/notification-templates`, `GET /admin/notification-templates/{codigo}`, `POST /admin/notification-templates/{codigo}/preview` y `POST /admin/notification-templates/{codigo}` SHALL estar disponibles únicamente para el rol `ADMIN`. Las peticiones `POST` MUST exigir un token CSRF válido. El menú Administración SHALL mostrar la opción "Plantillas de correo" sólo al rol `ADMIN`.

#### Scenario: PMO sin acceso
- **WHEN** un usuario con rol `INTERNAL` solicita el listado, la edición o la vista previa, o envía un guardado
- **THEN** la respuesta es HTTP 403 y ninguna plantilla cambia

#### Scenario: Proveedor sin acceso
- **WHEN** un usuario con rol `PROVIDER` solicita el listado, la edición o la vista previa, o envía un guardado
- **THEN** la respuesta es HTTP 403 y ninguna plantilla cambia

#### Scenario: Guardado sin token CSRF
- **WHEN** un Administrador envía `POST /admin/notification-templates/INVOICE_REJECTED` sin token CSRF o con uno inválido
- **THEN** la respuesta es HTTP 403 y la plantilla no cambia

#### Scenario: Opción en el menú
- **WHEN** un Administrador y un usuario `INTERNAL` abren el tablero
- **THEN** el menú del Administrador incluye "Plantillas de correo" y el del usuario `INTERNAL` no

### Requirement: Consulta de las plantillas
`GET /admin/notification-templates` SHALL listar las cuatro plantillas en el orden Autorizada, Rechazada, Observaciones y Cancelada. De cada una SHALL mostrar el nombre del evento, el destinatario, el asunto vigente y la fecha y el Administrador de la última modificación, o "Predeterminada" si nunca se ha modificado. El destinatario SHALL ser:
- "Recepción de Facturas" para Autorizada y Cancelada;
- "Proveedor (correo del catálogo)" para Rechazada y Observaciones.

La página de edición SHALL mostrar el destinatario como dato de solo lectura y la lista de variables de la plantilla, con su descripción y la marca de obligatoria. Las páginas MUST NOT usar scripts ni estilos en línea.

#### Scenario: Listado inicial
- **WHEN** el Administrador abre el listado en una instalación nueva
- **THEN** ve cuatro filas en el orden Autorizada, Rechazada, Observaciones y Cancelada, con los destinatarios "Recepción de Facturas", "Proveedor (correo del catálogo)", "Proveedor (correo del catálogo)" y "Recepción de Facturas", y todas con la última modificación "Predeterminada"

#### Scenario: Destinatario de solo lectura
- **WHEN** el Administrador abre la edición de la plantilla Rechazada
- **THEN** la página muestra "Destinatario: Proveedor (correo del catálogo)" y el formulario no tiene ningún campo para cambiarlo

### Requirement: Variables por plantilla
Cada plantilla SHALL admitir únicamente las variables de su evento y SHALL exigir en el cuerpo sus variables obligatorias. Todas las plantillas admiten `folio_interno`, `estatus` y `fecha_estatus`. Además:
- Autorizada: obligatorias `numero_factura`, `proveedor` y `monto`;
- Rechazada: obligatorias `numero_factura` y `observaciones`; disponibles `proveedor` y `monto`;
- Observaciones: obligatorias `numero_factura` y `observaciones`; disponibles `proveedor` y `monto`;
- Cancelada: obligatorias `numero_factura`, `proveedor` y `fecha_limite_cancelacion`; disponible `monto`.

#### Scenario: Variables de la plantilla Cancelada
- **WHEN** el Administrador abre la edición de la plantilla Cancelada
- **THEN** la página lista `numero_factura`, `folio_interno`, `proveedor`, `monto`, `estatus`, `fecha_estatus` y `fecha_limite_cancelacion`; marca como obligatorias `numero_factura`, `proveedor` y `fecha_limite_cancelacion`, y no lista `observaciones`

#### Scenario: Variable de otro evento
- **WHEN** el Administrador guarda la plantilla Rechazada con `{{fecha_limite_cancelacion}}` en el cuerpo
- **THEN** la respuesta es HTTP 400 con el error "Cuerpo: la variable {{fecha_limite_cancelacion}} no existe en esta plantilla" y la plantilla no cambia

### Requirement: Validación de la plantilla
Al guardar y al generar la vista previa, el sistema SHALL normalizar el texto (recortar los espacios de los extremos del asunto y del cuerpo, y convertir `CRLF` en `LF`) y SHALL validarlo con estas reglas:
- el asunto es obligatorio, tiene hasta 200 caracteres y no contiene saltos de línea;
- el cuerpo es obligatorio y tiene hasta 5000 caracteres;
- cada `{{...}}` del asunto o del cuerpo contiene, sin contar los espacios interiores, el nombre de una variable de la plantilla;
- ninguna `{{` queda sin su `}}` en la misma línea;
- el cuerpo incluye al menos una vez cada variable obligatoria de la plantilla.

El sistema SHALL reportar todos los errores juntos, con el formato "Campo: mensaje", responder HTTP 400 y conservar en el formulario el texto capturado. Una plantilla con errores MUST NOT guardarse.

#### Scenario: Variable desconocida
- **WHEN** el Administrador guarda la plantilla Rechazada con `{{rfc_proveedor}}` en el cuerpo
- **THEN** la respuesta es HTTP 400 con el error "Cuerpo: la variable {{rfc_proveedor}} no existe en esta plantilla. Variables disponibles: {{numero_factura}}, {{folio_interno}}, {{proveedor}}, {{monto}}, {{estatus}}, {{fecha_estatus}}, {{observaciones}}", y la plantilla conserva su texto y su versión

#### Scenario: Variable obligatoria ausente
- **WHEN** el Administrador guarda la plantilla Rechazada sin `{{observaciones}}` en el cuerpo
- **THEN** la respuesta es HTTP 400 con el error "Cuerpo: debe incluir la variable obligatoria {{observaciones}}"

#### Scenario: Variable obligatoria sólo en el asunto
- **WHEN** el Administrador guarda la plantilla Autorizada con `{{monto}}` en el asunto pero no en el cuerpo
- **THEN** la respuesta es HTTP 400 con el error "Cuerpo: debe incluir la variable obligatoria {{monto}}"

#### Scenario: Variable sin cerrar
- **WHEN** el cuerpo contiene `{{numero_factura` sin `}}` en la misma línea
- **THEN** la respuesta es HTTP 400 con el error "Cuerpo: hay una variable sin cerrar; falta }}"

#### Scenario: Asunto demasiado largo
- **WHEN** el asunto tiene 201 caracteres
- **THEN** la respuesta es HTTP 400 con el error "Asunto: admite hasta 200 caracteres"

#### Scenario: Espacios interiores y llaves sencillas
- **WHEN** el cuerpo usa `{{ numero_factura }}` y contiene el texto `{nota}`
- **THEN** la plantilla es válida, y la vista previa muestra "A-1024" en lugar de la variable y `{nota}` sin cambios

#### Scenario: Varios errores a la vez
- **WHEN** el Administrador guarda con el asunto vacío y un cuerpo sin `{{numero_factura}}`
- **THEN** la respuesta HTTP 400 incluye "Asunto: es obligatorio" y "Cuerpo: debe incluir la variable obligatoria {{numero_factura}}"

### Requirement: Vista previa con datos de ejemplo
`POST /admin/notification-templates/{codigo}/preview` SHALL validar el borrador con las mismas reglas del guardado. Si es válido, SHALL responder HTTP 200 con el formulario y, debajo, el asunto y el cuerpo compuestos con estos datos de ejemplo:
- `numero_factura` = "A-1024";
- `folio_interno` = "FAC-2026-00042";
- `proveedor` = "Servicios Digitales del Norte SA de CV";
- `monto` = "$116,000.00 MXN";
- `estatus` = el nombre del evento;
- `fecha_estatus` = "25/09/2026 10:30";
- `observaciones` = "El subtotal del XML no coincide con el de la orden de compra.";
- `fecha_limite_cancelacion` = "28/09/2026 10:30".

Si el borrador no es válido, SHALL responder HTTP 400 con los errores y sin vista previa. La vista previa MUST NOT guardar la plantilla, cambiar su versión ni generar registros de auditoría. SHALL funcionar sin JavaScript y mostrar el texto compuesto escapado.

#### Scenario: Vista previa del texto predeterminado
- **WHEN** el Administrador pide la vista previa de la plantilla Autorizada con su texto predeterminado
- **THEN** la respuesta es HTTP 200, el asunto es "Factura A-1024 autorizada para pago" y el cuerpo contiene "La factura número A-1024 del proveedor Servicios Digitales del Norte SA de CV por el monto $116,000.00 MXN ha sido Autorizada para su pago."

#### Scenario: La vista previa no guarda
- **WHEN** el Administrador modifica el cuerpo de la plantilla Rechazada, pide la vista previa y vuelve a abrir la plantilla
- **THEN** la plantilla conserva su texto y su versión anteriores, y no se agregó ningún registro a `audit_logs`

#### Scenario: Texto escapado
- **WHEN** el cuerpo contiene `<b>Urgente</b>` y el Administrador pide la vista previa
- **THEN** la página muestra el texto `<b>Urgente</b>` tal cual, y su HTML contiene `&lt;b&gt;Urgente&lt;/b&gt;`

#### Scenario: Borrador inválido
- **WHEN** el Administrador pide la vista previa de un borrador sin una variable obligatoria
- **THEN** la respuesta es HTTP 400 con el error correspondiente y la página no muestra la vista previa

### Requirement: Guardado con control de edición concurrente
`POST /admin/notification-templates/{codigo}` SHALL recibir `subject`, `body` y `version`, que es la versión que el Administrador tenía al abrir el formulario. Si el texto es válido y `version` coincide con la vigente, el sistema SHALL guardar el asunto y el cuerpo, aumentar la versión en 1 y registrar la fecha y el Administrador de la modificación. Después SHALL redirigir con HTTP 303 al listado, que muestra el aviso "Plantilla actualizada".

Si `version` no coincide con la vigente, el sistema SHALL responder HTTP 409 con el mensaje "Otro administrador modificó esta plantilla mientras usted la editaba. Revise la versión vigente y vuelva a aplicar sus cambios." y MUST NOT guardar. Un guardado cuyo texto normalizado es idéntico al vigente MUST NOT aumentar la versión ni generar auditoría.

#### Scenario: Guardado exitoso
- **WHEN** la plantilla Rechazada está en la versión 1 y el Administrador la guarda con el asunto "Su factura {{numero_factura}} fue rechazada" y `version = 1`
- **THEN** la respuesta es HTTP 303 al listado, la plantilla queda en la versión 2 y el listado muestra el nuevo asunto, el nombre del Administrador y la fecha de la modificación

#### Scenario: Edición concurrente
- **WHEN** dos Administradores abren la plantilla Rechazada en la versión 1, el primero guarda y el segundo guarda después con `version = 1`
- **THEN** el segundo recibe HTTP 409 con el mensaje de edición concurrente, y la plantilla conserva el texto del primero en la versión 2

#### Scenario: Guardado sin cambios
- **WHEN** el Administrador guarda la plantilla sin modificar el texto
- **THEN** la respuesta es HTTP 303 al listado, la versión no cambia y no se agrega ningún registro a `audit_logs`

### Requirement: Carga del texto predeterminado
`GET /admin/notification-templates/{codigo}?default=1` SHALL mostrar el formulario con el asunto y el cuerpo predeterminados del evento, la versión vigente y el aviso "Se cargó el texto predeterminado. Pulse Guardar para aplicarlo.". La plantilla MUST NOT cambiar hasta que el Administrador guarde.

#### Scenario: Cargar y guardar el texto predeterminado
- **WHEN** la plantilla Rechazada está modificada en la versión 3, el Administrador carga el texto predeterminado y después pulsa Guardar
- **THEN** tras la carga la plantilla sigue en la versión 3 con el texto modificado, y tras el guardado queda en la versión 4 con el texto predeterminado

### Requirement: Textos predeterminados conforme a las reglas de negocio
Los textos predeterminados SHALL cumplir las reglas de validación de su plantilla y SHALL reproducir la redacción de las reglas de negocio. Los asuntos SHALL ser:
- Autorizada: "Factura {{numero_factura}} autorizada para pago";
- Rechazada: "Factura {{numero_factura}} rechazada";
- Observaciones: "Factura {{numero_factura}} con observaciones";
- Cancelada: "Cancelación de la factura {{numero_factura}} de {{proveedor}}".

El cuerpo SHALL contener:
- Autorizada (RN-HU20-02): "La factura número {{numero_factura}} del proveedor {{proveedor}} por el monto {{monto}} ha sido Autorizada para su pago.";
- Rechazada (RN-HU20-03): "La factura número {{numero_factura}} ha sido “Rechazada” por la siguiente causa:", seguido de `{{observaciones}}`;
- Observaciones (RN-HU20-03): "La factura número {{numero_factura}} tiene “Observaciones” por la siguiente causa:", seguido de `{{observaciones}}`;
- Cancelada (HU-14): "La factura número {{numero_factura}} del proveedor {{proveedor}} ha sido cancelada. Por favor acepte la “Cancelación” antes del {{fecha_limite_cancelacion}}.".

#### Scenario: Textos predeterminados válidos
- **WHEN** se validan los cuatro textos predeterminados con las reglas de su plantilla
- **THEN** ninguno produce errores

#### Scenario: Texto predeterminado de Cancelada
- **WHEN** se compone un correo `INVOICE_CANCELLED` con la plantilla predeterminada, `numero_factura = "A-1024"`, `proveedor = "Servicios Digitales del Norte SA de CV"` y la fecha límite 2026-09-28 16:30 UTC
- **THEN** el cuerpo contiene "La factura número A-1024 del proveedor Servicios Digitales del Norte SA de CV ha sido cancelada. Por favor acepte la “Cancelación” antes del 28/09/2026 10:30."

### Requirement: Composición del correo de un evento
El sistema SHALL ofrecer un servicio de composición para las HU que envían notificaciones. El servicio recibe el evento y los valores de sus variables, y devuelve el asunto y el cuerpo compuestos con la plantilla vigente. El servicio:
- SHALL formatear los montos con separador de miles, dos decimales y la moneda (`$116,000.00 MXN`), y las fechas en la zona de negocio con el formato `dd/mm/aaaa HH:MM`;
- SHALL tomar `estatus` del nombre del evento;
- SHALL sustituir cada variable por su valor como texto literal: un valor que contiene `{{...}}` no se vuelve a sustituir;
- SHALL convertir los saltos de línea del asunto compuesto en espacios y recortarlo a 255 caracteres;
- MUST fallar con un error explícito, sin componer el correo, si falta el valor de alguna variable del evento o si una variable obligatoria llega vacía;
- si la plantilla guardada no cumple las reglas de validación, SHALL componer el correo con el texto predeterminado del evento y registrar el evento de log `notification.template_fallback`.

El servicio MUST NOT enviar el correo ni escribir en el log el asunto o el cuerpo compuestos.

#### Scenario: Composición con la plantilla vigente
- **WHEN** la plantilla Rechazada se guardó con el asunto "Su factura {{numero_factura}} fue rechazada" y se compone un correo `INVOICE_REJECTED` con `numero_factura = "A-1024"`
- **THEN** el asunto compuesto es "Su factura A-1024 fue rechazada"

#### Scenario: Formato de montos y fechas
- **WHEN** se compone un correo `INVOICE_CANCELLED` con la plantilla predeterminada, un monto de `Decimal("116000.00")` en `MXN`, la fecha de la solicitud 2026-09-25 16:30 UTC y la fecha límite 2026-09-28 16:30 UTC
- **THEN** el cuerpo contiene "antes del 28/09/2026 10:30", "Monto: $116,000.00 MXN" y "Fecha de la solicitud: 25/09/2026 10:30"

#### Scenario: Valor con llaves
- **WHEN** se compone un correo `INVOICE_OBSERVATIONS` con `observaciones = "Corrija el campo {{monto}}"`
- **THEN** el cuerpo contiene el texto literal "Corrija el campo {{monto}}" y no el monto de la factura

#### Scenario: Asunto en una sola línea
- **WHEN** la plantilla Observaciones tiene el asunto "Observaciones: {{observaciones}}" y se compone con `observaciones = "Línea 1\nLínea 2"`
- **THEN** el asunto compuesto es "Observaciones: Línea 1 Línea 2"

#### Scenario: Variable obligatoria vacía
- **WHEN** se compone un correo `INVOICE_REJECTED` con `observaciones = ""`
- **THEN** el servicio falla con un error que nombra la variable `observaciones` y no devuelve ningún correo

#### Scenario: Plantilla guardada inválida
- **WHEN** se ejecuta `UPDATE notification_templates SET body = 'Sin variables' WHERE event = 'INVOICE_REJECTED'` y después se compone un correo `INVOICE_REJECTED`
- **THEN** el correo se compone con el texto predeterminado de Rechazada, y el log contiene un evento `notification.template_fallback` con `event_code = "INVOICE_REJECTED"`, sin el asunto ni el cuerpo compuestos

### Requirement: Auditoría de cambios a plantillas
Cada guardado que cambia una plantilla SHALL generar un registro de auditoría `NOTIFICATION_TEMPLATE_UPDATED` con:
- la entidad `NotificationTemplate` y el código del evento como identificador;
- el Administrador que guardó;
- `old_value` con el asunto, el cuerpo y la versión anteriores;
- `new_value` con el asunto, el cuerpo y la versión nuevos.

La vista previa, la carga del texto predeterminado, los guardados rechazados (HTTP 400 o 409) y los guardados sin cambios MUST NOT generar registros de auditoría.

#### Scenario: Auditoría de un cambio
- **WHEN** el Administrador guarda un cambio en la plantilla Rechazada, que pasa de la versión 1 a la 2
- **THEN** `audit_logs` contiene un registro `NOTIFICATION_TEMPLATE_UPDATED` con el `user_id` del Administrador, `entity_id = "INVOICE_REJECTED"`, `old_value` con el texto de la versión 1 y `version = 1`, y `new_value` con el texto nuevo y `version = 2`

#### Scenario: Acciones sin auditoría
- **WHEN** el Administrador pide una vista previa, carga el texto predeterminado, recibe un HTTP 400 por un error de validación y recibe un HTTP 409 por edición concurrente
- **THEN** no se agrega ningún registro a `audit_logs`
