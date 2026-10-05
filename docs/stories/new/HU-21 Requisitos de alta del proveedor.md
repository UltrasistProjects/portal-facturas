# HU-21 · Requisitos de alta del proveedor

| Campo | Valor |
| --- | --- |
| ID | HU-21 |
| Rol | Administrador |
| Módulo | A. Administración y Configuración |
| Prioridad | Por confirmar con negocio. Condiciona la autorización de proveedores (HU-02) |
| Origen | Solicitud de negocio del 2026-10-02 (nueva). No está en el documento de HUs ni en la ERS v1.4 |
| Requisito funcional | Nuevo; se propone como RF-19 en la siguiente versión de la ERS. Modifica RF-02 (HU-02) |
| Regla de negocio | RN-HU21-01 a RN-HU21-03, de la solicitud (sección 5.1). Reglas derivadas RD-01 a RD-11 (sección 5.2) |
| Change OpenSpec sugerido | `requisitos-alta-proveedor` |
| Capacidad nueva | `requisitos-alta-proveedor` |
| Capacidades modificadas | `acceso-proveedores`, `motor-validacion`, `integridad-datos`, `observabilidad` |
| Estado | Lista para `/opsx:propose`. Las preguntas abiertas (sección 5.3) sólo cambian valores iniciales que el Administrador ajusta desde la pantalla; no cambian la estructura |
| Estimación | Por definir en el refinamiento |
| Versión / fecha | 1.0 · 2026-10-02 · Equipo Técnico |

## Cómo usar este documento con OpenSpec

Ejecutar `/opsx:propose requisitos-alta-proveedor` con este documento como entrada. Cada sección alimenta un artefacto:

| Artefacto OpenSpec | Secciones de esta HU |
| --- | --- |
| `proposal.md` — Why | 1, 2 |
| `proposal.md` — What Changes | 3, 6 |
| `proposal.md` — Capabilities | Tabla de metadatos, 8, 9 |
| `proposal.md` — Impact | 11 |
| `specs/requisitos-alta-proveedor/spec.md` | 8 (se copia tal cual bajo `## ADDED Requirements`) |
| `specs/acceso-proveedores/spec.md`, `specs/motor-validacion/spec.md`, `specs/integridad-datos/spec.md`, `specs/observabilidad/spec.md` | 9 (bloques listos para copiar) |
| `design.md` | 4, 5, 10 (las preguntas de 5.3 van a "Open Questions") |
| `tasks.md` | 11, 13 |

---

## 1. Historia de usuario

**Texto de la solicitud (2026-10-02, ortografía normalizada):**

> Para el alta del proveedor, se tiene que parametrizar en la sección configuración qué documentos mínimos se necesitan para dar de alta el proveedor, en este caso: Acta Constitutiva, Poderes, Cédula Fiscal, Identificación Representante Legal, Domicilio Representante Legal, Comprobante de domicilio, Estado de Cuenta Bancario. Con la parametrización de los requisitos para dar de alta proveedor, ahora sí, al momento de dar de alta el proveedor y querer activarlo me debe pedir estos requisitos, los cuales se marquen como obligatorios, y que algunos pueden ser opcionales.

**Redacción como HU:**

> Yo como administrador requiero parametrizar en la sección de configuración los documentos mínimos para dar de alta a un proveedor, marcando cada uno como obligatorio u opcional, para que el sistema me los pida al dar de alta al proveedor y no me permita activarlo mientras falte alguno obligatorio.

**Reformulación:**

- **Como** Administrador del portal,
- **quiero** definir en la configuración qué documentos son requisito de alta de un proveedor, y si cada uno es Obligatorio, Opcional o No aplica según el tipo de proveedor,
- **para** que el expediente de cada proveedor me pida esos documentos y el sistema no lo autorice (no le dé acceso al portal) mientras le falte alguno obligatorio.

**Términos de la solicitud y su equivalente en el sistema:**

| Término de la solicitud | En el sistema |
| --- | --- |
| Dar de alta el proveedor | Alta individual (`POST /suppliers`) o carga masiva (HU-01). El proveedor queda "Registrado" (`REGISTERED`), sin acceso al portal |
| Activarlo | Autorizarlo (HU-02): pasa de "Registrado" a "Autorizado" (`ACTIVE`), recibe su usuario y contraseña temporal (HU-03) y puede facturar (SUP-001). No se crea un estatus nuevo |
| Requisitos / documentos mínimos para dar de alta | Expediente del proveedor (Anexo A de los Lineamientos), que hoy está fijo en código (`SUPPLIER_REQUIREMENTS`) |
| Sección configuración | Menú **Administración** del Administrador, junto a "Archivos mínimos" (HU-04) |

## 2. Contexto y motivación

Los Lineamientos de facturación 2024 v1.4.1 condicionan el alta del Asociado a su expediente. En 1.i dicen: "debe estar dado de alta en el catálogo de Asociados con el cumplimiento al 100% de los requisitos detallados en el 'Anexo A'". El Anexo A ("De los requisitos para elaborar contrato") lista documentos distintos para personas morales y para personas físicas.

Hoy el PoC no cumple esa condición:

- **El expediente está fijo en código.** `SUPPLIER_REQUIREMENTS` en `app/core/constants.py` lista 11 documentos para persona moral y 8 para persona física. Para cambiar un requisito hay que desplegar. "Poderes" no existe.
- **La autorización no revisa el expediente.** `supplier_access_service.authorize()` pasa a "Autorizado" a cualquier proveedor "Registrado", aunque su expediente esté vacío. El proveedor recibe credenciales y entra al portal.
- **El expediente sólo se revisa al facturar.** La regla SUP-003 ("Expediente del proveedor incompleto") se evalúa al validar cada factura. Para entonces el proveedor ya tiene acceso: el control llega tarde.

HU-04 dejó fuera de su alcance el expediente del proveedor (su RD-02: "requisito para contratar, no archivo de la factura"). Esta HU cubre ese hueco y reutiliza el patrón que HU-04 estableció para configurar documentos: catálogo persistente, pantalla de administración, huella de concurrencia y auditoría.

**Archivos de la factura frente a requisitos de alta.** Son conceptos distintos y cada uno tiene su configuración:

| Concepto | Qué es | Cuándo se entrega | Configuración | Qué bloquea |
| --- | --- | --- | --- | --- |
| Archivos mínimos de la factura (HU-04) | XML, PDF o Invoice, orden de compra, Vo.Bo., soportes | Con **cada** factura | Administración › Archivos mínimos, por origen | El envío de la factura |
| Requisitos de alta (esta HU) | Acta constitutiva, poderes, cédula fiscal, identificaciones, comprobantes de domicilio, estado de cuenta | **Una vez**, antes de autorizar al proveedor | Administración › Requisitos de alta, por tipo de proveedor | La autorización del proveedor y, con SUP-003, el envío de sus facturas |

## 3. Alcance

### Dentro del alcance

- Catálogo persistente de requisitos de alta, con nombre en español, descripción y un nivel por tipo de proveedor: persona moral, persona física e internacional. Incluye los 12 documentos actuales del expediente y el nuevo "Poderes".
- Pantalla **Administración › Requisitos de alta** para fijar el nivel de cada requisito: Obligatorio, Opcional o No aplica.
- Alta, edición, desactivación y reactivación de requisitos definidos por el Administrador.
- Panel **Requisitos de alta** en el expediente del proveedor: checklist de obligatorios y opcionales, pendientes y cargados, y aviso "Faltan N requisitos obligatorios". La carga de documentos ofrece sólo los requisitos que aplican al proveedor.
- Autorización condicionada: un proveedor "Registrado" con requisitos obligatorios pendientes no se autoriza, ni en la autorización masiva ni desde su expediente.
- Botón **Autorizar proveedor** en el expediente, que usa la misma operación y las mismas reglas que la autorización masiva.
- Columna "Requisitos de alta" en el listado de proveedores ("Completos" o "Faltan N").
- SUP-003 evaluada con la misma configuración: una sola definición del expediente mínimo.
- Auditoría de la configuración y protección contra ediciones concurrentes.
- Migración con valores iniciales tomados de la solicitud (sección 6.3).

### Fuera del alcance

| Tema | Motivo / dónde se atiende |
| --- | --- |
| Adjuntar documentos en el formulario de alta o en la plantilla de Excel | La carga masiva no transporta archivos (HU-01) y el alta individual crea al proveedor antes de poder asociarle documentos. Se cargan en el expediente después del alta (RD-06) |
| Revisar el contenido de cada documento (que el PDF sea de verdad un acta constitutiva) | Lo revisa el Administrador antes de autorizar. El sistema sólo verifica que el documento esté cargado |
| Formatos por requisito (el Anexo A pide "archivos escaneados, con formato PDF") | Se conserva la validación global de `almacenamiento-documentos`. Si negocio lo pide, se agrega como en HU-04 |
| Exigencias condicionales, como el poder notarial "sólo en caso de que el apoderado no tenga facultades en el Acta Constitutiva" | Un requisito es Obligatorio u Opcional para todos los proveedores de su tipo (RD-04). La única condición que se conserva es la de la propuesta económica, que ya existe |
| Vigencia configurable por requisito, o que un documento vencido bloquee la autorización | La regla de tres meses (SUP-004) no cambia y no bloquea la autorización (RD-07, P-05) |
| Desautorizar a un proveedor ya autorizado cuando cambia la configuración | Ningún proceso cambia el estatus "Autorizado" (RD-08). SUP-003 detecta el expediente incompleto al facturar |
| Estatus "Inactivo" y reactivación de proveedores | No existe esa transición hoy. Sin cambios |
| Avisar por correo al proveedor de sus requisitos pendientes | No lo pide la solicitud. Posible HU futura |
| Archivos mínimos de la factura | HU-04. Sin cambios |

## 4. Situación actual del PoC

| Aspecto | Hoy | Brecha para HU-21 |
| --- | --- | --- |
| Documentos del expediente | `SUPPLIER_REQUIREMENTS` por tipo de persona (11 para moral, 8 para física) y nombres en `SUPPLIER_DOCUMENT_LABELS`, en `app/core/constants.py` | Fijos en código. No existe "Poderes" |
| Obligatoriedad | `_requirement()` en `app/services/supplier_service.py`. Son opcionales fijos el contrato, la debida diligencia y la ubicación (`OPTIONAL_SUPPLIER_DOCUMENTS`). La propuesta económica es obligatoria si el alta es por cotización (`economic_proposal`). Los dos comprobantes de domicilio son alternativos (`ALTERNATIVE_SUPPLIER_DOCUMENTS`) | No es configurable. La equivalencia de domicilios contradice la solicitud, que pide los dos |
| Proveedor internacional | El expediente le muestra la lista de su tipo de persona. SUP-003 y SUP-004 resultan `NOT_APPLICABLE` ("No aplica a proveedores internacionales") | No tiene expediente propio: P-02 de HU-04 y P-06 de EP-01 siguen abiertas |
| Carga de documentos | `POST /suppliers/{supplier_id}/documents`, para el Administrador o el propio Proveedor. Valida el tipo contra la lista de su tipo de persona ("Tipo de Anexo A invalido"). Reemplaza con `is_current` y `replaced_document_id` | El tipo se validará contra el catálogo. El reemplazo no cambia |
| Panel del expediente | "Expediente Anexo A" en `suppliers/detail.html`, con un asterisco en los obligatorios | No dice cuántos faltan ni si el proveedor puede autorizarse |
| Autorización | `authorize()` omite a quien no está "Registrado", a quien tiene el correo en uso y a quien falla en Keycloak | No revisa el expediente |
| Autorización individual | El expediente de un proveedor "Registrado" dice "Autorícelo desde el listado de proveedores" | El Administrador sale del expediente que acaba de completar para autorizar |
| SUP-003 | Se evalúa en cada validación con `supplier_requirement_status()`. Un `FAIL` (`ERROR`) impide enviar la factura (HU-13) | Leerá la configuración |
| Datos demo (`scripts/seed_db.py`) | Carga todos los documentos de `SUPPLIER_REQUIREMENTS` a los dos proveedores demo | Debe cargar también "Poderes" para que sus facturas conserven el resultado |
| Patrón de configuración | HU-04: tabla `invoice_document_types`, enumeración `DocumentRequirement`, `/admin/required-documents`, `config_version`, auditoría | Se reutiliza tal cual |

