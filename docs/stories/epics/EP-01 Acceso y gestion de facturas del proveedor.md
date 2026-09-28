# EP-01 · Acceso y gestión de facturas del proveedor

| Campo | Valor |
| --- | --- |
| ID | EP-01 |
| Rol | Proveedor Nacional e Internacional (rol `PROVIDER`) |
| Módulos (ERS v1.3) | B. Acceso y Seguridad · C. Gestión de Facturas |
| Historias | HU-10, HU-12, HU-13, HU-15, HU-16, HU-14, HU-17 |
| Requisitos funcionales | RF-06, RF-07, RF-08, RF-14, RF-15, RF-09, RF-16 |
| Reglas de negocio | RN-HU12-01, RN-HU13-01, RN-HU13-02 |
| Prioridad | Alta (alcance comprometido del MVP) |
| Depende de | HU-01 a HU-08 (Administración, implementadas). HU-17 depende además de HU-20 (EP-02) |
| Habilita | EP-02 · Validación de facturas por PMO |
| Estado | Lista para refinamiento. Cada HU se detalla en `docs/stories/new/` con el formato de HU-04 antes de `/opsx:propose` |
| Estimación | Tamaños relativos en la sección 3. La estimación se hace en el refinamiento |
| Versión / fecha | 1.0 · 2026-09-28 · Equipo Técnico |

## Cómo usar este documento

Una épica no alimenta directamente un change de OpenSpec. Este documento:

1. Fija las decisiones transversales (sección 5) que todas las HU de la épica deben respetar. La principal es el modelo de estatus de la factura (DT-01), que también usa EP-02.
2. Da a cada HU su punto de partida: qué existe hoy en el PoC y qué falta (sección 6).
3. Reúne las preguntas para negocio (sección 7) y propone el orden de entrega (sección 8).

Para cada HU: redactar su documento en `docs/stories/new/` con las secciones de HU-04, copiar las decisiones (DT) y preguntas (P) que le correspondan y ejecutar `/opsx:propose <change>` con el change sugerido en la sección 3.

---

## 1. Objetivo

El proveedor autorizado entra al portal de forma segura y opera sus facturas de principio a fin:

- las registra con sus archivos mínimos;
- las envía al PMO después de las validaciones automáticas;
- las cancela con su acuse;
- da seguimiento a su estatus y a las observaciones del PMO.

La épica cubre al proveedor nacional (CFDI: XML y PDF) y al internacional (Invoice en PDF).

**Valor:** sustituye la recepción de facturas por correo por un flujo con validación previa, control de duplicados y trazabilidad. Es lo que la minuta del 21-sep-2026 pide priorizar: "la recepción y validación de facturas, el control de duplicados, la gestión de estatus y las notificaciones automáticas".

## 2. Alcance

### Dentro del alcance

- Cambio obligatorio de la contraseña temporal en el primer inicio de sesión (HU-10).
- Registro de la factura nacional con sus archivos mínimos y el estatus "Cargada" (HU-12).
- Envío de la factura nacional a validación. Antes del envío, el XML se valida contra las Reglas de Validación y se controlan los duplicados por el identificador del XML. La factura enviada pasa a "Enviada" (HU-13).
- Registro del Invoice internacional con la captura de sus importes, sus documentos soporte y el control de duplicados por nombre de archivo (HU-15).
- Envío del Invoice internacional a validación, con validaciones "en la medida de lo posible" (HU-16).
- Cancelación con "Acuse de cancelación" obligatorio y correo a Recepción de Facturas con fecha límite de +72 h (HU-14).
- Consulta del estatus de las facturas, con las observaciones o el motivo de rechazo, y reenvío tras "Observaciones" (HU-17).
- Modelo de estatus del ERS (§3.6) aplicado al PoC y a sus datos existentes (DT-01).

### Fuera del alcance

| Tema | Motivo |
| --- | --- |
| Rotación periódica de la contraseña (HU-11) | Fuera del MVP (Validación de HUs, §3) |
| Recuperación de contraseña ("olvidé mi contraseña") | Fuera del MVP (Validación de HUs, §3, "Requerimiento General") |
| Caducidad de la contraseña temporal | Ninguna fuente la pide y hoy no expira (README). Puede agregarse después sin cambiar el diseño de HU-10 |
| Seguimiento del pago | El MVP termina en "Autorizada". El ERS no define estatus de pago (§3.6) |
| Extracción automática de datos del Invoice con IA | El PoC tiene analizadores en `app/services/ai/`, pero el alcance pide validar sólo "en la medida de lo posible". Se decide con las muestras (P-07) |
| Expediente del proveedor internacional (equivalente al Anexo A) | Pregunta P-02 de HU-04. HU-16 sólo decide si SUP-003 le aplica (P-06) |
| Decisión del PMO y sus correos | EP-02 (HU-20) |
| Motivo SAT de cancelación (01 a 04) y consulta del CFDI ante el SAT | Ni la HU ni la minuta lo piden |

## 3. Historias de la épica

