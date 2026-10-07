## MODIFIED Requirements

### Requirement: Una plantilla por evento de estatus de factura
El sistema SHALL mantener exactamente una plantilla de correo por cada evento de notificación:
- `INVOICE_AUTHORIZED`, que se muestra como "Autorizada";
- `INVOICE_REJECTED`, que se muestra como "Rechazada";
- `INVOICE_OBSERVATIONS`, que se muestra como "Observaciones";
- `INVOICE_CANCELLED`, que se muestra como "Cancelada";
- `INVOICE_PAID`, que se muestra como "Pagada" y es el aviso de pago al proveedor (spec `pago-facturas`);
- `PAYMENT_COMPLEMENT`, que se muestra como "Complemento de pago adjuntado" y es el aviso a Recepción de Facturas (spec `pago-facturas`);
- `SUPPLIER_CREDENTIALS`, que se muestra como "Credenciales de acceso" y es el correo de usuario y contraseña temporal del proveedor autorizado (HU-03).

Cada plantilla SHALL tener asunto, cuerpo, número de versión, fecha de la última modificación y el Administrador que la hizo. Las siete plantillas SHALL existir desde la instalación con su texto predeterminado, en la versión 1 y sin Administrador asociado. La interfaz MUST NOT permitir crear, eliminar ni desactivar plantillas.

#### Scenario: Instalación nueva
- **WHEN** se ejecuta `alembic upgrade head` sobre una base vacía
- **THEN** existen siete plantillas, una por evento, en la versión 1, con el texto predeterminado y sin Administrador de la última modificación

#### Scenario: Migración sobre una base existente
- **WHEN** se aplica `0018_invoice_payment` sobre una base con la plantilla Rechazada modificada en la versión 3
- **THEN** se agregan las plantillas Pagada y Complemento de pago adjuntado en la versión 1, y Rechazada conserva su texto y su versión 3

#### Scenario: Evento inexistente
- **WHEN** el Administrador solicita `GET /admin/notification-templates/INVOICE_ARCHIVED`
- **THEN** la respuesta es HTTP 404

### Requirement: Consulta de las plantillas
`GET /admin/notification-templates` SHALL listar las siete plantillas en el orden Autorizada, Rechazada, Observaciones, Cancelada, Pagada, Complemento de pago adjuntado y Credenciales de acceso. De cada una SHALL mostrar el nombre del evento, el destinatario, el asunto vigente y la fecha y el Administrador de la última modificación, o "Predeterminada" si nunca se ha modificado. El destinatario SHALL ser:
- "Recepción de Facturas" para Autorizada, Cancelada y Complemento de pago adjuntado;
- "Proveedor (correo del catálogo)" para Rechazada, Observaciones, Pagada y Credenciales de acceso.

La página de edición SHALL mostrar el destinatario como dato de solo lectura y la lista de variables de la plantilla, con su descripción y la marca de obligatoria. Las páginas MUST NOT usar scripts ni estilos en línea.

#### Scenario: Listado inicial
- **WHEN** el Administrador abre el listado en una instalación nueva
- **THEN** ve siete filas en el orden Autorizada, Rechazada, Observaciones, Cancelada, Pagada, Complemento de pago adjuntado y Credenciales de acceso, con los destinatarios "Recepción de Facturas", "Proveedor (correo del catálogo)", "Proveedor (correo del catálogo)", "Recepción de Facturas", "Proveedor (correo del catálogo)", "Recepción de Facturas" y "Proveedor (correo del catálogo)", y todas con la última modificación "Predeterminada"

#### Scenario: Destinatario de solo lectura
- **WHEN** el Administrador abre la edición de la plantilla Rechazada
- **THEN** la página muestra "Destinatario: Proveedor (correo del catálogo)" y el formulario no tiene ningún campo para cambiarlo

