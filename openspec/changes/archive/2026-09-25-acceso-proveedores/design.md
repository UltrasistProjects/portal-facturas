## Context

HU-02 y HU-03 cierran el ciclo del catálogo de proveedores que abrió HU-01: registro → autorización → acceso al portal. Estado actual:

- **Estatus:** `REGISTERED` ("Registrado", carga masiva de HU-01), `ACTIVE` ("Activo") e `INACTIVE`. SUP-001 exige `ACTIVE` para facturar. El alta individual (`POST /suppliers`) crea en `ACTIVE` y no verifica el correo contra otros proveedores ni usuarios.
- **Usuarios:** `users.email` es único y `users.supplier_id` liga al usuario `PROVIDER` con su proveedor. Hoy el Administrador los crea a mano en `/admin/users` y escribe la contraseña inicial.
- **Contraseñas:** Argon2 (`pwdlib`); `generate_password()` produce 20 caracteres con letra, dígito y carácter especial, que cumplen la política de RF-06.
- **Correo:** `notification_service.notify()` (HU-08) resuelve destinatarios, compone con la plantilla vigente (HU-05), envía después del commit y registra el envío en `email_deliveries` sin asunto ni cuerpo.
- **Interfaz:** listado de proveedores sin selección ni filtros; expediente sin información de acceso. El JavaScript vive en `app/static/js/` (la CSP prohíbe scripts en línea) y Bootstrap ya está incluido.

## Goals / Non-Goals

**Goals:**
- Autorizar muchos proveedores a la vez de forma segura: sin dobles autorizaciones, sin credenciales duplicadas y con un resumen claro.
- Que ningún proveedor autorizado se quede sin saber si recibió sus credenciales.
- Que la contraseña temporal sólo exista en claro en memoria y en el correo.

**Non-Goals:**
- Cambio obligatorio de contraseña (HU-10), expiración de la temporal y recuperación.
- Adaptador real de ClickCloud.
- Desautorizar o reactivar proveedores.

## Decisions

### D1. "Autorizado" es `ACTIVE`
`SUPPLIER_STATUS_LABELS[ACTIVE]` pasa a "Autorizado". No se agrega un valor a la enumeración ni se migra la columna. SUP-001, el selector de proveedores de `/invoices/new` y los datos demo siguen igual. Supuesto S1.

*Alternativa:* un estatus `AUTHORIZED` nuevo. Obligaría a migrar datos, a cambiar SUP-001 y a decidir qué significa `ACTIVE`.

### D2. Servicio `supplier_access_service`
Un solo módulo con `authorize()`, `resend_credentials()`, `provider_user()`, `credentials_status()` y `authorization_summary()`. El router sólo traduce HTTP, como en HU-04, HU-05 y HU-08.

### D3. Autorización en una transacción y credenciales después
`authorize(db, ids, admin, portal_url)`:
1. Valida la selección: de 1 a 100 ids únicos (400) y todos existentes (404).
2. Lee los proveedores con `SELECT … FOR UPDATE`, ordenados por id, y los usuarios cuyo correo coincide.
3. Clasifica cada proveedor:
   - si no está en `REGISTERED`, se omite: una segunda autorización simultánea lo encuentra ya autorizado;
   - si su correo lo usa un usuario que no es su propio `PROVIDER`, no se autoriza (conflicto);
   - si ya tiene su propio usuario, se autoriza sin credenciales nuevas;
   - en otro caso se autoriza, se crea el usuario `PROVIDER` con la contraseña temporal y se entrega esta al resguardo (D6).
4. Audita y confirma (D8).
5. Por cada credencial nueva llama a `notify(SUPPLIER_CREDENTIALS)`. Un error de transporte queda `FAILED` y no revierte nada (D5 de HU-08).
6. Registra `supplier.bulk_authorize`.

Si la creación de un usuario viola la unicidad del correo por una carrera con otra transacción, se revierte todo y responde 409 "Otro proceso usó el correo de un proveedor seleccionado. Intente de nuevo.".

*Alternativa:* enviar dentro de la transacción. Un correo podría salir para una autorización que después se revierte.

### D4. Selección en el listado con confirmación en JavaScript
`GET /suppliers?status=REGISTERED|ACTIVE|INACTIVE` filtra el listado. Un valor desconocido se ignora y muestra todos.

Para el Administrador, la tabla queda dentro de un formulario `POST /suppliers/authorize` con una casilla `supplier_ids` sólo en las filas "Registrado". `supplier_authorize.js` agrega:
- la casilla "seleccionar todos" y el contador;
- el botón deshabilitado mientras no hay selección;
- un modal de Bootstrap: "Se autorizarán N proveedores y se enviará a cada uno su usuario y contraseña temporal por correo." con "Cancelar" y "Autorizar y enviar credenciales".

Sin JavaScript el formulario funciona sin confirmación.

*Alternativa:* una página intermedia de confirmación. Duplica el listado y agrega una ruta, sin más seguridad que el modal.