| HU | Título | RF | RN | Depende de | Change OpenSpec sugerido | Tamaño relativo |
| --- | --- | --- | --- | --- | --- | --- |
| HU-10 | Cambio de contraseña en primer inicio de sesión | RF-06 | — | HU-03 ✅ | `primer-acceso-proveedor` | S |
| HU-12 | Registro de factura (nacional) | RF-07 | RN-HU12-01 | HU-04 ✅, HU-10 | `registro-envio-factura-nacional` | L (incluye DT-01) |
| HU-13 | Envío de factura por proveedor nacional | RF-08 | RN-HU13-01, RN-HU13-02 | HU-12, HU-06 ✅ | el mismo que HU-12 | M |
| HU-15 | Registro de factura por proveedor internacional | RF-14 | — | HU-04 ✅, HU-10 | `factura-internacional` | M |
| HU-16 | Envío de factura por proveedor internacional | RF-15 | — | HU-15, HU-06 ✅ | el mismo que HU-15 | L (depende de P-07) |
| HU-14 | Cancelación de factura | RF-09 | — | HU-12, HU-15, HU-08 ✅ | `cancelacion-factura` | M |
| HU-17 | Consulta de estatus de factura | RF-16 | — | HU-20 (EP-02) | `seguimiento-estatus-proveedor` | S |

✅ = implementada. Las dependencias son las de `docs/source-of-truth/DEPENDENCIAS_HUs.md`.

**Por qué HU-12 y HU-13 van en un solo change, igual que HU-15 y HU-16:** la HU de registro crea "Cargada" y la de envío crea "Enviada". Si se entregan por separado, la máquina de estados queda a medio migrar entre ambos changes. Hay precedente: el change `acceso-proveedores` cubrió HU-02 y HU-03.

**Nota:** el índice asigna HU-12 al "Proveedor" en general, pero RF-07 la limita al Nacional. El registro internacional es HU-15.

## 4. Punto de partida

### 4.1 Lo que la épica reutiliza

| Capacidad | Estado actual | Uso en la épica |
| --- | --- | --- |
| Autorización y credenciales (HU-02, HU-03; spec `acceso-proveedores`) | Crea el usuario `PROVIDER` con contraseña temporal. `users.last_login_at` existe. El reenvío de credenciales sólo procede si el usuario nunca inició sesión | HU-10 marca el usuario y exige el cambio |
| Política de contraseñas (`autenticacion-sesiones`) | `app/core/passwords.py`: de 8 a 128 caracteres, con letra, dígito y carácter especial, y fuera de la lista de contraseñas comunes. Hoy sólo se aplica en altas y en el seed | HU-10 la aplica al cambio |
| Sesiones revocables | Sesión del lado del servidor, con rotación del identificador en el login | HU-10 rota la sesión al cambiar la contraseña |
| Archivos mínimos (HU-04; `archivos-minimos-factura`) | Catálogo por origen, checklist, reglas DOC-001 a DOC-009 y el tipo `FOREIGN_INVOICE` | HU-12 y HU-15: "Cargada" = obligatorios completos |
| Reglas de Validación (HU-06; `reglas-validacion`, `motor-validacion`) | RFC, Razón Social, Código Postal, método, forma y usos de CFDI, comparados por XML-002 a XML-010. La Dirección se guarda como dato de referencia | HU-13 (comparación del XML) y HU-16 (Razón Social y Dirección frente al Invoice) |
| Catálogo de monedas (HU-07) | Claves activas | HU-15 (moneda del Invoice) |
| Plantillas y envío de correo (HU-05, HU-08) | Evento `INVOICE_CANCELLED` con `numero_factura`, `proveedor` y `fecha_limite_cancelacion`. Buzón Recepción de Facturas, copias por evento, servicio de envío con bitácora | HU-14 sólo invoca el servicio |
| Flujo de facturas del PoC (`flujo-facturas`) | Alta en dos pasos (datos y después carga documental). Prevalidar y enviar son acciones separadas. Listado con alcance por proveedor. Folio `FAC-AAAA-nnnnn`. Unicidad de (proveedor, número de factura) | Base de HU-12, HU-13 y HU-17 |
| Duplicados de CFDI | Restricción `uq_invoices_uuid` y regla FIN-004 (`CRITICAL`) | RN-HU13-01 (DT-03) |
| Datos del proveedor internacional (HU-01) | `origin`, `country` y `foreign_tax_id`, sin domicilio | HU-15 y HU-16 |

### 4.2 Brechas transversales encontradas en el PoC

| # | Brecha | Dónde | Se atiende en |
| --- | --- | --- | --- |
| B-01 | El PoC tiene 11 estatus de factura, incluidos los de ClickBalance; el ERS define 6 | `InvoiceStatus` y `ALLOWED_TRANSITIONS` en `app/core/constants.py` | DT-01 (HU-12/13) |
| B-02 | Nada obliga a cambiar la contraseña temporal | README: "Pendiente de HU-10" | HU-10 |
| B-03 | **Seguridad:** el formulario de alta envía al navegador los contratos activos de **todos** los proveedores, con proyecto y monto autorizado. El filtro por proveedor ocurre en el cliente | `_new_invoice_page` en `app/routers/invoices.py`; `invoices/new.html` | HU-12 (DT-05) |
| B-04 | Los usuarios `INTERNAL` y `ADMIN` pueden registrar facturas a nombre de cualquier proveedor | `create_invoice` | HU-12 (DT-04) |
| B-05 | Una validación fallida deja la factura en `REQUIRES_CORRECTION`, el mismo estatus que asigna el botón "Solicitar corrección" del PMO | `run_validation` y `review_invoice` | DT-01 y DT-02 |
| B-06 | Una factura internacional nunca llega a `PREVALIDATED`: sin XML fallan las reglas XML y SUP-003 | README, "Limitaciones" | HU-16 (DT-08) |
| B-07 | Una factura internacional queda con importes en cero, porque sólo se llenan desde el XML | `create_invoice` y `run_validation` | HU-15 (DT-06) |
| B-08 | El parser del CFDI no extrae `Serie` ni `Folio` | `app/services/xml_service.py` | Sólo si P-03 elige Serie y Folio |
| B-09 | No existen el estatus ni el flujo de cancelación | — | HU-14 |

