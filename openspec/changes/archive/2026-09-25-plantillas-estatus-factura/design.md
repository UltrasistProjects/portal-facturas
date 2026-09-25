## Context

La HU-05 (`docs/stories/new/HU-05 Configuracion de plantillas de estatus de factura.md`) pide plantillas de correo editables para los cambios de estatus "Autorizada", "Rechazada", "Observaciones" y "Cancelada". Sus reglas derivadas (RD-01 a RD-10) y los puntos de la sección 15 son propuestas del Equipo Técnico que no bloquean el diseño. Estado actual del PoC:

- **Configuración:** el menú Administración tiene Usuarios, Reglas (solo lectura, `BUSINESS_RULES`) y Audit Log. No hay parámetros persistentes editables. HU-04 (`archivos-minimos-por-tipo-proveedor`, en curso en paralelo) agrega "Archivos mínimos" en el mismo menú y rutas en `app/routers/admin.py`.
- **Correo:** no existe dependencia, configuración SMTP ni servicio de notificaciones.
- **Estatus de factura:** `ACCEPTED` ("Aceptada"), `REJECTED` y `REQUIRES_CORRECTION` ("Requiere correccion"). No hay estatus de cancelación.
- **Observaciones del PMO:** `review_invoice` guarda el comentario, opcional, en `invoices.comments` y `reviews.comments`.
- **Plantillas HTML:** Jinja2 con autoescape. La CSP es `default-src 'self'; form-action 'self'`, sin scripts ni estilos en línea.
- **Auditoría:** `audit(db, action, entity, entity_id, user_id, old, new)` sobre `audit_logs` (`old_value` y `new_value` en JSONB).
- **Fechas y montos:** `to_business` convierte a `America/Mexico_City`. El filtro `money` da `$1,234.56`, sin moneda.
- **Errores:** `InvalidInputError` (400), `BusinessRuleError` (409) y `NotFoundError` (404) se traducen a la página de error. No existe un mecanismo de avisos "flash" entre redirecciones.
- **Migraciones:** la cabeza es `0003_invoice_document_types` (HU-04, aún sin commit). Las pruebas crean la base con `alembic upgrade head` y comparten la base de la sesión.

## Goals / Non-Goals

**Goals:**
- Que el Administrador ajuste la redacción de los cuatro correos sin despliegues y sin poder quitar un dato que exige una regla de negocio.
- Que un texto escrito por el Administrador nunca pueda ejecutar código ni inyectar HTML.
- Un servicio de composición listo para HU-20 y HU-14, que nunca impida una notificación obligatoria por una plantilla dañada.
- Trazabilidad completa de cada cambio: quién, cuándo, texto anterior y texto nuevo.

**Non-Goals:**
- Enviar correos, configurar destinatarios o el transporte (HU-08, HU-20 y HU-14).
- Disparar notificaciones al cambiar el estatus y alinear los estatus del PoC con la ERS (HU-20 y HU-14).
- HTML, adjuntos, idiomas, historial con opción de volver a una versión anterior y correo de prueba.
- Pruebas de interfaz en navegador: las páginas no usan JavaScript y se prueban con `TestClient`.

## Decisions

### D1. Tabla `notification_templates` con una fila por evento
Columnas: `id`, `event` (enumeración, única), `subject` (`VARCHAR(200)`), `body` (`TEXT`), `version` (entero), `updated_at` (`TIMESTAMPTZ`) y `updated_by` (FK a `users`, `ON DELETE RESTRICT`, `NULL` mientras la plantilla no se ha modificado). Restricciones:
- `uq_notification_templates_event`;
- `ck_notification_templates_subject_length`: `char_length(subject) BETWEEN 1 AND 200`;
- `ck_notification_templates_body_length`: `char_length(body) BETWEEN 1 AND 5000`;
- `ck_notification_templates_version_positive`: `version >= 1`;
- el `CHECK` de la enumeración (`notificationevent`), como el resto de enumeraciones del esquema.

*Alternativas:*
- Archivos de texto en el repositorio: el Administrador no podría editarlos.
- Una tabla genérica clave-valor de parámetros: sin restricciones por campo ni control de versión. HU-08 decidirá su propio modelo para destinatarios y transporte.