### D5. Resumen desde la auditoría
El registro `SUPPLIER_BULK_AUTHORIZED` guarda en `new_value` las listas de ids `authorized`, `existing_access`, `skipped` y `conflicts`. `POST /suppliers/authorize` redirige a `/suppliers?authorization=<id del registro>`.

La página reconstruye el resumen con los nombres de los proveedores y, para cada credencial nueva, el último envío de `SUPPLIER_CREDENTIALS` de la bitácora (enviado o fallido, con el error). Un id que no corresponde a un registro `SUPPLIER_BULK_AUTHORIZED` se ignora. El parámetro nunca se refleja tal cual (patrón `?test=` de HU-08).

### D6. Resguardo de la contraseña temporal (RN-HU03-01)
`app/services/secret_vault.py` define el protocolo `SecretVault.store_temporary_password(supplier_id, username, password)` y `NullSecretVault`, que no guarda nada. `get_vault()` devuelve el adaptador activo.

La llamada ocurre antes del commit: un adaptador real que falle revierte la autorización y no deja credenciales que nadie pueda recuperar. El portal guarda sólo `hash_password(password)`. La contraseña no se pasa a `audit()`, al log ni a `email_deliveries`, que ya no guarda el cuerpo. Supuesto S5.

### D7. Plantilla `SUPPLIER_CREDENTIALS`
Se agrega a `NotificationEvent` y a `notification_templates.EVENTS`, con:
- nombre "Credenciales de acceso" y destinatario `Recipient.SUPPLIER`;
- variables `proveedor`, `usuario`, `contrasena_temporal` y `url_portal`; obligatorias las tres últimas;
- asunto predeterminado "Acceso al Portal de Proveedores ULTRASIST".

`compose()` recibe los argumentos `usuario`, `contrasena_temporal` y `url_portal`. `url_portal` es `request.url_for("login_page")`. El evento no está en `COPY_EVENTS` de HU-08: nunca lleva copias.

La migración `0006_supplier_credentials`:
- reemplaza el `CHECK notificationevent` de `notification_templates`, `notification_copies` y `email_deliveries`;
- inserta la plantilla en la versión 1;
- en el downgrade, se niega (`NotImplementedError`) si la plantilla se modificó o hay envíos de credenciales.

### D8. Auditoría
- Por proveedor autorizado: `SUPPLIER_STATUS_CHANGED` con `old_value = {"status": "REGISTERED"}` y `new_value = {"status": "ACTIVE"}`.
- Por usuario creado: `USER_CREATED` con `new_value = {"role": "PROVIDER", "supplier_id": …, "origin": "SUPPLIER_AUTHORIZATION"}`.
- Por operación: `SUPPLIER_BULK_AUTHORIZED` (D5).
- Por reenvío: `SUPPLIER_CREDENTIALS_RESENT` con `new_value = {"user_id": …}`.

Ninguno contiene la contraseña ni su hash.

### D9. Reenvío de credenciales
`POST /suppliers/{id}/credentials` (`ADMIN`, CSRF) exige, en este orden:
- el proveedor en `ACTIVE`;
- su usuario `PROVIDER` con su correo;
- el usuario activo;
- `last_login_at` nulo.

Si no se cumple, responde 409 con el motivo. Si se cumple, bloquea el usuario, genera y resguarda la contraseña nueva, audita, confirma y envía. Redirige a `/suppliers/{id}?credentials=<id del envío>`, que muestra el resultado sólo si el envío es de credenciales y pertenece a ese proveedor.

### D10. Alta individual
`POST /suppliers` crea con `status=REGISTERED`. Antes de crear, responde 409 "El correo ya lo usa otro proveedor o usuario." si el correo, sin distinguir mayúsculas, está en `suppliers.email` o en `users.email`. Es la misma regla que la carga masiva (RD-06 de HU-01).

## Risks / Trade-offs

- **[Envío síncrono de hasta 100 correos]** La respuesta puede tardar varios segundos con un servidor SMTP lento. → Límite de 100 por operación y `SMTP_TIMEOUT` configurable; el resumen muestra cada resultado.
- **[Contraseña temporal sin expiración ni cambio obligatorio]** → Documentado como pendiente de HU-10; el reenvío sólo es posible mientras el proveedor no ha iniciado sesión.
- **[ClickCloud sin integrar]** → HU-03 queda parcial en RN-HU03-01; el punto de integración y su prueba ya existen.
- **[Cambio de comportamiento del alta individual]** → Anotado en el README; el proveedor se autoriza desde el mismo listado.

## Migration Plan

1. `alembic upgrade head` aplica `0006_supplier_credentials`.
2. Los proveedores `ACTIVE` existentes se muestran como "Autorizado" sin cambios de datos.
3. Rollback: el downgrade a `0005` restaura las restricciones y borra la plantilla si no se modificó y no hay envíos de credenciales. Las autorizaciones y los usuarios creados se conservan.

## Open Questions

- API, credenciales y forma de resguardo en ClickCloud (RN-HU03-01).
- Si la contraseña temporal debe expirar (por ejemplo, a las 72 horas); hoy HU-10 no lo pide.
