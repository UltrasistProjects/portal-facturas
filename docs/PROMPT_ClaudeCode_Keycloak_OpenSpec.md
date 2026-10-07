# Prompt para Claude Code — Keycloak en el Portal de Facturas (OpenSpec)

> Copia todo lo que está debajo de la línea en Claude Code, desde la raíz del repositorio.

---

## Rol y contexto

Actúas como ingeniero senior en el repositorio del **Portal de Proveedores / Portal de Facturas ULTRASIST** (Python 3.12 · FastAPI · Jinja2 server-rendered · SQLAlchemy 2 · Alembic · SQLite). Trabajas con **OpenSpec** (spec-driven development): primero se escriben y validan los cambios en `openspec/changes/`, después se implementa.

Hay dos problemas que resolver, en este orden:

1. **Error de nomenclatura propagado.** Las fuentes de verdad (ERS v1.3, HUs, minuta, notas) mencionan un "gestor de secretos **ClickCloud**" (también puede aparecer como *ClickClock*, *Click Cloud*, *Clickcloud*). Es un error de transcripción: el componente real es **Keycloak**. Además, la descripción conceptual también está mal: Keycloak **no es un gestor de secretos**, es un **proveedor de identidad (IdP) / servidor de autenticación OIDC**. La corrección es de nombre **y** de concepto.
2. **Autenticación con Keycloak.** Hoy la app autentica localmente (formulario `/login`, `users.password_hash` con Argon2 vía pwdlib, `SessionMiddleware` con cookie firmada). Debe pasar a **OIDC Authorization Code + PKCE contra Keycloak**, cubriendo RF-02, RF-03 y RF-06 de la ERS.

Requisitos de la ERS afectados (léelos en los documentos del repo si existen):

- **RN-HU03-01** (original): *"La contraseña temporal del proveedor se resguarda en ClickCloud, evitando almacenarla dentro del sistema de proveedores."* → corregida: *"Las credenciales del proveedor, incluida la contraseña temporal, se gestionan exclusivamente en el proveedor de identidad (Keycloak); el sistema de proveedores no almacena contraseñas ni sus hashes."*
- **RF-02**: al quedar "Autorizado", el proveedor queda habilitado para acceder.
- **RF-03**: envío automático de usuario y contraseña temporal al autorizar.
- **RF-06**: cambio obligatorio de contraseña en primer acceso; mínimo 8 caracteres con al menos una letra, un número y un carácter especial.
- Roles: `ADMIN`, `PMO`, `PROVIDER` (ya existen en el modelo `User.role`).

Hallazgos de la auditoría técnica (2026-09-22) que este cambio **debe cerrar o no empeorar**: SEC-01 (SECRET_KEY por defecto), SEC-03 (credenciales demo en el HTML), SEC-04 (sin bloqueo por fuerza bruta), SEC-07 (logout sólo del lado cliente), SEC-08 (sin política de contraseñas en servidor), BD-03 (Alembic con `create_all`).

## Reglas de trabajo (obligatorias)

- **Ramas:** el flujo es `main → qa → dev → rama por HU`. Crea una rama desde `dev` (propuesta: `hu-auth-keycloak`). No hagas `push`, no hagas merge, no toques `qa` ni `main`.
- **Commits separados:** (1) specs OpenSpec, (2) corrección de nomenclatura, (3) implementación Keycloak, (4) pruebas. Mensajes en español, formato Conventional Commits.
- **Quality gate:** el código debe poder pasar SonarQube en `qa`. Nada de secretos hardcodeados, ni valores por defecto para secretos, ni credenciales en plantillas o README.
- **No reescribas `alembic/versions/0001_initial.py`.** Cualquier cambio de esquema va en una revisión nueva con operaciones explícitas (`op.batch_alter_table` para SQLite).
- **No amplíes el alcance:** no arregles otros hallazgos de la auditoría salvo los listados arriba. Si ves algo más, anótalo en el reporte final.
- **Puntos de parada:** detente y pregúntame en los `🛑 STOP` marcados abajo. No asumas la respuesta.

