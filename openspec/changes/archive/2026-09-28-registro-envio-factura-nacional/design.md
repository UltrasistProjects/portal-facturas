## Context

El flujo de facturas del PoC tiene cuatro pasos: alta, carga documental, "Procesar y prevalidar" y "Enviar a revisión". EP-01 lo ajusta al ERS (§3.6) y a HU-12/HU-13.

Estado actual relevante:

- **Estatus:** `InvoiceStatus` tiene 11 valores. `ALLOWED_TRANSITIONS` (`app/core/constants.py`) y `transition_invoice` (`app/services/invoice_service.py`) los gobiernan; cada cambio audita `STATUS_CHANGED`. La columna es `VARCHAR` con el `CHECK` `invoicestatus` (`enum_column`).
- **Editables:** `EDITABLE_STATUSES = {DRAFT, REQUIRES_CORRECTION, VALIDATION_FAILED}`. `UPLOADED` y `VALIDATING` sólo existen dentro de `run_validation`, que recorre `DRAFT → UPLOADED → VALIDATING → PREVALIDATED | REQUIRES_CORRECTION` en una sola transacción. `VALIDATION_FAILED` nunca se asigna.
- **Envío:** `POST /invoices/{id}/submit` sólo transiciona `PREVALIDATED → UNDER_REVIEW`; no valida.
- **Checklist (HU-04):** `document_requirements_service.checklist` y `pending_required` calculan los obligatorios pendientes con la configuración vigente.
- **Duplicados:** `uuid_owner` detecta el UUID de otra factura en cualquier estatus y FIN-004 (`CRITICAL`) lo reporta con el mensaje "Posible factura duplicada por UUID" y el UUID propio como valor detectado. `uq_invoices_uuid` resuelve las carreras (409).
- **Alta:** cualquier rol puede registrar. `_new_invoice_page` manda todos los contratos activos y `app.js` los filtra por proveedor en el navegador.
- **Seed:** 10 facturas demo; `run_validation` y después asigna el estatus final del escenario.

## Goals / Non-Goals

**Goals:**
- Un modelo de estatus que EP-01 y EP-02 compartan sin volver a migrarlo.
- Que el estatus refleje los archivos obligatorios sin que el proveedor haga nada.
- Que ninguna factura llegue al PMO sin superar las validaciones vigentes al momento del envío.
- Cerrar la fuga de contratos (B-03) y la separación de funciones (B-04).

**Non-Goals:**
- Factura internacional (HU-15/16), cancelación (HU-14), decisión del PMO y ClickBalance (HU-20).
- Historial de estatus y observaciones por ronda (HU-17).
- Rediseñar el tablero: sólo se ajustan las etiquetas de sus indicadores.

## Decisions

### D1. Se conservan las claves y cambia la etiqueta
`InvoiceStatus` queda con `DRAFT`, `UPLOADED`, `UNDER_REVIEW`, `ACCEPTED`, `REJECTED`, `REQUIRES_CORRECTION`, `READY_FOR_CLICKBALANCE` y `UPLOADED_TO_CLICKBALANCE`. Etiquetas: Borrador, Cargada, Enviada, Autorizada, Rechazada, Observaciones; las de ClickBalance no cambian.

Transiciones:

| Desde | Hacia | Quién |
| --- | --- | --- |
| `DRAFT` | `UPLOADED` | Sistema, al completar los obligatorios (D2) |
| `UPLOADED` | `DRAFT` | Sistema, si falta un obligatorio (D2) |
| `UPLOADED`, `REQUIRES_CORRECTION` | `UNDER_REVIEW` | Proveedor, envío sin `FAIL` (D3) |
| `UNDER_REVIEW` | `ACCEPTED`, `REJECTED`, `REQUIRES_CORRECTION` | PMO (sin cambios) |
| `ACCEPTED` → `READY_FOR_CLICKBALANCE` → `UPLOADED_TO_CLICKBALANCE` | | Sin cambios (HU-20) |

`EDITABLE_STATUSES = {DRAFT, UPLOADED, REQUIRES_CORRECTION}`.

*Alternativa:* renombrar las claves (`SUBMITTED`, `AUTHORIZED`, `OBSERVATIONS`). Obliga a reescribir `invoices.status`, los `audit_logs` históricos, las decisiones de `reviews` y las pruebas, sin cambiar el comportamiento. HU-02 ya siguió este enfoque con `ACTIVE` → "Autorizado".

### D2. "Borrador" ⇄ "Cargada" se recalcula al cambiar los documentos
`invoice_service.sync_upload_status(db, invoice, complete, user_id)` recibe si el checklist está completo (`pending_required(checklist(...)) == 0`) y transiciona `DRAFT → UPLOADED` o `UPLOADED → DRAFT` cuando corresponde, con `STATUS_CHANGED`. Con cualquier otro estatus no hace nada: "Observaciones" se conserva mientras el proveedor corrige (S3 de la propuesta).