## 5. Reglas de negocio

### 5.1 De la solicitud

| ID | Regla | Fuente |
| --- | --- | --- |
| RN-HU21-01 | Los documentos requeridos para dar de alta a un proveedor se parametrizan en la configuración del sistema, cada uno como obligatorio u opcional | Solicitud: "se tiene que parametrizar en la sección configuración"; "los cuales se marquen como obligatorios, y que algunos pueden ser opcionales" |
| RN-HU21-02 | Un proveedor sólo puede activarse (pasar a "Autorizado") con todos sus requisitos de alta obligatorios cargados | Solicitud: "al momento de dar de alta el proveedor y querer activarlo me debe pedir estos requisitos". Lineamientos 1.i: "cumplimiento al 100% de los requisitos detallados en el 'Anexo A'" |
| RN-HU21-03 | Los requisitos obligatorios iniciales son Acta constitutiva, Poderes, Cédula fiscal, Identificación del representante legal, Comprobante de domicilio del representante legal, Comprobante de domicilio y Estado de cuenta bancario | Solicitud: "en este caso: …" |

### 5.2 Derivadas

Fundamentadas en las fuentes del proyecto; ninguna está confirmada todavía por negocio:

| ID | Regla | Fundamento |
| --- | --- | --- |
| RD-01 | El nivel de cada requisito se define por tipo de proveedor: persona moral nacional, persona física nacional e internacional. El internacional es un tipo propio, sin importar su tipo de persona | El Anexo A distingue morales y físicas. Una persona física no tiene acta constitutiva. Los documentos de la solicitud son mexicanos (cédula fiscal), y el expediente del internacional sigue sin definirse (P-06) |
| RD-02 | Hay tres niveles: Obligatorio, Opcional y No aplica, los mismos de HU-04 (sección 6.2) | Solicitud: "obligatorios" y "opcionales". "No aplica" hace falta para que un documento de persona moral no se pida a una persona física |
| RD-03 | Valores iniciales (sección 6.3). Persona moral: los siete documentos de la solicitud son obligatorios. Persona física: sus equivalentes (identificación oficial, cédula fiscal, comprobante de domicilio y estado de cuenta). Internacional: ningún requisito, como hoy | RN-HU21-03. Anexo A para personas físicas. SUP-003 hoy no aplica al internacional |
| RD-04 | No hay exigencias condicionales configurables: un requisito es obligatorio u opcional para todos los proveedores de su tipo. Se conserva la regla existente de la propuesta económica: es exigible si el alta es por cotización o licitación (`economic_proposal`) y su nivel no es "No aplica" | La solicitud sólo distingue obligatorio y opcional. La propuesta económica condicionada ya existe y quitarla sería una regresión |
| RD-05 | Cada requisito se evalúa por sí mismo. Desaparece la equivalencia entre el comprobante de domicilio del proveedor y el del representante legal | La solicitud pide ambos como requisitos distintos. Si negocio acepta cualquiera de los dos, deja uno como Opcional (P-04) |
| RD-06 | Los requisitos se exigen al autorizar, no al dar de alta. El alta (individual o masiva) crea al proveedor "Registrado" sin documentos; el expediente se los pide y la autorización los verifica | La carga masiva no transporta archivos (HU-01). Solicitud: "al momento de dar de alta el proveedor y querer activarlo" |
| RD-07 | Un requisito se cumple con un documento vigente (`is_current`) de su tipo en el expediente del proveedor (`invoice_id` nulo). La antigüedad del documento (SUP-004, más de tres meses) se muestra como advertencia y no bloquea la autorización | SUP-004 es una advertencia (`WARNING`). El Anexo A marca algunos documentos como "no mayor a 3 meses" (P-05) |
| RD-08 | La configuración no cambia el estatus de nadie. Un proveedor "Autorizado" sigue autorizado aunque después se agregue un requisito obligatorio. Su checklist y SUP-003 se evalúan con la configuración vigente | Sólo la autorización (HU-02) cambia el estatus. Mismo criterio que la RD-08 de HU-04 |
| RD-09 | SUP-003 usa la misma configuración que la autorización. Para un proveedor internacional, SUP-003 se evalúa sólo si algún requisito es obligatorio para internacionales; si no, resulta `NOT_APPLICABLE` como hoy. SUP-004 no cambia | Dos definiciones del expediente mínimo, una en código y otra en configuración, se contradirían en el mismo expediente |
| RD-10 | Los requisitos del sistema no se editan ni se desactivan; sólo cambian sus niveles. Los del Administrador se desactivan, nunca se borran. Los documentos cargados conservan su tipo y siguen visibles y descargables aunque su requisito deje de aplicar | Mismo criterio que la RD-10 de HU-04. Spec `integridad-datos`: "Prohibición de borrado físico de evidencia fiscal" |
| RD-11 | Antes de la autorización, el Administrador carga los documentos. Después, el Proveedor puede cargar o reemplazar los suyos. El PMO sólo consulta | Permisos actuales de `POST /suppliers/{supplier_id}/documents`. Sin cambio |

### 5.3 Preguntas abiertas para negocio

Ninguna bloquea `/opsx:propose`. P-01 a P-06 sólo cambian valores que el Administrador ajusta desde la pantalla. P-07 decide un riesgo de despliegue.

| ID | Pregunta | Valor aplicado mientras tanto | Impacto de la respuesta |
| --- | --- | --- | --- |
| P-01 | La Opinión de cumplimiento del SAT es requisito del Anexo A y hoy cuenta para SUP-003, pero no está en la lista de la solicitud. ¿Es obligatoria? | Opcional, según la solicitud | Se cambia en la pantalla o en la siembra de la migración |
| P-02 | ¿Qué requisitos son obligatorios para la persona física? | Identificación oficial, Cédula fiscal, Comprobante de domicilio y Estado de cuenta bancario (RD-03) | Se ajusta en la pantalla |
| P-03 | Los Lineamientos piden el Poder notarial "sólo en caso de que el apoderado no tenga facultades en el Acta Constitutiva". ¿"Poderes" es obligatorio siempre? | Obligatorio, según la solicitud. Si el acta ya da las facultades, el Administrador carga el acta también como "Poderes" o negocio lo deja Opcional | Una exigencia condicional requiere una HU nueva (RD-04) |
| P-04 | ¿Se exigen los dos comprobantes de domicilio, o basta cualquiera? | Los dos, según la solicitud (RD-05) | Si basta uno, el del representante legal pasa a Opcional |
| P-05 | ¿Un documento con más de tres meses debe impedir la autorización? | No; se muestra la advertencia (RD-07) | Bloquear por vigencia requiere guardar qué requisitos tienen vigencia; hoy es una lista fija en código |
| P-06 | ¿Qué requisitos de alta tiene el proveedor internacional? (P-02 de HU-04, P-06 de EP-01) | Ninguno: se autoriza como hoy | El Administrador los define en la columna Internacional, sin cambios de código, y SUP-003 empieza a aplicarle (RD-09) |
| P-07 | Los proveedores ya autorizados no tienen "Poderes", que es nuevo. ¿Sus facturas deben bloquearse por SUP-003 hasta que lo carguen? | Sí: SUP-003 conserva su severidad `ERROR`. El listado los marca con "Faltan N" | Si no deben bloquearse, se despliega con "Poderes" en Opcional y se endurece cuando los proveedores lo carguen |

## 6. Catálogo de requisitos y configuración inicial

### 6.1 Tipos de proveedor

| Columna de la configuración | Proveedores a los que aplica |
| --- | --- |
| Persona moral | `origin = NATIONAL` y `supplier_type = PERSONA_MORAL` |
| Persona física | `origin = NATIONAL` y `supplier_type = PERSONA_FISICA` |
| Internacional | `origin = INTERNATIONAL`, con cualquier tipo de persona |

### 6.2 Niveles

Se reutiliza la enumeración `DocumentRequirement` de HU-04.

| Nivel | Valor | En el expediente | Al autorizar | En SUP-003 |
| --- | --- | --- | --- | --- |
| Obligatorio | `REQUIRED` | Se pide y el checklist lo marca "Obligatorio" | Si falta, el proveedor no se autoriza | Si falta, `FAIL` |
| Opcional | `OPTIONAL` | Se ofrece y el checklist lo marca "Opcional" | No se exige | No se exige |
| No aplica | `NOT_APPLICABLE` | No se ofrece; si se envía, se rechaza | No se exige | No se exige |

### 6.3 Requisitos del sistema y valores iniciales

La clave es el valor que ya guarda `documents.document_type`, así que los documentos existentes no cambian. **Negritas**: los siete documentos de la solicitud.

| Solicitud | Clave | Nombre | Descripción (ayuda en el expediente) | Persona moral | Persona física | Internacional |
| --- | --- | --- | --- | --- | --- | --- |
| Acta Constitutiva | `INCORPORATION_ACT` | **Acta constitutiva** | Acta constitutiva con cédula del Registro Público de la Propiedad y del Comercio | Obligatorio | No aplica | No aplica |
| Poderes | `POWER_OF_ATTORNEY` (nuevo) | **Poderes** | Poder notarial del representante legal | Obligatorio | No aplica | No aplica |
| Cédula Fiscal | `TAX_STATUS` | **Cédula fiscal** | Constancia de situación fiscal emitida por el SAT | Obligatorio | Obligatorio | No aplica |
| Identificación Representante Legal | `LEGAL_REP_ID` | **Identificación del representante legal** | Identificación oficial (INE o pasaporte) del apoderado legal | Obligatorio | No aplica | No aplica |
| Domicilio Representante Legal | `LEGAL_REP_ADDRESS_PROOF` | **Comprobante de domicilio del representante legal** | Recibo de teléfono, luz o agua a nombre del representante legal | Obligatorio | No aplica | No aplica |
| Comprobante de domicilio | `ADDRESS_PROOF` | **Comprobante de domicilio** | Recibo de teléfono, luz o agua del domicilio del proveedor | Obligatorio | Obligatorio | No aplica |
| Estado de Cuenta Bancario | `BANK_STATEMENT` | **Estado de cuenta bancario** | Carátula del último estado de cuenta con la CLABE | Obligatorio | Obligatorio | No aplica |
| — | `OFFICIAL_ID` | Identificación oficial | Identificación oficial (INE o pasaporte) de la persona física | No aplica | Obligatorio | No aplica |
| — | `SAT_OPINION` | Opinión de cumplimiento | Opinión de cumplimiento de obligaciones fiscales del SAT | Opcional (P-01) | Opcional (P-01) | No aplica |
| — | `ECONOMIC_PROPOSAL` | Propuesta económica | Propuesta económica autorizada por el líder de ULTRASIST | Opcional ¹ | Opcional ¹ | No aplica |
| — | `DUE_DILIGENCE` | Debida diligencia | Formato de debida diligencia requisitado | Opcional | No aplica | No aplica |
| — | `LOCATION` | Ubicación | Liga de Google Maps o coordenadas geográficas | Opcional | Opcional | No aplica |
| — | `SUPPLIER_CONTRACT` | Contrato | Contrato firmado con ULTRASIST | Opcional | Opcional | No aplica |

