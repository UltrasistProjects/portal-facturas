## MODIFIED Requirements

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
- `usuario` = "contacto@serviciosdelnorte.mx";
- `contrasena_temporal` = "Ejemplo#Temporal2026";
- `url_portal` = "https://proveedores.ultrasist.com.mx/login".

Si el borrador no es válido, SHALL responder HTTP 400 con los errores y sin vista previa. La vista previa MUST NOT guardar la plantilla, cambiar su versión ni generar registros de auditoría. SHALL funcionar sin JavaScript y mostrar el texto compuesto escapado.

El correo SHALL mostrarse como lo recibe el destinatario: la misma versión HTML que se envía (spec `notificaciones-correo`), con el logo como `data:` URI, en un `iframe` con `sandbox` sin `allow-scripts` y el documento en `srcdoc`. Debajo, plegada, SHALL mostrarse la versión de texto plano. La respuesta SHALL admitir en su CSP sólo los atributos `style` de ese correo (spec `proteccion-http`).

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

#### Scenario: Vista previa como el correo
- **WHEN** el Administrador pide la vista previa de la plantilla Credenciales de acceso con su texto predeterminado
- **THEN** la página contiene un `iframe` `sandbox="allow-same-origin"` cuyo `srcdoc` es el HTML del correo con el logo, el asunto "Acceso al Portal de Proveedores ULTRASIST" como título y "Contraseña temporal" con "Ejemplo#Temporal2026" en el bloque de datos, y la versión de texto plano plegada debajo