La invocan la carga de documentos, después del `flush` del documento nuevo, y el envío, antes de validar. El router calcula el checklist y le pasa el resultado; así `invoice_service` no depende de `document_requirements_service`, que ya importa `violates` de él.

Tras el `flush`, la colección `invoice.documents` no incluye el documento nuevo porque se creó por llave foránea: el router la expira (`db.expire(invoice, ["documents"])`) antes de calcular el checklist.

*Alternativa:* recalcular al leer. Mutar en un `GET` rompe el límite transaccional de la capa HTTP y no evita que el estatus guardado quede viejo. Si el Administrador cambia los archivos mínimos, el estatus guardado puede quedar desfasado hasta el siguiente cambio de documentos; el envío lo resincroniza (D3).

### D3. El envío valida y cambia el estatus en un paso
Nuevo `app/services/submission_service.py`, porque orquesta `invoice_service` y `validation_engine`, y `validation_engine` ya importa `invoice_service`:

1. Bloquea la fila de la factura (D5).
2. Si no es editable: 409 "La factura no puede enviarse en su estatus actual".
3. `sync_upload_status`. Si queda en `DRAFT`: 409 "Faltan archivos obligatorios. Cárguelos antes de enviar". Ya no se evalúa el motor: la carga documental muestra lo que falta.
4. `run_validation` con la configuración vigente.
5. Sin ningún `FAIL`: transición a `UNDER_REVIEW` (asigna `submitted_at`) y `INVOICE_SUBMITTED`.
6. Con algún `FAIL`: el estatus no cambia y los resultados quedan guardados.

El router confirma la transacción en ambos casos. Si el envío procedió, redirige (303) a `/invoices/{id}?notice=submitted`. Si no, responde **409 con el detalle de la factura**, que muestra "El envío no procedió" y la lista de reglas en `FAIL` con el valor esperado y el detectado. Es el patrón del portal: los errores se muestran en la misma página con 4xx y los éxitos redirigen. Volver a cargar la página repite el envío, que es idempotente.

Bloquea cualquier `FAIL` (`CRITICAL` o `ERROR`); `WARNING` no (S2 de la propuesta). Una carrera sobre `uq_invoices_uuid` sigue respondiendo 409 "El CFDI ya esta registrado en otra factura" sin persistir nada.

*Alternativa:* redirigir también cuando no procede (`?submit=blocked`). Un 303 esconde el fallo a quien no sea un navegador y a las pruebas.

### D4. "Verificar" y `run_validation` sin transiciones
`run_validation` guarda resultados, score, UUID, fecha e importes del XML, audita `VALIDATION_STARTED` y `VALIDATION_COMPLETED`, y ya no cambia el estatus. El evento `validation.completed` cambia `status` por `failures` (número de `FAIL`); conserva `duration_ms`, `score` y `blockers`.

`POST /invoices/{id}/validation` pasa a ser "Verificar": exige un estatus editable, ejecuta `run_validation` y redirige al detalle. Se conserva porque permite corregir antes de enviar y no cuesta nada: es el mismo motor.

### D5. Bloqueo de la fila de la factura
La carga de documentos, "Verificar" y el envío leen la factura con `SELECT ... FOR UPDATE` antes de comprobar su estatus. Sin esto, una carga concurrente con el envío podría dejar un documento sin validar en una factura "Enviada", y dos envíos simultáneos auditarían dos veces `INVOICE_SUBMITTED`. El bloqueo dura lo que la petición; el motor es local.

### D6. Acciones exclusivas del proveedor
`require_roles(Role.PROVIDER)` en `GET`/`POST /invoices/new`, `GET`/`POST /invoices/{id}/documents`, `POST /invoices/{id}/validation` y `POST /invoices/{id}/submit`. `INTERNAL` y `ADMIN` reciben 403 y conservan el listado, el detalle y las descargas. Las plantillas sólo muestran "Nueva factura", "Gestionar documentos", "Verificar" y "Enviar a validación" al proveedor.

Como `require_roles` se apoya en `get_current_user`, un proveedor con la contraseña temporal sigue yendo al cambio de contraseña (HU-10).

### D7. El alta toma el proveedor del usuario
El formulario ya no tiene selector de proveedor: muestra la razón social del proveedor del usuario y `POST /invoices/new` ignora cualquier `supplier_id` recibido. `_new_invoice_page` consulta sólo `Contract.supplier_id == user.supplier_id` y `status == ACTIVE`. `app.js` deja de filtrar contratos y sólo copia proyecto y líder del contrato elegido.

Verificaciones del alta, en este orden:

1. El proveedor debe estar `ACTIVE`: 409 "Su proveedor no está autorizado para registrar facturas", también en el `GET`.
2. Los datos del formulario (`InvoiceCreate`): 400.
3. El contrato debe ser del proveedor: 400 "Contrato no corresponde al proveedor". Debe estar activo: 400 "El contrato no está activo".

Sin contratos activos, el formulario lo dice y no ofrece el botón de continuar.

