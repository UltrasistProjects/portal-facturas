## Context

La búsqueda `rg -i "click[\s_-]*(cloud|clock)"` y la extracción de texto de los `.docx` y PDF del repositorio dan este inventario (2026-09-30):

- **ERS v1.3** (`docs/source-of-truth/`): 8 párrafos, cada uno en un único *run* de Word (se pueden editar sin perder formato).
- **PoC:** `README.md:459` y `:572`; docstrings de `app/services/secret_vault.py` y `app/services/supplier_access_service.py`; `tests/test_acceso_proveedores.py` ("gestor de secretos" en el nombre de un test y en mensajes).
- **Historias:** `docs/stories/epics/EP-01 … .md:458`.
- **Spec vigente:** `openspec/specs/acceso-proveedores/spec.md` ("gestor de secretos", sin el nombre).
- **Histórico:** 2 cambios archivados (`2026-09-25-acceso-proveedores`, `2026-09-28-primer-acceso-proveedor`) y 2 documentos de `docs/superseded/` (HUs v2 con "ClickCloude", validación de HUs).
- Sin apariciones: la minuta, el PDF de lineamientos y el zip de Copilot Studio.

## Goals / Non-Goals

**Goals:**
- Que las fuentes de verdad vigentes nombren Keycloak y lo describan como proveedor de identidad.
- Dejar RN-HU03-01 redactada como la implementará `add-keycloak-authentication`.

**Non-Goals:**
- Cambiar comportamiento, esquema o dependencias.
- Reescribir el histórico (cambios archivados y `docs/superseded/`).

## Decisions

### D1. Corregir la frase, no sólo el nombre
Cada aparición se reescribe en su frase. "Resguardar la contraseña en un gestor de secretos" pasa a "gestionar las credenciales en el proveedor de identidad". No se usa `sed`.

### D2. El histórico no se reescribe
Los cambios archivados y los documentos de `docs/superseded/` registran lo que se decidió con la información de entonces. Reescribirlos falsearía ese registro. La verificación de "cero apariciones" excluye `openspec/changes/archive/`, `docs/superseded/` y el prompt de trabajo `docs/PROMPT_ClaudeCode_Keycloak_OpenSpec.md`, y lo dice explícitamente:

```bash
rg -n -i "click[\s_-]*(cloud|clock)" --hidden -g '!.git' -g '!**/.venv/**' \
   -g '!openspec/changes/archive/**' -g '!docs/superseded/**' -g '!docs/PROMPT_*.md' \
   -g '!openspec/changes/correct-identity-provider-naming/**'
```

Este mismo cambio también queda excluido, porque describe el error.

*Alternativa:* corregir también el histórico con una nota. Se descarta: el archivo de OpenSpec es la bitácora del proyecto.

### D3. El comportamiento de RN-HU03-01 va en el cambio siguiente
La RN corregida dice que el portal "no almacena contraseñas ni sus hashes". Hoy el portal guarda el hash Argon2. Si este cambio lo exigiera en la spec, la spec afirmaría algo falso hasta que se aplique `add-keycloak-authentication`. Aquí sólo se corrige el término en el requirement vigente. El requirement de custodia en el IdP lo agrega `add-keycloak-authentication`, que es el cambio donde se vuelve cierto.

### D4. Edición de los `.docx` sobre el XML, run a run
Se edita el paquete OOXML con la biblioteca estándar (`zipfile`), sin instalar dependencias:
- Cada texto afectado ocupa un único `<w:t>`. Se reemplaza sólo ese contenido y se exige exactamente una aparición de cada texto de origen.
- Las demás partes del paquete se copian byte a byte; sólo cambian `word/document.xml` y `word/footer1.xml`.
- La fila v1.4 se agrega copiando la fila anterior de sombreado alterno (la 1.2) y cambiando sólo sus cuatro textos.
- La portada pasa de "Versión 1.3" a "Versión 1.4", con la fecha de la corrección, y el pie de página de "v1.3" a "v1.4".

*Alternativa:* python-docx. Se descarta: instala un paquete externo y reescribe todo el paquete al guardar.

Si algún párrafo no pudiera editarse así, no se regenera el documento: se lista con el texto actual y el propuesto para editarlo a mano.

**Precondición:** el ERS no puede estar abierto en LibreOffice. El archivo `.~lock.ERS_…docx#` indica que lo está.

### D5. Textos de la ERS