¹ Exigible cuando el alta es por cotización o licitación (RD-04).

Los niveles "No aplica" de persona moral y persona física reproducen las listas actuales de `SUPPLIER_REQUIREMENTS`: un documento que hoy no se pide a un tipo de persona sigue sin pedírsele.

**Cambios frente a hoy para un proveedor nacional:** "Poderes" es nuevo y obligatorio para la persona moral; la Opinión de cumplimiento pasa de obligatoria a opcional (P-01); los dos comprobantes de domicilio dejan de ser alternativos (RD-05).

### 6.4 Requisitos definidos por el Administrador

- **Campos:** nombre (3 a 80 caracteres, único sin distinguir mayúsculas), descripción opcional (hasta 300 caracteres) y un nivel por tipo de proveedor. Los niveles aparecen preseleccionados en "No aplica", así que crear un requisito no cambia nada hasta que el Administrador lo decida.
- **Clave:** la genera el sistema con el formato `REQUISITO_<id>` (por ejemplo, `REQUISITO_14`) y no cambia.
- **Edición:** nombre y descripción. Los niveles se cambian desde la configuración.
- **Desactivación:** el requisito deja de pedirse y de exigirse y pasa a la sección "Requisitos inactivos". Conserva sus niveles para cuando se reactive.
- **Ejemplo de uso:** la "Declaración de ISR por retenciones de salarios" del Anexo A, que el PoC no tiene, se agrega sin cambios de código.

### 6.5 Reglas SUP

| Código | Qué evalúa | Severidad | Cambio |
| --- | --- | --- | --- |
| SUP-001 | Proveedor "Autorizado" | `CRITICAL` | Sin cambios |
| SUP-002 | Contrato vigente | `CRITICAL` | Sin cambios |
| SUP-003 | Requisitos de alta exigibles con documento vigente | `ERROR` | Lee la configuración. El mensaje de `FAIL` nombra los pendientes. Para el internacional se evalúa si tiene algún requisito obligatorio (RD-09) |
| SUP-004 | Vigencia de los documentos con fecha (tres meses) | `WARNING` | Sin cambios |

## 7. Flujo de uso

**Administrador: configuración**

1. Entra a **Administración › Requisitos de alta** (`GET /admin/supplier-requirements`).
2. Ve una fila por requisito activo, con su descripción y un selector de nivel para Persona moral, Persona física e Internacional.
3. Cambia los niveles y pulsa **Guardar configuración** (`POST /admin/supplier-requirements`). El sistema valida, guarda los cambios en una transacción, audita y muestra "Configuración guardada", o "Sin cambios" si no cambió nada.
4. Para un documento que no está en el catálogo, usa **Nuevo requisito** (`POST /admin/supplier-requirements/types`). Edita un requisito propio (`POST /admin/supplier-requirements/types/{type_id}`) o lo desactiva y reactiva (`POST /admin/supplier-requirements/types/{type_id}/status`).

**Administrador: alta y activación de un proveedor**

5. Da de alta al proveedor con el formulario o con la carga masiva. Queda "Registrado". El alta individual lo lleva a su expediente.
6. El panel **Requisitos de alta** del expediente muestra primero los obligatorios, cada uno como cargado (archivo y fecha) o "Pendiente", y el aviso "Faltan N requisitos obligatorios" o "Requisitos de alta completos".
7. Carga cada documento desde **Agregar o reemplazar documento** (`POST /suppliers/{supplier_id}/documents`). El selector ofrece sólo los requisitos que aplican al proveedor.
8. Con los requisitos completos, pulsa **Autorizar proveedor** en el expediente y confirma en el diálogo. También puede seleccionarlo en el listado con **Autorizar seleccionados**. Las dos opciones envían `POST /suppliers/authorize`.
9. Si mientras tanto faltó un requisito obligatorio (por ejemplo, otro Administrador lo acaba de hacer obligatorio), el proveedor no se autoriza. El resumen lo lista en "No autorizado: faltan requisitos de alta", con los pendientes y la liga a su expediente.

**Listado de proveedores**

10. La columna **Requisitos de alta** muestra "Completos" o "Faltan N" para cada proveedor, incluidos los autorizados (RD-08). Sólo los "Registrado" con requisitos completos tienen casilla de selección; los demás "Registrado" muestran "Faltan N requisitos" con liga a su expediente.

## 8. Criterios de aceptación — spec `requisitos-alta-proveedor`

Los requisitos de esta sección siguen el formato de delta de OpenSpec. Se copian tal cual a `openspec/changes/requisitos-alta-proveedor/specs/requisitos-alta-proveedor/spec.md`, bajo el encabezado `## ADDED Requirements`.

### Requirement: Catálogo de requisitos de alta
El sistema SHALL mantener un catálogo persistente de los documentos que forman el expediente del proveedor (requisitos de alta). Cada requisito SHALL tener:
- una clave inmutable, que es el valor que se guarda en `documents.document_type` de los documentos del expediente;
- un nombre en español y una descripción opcional, que se muestran en el expediente;
- si es un requisito del sistema o uno definido por el Administrador;
- si está activo;
- un nivel para cada tipo de proveedor (persona moral, persona física e internacional): `REQUIRED` ("Obligatorio"), `OPTIONAL` ("Opcional") o `NOT_APPLICABLE` ("No aplica").

El tipo de proveedor SHALL determinarse así: un proveedor con `origin = INTERNATIONAL` es Internacional, sin importar su tipo de persona; uno nacional es Persona moral o Persona física según su `supplier_type`.

El catálogo SHALL incluir estos requisitos del sistema con estos valores iniciales (clave · nombre · persona moral · persona física · internacional):
- `INCORPORATION_ACT` · Acta constitutiva · Obligatorio · No aplica · No aplica;
- `POWER_OF_ATTORNEY` · Poderes · Obligatorio · No aplica · No aplica;
- `TAX_STATUS` · Cédula fiscal · Obligatorio · Obligatorio · No aplica;
- `LEGAL_REP_ID` · Identificación del representante legal · Obligatorio · No aplica · No aplica;
- `LEGAL_REP_ADDRESS_PROOF` · Comprobante de domicilio del representante legal · Obligatorio · No aplica · No aplica;
- `ADDRESS_PROOF` · Comprobante de domicilio · Obligatorio · Obligatorio · No aplica;
- `BANK_STATEMENT` · Estado de cuenta bancario · Obligatorio · Obligatorio · No aplica;
- `OFFICIAL_ID` · Identificación oficial · No aplica · Obligatorio · No aplica;
- `SAT_OPINION` · Opinión de cumplimiento · Opcional · Opcional · No aplica;
- `ECONOMIC_PROPOSAL` · Propuesta económica · Opcional · Opcional · No aplica;
- `DUE_DILIGENCE` · Debida diligencia · Opcional · No aplica · No aplica;
- `LOCATION` · Ubicación · Opcional · Opcional · No aplica;
- `SUPPLIER_CONTRACT` · Contrato · Opcional · Opcional · No aplica.

#### Scenario: Catálogo inicial tras la migración
- **WHEN** se aplica la migración sobre una base con proveedores y documentos de expediente existentes
- **THEN** el catálogo contiene los 13 requisitos del sistema, activos y con sus valores iniciales; ningún proveedor cambia de estatus y cada documento conserva su `document_type`

#### Scenario: Nombres en español
- **WHEN** el Administrador abre el expediente de un proveedor
- **THEN** los requisitos se muestran por su nombre del catálogo (por ejemplo "Cédula fiscal" y "Poderes"), no por su clave

### Requirement: Configuración exclusiva del Administrador
La página `GET /admin/supplier-requirements` y las operaciones `POST /admin/supplier-requirements`, `POST /admin/supplier-requirements/types`, `POST /admin/supplier-requirements/types/{type_id}` y `POST /admin/supplier-requirements/types/{type_id}/status` SHALL estar disponibles únicamente para el rol `Administrador`. Toda operación `POST` MUST exigir un token CSRF válido. El menú "Requisitos de alta" SHALL mostrarse sólo al rol `Administrador`.

#### Scenario: PMO sin acceso
- **WHEN** un usuario `PMO` solicita la página de configuración o envía cualquiera de sus operaciones
- **THEN** la respuesta es HTTP 403 y la configuración no cambia

#### Scenario: Proveedor sin acceso
- **WHEN** un usuario `Proveedor` solicita la página de configuración o envía cualquiera de sus operaciones
- **THEN** la respuesta es HTTP 403 y la configuración no cambia

#### Scenario: Envío sin token CSRF
- **WHEN** un Administrador envía `POST /admin/supplier-requirements` sin token CSRF o con uno inválido
- **THEN** la respuesta es HTTP 403 y la configuración no cambia

### Requirement: Configuración de los requisitos por tipo de proveedor
La página de configuración SHALL mostrar una fila por cada requisito activo, con su nombre, su descripción y un selector de nivel para Persona moral, otro para Persona física y otro para Internacional. Primero aparecen los requisitos del sistema, en el orden del catálogo, y después los del Administrador, por nombre.

Al guardar, el sistema SHALL validar todos los niveles recibidos y actualizar en una sola transacción los que cambiaron. Un nivel distinto de `REQUIRED`, `OPTIONAL` o `NOT_APPLICABLE`, o la falta del nivel de un requisito activo, SHALL rechazar el guardado completo con HTTP 400. Si ningún nivel cambió, el sistema SHALL informar "Sin cambios" sin modificar nada.

#### Scenario: Hacer opcional un requisito
- **WHEN** el Administrador cambia "Poderes" a Opcional en la columna Persona moral y guarda
- **THEN** la página muestra "Configuración guardada", y el expediente de una persona moral "Registrado" sin poderes muestra "Poderes" como "Opcional · Pendiente" y no lo cuenta entre los obligatorios pendientes

#### Scenario: Exigir un requisito al proveedor internacional
- **WHEN** el Administrador cambia "Estado de cuenta bancario" a Obligatorio en la columna Internacional y guarda
- **THEN** el expediente de un proveedor internacional muestra "Estado de cuenta bancario" como Obligatorio, y el proveedor no puede autorizarse sin ese documento

