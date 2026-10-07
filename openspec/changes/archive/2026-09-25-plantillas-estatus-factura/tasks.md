> Todas las rutas son relativas a la raíz de la PoC (`PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress-V1/PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress/`). Cada grupo termina con `ruff` limpio y con sus pruebas en verde sobre PostgreSQL (`docker compose up -d --wait db`). HU-04 se implementa en paralelo en el mismo árbol de trabajo: releer cada archivo compartido antes de editarlo y limitar los cambios a adiciones.

## 1. Constantes, modelo y migración

- [x] 1.1 `app/core/constants.py`: enumeración `NotificationEvent` (`INVOICE_AUTHORIZED`, `INVOICE_REJECTED`, `INVOICE_OBSERVATIONS`, `INVOICE_CANCELLED`) (D4).
- [x] 1.2 `app/models/__init__.py`: modelo `NotificationTemplate` (D1) con:
  - `event` como `enum_column(NotificationEvent)`;
  - `UniqueConstraint` sobre `event`;
  - `CheckConstraint` de longitud de asunto y de cuerpo, y de versión positiva;
  - `updated_by` con `restrict("users.id")`, que admite `NULL`, y la relación `updater`.

  Añadirlo a `__all__`.
- [x] 1.3 Revisión `alembic/versions/0004_notification_templates.py` (D9), con `down_revision = "0003_invoice_document_types"`:
  - tabla, restricciones y las cuatro plantillas predeterminadas en la versión 1, con los textos copiados en la migración;
  - downgrade que borra la tabla, o que lanza `NotImplementedError` ("… Restaure un respaldo.") si alguna plantilla tiene una versión mayor que 1.

  Verificar `alembic check` sin diferencias.
- [x] 1.4 Pruebas en `tests/test_integridad.py` (spec `integridad-datos`):
  - evento `INVOICE_PAID` por SQL rechazado;
  - segunda plantilla para `INVOICE_REJECTED` rechazada;
  - asunto vacío por SQL rechazado;
  - cuerpo de 5001 caracteres y versión 0 rechazados;
  - `updated_by` con `ON DELETE RESTRICT`, cubierto por la prueba general de `pg_constraint`.
- [x] 1.5 Pruebas en `tests/test_migraciones.py`:
  - añadir `notification_templates` a `DOMAIN_TABLES` y restarla de `BASELINE_TABLES`;
  - instalación nueva: cuatro plantillas en la versión 1, sin `updated_by`, con los mismos textos que el catálogo;
  - el downgrade de `0004` sin cambios funciona y se puede volver a `head`;
  - con una plantilla en la versión 2, el downgrade lanza `NotImplementedError` y la tabla se conserva.

## 2. Servicio de plantillas

- [x] 2.1 `app/services/notification_templates.py`, catálogo (D3):
  - `VARIABLES`, con nombre, descripción y ejemplo;
  - `EVENTS`, con nombre, destinatario, variables disponibles y obligatorias, y asunto y cuerpo predeterminados de la sección 6.4 de la HU;
  - función `spec_for_code(codigo)`, que lanza `NotFoundError` si el código no existe.
- [x] 2.2 Normalización y validación (D2):
  - `normalize(subject, body)`: recorta los extremos y convierte `CRLF` en `LF`;
  - `check_draft(spec, subject, body) -> Draft`: normaliza y valida con los mensajes exactos de la spec, en orden (asunto antes que cuerpo) y sin repetir una misma variable desconocida.
- [x] 2.3 Render y datos de ejemplo:
  - `render(template_text, values)` en una sola pasada;
  - `compose_sample(spec, draft)`, que compone el borrador válido con los datos de ejemplo de la sección 6.5 de la HU (`estatus` = nombre del evento).
- [x] 2.4 Lectura para la interfaz: `list_templates(db)` en el orden del catálogo, con la última modificación formateada en la zona de negocio o "Predeterminada", y `get_template(db, spec)`.
- [x] 2.5 `save_template(db, spec, subject, body, version, user)` (D6, D13):
  - `TemplateValidationError` (400) con la lista de errores y el borrador normalizado;
  - `ConcurrentEditError` (`BusinessRuleError`, 409) con el mensaje exacto de edición concurrente;
  - sin cambios: no escribe, no audita y no registra en el log;
  - con cambios: `UPDATE` condicionado a la versión, auditoría `NOTIFICATION_TEMPLATE_UPDATED` (`old` y `new` con asunto, cuerpo y versión), commit y evento `notification_template.updated` (`event_code` y `version`).