### D2. Sustitución propia de variables, sin Jinja2
Una expresión regular `\{\{(.*?)\}\}`, sin `DOTALL` para que no cruce líneas, localiza cada variable. El contenido, sin los espacios de los extremos, es el nombre. `re.sub` con una función reemplaza cada coincidencia por su valor ya formateado, en una sola pasada, así que un valor que contiene `{{...}}` no se vuelve a sustituir.

- **Validación:** un nombre que no está en las variables de la plantilla es un error. Una `{{` que sigue en el texto tras quitar las coincidencias es una variable sin cerrar.
- **Llaves sueltas:** una `{` o una `}` sueltas, y una `}}` sin su `{{`, son texto normal.

Las plantillas del Administrador nunca pasan por Jinja2.

*Alternativas:*
- Jinja2, incluso en su sandbox: un texto del Administrador podría evaluar expresiones (SSTI), y se hereda una sintaxis que el negocio no necesita.
- `str.format`: permite acceder a atributos (`{0.__class__}`).
- `string.Template`: usa `$`, que choca con los montos (`$116,000.00`).

### D3. Catálogo de eventos en código
`app/services/notification_templates.py` define:
- `VARIABLES`: nombre, descripción y ejemplo de cada variable, en el orden de la sección 6.2 de la HU;
- `EVENTS`: por cada `NotificationEvent`, el nombre en pantalla, el destinatario, las variables disponibles (en el orden de `VARIABLES`), las obligatorias y el asunto y el cuerpo predeterminados.

La validación, la interfaz, la vista previa y la composición leen el mismo catálogo. El orden de `EVENTS` es el del listado: Autorizada, Rechazada, Observaciones y Cancelada.

*Alternativa:* guardar el catálogo en la base de datos. Se podría quitar una variable obligatoria por SQL y romper RD-04.

### D4. Enumeración `NotificationEvent`, independiente de `InvoiceStatus`
Se define en `app/core/constants.py` con `INVOICE_AUTHORIZED`, `INVOICE_REJECTED`, `INVOICE_OBSERVATIONS` e `INVOICE_CANCELLED` (RD-02). Su nombre en pantalla vive en el catálogo (D3).

*Alternativa:* usar `InvoiceStatus` como llave. No existe "Cancelada", `ACCEPTED` se muestra como "Aceptada", y HU-05 quedaría atada a las decisiones de HU-20 y HU-14.

### D5. Vista previa en el servidor, sin JavaScript
El formulario de edición tiene dos botones de envío. "Guardar" usa la acción del formulario, y "Vista previa" usa `formaction` hacia `/preview`, que la CSP admite (`form-action 'self'`). "Cargar texto predeterminado" es un enlace `GET ?default=1`.

La respuesta de la vista previa es la misma página de edición con el borrador y, debajo, el asunto y el cuerpo compuestos con los datos de ejemplo. El cuerpo se muestra con autoescape en un bloque `.template-preview-body` con `white-space: pre-wrap`, definido en `app.css`.

*Alternativa:* vista previa en vivo con JavaScript. Duplica en el navegador la lógica de composición, que podría divergir de la del servidor.

### D6. Bloqueo optimista con la versión
El formulario lleva la versión en un campo oculto. El guardado:
1. normaliza y valida el texto (400 si hay errores);
2. lee la plantilla vigente; si la versión recibida no coincide, responde 409;
3. si el texto normalizado es idéntico al vigente, no escribe nada;
4. ejecuta `UPDATE notification_templates SET ..., version = version + 1 WHERE event = :event AND version = :version`. Si no afecta ninguna fila, otro Administrador guardó entre la lectura y la escritura, y responde 409.

*Alternativas:*
- Que gane la última escritura: un Administrador perdería sin aviso el cambio de otro.
- `version_id_col` del ORM: lanza `StaleDataError` al hacer flush. Es equivalente, pero menos explícito que el `UPDATE` condicionado que describe la spec.

### D7. Correo en texto plano
El asunto y el cuerpo son texto plano (RD-05). La HU que envíe podrá envolverlo en un diseño HTML fijo sin cambiar las plantillas.