#### Scenario: Guardar sin cambios
- **WHEN** el Administrador guarda la configuración sin modificar ningún nivel
- **THEN** la página muestra "Sin cambios" y no se agrega ningún registro de auditoría

#### Scenario: Nivel inválido
- **WHEN** la petición trae `MANDATORY` como nivel de un requisito, junto con otros cambios válidos
- **THEN** la respuesta es HTTP 400 con el mensaje "Nivel de exigencia inválido" y no se guarda ningún cambio

### Requirement: Requisitos definidos por el Administrador
El Administrador SHALL poder dar de alta requisitos con un nombre de 3 a 80 caracteres, una descripción opcional de hasta 300 caracteres y un nivel para cada tipo de proveedor, preseleccionado en "No aplica". El sistema SHALL:
- normalizar el nombre, recortando los espacios de los extremos y colapsando los internos repetidos;
- rechazar con HTTP 409 un nombre que ya use otro requisito, sin distinguir mayúsculas;
- asignar al requisito la clave `REQUISITO_<id>`, que no cambia.

El Administrador SHALL poder editar el nombre y la descripción de estos requisitos, y desactivarlos o reactivarlos. Un requisito inactivo MUST NOT ofrecerse en el expediente ni exigirse al autorizar o en SUP-003, y SHALL conservar sus niveles para cuando se reactive. Los requisitos del sistema MUST NOT editarse ni desactivarse; sólo cambian sus niveles.

#### Scenario: Alta de un requisito
- **WHEN** el Administrador da de alta "Declaración de ISR por retenciones de salarios", Obligatorio para Persona moral y No aplica para los demás
- **THEN** existe un requisito activo con clave `REQUISITO_<id>` que aparece en la configuración, y el expediente de una persona moral lo muestra como "Obligatorio · Pendiente"

#### Scenario: Nombre repetido
- **WHEN** el Administrador da de alta un requisito con el nombre "  cédula   FISCAL "
- **THEN** la respuesta es HTTP 409 con el mensaje "Ya existe un requisito con ese nombre" y no se crea ningún requisito

#### Scenario: Desactivación y reactivación
- **WHEN** el Administrador desactiva "Declaración de ISR por retenciones de salarios", que era Obligatorio para Persona moral
- **THEN** el expediente ya no lo pide, la autorización y SUP-003 ya no lo exigen, y los documentos ya cargados de ese tipo siguen listados y descargables; al reactivarlo vuelve a ser Obligatorio para Persona moral

#### Scenario: Requisito del sistema
- **WHEN** el Administrador envía la edición o la desactivación de "Cédula fiscal"
- **THEN** la respuesta es HTTP 409 con el mensaje "Los requisitos del sistema no se pueden editar ni desactivar" y el requisito no cambia

### Requirement: Requisitos que aplican a cada proveedor
Los requisitos que aplican a un proveedor SHALL ser los requisitos activos cuyo nivel para su tipo de proveedor es Obligatorio u Opcional. Los requisitos exigibles SHALL ser los Obligatorios y, si el alta es por cotización o licitación (`economic_proposal`), también "Propuesta económica" cuando su nivel no es No aplica. Un requisito SHALL cumplirse con un documento vigente (`is_current`) de su tipo en el expediente del proveedor (`invoice_id` nulo); la antigüedad del documento no afecta el cumplimiento.

`POST /suppliers/{supplier_id}/documents` SHALL rechazar con HTTP 400 y el mensaje "El documento no aplica a este proveedor", antes de escribir el archivo, un tipo que no aplica al proveedor: con nivel No aplica para su tipo, inactivo o inexistente. Las verificaciones existentes de permisos, contenido y tamaño SHALL mantenerse.

#### Scenario: Persona moral nacional
- **WHEN** con la configuración inicial se abre el expediente de una persona moral nacional
- **THEN** se piden como obligatorios Acta constitutiva, Poderes, Cédula fiscal, Identificación del representante legal, Comprobante de domicilio del representante legal, Comprobante de domicilio y Estado de cuenta bancario; se ofrecen como opcionales Opinión de cumplimiento, Propuesta económica, Debida diligencia, Ubicación y Contrato; no se ofrece Identificación oficial

#### Scenario: Persona física nacional
- **WHEN** con la configuración inicial se abre el expediente de una persona física nacional
- **THEN** se piden como obligatorios Identificación oficial, Cédula fiscal, Comprobante de domicilio y Estado de cuenta bancario, y no se ofrecen Acta constitutiva ni Poderes

#### Scenario: Proveedor internacional con la configuración inicial
- **WHEN** con la configuración inicial se abre el expediente de un proveedor internacional
- **THEN** el panel muestra "Sin requisitos de alta configurados para proveedores internacionales" y el proveedor puede autorizarse sin documentos

#### Scenario: Alta por cotización
- **WHEN** una persona moral tiene `economic_proposal` y "Propuesta económica" es Opcional para Persona moral
- **THEN** su expediente muestra "Propuesta económica" como Obligatorio, con la nota "Alta por cotización o licitación", y el proveedor no puede autorizarse sin ella

#### Scenario: Documento que no aplica
- **WHEN** se envía un documento con `document_type = INCORPORATION_ACT` al expediente de una persona física
- **THEN** la respuesta es HTTP 400 con el mensaje "El documento no aplica a este proveedor" y no se escribe ningún archivo en `storage/`

### Requirement: Checklist de requisitos de alta en el expediente
El expediente del proveedor SHALL mostrar el panel "Requisitos de alta" con los requisitos que le aplican, primero los exigibles y después los opcionales, cada grupo en el orden del catálogo. De cada requisito SHALL mostrar su nombre, su nivel, su descripción si la tiene y su estado: el nombre del archivo y la fecha del documento vigente, o "Pendiente". Un documento con más de tres meses SHALL mostrar "Advertencia de vigencia (+3 meses)" y contar como cargado.

El panel SHALL indicar "Falta 1 requisito obligatorio", "Faltan N requisitos obligatorios" o "Requisitos de alta completos"; sin requisitos que apliquen, "Sin requisitos de alta configurados para <tipo de proveedor>". Los documentos de tipos que ya no aplican MUST NOT contarse y SHALL listarse, descargables, en "Otros documentos del expediente". El formulario "Agregar o reemplazar documento" SHALL ofrecer sólo los requisitos que aplican, con los exigibles marcados como obligatorios.

#### Scenario: Requisitos pendientes
- **WHEN** con la configuración inicial una persona moral "Registrado" sólo tiene cargados el acta constitutiva, la cédula fiscal y el estado de cuenta bancario
- **THEN** el panel muestra Poderes, Identificación del representante legal, Comprobante de domicilio del representante legal y Comprobante de domicilio como "Obligatorio · Pendiente" e indica "Faltan 4 requisitos obligatorios"

#### Scenario: Requisitos completos
- **WHEN** ese proveedor carga los cuatro documentos pendientes
- **THEN** el panel indica "Requisitos de alta completos"

#### Scenario: Documento con más de tres meses
- **WHEN** la cédula fiscal cargada de un proveedor tiene fecha de hace cuatro meses y los demás obligatorios están cargados
- **THEN** la cédula fiscal muestra "Advertencia de vigencia (+3 meses)" y el panel indica "Requisitos de alta completos"

#### Scenario: Documento de un tipo que dejó de aplicar
- **WHEN** una persona moral tiene cargada su ubicación y el Administrador cambia "Ubicación" a No aplica en la columna Persona moral
- **THEN** el panel ya no lista la ubicación entre los requisitos, y "Otros documentos del expediente" la lista y permite descargarla

### Requirement: Protección contra ediciones concurrentes
La página de configuración SHALL incluir la huella `config_version` de la configuración que muestra: el SHA-256 de la clave, los tres niveles y el estado activo de todos los requisitos. Si al guardar la huella recibida falta o no coincide con la de la configuración vigente, el sistema SHALL responder HTTP 409 sin guardar ningún cambio.

#### Scenario: Dos Administradores editan a la vez
- **WHEN** los Administradores A y B abren la configuración, A guarda un cambio y después B guarda el suyo
- **THEN** B recibe HTTP 409 con el mensaje "La configuración cambió mientras la editaba. Recargue la página." y sólo persiste el cambio de A

### Requirement: Auditoría de la configuración de requisitos de alta
Cada cambio guardado SHALL generar un registro de auditoría con el `user_id` del Administrador:
- `SUPPLIER_REQUIREMENTS_UPDATED` al guardar la configuración, con el nivel anterior y el nuevo de cada requisito y tipo de proveedor que cambió, con las claves `persona_moral`, `persona_fisica` e `international`;
- `SUPPLIER_DOCUMENT_TYPE_CREATED` al dar de alta un requisito, con su clave, nombre y niveles;
- `SUPPLIER_DOCUMENT_TYPE_UPDATED` al editar un requisito, con los valores anteriores y nuevos de los campos que cambiaron;
- `SUPPLIER_DOCUMENT_TYPE_STATUS_CHANGED` al desactivar o reactivar un requisito.

Una operación rechazada o un guardado sin cambios MUST NOT generar registros de auditoría.

#### Scenario: Cambio de nivel auditado
- **WHEN** el Administrador cambia "Poderes" de Obligatorio a Opcional en la columna Persona moral y guarda
- **THEN** `audit_logs` contiene un registro `SUPPLIER_REQUIREMENTS_UPDATED` con su `user_id`, `old_value = {"POWER_OF_ATTORNEY": {"persona_moral": "REQUIRED"}}` y `new_value = {"POWER_OF_ATTORNEY": {"persona_moral": "OPTIONAL"}}`

#### Scenario: Operación rechazada sin auditoría
- **WHEN** una operación de configuración se rechaza con HTTP 400, 403 o 409
- **THEN** no se agrega ningún registro a `audit_logs`

## 9. Deltas sobre capacidades existentes

### 9.1 `acceso-proveedores`

Destino: `openspec/changes/requisitos-alta-proveedor/specs/acceso-proveedores/spec.md`. Los requisitos modificados reproducen el bloque completo vigente con los cambios aplicados. "Reglas de la autorización masiva" conserva su nombre y aplica también a la autorización desde el expediente.

