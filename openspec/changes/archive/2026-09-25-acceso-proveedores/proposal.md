## Why

La minuta del 21-sep-2026 (sección "Acceso de proveedores") dice que el acceso al portal se habilita cuando el proveedor registrado queda "Aprobado". En ese momento el sistema le envía automáticamente un correo con usuario y contraseña temporal. Dos HU del Administrador lo cubren:

- **HU-02 (RF-02):** actualizar de forma masiva el estatus del proveedor a "Autorizado", para que esté listo para operar.
- **HU-03 (RF-03, RN-HU03-01):** enviar al proveedor autorizado su usuario y contraseña temporal. La contraseña se resguarda en ClickCloud y no dentro del sistema de proveedores.

HU-01 deja los proveedores de la carga masiva en "Registrado", sin usuario ni correo, y dejó a HU-02 la transición a "Autorizado" y el ajuste del alta individual. HU-08 (módulo anterior) entregó el transporte de correo y el servicio `notify()`, y HU-05 el catálogo de plantillas al que HU-03 agrega su evento. Hoy un proveedor sólo obtiene acceso si el Administrador le crea un usuario a mano y le comunica la contraseña por otro medio.

## What Changes

- **Estatus "Autorizado"** (HU-02): el estatus operativo `ACTIVE` se muestra como "Autorizado". La única transición que ofrece la interfaz es "Registrado" → "Autorizado".
- **Alta individual alineada con HU-01:**
  - el proveedor dado de alta con el formulario nace "Registrado";
  - su correo no puede usarlo otro proveedor ni otro usuario (RD-06 de HU-01).
- **Autorización masiva** desde el listado de proveedores, exclusiva del rol `ADMIN`:
  - filtro por estatus y casillas en los proveedores "Registrado", con opción para seleccionar todos;
  - confirmación antes de enviar, que anuncia el envío de credenciales;
  - `POST /suppliers/authorize`, de 1 a 100 proveedores por operación, en una sola transacción con bloqueo de filas;
  - se omiten los que no están en "Registrado" y no se autorizan aquellos cuyo correo ya usa otro usuario;
  - resumen con los proveedores autorizados, el resultado del envío de credenciales de cada uno, los omitidos y los no autorizados;
  - auditoría por proveedor y de la operación completa, y evento de log `supplier.bulk_authorize`.
- **Credenciales al autorizar** (HU-03):
  - se crea el usuario `PROVIDER` del proveedor, con su correo del catálogo como usuario;
  - se genera una contraseña temporal aleatoria que cumple la política; el portal sólo guarda su hash Argon2;
  - después de confirmar la autorización se envía el correo "Credenciales de acceso" con la dirección de inicio de sesión;
  - un envío fallido no revierte la autorización: queda en la bitácora y en el expediente;
  - un proveedor que ya tenía su propio usuario se autoriza sin generar credenciales nuevas.
- **Resguardo de la contraseña temporal** (RN-HU03-01): punto de integración `secret_vault` con un adaptador nulo. El adaptador de ClickCloud queda pendiente de su API y credenciales.
- **Acceso al portal en el expediente del proveedor** (sólo `ADMIN`):
  - usuario, último acceso y resultado del último envío de credenciales;
  - **"Reenviar credenciales"**, sólo si el proveedor nunca ha iniciado sesión, con una contraseña nueva.
- **Plantilla "Credenciales de acceso"** (`SUPPLIER_CREDENTIALS`) en el catálogo de HU-05:
  - variables `proveedor`, `usuario`, `contrasena_temporal` y `url_portal`;
  - destinatario: el correo del proveedor, sin copias.
- **Migración** `0006_supplier_credentials`: el evento nuevo en las restricciones de las tres tablas de notificaciones y la plantilla predeterminada.

**Fuera de alcance:**
- cambio obligatorio de contraseña en el primer inicio de sesión y política de contraseña del proveedor (HU-10);
- rotación mensual (HU-11) y recuperación de contraseña (fuera del MVP);
- adaptador real de ClickCloud;
- desautorizar, inactivar o reactivar proveedores;
- dar de alta proveedores internacionales con el formulario individual;
- expiración de la contraseña temporal.