## 5. Decisiones transversales

Son recomendaciones del equipo técnico. Las que dependen de negocio remiten a su pregunta de la sección 7.

### DT-01 · Modelo de estatus de la factura (compartido con EP-02)

El ERS (§3.6) define seis estatus. Se propone conservar las claves cuyo significado ya equivale y cambiar sólo su etiqueta. Así se hizo en HU-02, donde `ACTIVE` se muestra como "Autorizado". Esto evita reescribir los valores guardados en `invoices.status`, en `audit_logs` y en las pruebas.

| Estatus en pantalla | Clave | Hoy | Lo asigna | Cuándo | ¿El proveedor puede editar? |
| --- | --- | --- | --- | --- | --- |
| Borrador (P-01) | `DRAFT` | "Borrador" | Sistema | Factura registrada a la que le faltan archivos obligatorios | Sí |
| Cargada | `UPLOADED` | "Cargada", transitorio | Sistema | Todos los archivos obligatorios cargados (RN-HU12-01) | Sí |
| Enviada | `UNDER_REVIEW` | "En revisión" | Sistema | El envío superó las validaciones (RN-HU13-02) | No |
| Autorizada | `ACCEPTED` | "Aceptada" | PMO | HU-20 | No |
| Rechazada | `REJECTED` | "Rechazada" | PMO | HU-20 | No: es definitiva (P-04) |
| Observaciones | `REQUIRES_CORRECTION` | "Requiere corrección", asignado por la validación o por el PMO | Sólo el PMO | HU-20 | Sí: corrige y reenvía |
| Cancelada | `CANCELLED` (nueva) | — | Proveedor | HU-14 | No: es definitiva |

**Transiciones:**

- `DRAFT ⇄ UPLOADED`: se recalcula con el checklist de HU-04 cada vez que se carga o reemplaza un documento.
- `UPLOADED → UNDER_REVIEW` y `REQUIRES_CORRECTION → UNDER_REVIEW`: el proveedor envía y las validaciones se superan (HU-13, HU-16).
- `UNDER_REVIEW → ACCEPTED | REJECTED | REQUIRES_CORRECTION`: decisión del PMO (HU-20).
- `→ CANCELLED`: el proveedor cancela desde los estatus que fije P-05 (HU-14).

Los estatus editables pasan a ser `DRAFT`, `UPLOADED` y `REQUIRES_CORRECTION`.

**Estatus que se retiran:**

- `VALIDATING`, `VALIDATION_FAILED` y `PREVALIDATED` se retiran en el change de HU-12/13, porque la validación pasa a ocurrir dentro del envío (DT-02).
- `READY_FOR_CLICKBALANCE` y `UPLOADED_TO_CLICKBALANCE` no se tocan en esta épica. Los resuelve HU-20 (EP-02, DT-06 y P-01).

**Migración de datos (revisión Alembic de HU-12/13):**

- `VALIDATING`, `VALIDATION_FAILED`, `PREVALIDATED` y `REQUIRES_CORRECTION` sin decisión del PMO pasan a `UPLOADED` o `DRAFT`, según el checklist.
- `REQUIRES_CORRECTION` cuya última revisión es del PMO se conserva y se muestra como "Observaciones".
- Cada factura migrada deja un registro de auditoría `STATUS_MIGRATED`.
- Se actualizan las 10 facturas demo de `scripts/seed_db.py`, el caso de flujo de `tests/test_demo_workflow.py` y el `CHECK` de estatus de `integridad-datos`.

### DT-02 · "Enviar" valida y cambia el estatus en un solo paso

El texto literal de HU-13 pide "enviar mi factura al área de validación (PMO), previo la validación". Hoy son dos acciones ("Procesar y prevalidar" y "Enviar a revisión") separadas por el estatus intermedio `PREVALIDATED`.

**Propuesta:** `POST /invoices/{id}/submit` ejecuta el motor con la configuración vigente. Esto resuelve la decisión RD-08 que HU-04 dejó a HU-13.

- **Sin ningún `FAIL`:** la factura pasa a "Enviada" (`UNDER_REVIEW`), se registra `submitted_at` y se audita `INVOICE_SUBMITTED`.
- **Con algún `FAIL`:** el estatus no cambia. Los resultados se guardan y la página muestra las reglas que fallaron, con el valor esperado y el detectado.

Bloquea cualquier `FAIL`, sea `CRITICAL` o `ERROR`, igual que hoy para llegar a `PREVALIDATED`. Un `WARNING` no bloquea y el PMO lo ve en la revisión.

El botón "Procesar y prevalidar" puede quedarse como **"Verificar"**: guarda los resultados sin cambiar el estatus, para que el proveedor corrija antes de enviar. Cada HU decide si lo conserva.

### DT-03 · Duplicado nacional = UUID (folio fiscal)