- [x] 2.6 `compose(db, event, **valores) -> ComposedEmail` (D8, D10):
  - formato de montos y fechas;
  - `NotificationDataError` si falta una variable del evento o si una obligatoria llega vacía;
  - asunto en una sola línea, de hasta 255 caracteres;
  - respaldo en el texto predeterminado con `notification.template_fallback` (`event_code`, `reason` y `errors`), sin texto ni valores en el log.

## 3. Rutas e interfaz

- [x] 3.1 `app/routers/admin.py` (D11, D12):
  - `GET /admin/notification-templates`, con el aviso `?updated=<codigo>`;
  - `GET /admin/notification-templates/{codigo}`, con `?default=1`;
  - `POST /admin/notification-templates/{codigo}/preview`;
  - `POST /admin/notification-templates/{codigo}`.

  Sólo para `ADMIN`, con CSRF en los `POST`, 404 para un evento desconocido, y 400 o 409 en la misma página de edición con el borrador.
- [x] 3.2 `app/templates/admin/notification_templates.html`: listado con evento, destinatario, asunto, última modificación y enlace "Editar".
- [x] 3.3 `app/templates/admin/notification_template_edit.html`:
  - destinatario de solo lectura y tabla de variables con descripción, ejemplo y marca de obligatoria;
  - campos `subject` y `body` y versión oculta;
  - botones "Vista previa" (`formaction`) y "Guardar", y enlace "Cargar texto predeterminado";
  - lista de errores, avisos y bloque de vista previa escapado.

  Sin scripts ni estilos en línea.
- [x] 3.4 `app/templates/base.html`: opción "Plantillas de correo" en el menú Administración, sólo para `ADMIN`.
- [x] 3.5 `app/static/css/app.css`: `.template-preview-body` con `white-space: pre-wrap` y el estilo mínimo del bloque de vista previa.

## 4. Pruebas de la capacidad

- [x] 4.1 `tests/test_plantillas_notificacion.py`:
  - fixture que restaura las cuatro plantillas (texto predeterminado, versión 1, sin `updated_by`);
  - utilidades para abrir, previsualizar y guardar.
- [x] 4.2 Escenarios de una plantilla por evento (instalación nueva, evento inexistente) y de acceso (INTERNAL y PROVIDER en las cuatro rutas, CSRF, opción en el menú).
- [x] 4.3 Escenarios de consulta (listado inicial, destinatario de solo lectura) y de variables por plantilla (Cancelada, variable de otro evento).
- [x] 4.4 Escenarios de validación: variable desconocida, obligatoria ausente, obligatoria sólo en el asunto, sin cerrar, asunto largo, espacios interiores y llaves sencillas, varios errores, asunto de varias líneas y normalización `CRLF`.
- [x] 4.5 Escenarios de vista previa: texto predeterminado, no guarda, texto escapado, borrador inválido.
- [x] 4.6 Escenarios de guardado: exitoso (listado con el asunto, el Administrador y la fecha), edición concurrente, sin cambios y carga del texto predeterminado seguida de guardado.
- [x] 4.7 Escenarios de textos predeterminados (los cuatro válidos, Cancelada compuesta) y de composición:
  - plantilla vigente;
  - formato de montos y fechas;
  - valor con llaves;
  - asunto en una sola línea y recorte a 255;
  - obligatoria vacía y variable faltante;
  - plantilla inválida por SQL y plantilla ausente.
- [x] 4.8 Escenarios de auditoría: registro de un cambio y acciones sin auditoría.
- [x] 4.9 `tests/test_observabilidad.py`: `notification_template.updated` y `notification.template_fallback`, sin asunto, cuerpo ni valores.

## 5. Documentación y verificación

- [x] 5.1 `README.md`: sección "Plantillas de correo" con el flujo, las reglas del texto, la tabla de variables por plantilla, el servicio de composición para HU-20 y HU-14, y la nota de que `reset_demo.py` las devuelve al texto predeterminado.
- [x] 5.2 `python scripts/check.py` en verde: ruff, formato, `alembic check`, pytest con cobertura ≥ 93 % y `pip-audit`.
- [x] 5.3 Verificación manual en la aplicación: listado, edición, vista previa, carga del texto predeterminado, guardado, edición concurrente con dos sesiones y consola del navegador sin violaciones de CSP. *(Automatizada con Chromium headless (Playwright) sobre una base temporal y uvicorn local: 22/22 verificaciones, incluidos el acceso del PMO (403), `white-space: pre-wrap` aplicado desde `app.css` y la consola sin errores ni violaciones de CSP.)*
- [x] 5.4 `openspec validate plantillas-estatus-factura --strict` sin errores.