---

## Fase 0 — Descubrimiento (sin modificar nada)

1. Verifica si OpenSpec está inicializado (`openspec/` con `project.md`, `specs/`, `changes/`). Si no lo está, ejecuta `openspec init` y rellena `openspec/project.md` con el stack, las convenciones de ramas y los roles descritos arriba.
2. Ejecuta `openspec list` y `openspec list --specs` para conocer cambios y capacidades existentes.
3. Busca **todas** las variantes del nombre erróneo, incluidas mayúsculas, espacios y guiones, en código, plantillas, `.md`, `.env*`, YAML, comentarios y tests:
   ```bash
   rg -n -i "click[\s_-]*(cloud|clock)" --hidden -g '!.git'
   ```
   Para archivos `.docx`/`.pdf` del repo, extrae el texto (p. ej. `python -c` con `python-docx`) y busca también ahí. Busca además la frase **"gestor de secretos"** / **"secret manager"**, que también debe corregirse.
4. Inventaria el código de autenticación actual: `app/core/security.py`, `app/core/config.py`, `app/routers/auth.py`, `app/routers/admin.py` (alta de usuarios), `app/main.py` (middlewares), `app/templates/auth/login.html`, `app/static/js/app.js`, `scripts/seed_db.py`, `tests/conftest.py`, `tests/test_auth*.py`, `tests/test_permissions.py`, el modelo `User` y cualquier dependencia `get_current_user` / `require_role`.
5. Entrégame un **reporte de descubrimiento**: lista de ocurrencias del nombre erróneo (archivo:línea), mapa del flujo de auth actual, y qué puntos de la app dependen de `password_hash`.

🛑 **STOP 1** — espera mi confirmación del reporte antes de escribir specs.

---

## Fase 1 — Cambios OpenSpec

Crea **dos** cambios. El segundo depende del primero.

### Cambio 1: `correct-identity-provider-naming`

**`openspec/changes/correct-identity-provider-naming/proposal.md`**

```markdown
## Why
Las fuentes de verdad (ERS v1.3, HUs, minuta) nombran "ClickCloud" como gestor de secretos
para la contraseña temporal del proveedor. Es un error de transcripción originado en notas de
trabajo: el componente real es Keycloak, que además es un proveedor de identidad (IdP), no un
gestor de secretos. El error distorsiona RN-HU03-01 y el diseño de autenticación.

## What Changes
- Reemplazar "ClickCloud" y variantes por "Keycloak" en todo el repositorio.
- Reemplazar la categoría "gestor de secretos" por "proveedor de identidad (IdP)" donde aplique.
- Reformular RN-HU03-01: las credenciales viven sólo en Keycloak; el sistema no almacena contraseñas ni hashes.
- Registrar la corrección en el control de versiones de la ERS (propuesta: v1.4).

## Impact
- Specs afectadas: `supplier-onboarding`
- Documentación: ERS, glosario, restricciones (2.4), suposiciones (2.5), interfaces externas (3.3), RNF de seguridad (3.4), tabla de RN (3.5)
- Sin cambios de comportamiento en código.
```

**`openspec/changes/correct-identity-provider-naming/specs/supplier-onboarding/spec.md`**
Usa `## MODIFIED Requirements` si la capacidad ya existe en `openspec/specs/`; si no existe, usa `## ADDED Requirements`.

```markdown
## ADDED Requirements

### Requirement: Custodia de credenciales del proveedor en el IdP
El sistema SHALL delegar la gestión de credenciales del proveedor, incluida la contraseña
temporal, al proveedor de identidad Keycloak, y SHALL NOT persistir contraseñas ni hashes de
contraseña en la base de datos del portal. (RN-HU03-01, corregida)

#### Scenario: Alta de proveedor autorizado
- **WHEN** un proveedor pasa a estatus "Autorizado"
- **THEN** su cuenta y credencial temporal se crean en Keycloak
- **AND** la base de datos del portal no contiene ninguna contraseña ni hash para ese proveedor

#### Scenario: Consulta de la base de datos del portal
- **WHEN** se inspecciona la tabla de usuarios del portal
- **THEN** no existe ningún valor de contraseña o hash utilizable para autenticar
```