- **Qué piden las fuentes:** RN-HU13-01 dice "buscando por el número de folio del XML". La minuta dice "control de duplicados mediante el identificador contenido en el XML".
- **Por qué el UUID:** el identificador del CFDI ante el SAT es el UUID, el "folio fiscal". En CFDI 4.0, `Serie` y `Folio` son opcionales y sólo son únicos por emisor.
- **Lo que ya existe:** el PoC ya bloquea los UUID repetidos con `uq_invoices_uuid` y la regla FIN-004 (`CRITICAL`).

**Propuesta:** RN-HU13-01 se cumple con el UUID, comparado contra todas las facturas en cualquier estatus, incluidas Rechazada y Cancelada. Un CFDI rechazado o cancelado no se reenvía: el proveedor emite otro con un UUID nuevo (P-04). FIN-005 (proveedor y número de factura) se conserva.

El mensaje de duplicado **no debe revelar datos de la otra factura** si pertenece a otro proveedor.

P-03 confirma esta interpretación. Si negocio elige Serie y Folio, hay que extraerlos del XML (B-08) y agregar una regla por RFC emisor.

### DT-04 · Sólo el proveedor registra, envía y cancela

El ERS (§2.3) asigna estas acciones al Proveedor, pero hoy `INTERNAL` y `ADMIN` también pueden registrar facturas (B-04).

**Propuesta:** el alta (`POST /invoices/new`), la carga de documentos, el envío y la cancelación quedan exclusivos del rol `PROVIDER`; los demás roles reciben 403. El PMO conserva la lectura.

**Motivo:** separación de funciones. Quien autoriza (el PMO) no debe registrar la factura que autoriza.

**Impacto:** el seed demo crea sus facturas directamente en la base de datos y no se ve afectado. Las pruebas que registran facturas con usuarios internos deben ajustarse. Si negocio necesita capturar facturas a nombre de un proveedor, se trata como una HU aparte.

### DT-05 · Contratos filtrados en el servidor

Corrige B-03 y forma parte de HU-12. El formulario de alta sólo recibe los contratos activos del proveedor del usuario. La verificación del servidor (`contract.supplier_id == supplier_id`) se conserva.

### DT-06 · El proveedor internacional captura los importes de su Invoice

Sin XML, la factura internacional necesita estos datos: fecha, subtotal, impuestos, total y moneda (catálogo de monedas, HU-07).

- El formulario de HU-15 los pide cuando el origen del proveedor es Internacional. Lo decide el servidor según el origen del proveedor, no un campo del formulario.
- Las reglas FIN-001 (monto frente al contrato), FIN-002 (consistencia de importes) y FIN-003 (moneda frente al contrato) usan los importes capturados.
- En la factura nacional, los importes siguen saliendo del XML.

### DT-07 · Duplicado internacional por nombre de archivo

La minuta pide "evitar duplicados inicialmente por nombre de archivo".

**Propuesta:**

- **Qué se compara:** el nombre del archivo del documento `FOREIGN_INVOICE`, normalizado (sin espacios en los extremos y en minúsculas).
- **Contra qué:** los `FOREIGN_INVOICE` vigentes de las demás facturas del mismo proveedor, excepto las canceladas (P-08).
- **Cuándo:**
  - al cargar el archivo: HTTP 409 y el archivo no se escribe;
  - al enviar: una regla nueva de severidad `CRITICAL`, que cubre cargas concurrentes.
- **Excepción:** reemplazar el Invoice de la misma factura con un archivo del mismo nombre sí se permite.
- **Pendiente para HU-15:** la garantía ante concurrencia, por ejemplo un bloqueo consultivo por proveedor como el que usa HU-08.

### DT-08 · Validación internacional "en la medida de lo posible"

- **Reglas que dejan de aplicar:** XML-001 a XML-010 y FIN-004 resultan `NOT_APPLICABLE` para el origen Internacional, con el mensaje "No aplica a proveedores internacionales".
- **Reglas nuevas (categoría `INT`):** se evalúan sobre el texto del PDF. Hoy `analyze_pdf` sólo guarda los primeros 2 000 caracteres en `text_preview`, así que el motor debe releer el PDF completo.
  - INT-001: el identificador fiscal del proveedor (`foreign_tax_id`) aparece en el Invoice.
  - INT-002: la Razón Social de ULTRASIST (Reglas de Validación) aparece en el Invoice.
  - INT-003: la Dirección de ULTRASIST o, si está vacía, su Código Postal, aparece en el Invoice.
- **Severidad de las reglas INT:** `WARNING`. Nunca bloquean el envío, porque el texto puede no extraerse bien o venir con otro formato. Si el PDF no tiene capa de texto (por ejemplo, un escaneo), resultan `NOT_EVALUATED`.
- **Expediente del proveedor:** que SUP-003 y SUP-004 apliquen o no al internacional lo decide P-06.
- **Qué bloquea el envío internacional:** la regla DOC-008 y los demás documentos obligatorios, el duplicado por nombre (DT-07), FIN-005, SUP-001, SUP-002 y CON-001, y FIN-001 a FIN-003 calculadas con los importes capturados.
- **Calibración:** las reglas se ajustan con las tres muestras de invoices extranjeros acordadas en la minuta (responsable Octavio Rivera, 22-sep-2026). Las muestras no están en el repositorio.

### DT-09 · Correos después de confirmar la transacción

HU-14 (y HU-20 en EP-02) envían el correo con el servicio de HU-08 **después** de confirmar la transacción de negocio:

- un correo fallido no revierte la operación (spec `notificaciones-correo`);
- el envío queda en la bitácora;
- la pantalla muestra al usuario el resultado del envío.