```markdown
## MODIFIED Requirements

### Requirement: Estatus "Autorizado"
El estatus operativo `ACTIVE` de un proveedor SHALL mostrarse como "Autorizado" en el listado y en el expediente. La interfaz SHALL ofrecer como única transición de estatus el paso de "Registrado" (`REGISTERED`) a "Autorizado", mediante la autorización: masiva desde el listado o individual desde el expediente. Un proveedor SHALL pasar a "Autorizado" sólo con sus requisitos de alta exigibles completos (capacidad `requisitos-alta-proveedor`). Un proveedor autorizado cumple la regla SUP-001.

#### Scenario: Etiqueta del estatus
- **WHEN** el Administrador abre el listado de proveedores de la demo
- **THEN** los proveedores con estatus `ACTIVE` se muestran como "Autorizado"

### Requirement: Selección de proveedores en el listado
`GET /suppliers` SHALL aceptar `?status=` con `REGISTERED`, `ACTIVE` o `INACTIVE` para filtrar el listado, e ignorar cualquier otro valor. El listado SHALL mostrar la columna "Requisitos de alta" con "Completos" o "Faltan N" para cada proveedor, calculada con la configuración vigente. Para el Administrador, cada proveedor "Registrado" con sus requisitos de alta exigibles completos SHALL tener una casilla de selección; un "Registrado" con requisitos pendientes MUST NOT tenerla y SHALL mostrar "Faltan N requisitos" con una liga a su expediente; los demás MUST NOT tenerla. Con JavaScript, la página SHALL ofrecer "seleccionar todos", mantener deshabilitado el botón "Autorizar seleccionados" mientras no haya selección y pedir confirmación con el texto "Se autorizarán N proveedores y se enviará a cada uno su usuario y contraseña temporal por correo." La página MUST NOT usar scripts ni estilos en línea.

#### Scenario: Filtro por estatus
- **WHEN** el Administrador abre `/suppliers?status=REGISTERED`
- **THEN** el listado muestra sólo proveedores "Registrado", y cada uno con sus requisitos de alta completos tiene su casilla

#### Scenario: Sin casilla para autorizados
- **WHEN** el Administrador abre `/suppliers`
- **THEN** los proveedores "Autorizado" no tienen casilla de selección

#### Scenario: Registrado con requisitos pendientes
- **WHEN** el Administrador abre `/suppliers` y un proveedor "Registrado" no tiene cargados 3 requisitos obligatorios
- **THEN** ese proveedor no tiene casilla, muestra "Faltan 3 requisitos" con la liga a su expediente, y su columna "Requisitos de alta" dice "Faltan 3"

### Requirement: Reglas de la autorización masiva
`POST /suppliers/authorize` SHALL recibir de 1 a 100 identificadores `supplier_ids` distintos. En estos casos nada cambia:
- sin selección: HTTP 400 "Seleccione al menos un proveedor.";
- con más de 100: HTTP 400 "Autorice hasta 100 proveedores por operación.";
- con un identificador inexistente: HTTP 404.

Con una selección válida, el sistema SHALL procesar los proveedores seleccionados en una transacción, con sus filas bloqueadas y un punto de guardado por proveedor:
- un proveedor que no está "Registrado" SHALL omitirse sin cambios;
- un proveedor al que le falta algún requisito de alta exigible, evaluado con la configuración vigente en la misma transacción, MUST NOT autorizarse: no se crea su usuario ni su cuenta en Keycloak y no se le envía correo;
- un proveedor cuyo correo usa un usuario distinto de su propio usuario `Proveedor`, en el portal o en Keycloak según las reglas de enlace, MUST NOT autorizarse;
- un proveedor cuyo aprovisionamiento en Keycloak falla MUST NOT autorizarse: se revierte sólo su punto de guardado y los demás se procesan;
- los demás SHALL pasar a "Autorizado".

Si la transacción no puede confirmarse, ningún proveedor SHALL cambiar en el portal.

#### Scenario: Autorización de proveedores registrados
- **WHEN** el Administrador autoriza 3 proveedores "Registrado" con sus requisitos de alta completos
- **THEN** los 3 quedan "Autorizado" y cumplen la regla SUP-001

#### Scenario: Proveedor ya autorizado en la selección
- **WHEN** la selección incluye un proveedor "Registrado" con sus requisitos completos y uno "Autorizado"
- **THEN** el registrado queda "Autorizado", el otro se omite sin cambios y no recibe credenciales

#### Scenario: Proveedor con requisitos incompletos
- **WHEN** el Administrador autoriza 2 proveedores "Registrado" y a uno le falta "Poderes", obligatorio para su tipo
- **THEN** el otro queda "Autorizado"; el que no tiene poderes sigue "Registrado", sin usuario local ni cuenta en Keycloak y sin correo de credenciales

#### Scenario: Correo usado por otro usuario
- **WHEN** existe un usuario `PMO` con el correo de un proveedor "Registrado" seleccionado con sus requisitos completos
- **THEN** ese proveedor sigue "Registrado", no se crea usuario ni se envía correo, y el resumen lo muestra como no autorizado por correo en uso

#### Scenario: Fallo parcial al aprovisionar
- **WHEN** el Administrador autoriza 3 proveedores con sus requisitos completos y Keycloak rechaza la creación de uno de ellos
- **THEN** los otros 2 quedan "Autorizado" con su usuario en Keycloak, el fallido sigue "Registrado" sin usuario local, y el error queda en la auditoría

#### Scenario: Selección vacía
- **WHEN** el Administrador envía la autorización sin proveedores seleccionados
- **THEN** la respuesta es HTTP 400 con "Seleccione al menos un proveedor."

#### Scenario: Demasiados proveedores
- **WHEN** el Administrador envía 101 identificadores
- **THEN** la respuesta es HTTP 400 con "Autorice hasta 100 proveedores por operación." y ningún proveedor cambia

### Requirement: Resumen de la autorización
Tras la autorización, el sistema SHALL redirigir al listado con un resumen que muestre:
- los proveedores autorizados, cada uno con el resultado de su correo de credenciales ("Credenciales enviadas", o "Envío fallido" con el error), o "Ya tenía usuario" si no se generaron credenciales;
- los omitidos por no estar "Registrado";
- los no autorizados por requisitos de alta incompletos, cada uno con los nombres de sus requisitos exigibles pendientes al consultar el resumen y una liga a su expediente;
- los no autorizados por correo en uso;
- los no autorizados porque el servicio de identidad no pudo crear su cuenta.

El resumen SHALL reconstruirse con el registro de auditoría de la operación, la bitácora de envíos y el expediente vigente. Un parámetro que no corresponde a una autorización MUST NOT mostrar ningún resumen.

#### Scenario: Resumen con un envío fallido
- **WHEN** el Administrador autoriza 2 proveedores y el correo de uno falla
- **THEN** el resumen lista los 2 proveedores autorizados, uno con "Credenciales enviadas" y el otro con "Envío fallido" y el error técnico

#### Scenario: Resumen con un aprovisionamiento fallido
- **WHEN** el Administrador autoriza 2 proveedores y Keycloak rechaza uno
- **THEN** el resumen lista uno como autorizado y el otro como no autorizado porque el servicio de identidad no pudo crear su cuenta

#### Scenario: Resumen con requisitos incompletos
- **WHEN** el Administrador autoriza un proveedor "Registrado" al que le faltan "Poderes" y "Estado de cuenta bancario"
- **THEN** el resumen lo lista con "No autorizado: faltan requisitos de alta (Poderes, Estado de cuenta bancario)" y la liga a su expediente

### Requirement: Auditoría del acceso de proveedores
El sistema SHALL registrar en `audit_logs`:
- por cada proveedor autorizado: `SUPPLIER_STATUS_CHANGED`, con `old_value = {"status": "REGISTERED"}` y `new_value = {"status": "ACTIVE"}`;
- por cada usuario creado: `USER_CREATED`, con el rol, el `supplier_id`, el origen `SUPPLIER_AUTHORIZATION` y si la cuenta de Keycloak se creó o se enlazó (`idp_account`: `created` o `linked`);
- por cada proveedor cuyo aprovisionamiento falló: `SUPPLIER_PROVISIONING_FAILED`, con el código del error y sin el cuerpo de la respuesta de Keycloak;
- por cada operación: `SUPPLIER_BULK_AUTHORIZED`, con las listas de autorizados, con usuario previo, omitidos, no autorizados por requisitos de alta incompletos (`requirements_incomplete`), no autorizados por correo en uso y no autorizados por fallo de aprovisionamiento;
- por cada reenvío: `SUPPLIER_CREDENTIALS_RESENT`, con el usuario.

Estos registros MUST NOT contener la contraseña temporal, tokens ni secretos. Las operaciones rechazadas (HTTP 400, 404, 409 o 503) MUST NOT generar registros, salvo `SUPPLIER_PROVISIONING_FAILED`.

#### Scenario: Auditoría de una autorización
- **WHEN** el Administrador autoriza un proveedor "Registrado" sin usuario y con sus requisitos completos
- **THEN** `audit_logs` contiene `SUPPLIER_STATUS_CHANGED`, `USER_CREATED` con `idp_account = "created"` y `SUPPLIER_BULK_AUTHORIZED` con su `user_id`, y ninguno contiene la contraseña temporal

#### Scenario: Auditoría de un aprovisionamiento fallido
- **WHEN** Keycloak rechaza la creación del usuario de un proveedor
- **THEN** `audit_logs` contiene `SUPPLIER_PROVISIONING_FAILED` para ese proveedor, y no contiene `SUPPLIER_STATUS_CHANGED` ni `USER_CREATED` para él

#### Scenario: Auditoría de una autorización con requisitos incompletos
- **WHEN** el Administrador autoriza un proveedor "Registrado" al que le falta un requisito obligatorio
- **THEN** `audit_logs` contiene `SUPPLIER_BULK_AUTHORIZED` con ese proveedor en `requirements_incomplete`, y no contiene `SUPPLIER_STATUS_CHANGED` ni `USER_CREATED` para él

## ADDED Requirements

### Requirement: Autorización desde el expediente
El expediente de un proveedor "Registrado" SHALL mostrar al Administrador el botón "Autorizar proveedor" en la sección de acceso al portal, en lugar de remitirlo al listado:
- con los requisitos de alta exigibles completos, el botón SHALL pedir confirmación en un diálogo de la página con el texto "Se autorizará a <razón social> y se le enviará su usuario y contraseña temporal por correo." y enviar `POST /suppliers/authorize` con su identificador, con las mismas reglas, auditoría y resumen que la autorización masiva;
- con requisitos pendientes, el botón SHALL mostrarse deshabilitado con el texto "Cargue los requisitos obligatorios para autorizar".

El botón MUST NOT mostrarse a los roles `PMO` ni `Proveedor`, ni en el expediente de un proveedor que no está "Registrado".

#### Scenario: Autorización individual
- **WHEN** el Administrador completa los requisitos de una persona moral "Registrado", pulsa "Autorizar proveedor" y confirma
- **THEN** el proveedor queda "Autorizado", recibe su correo de credenciales y el resumen del listado lo muestra con "Credenciales enviadas"

#### Scenario: Botón deshabilitado
- **WHEN** el Administrador abre el expediente de un proveedor "Registrado" con 2 requisitos obligatorios pendientes
- **THEN** el botón "Autorizar proveedor" está deshabilitado con "Cargue los requisitos obligatorios para autorizar", y el panel de requisitos indica "Faltan 2 requisitos obligatorios"

#### Scenario: Petición manipulada
- **WHEN** el Administrador envía `POST /suppliers/authorize` con el identificador de un proveedor con requisitos pendientes
- **THEN** el proveedor sigue "Registrado" y el resumen lo lista como no autorizado por requisitos de alta incompletos
```

### 9.2 `motor-validacion`

Destino: `openspec/changes/requisitos-alta-proveedor/specs/motor-validacion/spec.md`. El requisito modificado reproduce el bloque completo vigente con los cambios aplicados.