| ¶ | Sección | Texto actual | Texto propuesto |
|---|---|---|---|
| 4 | Portada | Versión 1.3 | Versión 1.4 |
| 55 | 1.3 Glosario (término) | ClickCloud | Keycloak |
| 56 | 1.3 Glosario (definición) | Gestor de secretos donde se resguarda la contraseña temporal del proveedor (RN-HU03-01). | Proveedor de identidad (IdP): servidor de autenticación OIDC que gestiona las cuentas de los usuarios del portal y sus credenciales, incluida la contraseña temporal del proveedor (RN-HU03-01). |
| 84 | 2.4 Restricciones | La contraseña temporal debe resguardarse en un gestor de secretos (ClickCloud) y no dentro del sistema de proveedores (RN-HU03-01). | Las credenciales del proveedor, incluida la contraseña temporal, deben gestionarse en el proveedor de identidad (Keycloak); el sistema de proveedores no almacena contraseñas ni sus hashes (RN-HU03-01). |
| 89 | 2.5 Suposiciones | Se asume la disponibilidad del gestor de secretos (ClickCloud) para el resguardo de contraseñas temporales. | Se asume la disponibilidad del proveedor de identidad (Keycloak) para la autenticación de los usuarios y la gestión de sus credenciales. |
| 194 | RF-03, criterio | La contraseña temporal deberá resguardarse en ClickCloud (gestor de secretos) y no almacenarse dentro del sistema de proveedores (RN-HU03-01). | La contraseña temporal deberá gestionarse en el proveedor de identidad (Keycloak) y no almacenarse, ni en claro ni como hash, dentro del sistema de proveedores (RN-HU03-01). |
| 311 | 3.3 Interfaces externas | Gestor de secretos (ClickCloud): almacenamiento seguro de la contraseña temporal del proveedor. | Proveedor de identidad (Keycloak): autenticación OIDC de los usuarios del portal y gestión de sus credenciales, incluida la contraseña temporal del proveedor. |
| 316 | 3.4 RNF Seguridad | …; resguardo de contraseñas temporales en gestor de secretos, sin persistirlas en el sistema. | …; gestión de credenciales, incluidas las contraseñas temporales, en el proveedor de identidad (Keycloak), sin persistirlas ni guardar sus hashes en el sistema. |
| 332 | 3.5 Tabla de RN | La contraseña temporal del proveedor se resguarda en ClickCloud, evitando almacenarla dentro del sistema de proveedores. | Las credenciales del proveedor, incluida la contraseña temporal, se gestionan exclusivamente en el proveedor de identidad (Keycloak); el sistema de proveedores no almacena contraseñas ni sus hashes. |

**Fila nueva del control de versiones:** `1.4 | 30/09/2026 | Equipo Técnico | Corrección de nomenclatura: "ClickCloud" era un error de transcripción; el componente es Keycloak, un proveedor de identidad (IdP), no un gestor de secretos. Se reformula RN-HU03-01 y se ajustan 1.3, 2.4, 2.5, RF-03, 3.3, 3.4 y 3.5.`

### D6. Textos en el código y la documentación de la PoC
- `README.md:459` pasa a "**Proveedor de identidad (RN-HU03-01):** `app/services/secret_vault.py` es el punto de integración provisional …; lo sustituye el aprovisionamiento en Keycloak (`add-keycloak-authentication`)". `:572` pasa a "La contraseña temporal aún no se gestiona en Keycloak …".
- Docstrings: "gestor de secretos (ClickCloud)" pasa a "proveedor de identidad (Keycloak)". Los nombres de clases y funciones no cambian (sin cambios de código).
- `tests/test_acceso_proveedores.py`: `test_resguardo_en_el_gestor_de_secretos` pasa a `test_entrega_al_proveedor_de_identidad`, y los mensajes "Gestor de secretos no disponible" pasan a "Proveedor de identidad no disponible". La lógica de las pruebas no cambia.

## Risks / Trade-offs

- **[El ERS está abierto en LibreOffice]** → si se guarda desde LibreOffice después de la edición, se pierde. Hay que cerrarlo antes (D4).
- **[Edición directa del XML]** → al terminar se compara el texto de todos los párrafos antes y después (sólo cambian la portada, los 8 párrafos y la fila nueva), se comprueba que las demás partes del paquete son idénticas y que el ZIP es íntegro.
- **[La fila 1.4 menciona "ClickCloud"]** → es intencional: describe la corrección. Es la única aparición que queda en el ERS.
- **[Grep con exclusiones]** → una aparición nueva en una ruta excluida no se detectaría. Las exclusiones son sólo de registro histórico, que no se edita.