## Supuestos

Decisiones tomadas ante ambigüedades de las HU, consistentes con el código existente y confirmadas en el plan de módulos:

- **S1.** "Autorizado" es el estatus `ACTIVE` que ya exige la regla SUP-001, con una nueva etiqueta. No se agrega otro valor a la enumeración. Así las reglas y los datos existentes no cambian (D5 de HU-01).
- **S2.** El alta individual pasa a "Registrado", como la carga masiva. Es un cambio visible: un proveedor dado de alta a mano no puede facturar hasta que se autorice.
- **S3.** Máximo 100 proveedores por operación, porque el envío de credenciales es síncrono (HU-08, S3).
- **S4.** Un proveedor que ya tiene un usuario `PROVIDER` propio con su correo se autoriza sin generar ni enviar credenciales. Si el correo lo usa otro usuario, el proveedor no se autoriza y el resumen lo indica.
- **S5.** RN-HU03-01: el portal nunca guarda la contraseña temporal en claro, sólo su hash. Tampoco la escribe en el log, la auditoría ni la bitácora de envíos. El resguardo en ClickCloud pasa por un punto de integración cuyo adaptador actual no guarda nada. HU-03 queda **parcial** en esta regla hasta tener la API de ClickCloud.
- **S6.** La dirección del portal en el correo es la de inicio de sesión del servidor que atiende la autorización (`/login`). No se agrega una variable de entorno.
- **S7.** La contraseña temporal no expira. Obligar a cambiarla en el primer acceso es HU-10.
- **S8.** "Reenviar credenciales" sólo se ofrece mientras el proveedor no ha iniciado sesión: genera una contraseña nueva e invalida la anterior.
- **S9.** El resumen de la autorización se reconstruye con el registro de auditoría de la operación y la bitácora de envíos, porque el portal no tiene avisos entre redirecciones.

## Capabilities

### New Capabilities
- `acceso-proveedores`: estatus "Autorizado", alta individual en "Registrado", autorización masiva, usuario y contraseña temporal al autorizar, correo de credenciales, resguardo de la contraseña, acceso en el expediente, reenvío de credenciales y auditoría.

### Modified Capabilities
- `plantillas-notificacion`: quinta plantilla, "Credenciales de acceso", con sus variables, datos de ejemplo y texto predeterminado; el listado muestra cinco plantillas.
- `notificaciones-correo`: el correo de credenciales va al correo del proveedor y no admite copias.
- `observabilidad`: evento `supplier.bulk_authorize`.
- `integridad-datos`: la enumeración de eventos de notificación incluye `SUPPLIER_CREDENTIALS`.

## Impact

- **Código:**
  - `app/core/constants.py`: etiqueta "Autorizado" y `NotificationEvent.SUPPLIER_CREDENTIALS`;
  - `app/services/notification_templates.py`: variables `usuario`, `contrasena_temporal` y `url_portal`, y el evento de credenciales;
  - nuevos `app/services/supplier_access_service.py` y `app/services/secret_vault.py`;
  - `app/routers/suppliers.py`: filtro, `POST /suppliers/authorize`, `POST /suppliers/{id}/credentials`, alta individual en "Registrado" y correo único;
  - plantillas `suppliers/list.html` y `suppliers/detail.html`; nuevo `app/static/js/supplier_authorize.js`.
- **Esquema:** nueva revisión Alembic `0006_supplier_credentials`, posterior a `0005_notification_recipients`.
- **Rutas nuevas:** `POST /suppliers/authorize` y `POST /suppliers/{supplier_id}/credentials`; `GET /suppliers` acepta `?status=` y `?authorization=`, y `GET /suppliers/{id}` acepta `?credentials=`.
- **Dependencias:** ninguna nueva.
- **Pruebas:** nuevo `tests/test_acceso_proveedores.py`; ajustes en `tests/test_plantillas_notificacion.py`, `tests/test_migraciones.py`, `tests/test_integridad.py`, `tests/test_observabilidad.py` y `tests/test_altas.py`.
- **Documentación:** `README.md`.
- **Sin cambios:** regla SUP-001, datos demo, carga masiva (HU-01), inicio de sesión.