**`tasks.md`**
```markdown
## 1. Corrección de nomenclatura
- [ ] 1.1 Reemplazar "ClickCloud"/"ClickClock"/variantes por "Keycloak" en archivos de texto
- [ ] 1.2 Reemplazar "gestor de secretos" por "proveedor de identidad (IdP)" donde se refiera a este componente
- [ ] 1.3 Actualizar documentos .docx del repo con python-docx preservando formato (o listar para edición manual si no es posible)
- [ ] 1.4 Añadir fila v1.4 al control de versiones de la ERS describiendo la corrección
- [ ] 1.5 Verificar que `rg -i "click[\s_-]*(cloud|clock)"` no devuelve resultados
```

**Nota de edición:** no hagas `sed` ciego. Cada ocurrencia debe leerse en su frase: "resguardar en ClickCloud (gestor de secretos)" no se corrige con sólo cambiar el nombre, sino reescribiendo la frase al concepto correcto. Si un `.docx` no puede editarse preservando formato, **no lo regeneres**: lístalo en el reporte con el texto actual y el texto propuesto.

### Cambio 2: `add-keycloak-authentication`

**`proposal.md`**

```markdown
## Why
La autenticación local (formulario + Argon2 + cookie firmada) no cumple RN-HU03-01 corregida,
no aplica política de contraseñas en servidor (SEC-08), no bloquea fuerza bruta (SEC-04) y no
invalida sesiones en el servidor (SEC-07). Keycloak resuelve estos puntos de forma nativa y
cubre RF-02, RF-03 y RF-06.

## What Changes
- **BREAKING**: se elimina el login local por contraseña; la autenticación pasa a OIDC
  Authorization Code + PKCE contra Keycloak.
- Los roles ADMIN/PMO/PROVIDER se leen de realm roles de Keycloak.
- La autorización por proveedor (scoping por supplier_id) se mantiene en la BD local, enlazada por `sub`.
- Autorizar un proveedor (RF-02) crea/habilita su usuario en Keycloak con credencial temporal (RF-03).
- Primer acceso fuerza cambio de contraseña con la política de RF-06, aplicada por Keycloak.
- Logout termina la sesión en Keycloak (end_session_endpoint).
- Entorno local de Keycloak con realm versionado (sin secretos) para desarrollo.

## Impact
- Specs: `authentication`, `supplier-onboarding`
- Código: config, security, routers/auth, routers/admin, main, plantillas de login, seed, tests
- Esquema: nueva columna `users.keycloak_sub` (UNIQUE); `password_hash` pasa a nullable y queda deprecada
- Dependencias: Authlib (cliente OIDC); httpx pasa a ser dependencia de producción
```

**`specs/authentication/spec.md`**