```markdown
## ADDED Requirements

### Requirement: Expediente mínimo según los requisitos de alta configurados
Al validar una factura, SUP-003 (`ERROR`) SHALL evaluar los requisitos de alta exigibles del proveedor de la factura con la configuración vigente (capacidad `requisitos-alta-proveedor`):
- `PASS` con el mensaje "Expediente mínimo disponible" si cada requisito exigible tiene un documento vigente en el expediente;
- `FAIL` con el mensaje "Expediente del proveedor incompleto. Pendientes: <nombre>, <nombre>" en otro caso, con los nombres en el orden del catálogo;
- `NOT_APPLICABLE` con el mensaje "No aplica a proveedores internacionales" si el proveedor es Internacional y no tiene requisitos de alta exigibles.

La antigüedad de los documentos MUST NOT afectar SUP-003. SUP-004 no cambia.

#### Scenario: Proveedor demo con expediente completo
- **WHEN** se valida la factura demo A-CORRECTA después de la migración y de `reset_demo`
- **THEN** SUP-003 resulta `PASS` con "Expediente mínimo disponible"

#### Scenario: Requisito obligatorio agregado después de la autorización
- **WHEN** el Administrador da de alta "Declaración de ISR por retenciones de salarios", Obligatorio para Persona moral, y se valida una factura de una persona moral "Autorizado" que no tiene ese documento
- **THEN** SUP-003 resulta `FAIL` con "Expediente del proveedor incompleto. Pendientes: Declaración de ISR por retenciones de salarios", el envío no procede y el proveedor sigue "Autorizado"

#### Scenario: Opinión de cumplimiento opcional
- **WHEN** con la configuración inicial se valida una factura de una persona moral con todos sus requisitos obligatorios y sin opinión de cumplimiento
- **THEN** SUP-003 resulta `PASS`

#### Scenario: Proveedor internacional con un requisito configurado
- **WHEN** "Estado de cuenta bancario" es Obligatorio para Internacional y se valida una factura de un proveedor internacional sin ese documento
- **THEN** SUP-003 resulta `FAIL` con "Expediente del proveedor incompleto. Pendientes: Estado de cuenta bancario"

## MODIFIED Requirements

### Requirement: Reglas nacionales que no aplican a la factura internacional
Al validar una factura de un proveedor de origen Internacional, el motor SHALL reportar como `NOT_APPLICABLE`, con el mensaje "No aplica a proveedores internacionales" y conservando la severidad de cada regla:
- las reglas del CFDI, XML-001 a XML-010, sin intentar leer un XML;
- FIN-004 (UUID duplicado);
- SUP-003 (expediente mínimo), cuando el proveedor no tiene requisitos de alta exigibles; si los tiene, SUP-003 se evalúa conforme a "Expediente mínimo según los requisitos de alta configurados";
- SUP-004 (vigencia de los documentos del expediente).

SEM-001 SHALL resultar `NOT_EVALUATED` con "Sin conceptos que comparar: el Invoice no es un CFDI". Las demás reglas (DOC, SUP-001, SUP-002, CON, DAT y FIN-001, FIN-002, FIN-003, FIN-005 y FIN-006) SHALL evaluarse igual que para el proveedor nacional, con los importes y la moneda capturados. La validación de facturas de proveedores nacionales MUST NOT cambiar, salvo SUP-003, que sigue la configuración de requisitos de alta.

#### Scenario: Factura internacional completa
- **WHEN** con la configuración inicial de requisitos de alta se valida una factura internacional con Invoice, orden de compra y Vo.Bo., importes que cuadran y dentro del monto de su contrato vigente
- **THEN** XML-001 a XML-010, FIN-004, SUP-003 y SUP-004 resultan `NOT_APPLICABLE`, ninguna regla resulta `FAIL` y la factura puede enviarse

#### Scenario: Monto excedido
- **WHEN** el subtotal capturado de una factura internacional excede el monto autorizado de su contrato
- **THEN** FIN-001 resulta `FAIL` con severidad `CRITICAL` y el envío no procede

#### Scenario: Factura nacional sin cambios
- **WHEN** se valida la factura demo A-CORRECTA
- **THEN** sus resultados son los mismos que antes de este cambio y no incluyen reglas INT ni FIN-007
```

### 9.3 `integridad-datos`

Destino: `openspec/changes/requisitos-alta-proveedor/specs/integridad-datos/spec.md`. El requisito modificado reproduce el bloque completo vigente con los cambios aplicados.

```markdown
## MODIFIED Requirements

### Requirement: Restricciones CHECK sobre estados, montos y vigencias
La base de datos SHALL rechazar:
- valores de estado, rol, tipo de proveedor, origen de proveedor, nivel de exigencia de archivo o de requisito de alta, evento de notificación, buzón de notificación, resultado de envío de correo, tipo de catálogo, severidad, estado de regla, decisión de revisión o estado de procesamiento que no pertenezcan a su enumeración;
- montos negativos en factura;
- `authorized_amount <= 0` en contratos y `new_amount <= 0` en enmiendas;
- `end_date < start_date` en contratos;
- `validation_score` fuera de 0..100;
- `confidence` fuera de 0..1;
- una factura `CANCELLED` sin `cancelled_at`, `cancelled_by` o `cancellation_deadline`, con `cancellation_deadline` no posterior a `cancelled_at`, o una factura en otro estatus con alguno de esos datos.

`invoices.status` SHALL ser una enumeración tipada (`DRAFT`, `UPLOADED`, `UNDER_REVIEW`, `ACCEPTED`, `REJECTED`, `REQUIRES_CORRECTION`, `CANCELLED`), `suppliers.status` SHALL ser una enumeración tipada (`REGISTERED`, `ACTIVE`, `INACTIVE`), `suppliers.origin` SHALL ser una enumeración tipada (`NATIONAL`, `INTERNATIONAL`), `invoice_document_types.national_requirement` e `invoice_document_types.international_requirement` SHALL ser enumeraciones tipadas (`REQUIRED`, `OPTIONAL`, `NOT_APPLICABLE`), `supplier_document_types.persona_moral_requirement`, `supplier_document_types.persona_fisica_requirement` y `supplier_document_types.international_requirement` SHALL ser enumeraciones tipadas (`REQUIRED`, `OPTIONAL`, `NOT_APPLICABLE`), `notification_templates.event`, `notification_copies.event` y `email_deliveries.event` SHALL ser enumeraciones tipadas (`INVOICE_AUTHORIZED`, `INVOICE_REJECTED`, `INVOICE_OBSERVATIONS`, `INVOICE_CANCELLED`, `SUPPLIER_CREDENTIALS`), `notification_mailboxes.code` SHALL ser una enumeración tipada (`INVOICE_RECEPTION`), `email_deliveries.status` SHALL ser una enumeración tipada (`SENT`, `FAILED`), `catalog_entries.catalog` SHALL ser una enumeración tipada (`CURRENCY`, `CFDI_USE`, `PAYMENT_FORM`, `PAYMENT_METHOD`, `TAX_REGIME`, `INDUSTRY`) y `contracts.status` SHALL ser una enumeración tipada (`ACTIVE`, `INACTIVE`).

#### Scenario: Estado inválido por SQL directo
- **WHEN** se ejecuta `UPDATE invoices SET status = 'APROBADA'`
- **THEN** la base de datos rechaza la operación

#### Scenario: Estatus de factura retirado
- **WHEN** se ejecuta `UPDATE invoices SET status = 'PREVALIDATED'` o `UPDATE invoices SET status = 'READY_FOR_CLICKBALANCE'`
- **THEN** la base de datos rechaza la operación

#### Scenario: Estatus de proveedor fuera de catálogo
- **WHEN** se ejecuta `UPDATE suppliers SET status = 'PENDIENTE'`
- **THEN** la base de datos rechaza la operación

#### Scenario: Nivel de exigencia fuera de catálogo
- **WHEN** se ejecuta `UPDATE invoice_document_types SET national_requirement = 'MANDATORY' WHERE code = 'ADDITIONAL'`
- **THEN** la base de datos rechaza la operación

#### Scenario: Nivel de requisito de alta fuera de catálogo
- **WHEN** se ejecuta `UPDATE supplier_document_types SET persona_moral_requirement = 'MANDATORY' WHERE code = 'POWER_OF_ATTORNEY'`
- **THEN** la base de datos rechaza la operación

#### Scenario: Evento de notificación fuera de catálogo
- **WHEN** se ejecuta `UPDATE notification_templates SET event = 'INVOICE_PAID' WHERE event = 'INVOICE_CANCELLED'`
- **THEN** la base de datos rechaza la operación

#### Scenario: Resultado de envío fuera de catálogo
- **WHEN** se inserta en `email_deliveries` una fila con `status = 'QUEUED'`
- **THEN** la base de datos rechaza la operación

#### Scenario: Monto negativo
- **WHEN** se intenta guardar una factura con `total = -1.00`
- **THEN** la base de datos rechaza la operación

#### Scenario: Vigencia invertida
- **WHEN** se intenta crear un contrato con `end_date` anterior a `start_date`
- **THEN** la base de datos rechaza la operación y el formulario muestra el error sin HTTP 500

#### Scenario: Score fuera de rango
- **WHEN** se intenta guardar `validation_score = 101`
- **THEN** la base de datos rechaza la operación

#### Scenario: Tipo de catálogo fuera de catálogo
- **WHEN** se ejecuta `UPDATE catalog_entries SET catalog = 'COUNTRY'`
- **THEN** la base de datos rechaza la operación

#### Scenario: Cancelada sin fecha límite
- **WHEN** se ejecuta `UPDATE invoices SET status = 'CANCELLED'` sobre una factura sin datos de cancelación
- **THEN** la base de datos rechaza la operación

## ADDED Requirements

### Requirement: Integridad del catálogo de requisitos de alta
La base de datos SHALL imponer sobre `supplier_document_types`:
- unicidad de `code` y de `lower(name)`;
- que un requisito del sistema (`is_system`) esté siempre activo.

#### Scenario: Requisito del sistema desactivado por SQL
- **WHEN** se ejecuta `UPDATE supplier_document_types SET is_active = false WHERE code = 'TAX_STATUS'`
- **THEN** la base de datos rechaza la operación

#### Scenario: Nombre repetido con otra capitalización
- **WHEN** se inserta un requisito con `name = 'PODERES'`
- **THEN** la base de datos rechaza la operación
```

### 9.4 `observabilidad`

Destino: `openspec/changes/requisitos-alta-proveedor/specs/observabilidad/spec.md`. El requisito modificado reproduce el bloque completo vigente; cambian el punto de la autorización masiva y su escenario, y se agrega un escenario.