### Requirement: Variables por plantilla
Cada plantilla SHALL admitir únicamente las variables de su evento y SHALL exigir en el cuerpo sus variables obligatorias. Las seis plantillas de factura admiten `folio_interno`, `estatus` y `fecha_estatus`. Además:
- Autorizada: obligatorias `numero_factura`, `proveedor` y `monto`;
- Rechazada: obligatorias `numero_factura` y `observaciones`; disponibles `proveedor` y `monto`;
- Observaciones: obligatorias `numero_factura` y `observaciones`; disponibles `proveedor` y `monto`;
- Cancelada: obligatorias `numero_factura`, `proveedor` y `fecha_limite_cancelacion`; disponible `monto`;
- Pagada: obligatorias `numero_factura` y `aviso_complemento`; disponibles `proveedor` y `monto`. `aviso_complemento` es condicional: el sistema sólo le da valor cuando la factura requiere Complemento de Pago (spec `pago-facturas`);
- Complemento de pago adjuntado: obligatorias `numero_factura` y `proveedor`; disponible `monto`.

La plantilla Credenciales de acceso admite sólo `proveedor`, `usuario`, `contrasena_temporal` y `url_portal`, y exige `usuario`, `contrasena_temporal` y `url_portal`.

#### Scenario: Variables de la plantilla Cancelada
- **WHEN** el Administrador abre la edición de la plantilla Cancelada
- **THEN** la página lista `numero_factura`, `folio_interno`, `proveedor`, `monto`, `estatus`, `fecha_estatus` y `fecha_limite_cancelacion`; marca como obligatorias `numero_factura`, `proveedor` y `fecha_limite_cancelacion`, y no lista `observaciones`

#### Scenario: Variables de la plantilla Pagada
- **WHEN** el Administrador abre la edición de la plantilla Pagada
- **THEN** la página lista `numero_factura`, `folio_interno`, `proveedor`, `monto`, `estatus`, `fecha_estatus` y `aviso_complemento`; marca como obligatorias `numero_factura` y `aviso_complemento`, y describe `aviso_complemento` como el aviso del Complemento de Pago que sólo aparece en las facturas nacionales PPD

#### Scenario: Aviso del complemento retirado
- **WHEN** el Administrador guarda la plantilla Pagada sin `{{aviso_complemento}}` en el cuerpo
- **THEN** la respuesta es HTTP 400 con el error "Cuerpo: debe incluir la variable obligatoria {{aviso_complemento}}" y la plantilla no cambia

#### Scenario: Variable de otro evento
- **WHEN** el Administrador guarda la plantilla Rechazada con `{{fecha_limite_cancelacion}}` en el cuerpo
- **THEN** la respuesta es HTTP 400 con el error "Cuerpo: la variable {{fecha_limite_cancelacion}} no existe en esta plantilla" y la plantilla no cambia

#### Scenario: Variables de la plantilla de credenciales
- **WHEN** el Administrador guarda la plantilla Credenciales de acceso sin `{{contrasena_temporal}}` en el cuerpo, o con `{{numero_factura}}`
- **THEN** la respuesta es HTTP 400 con el error de la variable obligatoria ausente o de la variable que no existe en esta plantilla, y la plantilla no cambia

### Requirement: Vista previa con datos de ejemplo
`POST /admin/notification-templates/{codigo}/preview` SHALL validar el borrador con las mismas reglas del guardado. Si es válido, SHALL responder HTTP 200 con el formulario y, debajo, el asunto y el correo compuestos con estos datos de ejemplo:
- `numero_factura` = "A-1024";
- `folio_interno` = "FAC-2026-00042";
- `proveedor` = "Servicios Digitales del Norte SA de CV";
- `monto` = "$116,000.00 MXN";
- `estatus` = el nombre del evento;
- `fecha_estatus` = "25/09/2026 10:30";
- `observaciones` = "El subtotal del XML no coincide con el de la orden de compra.";
- `fecha_limite_cancelacion` = "28/09/2026 10:30";
- `aviso_complemento` = "Es importante que adjunte su “Complemento de Pago” a dicha factura pagada antes del 28/09/2026 10:30. Mientras no lo adjunte, el portal no le permitirá enviar nuevas facturas a validación.";
- `usuario` = "contacto@serviciosdelnorte.mx";
- `contrasena_temporal` = "Ejemplo#Temporal2026";
- `url_portal` = "https://proveedores.ultrasist.com.mx/login".