### DT-10 · El "Acuse de cancelación" es un tipo de documento del sistema

HU-04 dejó a HU-14 la decisión de cómo modelar el acuse.

**Propuesta:** un tipo del sistema `CANCELLATION_ACK`, "Acuse de cancelación", en `invoice_document_types`:

- formatos PDF y XML;
- nivel fijo "No aplica" para ambos orígenes, para que no se ofrezca en la carga documental ni se exija al enviar;
- se carga sólo desde el formulario de cancelación;
- se amplía el `CHECK` de niveles fijos de HU-04 para incluirlo.

Así el detalle de la factura lo muestra con su nombre en español (RD-10 de HU-04).

## 6. Brechas y alcance por HU

Cada HU lista lo que existe hoy, lo que falta, los criterios clave a nivel épica y lo que debe decidir su propio documento. Los criterios completos, con sus escenarios, se redactan en cada HU.

### HU-10 · Cambio de contraseña en primer inicio de sesión

El texto literal dice "me solicite cambiar mi **correo**": es una errata de "contraseña", como interpreta RF-06.

**Hoy:** el proveedor entra con la contraseña temporal sin límite de tiempo, y nada lo obliga a cambiarla.

**Falta:**

- **Marca de cambio pendiente:** `users.must_change_password`. Se activa al crear el usuario en la autorización (HU-03), al reenviar credenciales y, según P-02, en las altas de `/admin/users`. La migración la activa para los usuarios `PROVIDER` que nunca han iniciado sesión.
- **Bloqueo de la navegación:** mientras la marca esté activa, toda petición autenticada redirige (303) a la página de cambio, salvo esa página, el cierre de sesión y los archivos estáticos.
- **Página de cambio:** pide la contraseña actual, la nueva y su confirmación. Valida la política de RF-06 (reutiliza `passwords.py`), que la confirmación coincida y que la nueva sea distinta de la actual. Reporta todos los errores juntos con HTTP 400.
- **Al guardar:**
  - guarda el hash Argon2 y apaga la marca;
  - rota la sesión y revoca las demás sesiones del usuario;
  - audita `PASSWORD_CHANGED` sin la contraseña;
  - redirige al tablero con un aviso.

**Criterios clave:**

- Un proveedor que entra con la contraseña temporal sólo puede ver la página de cambio; cualquier otra URL lo redirige a ella.
- `Password123` se rechaza con "falta un carácter especial"; `Portal#2026x` se acepta.
- Después del cambio, la contraseña temporal deja de funcionar.

**Decide la HU:**

- si el reenvío de credenciales de HU-03 pasa a exigir "marca de cambio activa" en lugar de "nunca inició sesión";
- si el formulario de cambio se protege con la limitación de intentos del login.

**Capacidades:** modifica `autenticacion-sesiones` y `acceso-proveedores`.

### HU-12 · Registro de factura (nacional)

**Hoy:** el alta pide proveedor, contrato, número, periodo, proyecto, orden de compra y líder, y lleva a la carga documental con el checklist de HU-04. La factura queda en `DRAFT` hasta que se prevalida.

**Falta:**

- el modelo de DT-01: "Cargada" al completar los obligatorios, "Borrador" antes de completarlos, la migración de datos, las etiquetas y los estatus editables;
- DT-04 (sólo `PROVIDER`) y DT-05 (sólo los contratos del proveedor);
- rechazar el alta si el proveedor no está "Autorizado";
- el aviso "Factura cargada. Ya puede enviarla a validación" en la carga documental.

**Criterios clave:**

- Una factura nacional con XML, PDF y orden de compra, pero sin Vo.Bo., queda en "Borrador" con el aviso "Falta 1 archivo obligatorio". Al cargar el Vo.Bo. pasa a "Cargada".
- El HTML del formulario de alta no contiene contratos de otros proveedores.
- Un usuario `INTERNAL` que envía `POST /invoices/new` recibe HTTP 403.

**Decide la HU:** P-01 y el detalle del mapeo de la migración.

**Capacidades:** modifica `flujo-facturas`, `integridad-datos` y `motor-validacion` (la validación deja de asignar `REQUIRES_CORRECTION`).

### HU-13 · Envío de factura por proveedor nacional

**Hoy:** prevalidar y enviar son acciones separadas. El duplicado por UUID ya se detecta.

**Falta:**

- DT-02: enviar = validar + "Enviada";
- DT-03: duplicados por UUID;
- mostrar el motivo cuando el envío no procede;
- permitir el envío desde "Observaciones".

**Criterios clave:**

- Con el Código Postal configurado en `03930` y un XML con `06600`, el envío no procede: la factura sigue "Cargada" y la página muestra XML-010 con el valor esperado y el detectado.
- Un XML cuyo UUID ya tiene otra factura no se envía, y el mensaje no revela datos de esa otra factura.
- Una factura sin fallas pasa a "Enviada" con `submitted_at` y ya no admite cambios de documentos.
- Si las Reglas de Validación cambian después de "Verificar", el envío evalúa con la configuración vigente.

**Decide la HU:** P-03 y si se conserva el botón "Verificar".

**Capacidades:** modifica `flujo-facturas` y `motor-validacion`.

### HU-15 · Registro de factura por proveedor internacional

**Hoy:** HU-04 ya ofrece el Invoice (PDF) y los soportes al proveedor internacional. El formulario de alta es igual al nacional y los importes quedan en cero.

**Falta:**