```markdown
## ADDED Requirements

### Requirement: Inicio de sesión mediante Keycloak (OIDC)
El sistema SHALL autenticar a todos los usuarios mediante el flujo OIDC Authorization Code
con PKCE (S256) contra Keycloak, y SHALL NOT aceptar credenciales en un formulario propio.

#### Scenario: Usuario no autenticado accede a una ruta protegida
- **WHEN** un usuario sin sesión solicita una ruta protegida
- **THEN** es redirigido al endpoint de autorización de Keycloak con `state`, `nonce` y `code_challenge`

#### Scenario: Callback válido
- **WHEN** Keycloak redirige al callback con un `code` y un `state` que coinciden con la sesión
- **THEN** el sistema intercambia el código, valida firma (JWKS), `iss`, `aud`, `exp` y `nonce` del ID token
- **AND** crea la sesión local con el usuario enlazado por `sub`

#### Scenario: Callback con state o nonce inválido
- **WHEN** el `state` o el `nonce` no coinciden
- **THEN** el sistema rechaza el inicio de sesión con 400 y no crea sesión

### Requirement: Autorización por roles de Keycloak
El sistema SHALL derivar el rol del usuario (ADMIN, PMO, PROVIDER) de los realm roles del token,
y SHALL mantener el aislamiento por proveedor usando el `supplier_id` de la BD local, no del token.

#### Scenario: Usuario sin rol reconocido
- **WHEN** el token no contiene ninguno de los roles ADMIN, PMO o PROVIDER
- **THEN** el acceso se deniega con 403

#### Scenario: Proveedor consulta factura de otro proveedor
- **WHEN** un usuario PROVIDER solicita una factura o documento de otro proveedor
- **THEN** el sistema responde 404, igual que antes de la migración

#### Scenario: Usuario desactivado localmente
- **WHEN** un usuario con sesión válida tiene `is_active = false` en la BD local
- **THEN** el acceso se deniega en la siguiente petición

### Requirement: Política de contraseñas y primer acceso
Keycloak SHALL exigir cambio de contraseña en el primer acceso y SHALL aplicar la política:
mínimo 8 caracteres, al menos una letra, un número y un carácter especial. (RF-06)

#### Scenario: Primer acceso con contraseña temporal
- **WHEN** un proveedor inicia sesión con su contraseña temporal
- **THEN** Keycloak le exige definir una nueva contraseña antes de volver al portal

#### Scenario: Contraseña que no cumple la política
- **WHEN** la nueva contraseña no contiene un carácter especial
- **THEN** Keycloak la rechaza y no completa el inicio de sesión

### Requirement: Protección contra fuerza bruta
El realm SHALL tener activa la detección de fuerza bruta con bloqueo temporal tras intentos fallidos.

#### Scenario: Intentos fallidos repetidos
- **WHEN** una cuenta acumula 5 intentos fallidos consecutivos
- **THEN** Keycloak bloquea temporalmente la cuenta

### Requirement: Cierre de sesión
El logout SHALL limpiar la sesión local y SHALL terminar la sesión SSO en Keycloak.

#### Scenario: Logout
- **WHEN** el usuario cierra sesión
- **THEN** la sesión local se elimina y el navegador es redirigido al `end_session_endpoint` de Keycloak
- **AND** una nueva visita a una ruta protegida exige autenticarse de nuevo
```

**`specs/supplier-onboarding/spec.md`**

```markdown
## ADDED Requirements

### Requirement: Aprovisionamiento del proveedor autorizado en Keycloak
Al autorizar proveedores (individual o masivamente), el sistema SHALL crear o habilitar su usuario
en Keycloak con rol PROVIDER, credencial temporal y acción requerida de cambio de contraseña,
y SHALL enlazar el `sub` resultante con el registro local. (RF-02, RF-03)

#### Scenario: Autorización masiva
- **WHEN** el administrador autoriza N proveedores en una operación
- **THEN** cada proveedor tiene un usuario habilitado en Keycloak con rol PROVIDER
- **AND** cada proveedor recibe un correo de acceso (según la decisión D1 de design.md)

#### Scenario: Fallo parcial al aprovisionar
- **WHEN** Keycloak rechaza la creación de uno de los proveedores
- **THEN** los demás se procesan, el fallido queda sin autorizar y el error se registra en auditoría

#### Scenario: Proveedor ya existente en Keycloak
- **WHEN** el correo del proveedor ya existe como usuario en Keycloak
- **THEN** el sistema enlaza el usuario existente en lugar de duplicarlo
```

**`design.md`** — debe contener como mínimo:

- **Contexto y objetivos / no-objetivos.** No-objetivos: sesiones server-side completas (SEC-07 queda parcialmente cubierto por el logout en Keycloak), migración a PostgreSQL, SSO con terceros.
- **Arquitectura:**
  - Client `portal-facturas-web`: confidential, Standard Flow, PKCE S256, redirect URI `/auth/callback`, post-logout redirect URI.
  - Client `portal-facturas-admin`: sólo service account, con los roles de `realm-management` estrictamente necesarios (`manage-users`, `view-users`, `query-users`) para el aprovisionamiento.
  - Realm roles `ADMIN`, `PMO`, `PROVIDER`.
  - Password policy del realm: `length(8) and digits(1) and specialChars(1) and regexPattern(.*[A-Za-z].*) and notUsername`.
  - Brute force detection activado.