Si el borrador no es válido, SHALL responder HTTP 400 con los errores y sin vista previa. La vista previa MUST NOT guardar la plantilla, cambiar su versión ni generar registros de auditoría. SHALL funcionar sin JavaScript y mostrar el texto compuesto escapado.

El correo SHALL mostrarse como lo recibe el destinatario: la misma versión HTML que se envía (spec `notificaciones-correo`), con el logo como `data:` URI, en un `iframe` con `sandbox` sin `allow-scripts` y el documento en `srcdoc`. Debajo, plegada, SHALL mostrarse la versión de texto plano. La respuesta SHALL admitir en su CSP sólo los atributos `style` de ese correo (spec `proteccion-http`).

#### Scenario: Vista previa del texto predeterminado
- **WHEN** el Administrador pide la vista previa de la plantilla Autorizada con su texto predeterminado
- **THEN** la respuesta es HTTP 200, el asunto es "Factura A-1024 autorizada para pago" y el cuerpo contiene "La factura número A-1024 del proveedor Servicios Digitales del Norte SA de CV por el monto $116,000.00 MXN ha sido Autorizada para su pago."

#### Scenario: Vista previa de Pagada
- **WHEN** el Administrador pide la vista previa de la plantilla Pagada con su texto predeterminado
- **THEN** el asunto es "Factura A-1024 pagada" y el cuerpo contiene "Su factura número A-1024 ha sido pagada." y "Es importante que adjunte su “Complemento de Pago” a dicha factura pagada antes del 28/09/2026 10:30."

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

#### Scenario: Vista previa como el correo
- **WHEN** el Administrador pide la vista previa de la plantilla Credenciales de acceso con su texto predeterminado
- **THEN** la página contiene un `iframe` `sandbox="allow-same-origin"` cuyo `srcdoc` es el HTML del correo con el logo, el asunto "Acceso al Portal de Proveedores ULTRASIST" como título y "Contraseña temporal" con "Ejemplo#Temporal2026" en el bloque de datos, y la versión de texto plano plegada debajo

### Requirement: Textos predeterminados conforme a las reglas de negocio
Los textos predeterminados SHALL cumplir las reglas de validación de su plantilla y SHALL reproducir la redacción de las reglas de negocio. Los asuntos SHALL ser:
- Autorizada: "Factura {{numero_factura}} autorizada para pago";
- Rechazada: "Factura {{numero_factura}} rechazada";
- Observaciones: "Factura {{numero_factura}} con observaciones";
- Cancelada: "Cancelación de la factura {{numero_factura}} de {{proveedor}}";
- Pagada: "Factura {{numero_factura}} pagada";
- Complemento de pago adjuntado: "Complemento de pago de la factura {{numero_factura}}";
- Credenciales de acceso: "Acceso al Portal de Proveedores ULTRASIST".