```markdown
## MODIFIED Requirements

### Requirement: Registro de eventos técnicos del flujo
El sistema SHALL registrar:
- subida de documento: `invoice_id` o `supplier_id`, tipo documental, extensión y tamaño en bytes;
- inicio y fin de validación, con `invoice_id`, duración en milisegundos, score, número de bloqueos y estado resultante;
- decisión de revisión, con `invoice_id` y decisión;
- todo fallo de parseo de XML o de apertura de PDF, con el tipo y el mensaje técnico de la excepción, registrado **antes** de devolver el mensaje genérico al usuario;
- carga masiva de proveedores: evento `supplier.bulk_import` con `mode` (`strict` o `partial`), `result` (`imported`, `partial`, `rejected` o `conflict`), filas leídas (`rows`), proveedores registrados (`registered`), proveedores omitidos (`skipped`), filas con errores (`invalid`), tamaño del archivo en bytes (`size_bytes`) y duración en milisegundos (`duration_ms`);
- cambio de una plantilla de notificación: evento `notification_template.updated` con el código del evento (`event_code`) y la nueva versión (`version`);
- composición de un correo con el texto predeterminado porque la plantilla guardada no es válida: evento `notification.template_fallback` con `event_code` y el motivo (`reason`);
- envío de un correo: evento `notification.sent` con el id del envío en la bitácora (`delivery_id`), `event_code` (`TEST` para el correo de prueba), el transporte (`transport`), el número de destinatarios (`recipients`) y la duración en milisegundos (`duration_ms`);
- correo que no se pudo enviar: evento `notification.failed` con los mismos campos y el tipo de la excepción (`error_type`);
- cambio de los destinatarios de notificaciones: evento `notification_recipients.updated` con los códigos de las listas que cambiaron (`lists`);
- autorización masiva de proveedores: evento `supplier.bulk_authorize` con los proveedores solicitados (`requested`), autorizados (`authorized`), autorizados que ya tenían usuario (`existing_access`), omitidos (`skipped`), no autorizados por requisitos de alta incompletos (`requirements_incomplete`), no autorizados por correo en uso (`conflicts`), credenciales enviadas (`credentials_sent`) y fallidas (`credentials_failed`), y la duración en milisegundos (`duration_ms`);
- cambio de las Reglas de Validación: evento `validation_settings.updated` con los nombres de los campos que cambiaron (`fields`) y la nueva versión (`version`);
- carga de un catálogo desde Excel: evento `catalog.import` con el catálogo (`catalog`), `result` (`imported` o `rejected`), filas leídas (`rows`), claves agregadas (`added`), actualizadas (`updated`) y sin cambios (`unchanged`), filas con errores (`invalid`), tamaño del archivo en bytes (`size_bytes`) y duración en milisegundos (`duration_ms`); y un fallo al leer el archivo, con el evento `catalog_import.read_failed` y el tipo y el mensaje técnico de la excepción.

Los eventos de plantillas y notificaciones MUST NOT incluir el asunto, el cuerpo, los valores de las variables, las direcciones de correo ni el mensaje técnico de un error de envío. El evento de autorización masiva MUST NOT incluir razones sociales, correos, identificadores fiscales, nombres de requisitos ni contraseñas. El evento de las Reglas de Validación MUST NOT incluir los valores de los campos.

#### Scenario: Validación registrada
- **WHEN** se ejecuta la prevalidación de una factura
- **THEN** el log contiene un evento `validation.started` y un evento `validation.completed` con `duration_ms`, `score` y `blockers`

#### Scenario: PDF dañado
- **WHEN** se sube un PDF que PyMuPDF no puede abrir
- **THEN** el usuario ve "El PDF no puede abrirse o esta danado" y el log contiene un evento `pdf.analysis_failed` con el tipo y el mensaje de la excepción original

#### Scenario: Carga masiva registrada
- **WHEN** el Administrador carga un archivo válido con 3 proveedores nuevos
- **THEN** el log contiene un evento `supplier.bulk_import` con `mode = "strict"`, `result = "imported"`, `rows = 3`, `registered = 3`, `skipped = 0`, `invalid = 0`, `size_bytes` y `duration_ms`

#### Scenario: Carga parcial registrada
- **WHEN** el Administrador agrega las filas válidas de un archivo con 2 filas con errores
- **THEN** el log contiene un evento `supplier.bulk_import` con `mode = "partial"`, `result = "partial"` e `invalid = 2`

#### Scenario: Cambio de plantilla registrado
- **WHEN** el Administrador guarda un cambio en la plantilla Rechazada y esta queda en la versión 2
- **THEN** el log contiene un evento `notification_template.updated` con `event_code = "INVOICE_REJECTED"` y `version = 2`, sin el asunto ni el cuerpo

#### Scenario: Plantilla inválida registrada
- **WHEN** se compone un correo `INVOICE_REJECTED` y la plantilla guardada no es válida
- **THEN** el log contiene un evento `notification.template_fallback` con `event_code = "INVOICE_REJECTED"` y `reason`, sin el asunto, el cuerpo ni los valores de las variables

#### Scenario: Envío registrado
- **WHEN** se envía el correo de Autorizada de una factura al buzón "Recepción de Facturas"
- **THEN** el log contiene un evento `notification.sent` con `event_code = "INVOICE_AUTHORIZED"`, `delivery_id`, `transport`, `recipients` y `duration_ms`, y no contiene la dirección del buzón, el asunto ni el cuerpo

#### Scenario: Envío fallido registrado
- **WHEN** el servidor SMTP rechaza la conexión al enviar un correo de prueba
- **THEN** el log contiene un evento `notification.failed` con `event_code = "TEST"` y `error_type`, sin la dirección de destino

#### Scenario: Cambio de destinatarios registrado
- **WHEN** el Administrador cambia las copias de Rechazada
- **THEN** el log contiene un evento `notification_recipients.updated` con `lists = ["INVOICE_REJECTED"]` y sin direcciones de correo

#### Scenario: Autorización masiva registrada
- **WHEN** el Administrador autoriza 3 proveedores "Registrado" sin usuario y con sus requisitos completos y un proveedor ya autorizado, y los 3 correos de credenciales se envían
- **THEN** el log contiene un evento `supplier.bulk_authorize` con `requested = 4`, `authorized = 3`, `existing_access = 0`, `skipped = 1`, `requirements_incomplete = 0`, `conflicts = 0`, `credentials_sent = 3`, `credentials_failed = 0` y `duration_ms`, sin correos ni contraseñas

#### Scenario: Autorización con requisitos incompletos registrada
- **WHEN** el Administrador autoriza 2 proveedores "Registrado" y a uno le faltan requisitos obligatorios
- **THEN** el log contiene un evento `supplier.bulk_authorize` con `requested = 2`, `authorized = 1` y `requirements_incomplete = 1`, sin nombres de requisitos

#### Scenario: Cambio de las Reglas de Validación registrado
- **WHEN** el Administrador cambia la Razón Social y la forma de pago y la configuración queda en la versión 2
- **THEN** el log contiene un evento `validation_settings.updated` con `fields = ["receiver_name", "payment_form"]` y `version = 2`, sin los valores

#### Scenario: Carga de catálogo registrada
- **WHEN** el Administrador carga en monedas un archivo con 2 filas que agrega una clave y actualiza otra
- **THEN** el log contiene un evento `catalog.import` con `catalog = "CURRENCY"`, `result = "imported"`, `rows = 2`, `added = 1`, `updated = 1`, `unchanged = 0`, `invalid = 0`, `size_bytes` y `duration_ms`
```

## 10. Notas de diseño (insumo para `design.md`)

| # | Decisión | Alternativas descartadas y motivo |
| --- | --- | --- |
| D1 | Tabla `supplier_document_types` con una columna de nivel por tipo de proveedor (`persona_moral_requirement`, `persona_fisica_requirement`, `international_requirement`) que reutiliza la enumeración `DocumentRequirement` | Agregar columnas a `invoice_document_types`: mezcla dos catálogos con dimensiones distintas (origen frente a tipo de persona) y la RD-02 de HU-04 los separa. Tabla genérica (perfil, tipo, nivel): con tres perfiles fijos añade uniones y filas ausentes que hay que interpretar, como ya se razonó en el D1 de HU-04 |
| D2 | Tres tipos de proveedor: persona moral nacional, persona física nacional e internacional. Enumeración nueva `RequirementProfile` (`PERSONA_MORAL`, `PERSONA_FISICA`, `INTERNATIONAL`) y una función que la deriva de `origin` y `supplier_type`. No se usa el nombre `SupplierProfile`, que ya es un esquema | Dos columnas por tipo de persona: el internacional heredaría requisitos mexicanos (cédula fiscal) y no podría autorizarse. Cuatro columnas (origen × persona): duplica configuración sin una fuente que la pida (P-06) |
| D3 | Un solo servicio, `supplier_requirements_service`, calcula para un proveedor los requisitos que aplican, los exigibles, los pendientes y el checklist. Lo usan el expediente, el listado, la autorización y SUP-003. Reemplaza `supplier_requirement_status()` y las constantes `SUPPLIER_REQUIREMENTS`, `SUPPLIER_DOCUMENT_LABELS`, `OPTIONAL_SUPPLIER_DOCUMENTS` y `ALTERNATIVE_SUPPLIER_DOCUMENTS`, que se eliminan. Se conservan `QUOTATION_DOCUMENT` y `DATED_SUPPLIER_DOCUMENTS`, que son reglas por clave | Mantener las constantes para SUP-003 y la tabla para la autorización: dos definiciones del expediente mínimo que se contradicen en la misma pantalla |
| D4 | La autorización reutiliza `authorize()`. Verifica los requisitos de cada proveedor "Registrado" después de omitir a los no registrados y antes del conflicto de correo y de Keycloak: es la verificación más barata y la que el Administrador puede resolver. Lee en una consulta los documentos vigentes de los seleccionados y la configuración, dentro de la misma transacción | Verificar en el router: la autorización masiva y la individual podrían divergir. Verificar después de Keycloak: crearía cuentas que habría que revertir |
| D5 | La autorización desde el expediente envía el mismo `POST /suppliers/authorize` con un solo `supplier_ids` y termina en el mismo resumen. Sin endpoint nuevo | `POST /suppliers/{supplier_id}/authorize`: duplicaría reglas, auditoría y pruebas. Volver al expediente en lugar del listado: requeriría un parámetro de retorno validado, sin ganancia funcional |
| D6 | `SUPPLIER_BULK_AUTHORIZED` guarda la lista de identificadores `requirements_incomplete`, con la misma forma que las demás listas. El resumen recalcula los nombres de los pendientes al mostrarse, igual que reconstruye el estado del correo con la bitácora (D5 de HU-02) | Guardar los códigos pendientes en la auditoría: cambia la forma de `new_value`, que `authorization_summary()` lee como listas de enteros |
| D7 | Listado: los documentos vigentes de los proveedores de la página se leen en una consulta, y el catálogo en otra. Sin N+1 (spec `listados-paginados`) | Calcular por proveedor: una consulta por fila |
| D8 | Huella `config_version` (SHA-256 de clave, niveles y estado activo) en un campo oculto; si no coincide al guardar, 409. Igual que el D8 de HU-04 | Bloqueo pesimista o última escritura gana: mismos motivos que en HU-04 |
| D9 | Clave `REQUISITO_<id>` asignada tras el `flush`, como `SOPORTE_<id>` en HU-04 | Derivar la clave del nombre: cambiaría al renombrar y choca con acentos y espacios |
| D10 | Revisión Alembic `0016_supplier_document_types`, posterior a `0015_keycloak_identity`: crea la tabla con sus restricciones y siembra los 13 requisitos del sistema con los valores de la sección 6.3. No toca `suppliers` ni `documents`. El downgrade lanza `NotImplementedError` si hay requisitos del Administrador o documentos `POWER_OF_ATTORNEY` o `REQUISITO_*`, porque revertir perdería datos | Editar revisiones anteriores: prohibido por la regla "Una revisión por cambio de modelo" |
| D11 | `documents.document_type` sigue sin llave foránea: guarda claves de dos catálogos (factura y expediente). La aplicación valida el tipo al cargar, como el D6 de HU-04 | Llave foránea: obligaría a unir los dos catálogos |
| D12 | Sin niveles fijos. Ningún flujo del sistema depende de un requisito concreto; una configuración equivocada sólo impide autorizar, se ve en el checklist, es reversible y queda auditada | Fijar "Acta constitutiva: No aplica" para persona física, como los candados de HU-04: añade restricciones `CHECK` y pantalla de candados para un error que no rompe nada |
| D13 | Pantalla `/admin/supplier-requirements` con formularios HTML normales, como `/admin/required-documents`. El diálogo de confirmación del expediente reutiliza el modal de la autorización del listado, sin diálogos nativos ni scripts en línea (CSP `default-src 'self'`, change `interfaz-sin-dialogos-nativos`) | Guardado celda por celda con `fetch`: mismos motivos que el D11 de HU-04 |
| D14 | El panel del expediente se renombra de "Expediente Anexo A" a "Requisitos de alta" | Conservar "Anexo A": no dice para qué sirve el panel y los requisitos del Administrador no vienen del Anexo A |