- **Sesión:** la cookie firmada guarda sólo `user_id`, `csrf_token` y lo imprescindible para el logout. **Nunca** access/refresh tokens en la cookie (va firmada, no cifrada). El CSRF existente se conserva y se rota al iniciar sesión.
- **Configuración:** `KEYCLOAK_SERVER_URL`, `KEYCLOAK_REALM`, `KEYCLOAK_CLIENT_ID`, `KEYCLOAK_CLIENT_SECRET`, `KEYCLOAK_ADMIN_CLIENT_ID`, `KEYCLOAK_ADMIN_CLIENT_SECRET`. Los secretos **sin valor por defecto** y con validador que impida arrancar sin ellos (misma lección que SEC-01). Aprovecha para quitar el default de `SECRET_KEY`.
- **Datos:** revisión Alembic nueva: `users.keycloak_sub` (String, UNIQUE, nullable al inicio); `password_hash` pasa a nullable. El borrado de `password_hash` queda para un cambio posterior, una vez migrados todos los usuarios.
- **Migración de usuarios existentes:** script idempotente que crea/enlaza en Keycloak los usuarios locales por email, con credencial temporal y acción requerida `UPDATE_PASSWORD`.
- **Entorno local:** `docker-compose` con Keycloak (imagen oficial, versión concreta fijada, verifica la estable vigente) en `start-dev --import-realm`, con el realm exportado en `infra/keycloak/realm-ultrasist-portal.json`. El JSON **no** contiene secretos de clientes ni contraseñas de usuarios reales; los usuarios demo sólo existen en el realm de desarrollo.
- **Decisiones abiertas** (D1–D4, ver abajo) con alternativas y trade-offs.
- **Riesgos:** caída de Keycloak = nadie entra (documentar); desfase de reloj en validación de `exp`; SQLite + nueva migración sobre un Alembic defectuoso (BD-03).

**Decisiones abiertas para `design.md`:**

- **D1 — Correo de acceso (RF-03).** La HU-03 pide literalmente enviar *usuario y contraseña temporal* por correo.
  - *A (literal):* el portal genera la contraseña temporal, la registra en Keycloak con `temporary=true` y la envía con la plantilla de RF-05 al destinatario de RF-13. La contraseña existe sólo en memoria durante la petición; nunca se persiste ni se loguea.
  - *B (recomendada por seguridad):* Keycloak envía un enlace de acción (`execute-actions-email` con `UPDATE_PASSWORD`); no viaja ninguna contraseña por correo. Requiere ajustar la redacción de RF-03 con negocio.
- **D2 — SMTP:** ¿correos de Keycloak por el mismo SMTP del portal o uno propio?
- **D3 — Despliegue:** ¿Keycloak compartido de Ultrasist o instancia dedicada? Nombre definitivo de realm y clientes.
- **D4 — Sesión Keycloak:** duración de la sesión SSO y del idle timeout (hoy la cookie local dura 8 h).

**`tasks.md`**