El cuerpo SHALL contener:
- Autorizada (RN-HU20-02): "La factura número {{numero_factura}} del proveedor {{proveedor}} por el monto {{monto}} ha sido Autorizada para su pago.";
- Rechazada (RN-HU20-03): "La factura número {{numero_factura}} ha sido “Rechazada” por la siguiente causa:", seguido de `{{observaciones}}`;
- Observaciones (RN-HU20-03): "La factura número {{numero_factura}} tiene “Observaciones” por la siguiente causa:", seguido de `{{observaciones}}`;
- Cancelada (HU-14): "La factura número {{numero_factura}} del proveedor {{proveedor}} ha sido cancelada. Por favor acepte la “Cancelación” antes del {{fecha_limite_cancelacion}}.";
- Pagada (HU Complemento de Pagos): "Su factura número {{numero_factura}} ha sido pagada.", seguido de `{{aviso_complemento}}` en una línea propia;
- Complemento de pago adjuntado (HU Complemento de Pagos): "El Complemento de Pago ha sido adjuntado a la factura {{numero_factura}} del proveedor {{proveedor}}.";
- Credenciales de acceso (HU-03): las líneas "Portal: {{url_portal}}", "Usuario: {{usuario}}" y "Contraseña temporal: {{contrasena_temporal}}".

#### Scenario: Textos predeterminados válidos
- **WHEN** se validan los siete textos predeterminados con las reglas de su plantilla
- **THEN** ninguno produce errores

#### Scenario: Texto predeterminado de Cancelada
- **WHEN** se compone un correo `INVOICE_CANCELLED` con la plantilla predeterminada, `numero_factura = "A-1024"`, `proveedor = "Servicios Digitales del Norte SA de CV"` y la fecha límite 2026-09-28 16:30 UTC
- **THEN** el cuerpo contiene "La factura número A-1024 del proveedor Servicios Digitales del Norte SA de CV ha sido cancelada. Por favor acepte la “Cancelación” antes del 28/09/2026 10:30."

#### Scenario: Texto predeterminado de Complemento de pago adjuntado
- **WHEN** se compone un correo `PAYMENT_COMPLEMENT` con la plantilla predeterminada, `numero_factura = "A-1024"` y `proveedor = "Servicios Digitales del Norte SA de CV"`
- **THEN** el asunto es "Complemento de pago de la factura A-1024" y el cuerpo contiene "El Complemento de Pago ha sido adjuntado a la factura A-1024 del proveedor Servicios Digitales del Norte SA de CV."

### Requirement: Composición del correo de un evento
El sistema SHALL ofrecer un servicio de composición para las HU que envían notificaciones. El servicio recibe el evento y los valores de sus variables, y devuelve el asunto y el cuerpo compuestos con la plantilla vigente. El servicio:
- SHALL formatear los montos con separador de miles, dos decimales y la moneda (`$116,000.00 MXN`), y las fechas en la zona de negocio con el formato `dd/mm/aaaa HH:MM`;
- SHALL tomar `estatus` del nombre del evento;
- SHALL sustituir cada variable por su valor como texto literal: un valor que contiene `{{...}}` no se vuelve a sustituir;
- SHALL convertir los saltos de línea del asunto compuesto en espacios y recortarlo a 255 caracteres;
- MUST fallar con un error explícito, sin componer el correo, si falta el valor de alguna variable del evento o si una variable obligatoria llega vacía, salvo una variable condicional (`aviso_complemento`), que puede llegar vacía;
- cuando una variable condicional llega vacía, SHALL eliminar del cuerpo la línea que sólo contenía esa variable y SHALL reducir a una sola las líneas en blanco consecutivas que resulten;
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

#### Scenario: Aviso del complemento vacío
- **WHEN** se compone un correo `INVOICE_PAID` con la plantilla predeterminada, `numero_factura = "A-1024"` y `aviso_complemento = ""`
- **THEN** el correo se compone, el cuerpo contiene "Su factura número A-1024 ha sido pagada.", no contiene "Complemento de Pago" y no tiene dos líneas en blanco seguidas

#### Scenario: Plantilla guardada inválida
- **WHEN** se ejecuta `UPDATE notification_templates SET body = 'Sin variables' WHERE event = 'INVOICE_REJECTED'` y después se compone un correo `INVOICE_REJECTED`
- **THEN** el correo se compone con el texto predeterminado de Rechazada, y el log contiene un evento `notification.template_fallback` con `event_code = "INVOICE_REJECTED"`, sin el asunto ni el cuerpo compuestos