- DT-06: captura de fecha, subtotal, impuestos, total y moneda;
- DT-07: duplicado por nombre de archivo;
- los estatus "Borrador" y "Cargada" de DT-01.

**Criterios clave:**

- Si el Invoice `INV-2026-001.pdf` ya está cargado en otra factura del mismo proveedor, la carga responde HTTP 409 y no se escribe ningún archivo.
- Una moneda que no está activa en el catálogo se rechaza con HTTP 400.
- Una factura internacional con Invoice, orden de compra y Vo.Bo. queda "Cargada".

**Decide la HU:**

- P-08;
- si la consistencia de los importes se valida en el formulario o sólo con FIN-002 al enviar;
- si los importes se pueden editar mientras la factura es editable.

**Capacidades:** modifica `flujo-facturas`, `motor-validacion` (regla de duplicado por nombre) e `integridad-datos`.

### HU-16 · Envío de factura por proveedor internacional

**Hoy:** una factura internacional no puede pasar la validación (B-06).

**Falta:** DT-08, el envío de DT-02 y que el proveedor y el PMO vean los resultados de las reglas INT.

**Criterios clave:**

- Un Invoice sin XML deja las reglas XML en `NOT_APPLICABLE`, y eso no bloquea el envío.
- Si el texto del Invoice no contiene la Razón Social de ULTRASIST, INT-002 resulta `WARNING` y la factura pasa a "Enviada".
- Un PDF escaneado sin texto deja las reglas INT en `NOT_EVALUATED` con el mensaje "No se pudo leer el texto del Invoice", y la factura se envía.

**Decide la HU:** P-06, P-07 y la lista final de reglas INT, una vez analizadas las muestras.

**Capacidades:** modifica `motor-validacion`. Puede crear una capacidad nueva `validacion-internacional`.

### HU-14 · Cancelación de factura

**Hoy:** no existe.

**Falta:**

- **Acción "Cancelar factura":** aparece en el detalle, para el proveedor, en los estatus que fije P-05. Su formulario pide el acuse (DT-10), que se valida por contenido como cualquier carga, y una confirmación.
- **Datos de la cancelación:** el estatus `CANCELLED` y las columnas `cancelled_at`, `cancelled_by` y `cancellation_deadline`. La fecha límite es `cancelled_at + 72 h`: se guarda en UTC y se muestra en la zona de negocio.
- **Correo:** `INVOICE_CANCELLED` a Recepción de Facturas, con las copias del evento (HU-08), después del commit (DT-09).
- **Auditoría:** `INVOICE_CANCELLED`, con el estatus anterior y el documento de acuse.
- **Efecto en el PMO:** una factura "Enviada" que se cancela sale de la bandeja del PMO (EP-02).

**Criterios clave:**

- Cancelar sin acuse responde HTTP 400 con "Cargue el Acuse de cancelación" y nada cambia.
- Una cancelación del 25/09/2026 a las 10:30 envía a Recepción el texto "antes del 28/09/2026 10:30".
- Si el correo falla, la factura queda "Cancelada", la bitácora registra `FAILED` y el proveedor ve el aviso.
- Cancelar una factura ya "Cancelada" responde HTTP 409. Cancelar la factura de otro proveedor responde HTTP 404.

**Decide la HU:** P-05, P-09, P-10 y P-11.

**Capacidades:** modifica `flujo-facturas`, `archivos-minimos-factura` (tipo del sistema) e `integridad-datos`. Puede crear una capacidad nueva `cancelacion-facturas`.

### HU-17 · Consulta de estatus de factura

**Hoy:**

- listado con alcance por proveedor, búsqueda, filtro por estatus y paginación;
- detalle con el último comentario (`invoices.comments`) y la matriz de validaciones;
- tablero con indicadores por estatus.

**Falta:**

- estatus, filtros e indicadores del tablero según DT-01;
- en el detalle, una sección "Seguimiento" con el historial de estatus y las observaciones del PMO de cada ronda, no sólo el último comentario;
- la causa destacada cuando la factura está "Rechazada" u "Observaciones";
- en "Observaciones", el acceso directo a corregir y reenviar;
- en "Cancelada", la fecha límite y el acuse.

Las observaciones que ve el proveedor deben ser las mismas que recibió por correo (tabla de dependencias de HU-05).

**Criterios clave:**

- El filtro "Observaciones" muestra sólo las facturas del proveedor en ese estatus.
- El detalle de una factura "Rechazada" muestra la causa capturada por el PMO, con el mismo texto que el correo.
- Un proveedor que pide una factura de otro proveedor recibe HTTP 404.
- El listado responde en 3 s o menos con 25 facturas por página (RNF de rendimiento, propuesto).

**Decide la HU:** si el proveedor ve el nombre del revisor (se propone mostrar sólo "PMO").

**Capacidades:** modifica `flujo-facturas`.

## 7. Preguntas abiertas para negocio

Ninguna bloquea el inicio de la épica. Cada una tiene un valor que se aplica mientras no haya respuesta.