*Alternativa:* HTML escrito por el Administrador. Exige sanitizarlo, choca con la CSP en la vista previa (estilos en línea) y facilita enlaces engañosos.

### D8. Composición con respaldo en el texto predeterminado
`compose(db, event, **valores)` lee la plantilla vigente y la valida de nuevo con las mismas reglas del guardado. Si la fila no existe o no es válida:
- compone con el texto predeterminado del evento;
- registra `notification.template_fallback` con `event_code` y `reason` (`missing` o `invalid`) y, si es inválida, el número de errores (`errors`).

Ni el log ni la excepción incluyen los mensajes de validación, porque contienen fragmentos del texto de la plantilla.

*Alternativa:* fallar la composición. El cambio de estatus de HU-20 fallaría, o se perdería una notificación que las RN hacen obligatoria.

### D9. Revisión `0004_notification_templates`
La revisión va después de `0003_invoice_document_types` (HU-04), no después de `0002_supplier_bulk_import` como sugiere la HU: esa revisión ya ocupa el número 3 en la cadena. La HU-04 está en curso en el mismo árbol de trabajo, y una rama paralela dejaría dos cabezas.

- **Upgrade:** crea la tabla con sus restricciones e inserta las cuatro plantillas en la versión 1, sin `updated_by`. Los textos se copian en la propia migración.
- **Downgrade:** borra la tabla. Si alguna plantilla tiene una versión mayor que 1, lanza `NotImplementedError` ("… Restaure un respaldo."), porque revertir perdería los cambios del Administrador.

Una prueba compara los textos sembrados por la migración con los del catálogo (D3), para que no diverjan.

*Alternativas:*
- Importar los textos desde `app`: la migración cambiaría cada vez que cambie el código, y `test_revisiones_explicitas_sin_create_all_ni_modelos` prohíbe importar `app.models`.
- Crear las plantillas al arrancar la aplicación: el esquema y sus datos mínimos quedarían en dos lugares.

### D10. Valores tipados en la composición
`compose` recibe argumentos por nombre, todos opcionales en la firma:
- `numero_factura`, `folio_interno` y `proveedor` (`str`);
- `monto` (`Decimal`) y `moneda` (`str`);
- `fecha_estatus` (`datetime`);
- `observaciones` (`str`);
- `fecha_limite_cancelacion` (`datetime`).

`estatus` sale del nombre del evento. El servicio formatea los montos como `$116,000.00 MXN` y las fechas con `to_business` y `%d/%m/%Y %H:%M`. Las reglas de los valores son:
- si falta el valor de una variable del evento (`None`, o `monto` sin `moneda`), lanza `NotificationDataError` (subclase de `ValueError`) con el nombre de la variable;
- si una variable obligatoria queda vacía tras recortar espacios, lanza el mismo error;
- ignora los valores de variables que el evento no admite, para que HU-20 pueda pasar los mismos argumentos a sus tres eventos;
- en el asunto compuesto, convierte cada salto de línea en un espacio y lo recorta a 255 caracteres.

El resultado es un `ComposedEmail(subject, body)` inmutable. El servicio no envía nada ni registra el texto compuesto.

*Alternativa:* recibir la factura (`Invoice`). Acopla el servicio al modelo y a los campos que agregará HU-14, como la fecha de la solicitud de cancelación.

### D11. Rutas en `app/routers/admin.py`, lógica en el servicio
Las cuatro rutas usan el prefijo `/admin` existente y la dependencia `require_roles(Role.ADMIN)`. Los `POST` llaman a `validate_csrf` antes de cualquier otra cosa.

- **Evento desconocido:** el código de la ruta se convierte con `NotificationEvent(codigo)`; si no existe, `NotFoundError` responde 404. Tiparlo en la firma daría un 422 de FastAPI.
- **Campos del formulario:** `subject` y `body` llegan con valor por omisión `""`, para que su ausencia se reporte como "es obligatorio" y no como 422. `version` llega con valor por omisión `0`, que nunca coincide con una versión vigente, así que su ausencia da 409.