### D8. Migración `0010_invoice_status_model`
1. Calcula en SQL si cada factura tiene completos sus obligatorios con la configuración vigente: tipos activos cuyo nivel para el origen del proveedor es `REQUIRED`, contra sus documentos `is_current`. Es la misma regla que `checklist`.
2. Para cada factura en `DRAFT`, `UPLOADED`, `VALIDATING`, `VALIDATION_FAILED`, `PREVALIDATED` o `REQUIRES_CORRECTION`:
   - si su última revisión con decisión (distinta de `COMMENT`) es `REQUIRES_CORRECTION`, el PMO la devolvió y aún no se reenvía: queda en `REQUIRES_CORRECTION`;
   - en otro caso, `UPLOADED` si tiene completos los obligatorios y `DRAFT` si no.
3. Cada factura cuyo estatus cambia recibe un registro `STATUS_MIGRATED` (entidad `Invoice`, sin usuario) con el estatus anterior y el nuevo.
4. Reconstruye el `CHECK` `invoicestatus` con los 8 valores vigentes.

El downgrade restaura el `CHECK` de 11 valores. Los estatus migrados no se revierten: todos son válidos en la versión anterior.

*Alternativa:* mapear `PREVALIDATED` a `UNDER_REVIEW`. Enviaría al PMO facturas que el proveedor nunca envió.

### D9. Seed demo
`run_validation` ya no cambia el estatus, así que el seed sigue asignando el estatus final después de validar. Los escenarios quedan:

| Factura | Antes | Ahora |
| --- | --- | --- |
| BORRADOR-001 | Borrador | Borrador |
| A-CORRECTA, E-SEMANTICO | Prevalidada | Cargada, lista para enviar |
| B-EXCEDE | Requiere corrección | Cargada; el envío no procede por FIN-001 |
| D-SIN-VOBO | Requiere corrección | Borrador; falta el Vo.Bo. |
| REVISION-001 | En revisión | Enviada |
| ACEPTADA-001 | Aceptada | Autorizada |
| C-RFC-ERROR | Rechazada | Rechazada |
| CLICK-READY, CLICK-DONE | Sin cambio | Sin cambio |

Las facturas enviadas o posteriores reciben `submitted_at`. Una factura demo en "Observaciones" llega con HU-17, que la necesita para su seguimiento.

### D10. Interfaz
- **Detalle:** "Gestionar documentos" y "Verificar" en los estatus editables; "Enviar a validación" en "Cargada" y "Observaciones", sólo para el proveedor. Con resultados en `FAIL` y un estatus editable, un panel "Reglas que impiden el envío" lista código, mensaje, esperado y detectado. Tras un envío exitoso, el aviso "Factura enviada a validación".
- **Carga documental:** pasos "Información · Documentos · Envío"; con los obligatorios completos, "Factura cargada. Ya puede enviarla a validación" y los botones "Verificar" y "Enviar a validación".
- **Tablero y listado:** las etiquetas nuevas vienen de `STATUS_LABELS`; los indicadores dicen "Enviadas", "Observaciones" y "Autorizadas", y el de `PREVALIDATED` desaparece.
- **Estilos:** `app.css` agrega las clases de `status-draft` y `status-uploaded` si faltan, y retira las de los estatus eliminados.

## Risks / Trade-offs

- **[La migración cambia el estatus de facturas existentes]** → Mapeo explícito, auditoría `STATUS_MIGRATED` por factura y pruebas de migración con cada caso.
- **[Estatus desfasado si cambian los archivos mínimos]** → El envío resincroniza antes de validar y responde con lo que falta; la carga documental siempre muestra el checklist vigente.
- **[`0010` depende de `0009_supplier_profile`, aún sin confirmar]** → Si `0009` no se integra antes, ajustar `down_revision` a `0008_password_change_required`. `test_migraciones` detecta una cabeza doble.
- **[Enlaces guardados con `?status=PREVALIDATED`]** → El listado ya trata un estatus desconocido como filtro vacío; no hay error.
- **[El envío tarda lo que tarda el motor, con la fila bloqueada]** → Hoy el motor es local y el análisis semántico, simulado. Medir con el analizador real antes del piloto (riesgo de EP-01).
- **[`INTERNAL` y `ADMIN` pierden el alta]** → Separación de funciones (DT-04). Si negocio necesita capturar a nombre de un proveedor, es una HU aparte.

## Migration Plan

1. `alembic upgrade head` aplica `0010`. Es idempotente sobre datos ya migrados: los estatus retirados dejan de existir.
2. `reset_demo` siembra el modelo nuevo.
3. Rollback: `alembic downgrade 0009_supplier_profile` restaura el `CHECK`; el código anterior acepta los estatus migrados, aunque ya no volverán a `PREVALIDATED` hasta la siguiente prevalidación.

## Open Questions

- P-01, P-03 y P-04 de EP-01 siguen abiertas con negocio; este change aplica sus valores por defecto (S1).
- ¿El PMO debe ver los resultados de "Verificar" de una factura que aún no se envía? Hoy el detalle los muestra a quien puede ver la factura. HU-18/19 lo decide.