```markdown
## 1. Infraestructura local
- [ ] 1.1 docker-compose con Keycloak (versión fijada) e import del realm
- [ ] 1.2 Realm export: roles, clients, password policy, brute force, sin secretos
- [ ] 1.3 .env.example con variables KEYCLOAK_* sin valores sensibles

## 2. Configuración
- [ ] 2.1 Settings KEYCLOAK_* obligatorios con validadores
- [ ] 2.2 Quitar default de SECRET_KEY y rechazar el placeholder

## 3. Datos
- [ ] 3.1 Revisión Alembic nueva: users.keycloak_sub UNIQUE, password_hash nullable
- [ ] 3.2 Script idempotente de migración/enlace de usuarios existentes

## 4. Autenticación
- [ ] 4.1 Cliente OIDC (Authlib) con PKCE S256, state y nonce
- [ ] 4.2 Rutas /login (redirect), /auth/callback, /logout (end_session)
- [ ] 4.3 get_current_user y require_role basados en sesión + BD local (roles desde token al iniciar sesión)
- [ ] 4.4 Eliminar formulario de login local, botones demo (data-demo) y su JS

## 5. Aprovisionamiento
- [ ] 5.1 Servicio keycloak_admin (service account): crear/habilitar usuario, asignar rol, credencial temporal
- [ ] 5.2 Integrar en la autorización individual y masiva de proveedores (RF-02)
- [ ] 5.3 Correo de acceso según D1, usando plantillas RF-05 y destinatarios RF-13
- [ ] 5.4 Alta de usuarios ADMIN/PMO desde admin vía Keycloak (quitar password del formulario)
- [ ] 5.5 Auditoría de cada aprovisionamiento y de sus fallos

## 6. Pruebas
- [ ] 6.1 Mock del IdP (JWKS y tokens firmados de prueba); sin Keycloak real en pytest
- [ ] 6.2 Callback válido, state inválido, nonce inválido, token expirado, aud incorrecta
- [ ] 6.3 Rol ausente → 403; usuario inactivo → sin acceso
- [ ] 6.4 Regresión RBAC: proveedor no ve facturas/documentos de otro proveedor
- [ ] 6.5 Aprovisionamiento: éxito, fallo parcial, usuario ya existente (cliente admin mockeado)
- [ ] 6.6 Ninguna contraseña persistida ni en logs tras el aprovisionamiento

## 7. Documentación
- [ ] 7.1 README: levantar Keycloak local, variables, flujo de login, cómo crear usuarios
- [ ] 7.2 Eliminar credenciales demo del README
```

### Validación de specs

```bash
openspec validate correct-identity-provider-naming --strict
openspec validate add-keycloak-authentication --strict
openspec show add-keycloak-authentication
```

Corrige hasta que ambas validen sin errores. Recuerda el formato: cada `### Requirement:` necesita al menos un `#### Scenario:` (con cuatro `#`), y cada requirement usa SHALL/MUST.

🛑 **STOP 2** — muéstrame los dos cambios validados y **pregúntame D1–D4**. No implementes hasta tener respuestas; actualiza `design.md` y, si D1 = B, el requirement correspondiente.

---

## Fase 2 — Implementación

1. Aplica `correct-identity-provider-naming` (commit propio). Verifica que la búsqueda de variantes devuelve cero resultados.
2. Implementa `add-keycloak-authentication` siguiendo `tasks.md` en orden, marcando cada casilla `[x]` al terminarla.
3. Reglas de implementación:
   - Captura errores del Admin API de Keycloak y tradúcelos a respuestas 4xx/5xx controladas; nunca dejes que un error de red produzca un traceback.
   - Timeouts explícitos en todas las llamadas HTTP a Keycloak.
   - No loguees tokens, contraseñas temporales ni el cuerpo de respuestas del token endpoint.
   - Mantén la separación de capas existente: routers como traducción HTTP; la lógica de aprovisionamiento en `services/`.
   - Las pruebas no deben requerir Keycloak ni red.

## Fase 3 — Verificación y reporte

```bash
pytest -q
ruff check . && ruff format --check .   # si ruff está disponible
rg -n -i "click[\s_-]*(cloud|clock)" --hidden -g '!.git'
rg -n -i "password_hash|hash_password|verify_password" app/
openspec validate --strict
```

Entrega un reporte final con:
- Resumen de cambios por commit.
- Estado de `tasks.md` de ambos cambios.
- Resultado de pruebas y validación OpenSpec.
- Hallazgos de la auditoría cerrados (SEC-01, SEC-03, SEC-04, SEC-08) y parcialmente cubiertos (SEC-07).
- Ocurrencias en `.docx` que no pudiste corregir, con texto actual → propuesto.
- Riesgos pendientes y cualquier problema fuera de alcance que hayas detectado.

No ejecutes `openspec archive` hasta que yo lo apruebe después de la revisión en `dev`.