| ID | Pregunta | Valor aplicado mientras tanto | HU | Impacto de la respuesta |
| --- | --- | --- | --- | --- |
| P-01 | ¿Se acepta el estatus "Borrador" para una factura registrada a la que le faltan archivos obligatorios? El ERS sólo define "Cargada" | Sí: "Borrador" antes de "Cargada" | HU-12, HU-15 | Si no se acepta, el registro debe exigir todos los obligatorios en un solo envío |
| P-02 | ¿También deben cambiar la contraseña en su primer acceso los usuarios internos a quienes el Administrador asigna una contraseña inicial? | Sí, con el mismo mecanismo | HU-10 | Sólo cambia qué altas activan la marca |
| P-03 | RN-HU13-01: ¿el "número de folio del XML" es el UUID (folio fiscal)? | Sí (DT-03), y el PoC ya lo garantiza | HU-13 | Si es Serie y Folio: extraerlos del XML y agregar una regla por RFC emisor |
| P-04 | ¿"Rechazada" es definitiva, de modo que el proveedor debe emitir un CFDI nuevo? | Sí. "Observaciones" es la vía para corregir la misma factura | HU-13, HU-17, EP-02 | Si no es definitiva, "Rechazada" debe admitir reenvío y la unicidad del UUID cambia |
| P-05 | ¿Desde qué estatus puede cancelar el proveedor? ¿También desde "Autorizada", con el pago en curso? | Desde cualquier estatus excepto "Cancelada": el SAT pedirá a ULTRASIST aceptar la cancelación en todos los casos | HU-14 | Cambia las transiciones a "Cancelada" y lo que ve el PMO |
| P-06 | ¿Qué expediente debe tener el proveedor internacional? (P-02 de HU-04) | SUP-003 y SUP-004 no aplican al internacional | HU-16 | Si se define, se agrega su lista y SUP-003 vuelve a aplicarle |
| P-07 | Con las tres muestras de invoices extranjeros: ¿qué datos deben verificarse y con qué severidad? ¿Se requiere extracción automática con IA? | INT-001 a INT-003 como advertencias sobre el texto del PDF | HU-16 | Puede agregar reglas o subir severidades. La IA sería una HU aparte |
| P-08 | El duplicado por nombre de archivo, ¿se busca dentro del mismo proveedor o en todo el portal? ¿Cuentan las facturas canceladas? | Mismo proveedor, sin contar las canceladas | HU-15 | Cambia la consulta de la regla |
| P-09 | ¿La cancelación es inmediata ("Cancelada", ERS §3.6) o una solicitud que Recepción revisa y autoriza (la minuta dice "para revisión y autorización")? | Inmediata. La aceptación ocurre ante el SAT, fuera del portal | HU-14 | Si es una solicitud: estatus "Cancelación solicitada", una acción para Recepción (rol nuevo o PMO) y otra plantilla de correo |
| P-10 | ¿Qué acuse entrega el proveedor internacional, que no cancela ante el SAT? | Cualquier PDF que documente la cancelación | HU-14 | Formatos o tipo de documento distintos por origen |
| P-11 | ¿"Recepción de Facturas" y "Facturas Electrónicas" (la minuta, en la cancelación) son la misma área y el mismo buzón? (Validación de HUs, §5) | Sí: el buzón Recepción de Facturas de HU-08 | HU-14 | Si no, HU-08 agrega un buzón nuevo |

## 8. Secuencia de entrega

**Ruta crítica del MVP:** HU-10 → HU-12/13 → HU-18/19 (EP-02) → HU-20 (EP-02) → HU-17.

Plan conjunto con EP-02. Cada ola puede corresponder a un sprint de dos semanas (minuta), según lo que resulte de la estimación.

| Ola | EP-01 | EP-02 | Condición de inicio |
| --- | --- | --- | --- |
| 1 | `primer-acceso-proveedor` (HU-10) y `registro-envio-factura-nacional` (HU-12, HU-13) | — | Ninguna. La dependencia de HU-12 sobre HU-10 es del recorrido del usuario, no del código, así que ambos changes pueden avanzar en paralelo |
| 2 | `factura-internacional` (HU-15, HU-16) | `bandeja-y-detalle-pmo` (HU-18, HU-19) | Archivado el change de HU-12/13 (DT-01 y DT-02). Las reglas INT se ajustan cuando lleguen las muestras (P-07) |
| 3 | `cancelacion-factura` (HU-14) | `cambio-estatus-factura` (HU-20) | Olas 1 y 2 archivadas |
| 4 | `seguimiento-estatus-proveedor` (HU-17) | — | HU-20 archivada |

## 9. Dependencias externas e integraciones pendientes

| Integración | Estado actual | Efecto en la épica | Mitigación |
| --- | --- | --- | --- |
| Servidor SMTP (HU-08) | En desarrollo se usa el transporte `file`. El README tiene la guía "Conectar el servidor SMTP" | El correo de cancelación (HU-14) no sale del portal hasta conectarlo | El envío se registra en la bitácora y las pruebas usan `MAIL_BACKEND=file`. Conectar el servidor antes del piloto |
| ClickCloud (RN-HU03-01) | Adaptador `NullSecretVault`: hoy no se resguarda nada | HU-10 no depende de ClickCloud: la contraseña temporal deja de servir al cambiarla | Cuando se integre, evaluar si se purga la contraseña temporal del gestor después del cambio |
| Muestras de invoices extranjeros (minuta; Octavio Rivera, 22-sep-2026) | No están en el repositorio | Sin ellas no se pueden calibrar las reglas INT (HU-16) | Entregar las reglas como advertencias no bloqueantes y ajustarlas con las muestras |

## 10. Riesgos y mitigaciones