*Alternativa:* un router nuevo. Sería un archivo más para cuatro rutas de la misma sección.

### D12. Respuestas de error en la misma página de edición
- **400 (validación)** y **409 (edición concurrente):** responden la página de edición con el borrador del Administrador y el mensaje o la lista "Campo: mensaje".
- **Versión en el 409:** la página conserva la versión que el Administrador envió, así que un nuevo guardado vuelve a dar 409 hasta que abra la versión vigente con el enlace del aviso. Así no se pierde su texto y no se sobrescribe el del otro Administrador.
- **Guardado exitoso o sin cambios:** redirige con 303 a `/admin/notification-templates?updated=<codigo>`. El listado muestra "Plantilla actualizada: <nombre>." sólo si `updated` es un código de evento válido.

El PoC no tiene avisos "flash" en sesión, y un parámetro de consulta basta para un aviso sin datos sensibles.

### D13. El servicio confirma la transacción del guardado
`save_template` hace el `UPDATE`, agrega la auditoría, hace commit y, después del commit, registra `notification_template.updated`. Así el log sólo refleja cambios confirmados.

`SaveResult` indica si hubo cambio y la versión resultante. Los errores de validación se lanzan como `TemplateValidationError`, una subclase de `InvalidInputError` que lleva la lista de errores y el borrador normalizado.

## Risks / Trade-offs

- **El Administrador quita información útil pero no obligatoria, como el folio interno** → sólo se protegen las variables que exigen las RN. El resto es una decisión de redacción, y la auditoría registra quién hizo cada cambio.
- **Texto engañoso o erróneo** → sólo el rol `ADMIN` edita, cada cambio queda auditado con el texto anterior y el nuevo, y la vista previa permite revisarlo antes de guardar.
- **Observaciones largas o de varias líneas en el asunto** → la composición convierte los saltos de línea en espacios y recorta el asunto a 255 caracteres.
- **Acentos y "ñ" en los correos** → las plantillas se guardan en UTF-8. La HU que envíe (HU-08) debe declarar `charset=utf-8`.
- **Base de pruebas compartida por toda la sesión** → un fixture restaura las cuatro plantillas a su texto predeterminado, en la versión 1 y sin `updated_by`, después de cada prueba que las modifica.
- **Estatus del PoC distintos a los de la ERS** → los eventos no dependen de la enumeración. HU-20 y HU-14 hacen el mapeo al disparar cada correo.
- **HU-04 en paralelo en el mismo árbol de trabajo** →
  - la revisión encadena después de `0003_invoice_document_types`;
  - las ediciones en archivos compartidos (`constants.py`, `models/__init__.py`, `admin.py`, `base.html`, `app.css`, `README.md` y pruebas) son adiciones al final o en puntos acotados;
  - el delta `MODIFIED` de `integridad-datos` ya incluye el texto de HU-04, así que este change se archiva después de `archivos-minimos-por-tipo-proveedor`. Si HU-04 se abandonara, habría que quitar de ese bloque el nivel de exigencia de archivo y su escenario.
- **`reset_demo.py` recrea el esquema** → las plantillas vuelven al texto predeterminado al reiniciar la demo. Es coherente con un reinicio, y el README lo advierte.

## Migration Plan

1. `alembic upgrade head` aplica `0004_notification_templates` después de `0003_invoice_document_types`: crea la tabla y siembra las cuatro plantillas.
2. Sin pasos manuales: la opción de menú aparece al rol `ADMIN` con las plantillas predeterminadas.
3. **Reversión:** `alembic downgrade 0003_invoice_document_types` borra la tabla si ninguna plantilla se modificó. Si alguna se modificó, la migración se niega y hay que restaurar un respaldo (`scripts/restore_backup.py`).

## Open Questions

Los puntos de la sección 15 de la HU tienen una propuesta ya reflejada en este diseño y se confirman en la revisión de la HU:
1. idioma de los correos a proveedores internacionales (propuesta: español);
2. formato del correo (texto plano);
3. destinatarios por evento (los de las RN);
4. plantillas no desactivables;
5. textos predeterminados de la sección 6.4, pendientes de aprobación del PMO y de Recepción de Facturas.