**Riesgos y mitigaciones**

- **Proveedores ya autorizados sin "Poderes"** → con la configuración inicial, SUP-003 resulta `FAIL` y sus facturas no pueden enviarse hasta que lo carguen. Los datos demo no se ven afectados: `seed_db` carga "Poderes". En un ambiente con proveedores reales, P-07 decide si se despliega con "Poderes" en Opcional. El listado marca a los afectados con "Faltan N".
- **Los comprobantes de domicilio dejan de ser alternativos** → una persona moral autorizada con uno solo queda con SUP-003 en `FAIL`. Misma mitigación; P-04.
- **La Opinión de cumplimiento pasa a opcional** → SUP-003 se relaja frente a hoy. Es el literal de la solicitud; P-01 lo confirma.
- **El Administrador hace obligatorio un documento que nadie tiene** → nadie puede autorizarse. El checklist dice qué falta, el cambio es reversible y queda auditado.
- **Pruebas que autorizan proveedores recién registrados** → hoy basta el estatus "Registrado". Las pruebas de autorización (pytest y la suite Playwright de HU-02, HU-03 y HU-10) tienen que cargar los requisitos antes, con un fixture común.
- **El proveedor internacional no puede cargar documentos de expediente con la configuración inicial** → ningún requisito le aplica. Es coherente con P-06; cuando se definan, el Administrador los habilita.

## 11. Impacto

| Área | Cambio |
| --- | --- |
| `app/core/constants.py` | Enumeración `RequirementProfile` con etiquetas en español. Se eliminan `SUPPLIER_REQUIREMENTS`, `SUPPLIER_DOCUMENT_LABELS`, `OPTIONAL_SUPPLIER_DOCUMENTS` y `ALTERNATIVE_SUPPLIER_DOCUMENTS` (D3) |
| `app/models/__init__.py` | Modelo `SupplierDocumentType` con unicidad de clave y de nombre sin mayúsculas, y `CHECK` de requisito del sistema activo |
| `alembic/versions/` | Nueva revisión `0016_supplier_document_types` (D10) |
| `app/schemas/__init__.py` | `SupplierDocumentTypeCreate` y `SupplierDocumentTypeUpdate` (nombre y descripción) |
| `app/services/` | Nuevo `supplier_requirements_service.py`: perfil, requisitos que aplican y exigibles, checklist, pendientes por proveedor y por página, validación de la matriz, huella y auditoría. `supplier_service.py` pierde `supplier_requirement_status()` y `_requirement()` |
| `app/services/supplier_access_service.py` | `authorize()` verifica requisitos y agrega `requirements_incomplete` al resultado, a la auditoría, al log y a `AuthorizationSummary` |
| `app/rules/supplier_rules.py` y `app/services/validation_engine.py` | SUP-003 con los requisitos exigibles de la configuración y mensaje con los pendientes; regla del internacional según RD-09 |
| `app/routers/admin.py` | Rutas `/admin/supplier-requirements*` |
| `app/routers/suppliers.py` | Expediente con checklist y "Otros documentos del expediente"; validación del tipo al cargar; requisitos de la página en el listado |
| `app/templates/admin/supplier_requirements.html` | Nueva pantalla: matriz, alta, edición y requisitos inactivos |
| `app/templates/suppliers/detail.html` | Panel "Requisitos de alta", formulario de carga filtrado y botón "Autorizar proveedor" con su diálogo |
| `app/templates/suppliers/list.html` | Columna "Requisitos de alta", casilla sólo con requisitos completos y grupo "No autorizado: faltan requisitos de alta" en el resumen |
| `app/templates/base.html` | Enlace "Requisitos de alta" en Administración |
| `scripts/seed_db.py` | Carga a los proveedores demo los requisitos que les aplican según el catálogo, incluido "Poderes" |
| `README.md` | Sección de requisitos de alta, cambio en la autorización y en SUP-003 |
| `tests/` | Nuevo `test_requisitos_alta.py`, con un escenario por requisito. Ajustes en `test_acceso_proveedores.py`, `test_datos_proveedor.py`, `test_factura_internacional.py`, `test_archivos.py`, `test_observabilidad.py`, `test_migraciones.py`, `test_integridad.py`, `test_permissions.py` y en el fixture que autoriza proveedores en `conftest.py` |
| `tests/hu/` | Las especificaciones de HU-02, HU-03 y HU-10 cargan los requisitos antes de autorizar. Nueva especificación de HU-21 con su evidencia y su entrada en `hu-catalogo.json` |
| `requirements.txt` / `requirements.lock` | Sin dependencias nuevas |

## 12. Dependencias

- **Depende de:** HU-01 (el alta deja al proveedor "Registrado" y guarda su origen) y HU-02 (la autorización que esta HU condiciona). Técnicamente reutiliza `DocumentRequirement` y el patrón de configuración de HU-04 (change archivado `2026-09-25-archivos-minimos-por-tipo-proveedor`).
- **Modifica:** HU-02 (la autorización exige los requisitos y se ofrece también desde el expediente) y la regla SUP-003 que consumen HU-13 y HU-16.
- **Habilita** (con lo que cada HU recibe de esta):

| HU | Qué recibe de HU-21 | Qué le toca decidir a esa HU |
| --- | --- | --- |
| HU-03 | Sólo recibe credenciales un proveedor con expediente completo | — |
| HU-13 | SUP-003 con el expediente configurado | — |
| HU-16 | La columna Internacional para definir el expediente del proveedor extranjero | Cerrar P-06 de EP-01 cuando negocio defina esos requisitos |
| HU-07 | Un catálogo administrable más | Si esta pantalla se integra a la administración de catálogos |

## 13. Definición de terminado

- [ ] Change `requisitos-alta-proveedor` creado con proposal, specs, design y tasks; `openspec validate requisitos-alta-proveedor --strict` sin errores.
- [ ] Preguntas P-01 a P-07 respondidas por negocio o registradas como "Open Questions" en `design.md`.
- [ ] Cada escenario de las secciones 8 y 9 tiene al menos una prueba automatizada que pasa sobre la base PostgreSQL temporal de la sesión.
- [ ] La cobertura no baja del umbral vigente (`--cov-fail-under=93`).
- [ ] Revisión Alembic nueva; `alembic check` sin diferencias; downgrade conforme a D10.
- [ ] `scripts/check.py` en verde (ruff, pytest, `alembic check`, `pip-audit`).
- [ ] `reset_demo` reproduce el resultado de las 10 facturas demo; los dos proveedores demo muestran "Requisitos de alta completos" y SUP-003 resulta `PASS`.
- [ ] Suite Playwright de `tests/hu` en verde, con la nueva especificación de HU-21 y su evidencia en el PDF.
- [ ] Prueba manual: cambiar niveles; crear, editar, desactivar y reactivar un requisito; dar de alta una persona moral; intentar autorizarla con requisitos pendientes desde el listado y desde el expediente; completar los requisitos y autorizarla.
- [ ] README actualizado.
- [ ] RF-19 incorporado a la siguiente versión de la ERS.
- [ ] Change archivado y specs sincronizadas (`/opsx:archive`).

## 14. Trazabilidad

| Elemento | Referencia |
| --- | --- |
| Solicitud de negocio (2026-10-02) | Texto de la sección 1: parametrizar los documentos mínimos de alta en la configuración, pedirlos al dar de alta y activar al proveedor, obligatorios y opcionales. Lista: Acta Constitutiva, Poderes, Cédula Fiscal, Identificación Representante Legal, Domicilio Representante Legal, Comprobante de domicilio, Estado de Cuenta Bancario |
| Lineamientos de facturación 2024 v1.4.1 | 1.i: alta en el catálogo de Asociados "con el cumplimiento al 100% de los requisitos detallados en el 'Anexo A'". Anexo A: listas para personas morales y físicas; "Poder Notarial (solo en caso de que el apoderado no tenga facultades en el Acta Constitutiva)"; formato PDF; vigencia "no mayor a 3 meses" |
| ERS v1.4 | RF-02 (autorización, HU-02), que esta HU modifica. RF-19 propuesto para esta HU |
| HU-02 | Autorización masiva: se agrega la condición de requisitos y la autorización desde el expediente |
| HU-04 | RD-02 y "Fuera del alcance": dejó el expediente del proveedor (Anexo A) fuera de su alcance. Patrón de configuración reutilizado (D1, D8, D9, D11 y D13 de HU-04) |
| EP-01 | P-06: expediente del proveedor internacional; esta HU lo vuelve configurable (P-06 de esta HU) |
| OpenSpec | Capacidad nueva `requisitos-alta-proveedor`; deltas en `acceso-proveedores`, `motor-validacion`, `integridad-datos` y `observabilidad`; sin cambios en `almacenamiento-documentos` (extensiones globales) ni en `archivos-minimos-factura` |

## 15. Puntos a confirmar en la revisión

Interpretaciones de la solicitud que conviene validar con quien la hizo, además de las preguntas de 5.3:

1. **"Activar" es "Autorizar".** No se crea un estatus nuevo: activar es el paso de "Registrado" a "Autorizado" de HU-02, que también envía las credenciales.
2. **"Al dar de alta me debe pedir estos requisitos".** El alta crea al proveedor y lo lleva a su expediente, donde el panel pide los requisitos; la autorización los exige. No se agregan campos de archivo al formulario de alta, porque la carga masiva no puede llevarlos.
3. **Tipo de proveedor.** La lista de la solicitud aplica a la persona moral. Para la persona física y el internacional se proponen los valores de la sección 6.3.
4. **Catálogo completo.** Además de los siete documentos de la solicitud, el catálogo conserva los otros documentos que el expediente ya tiene (Opinión de cumplimiento, Propuesta económica, etc.), como Opcional o No aplica, para no perder documentos ya cargados.