- **La migración de estatus rompe los escenarios demo o las pruebas.** Mitigación: mapeo explícito en la revisión Alembic, auditoría `STATUS_MIGRATED`, `reset_demo` verificado y `test_demo_workflow.py` actualizado en el mismo change.
- **Las reglas nacionales bloquean al proveedor internacional.** Mitigación: HU-15 y HU-16 se entregan en el mismo change, de modo que no existe un registro internacional sin sus validaciones.
- **El envío tarda más porque ahora ejecuta el motor completo de forma síncrona.** Mitigación: medir el tiempo de respuesta con el analizador semántico real, no con el simulado. El RNF de 3 s aplica a las consultas, no al envío.
- **Un proveedor ve datos de otro,** por los contratos (B-03) o por los mensajes de duplicado. Mitigación: DT-03, DT-05 y pruebas en `test_aislamiento.py`.
- **Un correo falla sin que nadie lo note.** Mitigación: bitácora de envíos y aviso en pantalla (DT-09).
- **EP-02 necesita cambiar el modelo de estatus a mitad de camino.** Mitigación: el modelo se fija aquí (DT-01). EP-02 sólo agrega sus transiciones y resuelve los estatus de ClickBalance.

## 11. Criterios de aceptación de la épica

Recorrido de extremo a extremo que debe funcionar al cerrar la épica:

1. Un proveedor recién autorizado entra con su contraseña temporal, el portal lo obliga a cambiarla y no puede hacer nada más hasta cambiarla.
2. Un proveedor nacional registra una factura y carga sus obligatorios; la factura queda "Cargada".
3. Ese proveedor intenta enviar un XML cuyos datos no coinciden con las Reglas de Validación, o cuyo UUID ya existe: el envío no procede, se muestra el motivo y la factura sigue "Cargada". Con un XML correcto, la factura queda "Enviada".
4. Un proveedor internacional registra su Invoice con sus importes. Un Invoice con un nombre de archivo repetido se rechaza. Al enviar uno válido, las reglas INT aparecen como advertencias y la factura queda "Enviada".
5. Un proveedor cancela una factura cargando su acuse: la factura queda "Cancelada" y Recepción de Facturas recibe el correo con el número de factura, el proveedor y la fecha límite de +72 h.
6. Un proveedor ve el estatus de todas sus facturas y, en "Rechazada" u "Observaciones", la causa capturada por el PMO. Una factura en "Observaciones" se corrige y se reenvía.
7. Ningún proveedor puede ver facturas, contratos ni documentos de otro proveedor.

## 12. Definición de terminado de la épica

- [ ] Las siete HU tienen su documento en `docs/stories/new/`, y sus changes están archivados con las specs sincronizadas.
- [ ] Las preguntas P-01 a P-11 están respondidas por negocio o registradas como "Open Questions" en el `design.md` del change correspondiente.
- [ ] El recorrido de la sección 11 está automatizado en una prueba de flujo (como `test_demo_workflow.py`), con un proveedor nacional y uno internacional.
- [ ] `scripts/check.py` está en verde y la cobertura no baja de `--cov-fail-under=93`.
- [ ] `reset_demo` siembra facturas en los siete estatus, incluida una de un proveedor internacional.
- [ ] El README describe el flujo del proveedor y el modelo de estatus, y ya no lista la limitación de las facturas internacionales.
- [ ] Antes del piloto se prueba la cancelación con el servidor SMTP real.

## 13. Trazabilidad

| HU | RF | RN | Alcance del MVP (minuta del 21-sep-2026) | Validación de HUs |
| --- | --- | --- | --- | --- |
| HU-10 | RF-06 | — | Acceso de proveedores: "En el primer inicio de sesión, el proveedor deberá cambiar la contraseña antes de continuar" | Dentro del MVP |
| HU-12 | RF-07 | RN-HU12-01 | Rol Proveedor: "registrar, validar y dar seguimiento a las facturas"; "Proveedores nacionales: carga de PDF y XML; documentos soporte" | Dentro del MVP |
| HU-13 | RF-08 | RN-HU13-01, RN-HU13-02 | "control de duplicados mediante el identificador contenido en el XML"; "Validación nacional: comparar RFC, Razón Social, Dirección y Código Postal" | Dentro del MVP |
| HU-15 | RF-14 | — | "Proveedores extranjeros: carga de Invoice en PDF y documentos soporte; evitar duplicados inicialmente por nombre de archivo" | Nueva (cierre de cobertura) |
| HU-16 | RF-15 | — | "Validación extranjera: validar, en la medida de lo posible, la información del Invoice, incluyendo datos del proveedor, datos de ULTRASIST y dirección" | Nueva (cierre de cobertura) |
| HU-14 | RF-09 | — | "Cancelación: permitir solicitar la cancelación y enviar una notificación automática al área de Facturas Electrónicas para revisión y autorización" | Dentro del MVP |
| HU-17 | RF-16 | — | "El portal permitirá registrar, validar y dar seguimiento a las facturas" | Nueva (cierre de cobertura) |

**Otras referencias:**

- ERS v1.3: §2.3 (roles), §2.4 (restricciones), §3.4 (RNF), §3.6 (modelo de estados) y §4.2 (cobertura).
- HU-04: RD-08, P-02 y su tabla de dependencias.
- HU-05: tabla de dependencias hacia HU-14 y HU-17.
- HU-01: país e identificador fiscal del proveedor internacional.
- README: "Limitaciones y fuera de alcance".
- Specs: `flujo-facturas`, `motor-validacion`, `acceso-proveedores`, `autenticacion-sesiones`, `notificaciones-correo` y `plantillas-notificacion`.
