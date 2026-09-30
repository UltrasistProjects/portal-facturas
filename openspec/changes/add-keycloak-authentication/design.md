> Rutas relativas a la raíz de la PoC (`PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress-V1/PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress/`), salvo `openspec/` y `docs/`.

## Context

**Autenticación actual:**
- `POST /login`: CSRF → `login_throttle.check` (5 fallos por correo con bloqueo exponencial hasta 60 min; 20 fallos por IP en 15 min) → Argon2 contra `users.password_hash` → `session_service.create`.
- La cookie firmada lleva sólo `sid` y `csrf_token`. `user_sessions` guarda el SHA-256 del `sid`, con 60 min de inactividad y 8 h de duración máxima.
- Dependencias: `get_authenticated_user` → `get_current_user` (redirige a `/account/password` si `must_change_password`) → `require_roles`.
- HU-10: `/account/password` con la política de `app/core/passwords.py` (8–128 caracteres, letra, número, carácter especial, lista de comunes).
- HU-02/03: `supplier_access_service.authorize()` crea el usuario `Proveedor` con una contraseña temporal (hash + marca), la entrega al `secret_vault` nulo, confirma y envía el correo `SUPPLIER_CREDENTIALS` con la contraseña en claro. `resend_credentials()` repite el proceso.
- `/admin/users` crea usuarios con una contraseña que teclea el Administrador. `toggle` revoca las sesiones al deshabilitar.
- Roles: `Administrador`, `Proveedor`, `PMO` (commit `431b550`). `CHECK ck_users_provider_supplier` liga `Proveedor` con `supplier_id`.
- Base: PostgreSQL 18 en `compose.yaml`. Última revisión Alembic: `0014_business_role_names`.

**Hallazgos de la auditoría:** SEC-01, SEC-03, SEC-04, SEC-07, SEC-08 y BD-03 ya están cerrados (cambio archivado `2026-09-24-remediar-auditoria-tecnica`). La restricción de este cambio es **no reabrir ninguno**.

## Goals / Non-Goals

**Goals:**
- Que el portal no reciba, guarde ni verifique contraseñas de usuario (RN-HU03-01 corregida).
- Conservar cada control existente, trasladado a Keycloak o mantenido en el portal: sesiones del servidor, fuerza bruta, política, primer acceso, CSRF y cabeceras.
- Autorizar proveedores con aprovisionamiento en Keycloak y tolerar fallos parciales (RF-02, RF-03).
- Que el entorno local levante Keycloak sin secretos versionados y que las pruebas no necesiten Keycloak ni red.

**Non-Goals:**
- Eliminar `password_hash` y `must_change_password` (cambio de limpieza posterior, cuando todos los usuarios estén enlazados).
- Back-channel logout de Keycloak hacia el portal.
- SSO con proveedores externos (Azure AD, Google), recuperación de contraseña desde el portal y rotación periódica (HU-11).
- Sincronizar hacia Keycloak un cambio del correo del proveedor en el catálogo.
- Límite de intentos por IP (ver Riesgos).

## Decisiones de negocio (D1–D4, resueltas el 2026-09-30)

| | Decisión | Efecto en los specs |
|---|---|---|
| D1 | **A**: contraseña temporal por correo (literal HU-03) | ninguno: los specs ya la usan |
| D2 | **El mismo SMTP del portal** para los correos de Keycloak | ninguno: es configuración de despliegue (ver D2) |
| D3 | **Instancia dedicada**: realm `ultrasist-portal`, clientes `portal-facturas-web` y `portal-facturas-admin`, realm roles | ninguno |
| D4 | **Igual a la sesión local**: 60 min de inactividad, 8 h de máximo, sin "Recordarme" | ninguno |

A continuación, las alternativas que se evaluaron.

### D1. Correo de acceso (RF-03)
HU-03 pide literalmente enviar *usuario y contraseña temporal* por correo.

- **A (literal, elegida):** el portal genera la contraseña temporal (`generate_password`, 20 caracteres, cumple la política), la registra en Keycloak con `temporary=true` y la envía con la plantilla `SUPPLIER_CREDENTIALS` (RF-05) al correo del proveedor (RF-13). La contraseña existe sólo en memoria durante la petición: no se persiste ni se escribe en el log. Para los usuarios internos que da de alta el Administrador, la contraseña temporal se muestra una única vez en la respuesta del alta (`Cache-Control: no-store`), que es el equivalente a hoy, cuando el Administrador la teclea.
  - *A favor:* cumple la HU al pie de la letra; no requiere SMTP en Keycloak; conserva las plantillas.
  - *En contra:* una contraseña viaja por correo (mitigado: es temporal y Keycloak exige cambiarla en el primer uso).
- **B (recomendada por seguridad, descartada):** Keycloak envía un enlace de acción (`PUT /users/{id}/execute-actions-email` con `UPDATE_PASSWORD` y vigencia configurable). No viaja ninguna contraseña.
  - *A favor:* ningún secreto en correo; el enlace caduca.
  - *En contra:* hay que ajustar la redacción de RF-03 con negocio; el correo lo compone Keycloak (su tema, no la plantilla RF-05, que dejaría de aplicar a este evento); requiere SMTP en Keycloak (D2).
  - *Specs a cambiar:* `acceso-proveedores` ("Correo de credenciales", "Usuario y contraseña temporal al autorizar", "Reenvío de credenciales", texto de confirmación de "Selección de proveedores en el listado"), `plantillas-notificacion` (retirar o reconvertir `SUPPLIER_CREDENTIALS`) y `administracion-usuarios` (alta).

### D2. SMTP de Keycloak
- **Decidido:** Keycloak usa el mismo servidor y remitente que el portal.
- Con D1 = A, hoy Keycloak no envía ningún correo en el flujo del MVP. El SMTP queda configurado para cuando se habiliten correos de Keycloak ("olvidé mi contraseña", verificación de correo, enlaces de acción), sin decidirlo de nuevo.
- **QA y producción:** el `smtpServer` del realm toma `SMTP_HOST`, `SMTP_PORT`, `SMTP_SECURITY` (`starttls` → `starttls=true`, `ssl` → `ssl=true`), `SMTP_USERNAME` y `MAIL_FROM` del portal. La contraseña se configura en el servidor de Keycloak (consola o variable de entorno en la importación), nunca en el JSON versionado.
- **Desarrollo:** el realm versionado no declara `smtpServer`. En desarrollo el portal usa el transporte `file` (sin servidor SMTP) y Keycloak no tiene correos que enviar.
- Alternativa descartada: una cuenta propia de Keycloak.

### D3. Despliegue, realm y clientes
- **Decidido:** instancia de Keycloak dedicada, realm `ultrasist-portal`, clientes `portal-facturas-web` y `portal-facturas-admin`, roles como realm roles. La instancia debe tener `common_passwords.txt` en `data/password-blacklists/` (D17) y, frente a ella, *rate limiting* por IP en el proxy inverso (ver Riesgos).
- Alternativa descartada, Keycloak compartido con otras aplicaciones de Ultrasist, que habría exigido:
  - los roles deben pasar a **roles del cliente** `portal-facturas-web`, para no chocar con un realm role `Administrador` ajeno; el claim leído cambia de `realm_access.roles` a `resource_access.portal-facturas-web.roles`;
  - la cuenta de servicio sólo debería poder gestionar los usuarios del portal (Fine-Grained Admin Permissions v2), no todos los del realm;
  - el archivo de la lista de contraseñas comunes (D17) debe instalarse en ese servidor.

### D4. Duración de la sesión en Keycloak
- **Decidido:** `ssoSessionIdleTimeout` = 3600 s y `ssoSessionMaxLifespan` = 28800 s, iguales a la sesión local; `rememberMe: false`.
- Alternativa descartada: una sesión SSO más larga. Si la sesión SSO durara más que la local, al vencer la local el usuario volvería a entrar sin teclear nada (SSO silencioso). En la práctica, el límite efectivo sería el de Keycloak.

## Decisions

### D5. Cliente OIDC con Authlib
Se usa la integración de Starlette de Authlib (versión estable al implementar; hoy 1.8.0), con `server_metadata_url` apuntando al *discovery* del realm y `code_challenge_method="S256"`.

Authlib guarda `state`, `nonce` y `code_verifier` en `request.session` sólo durante el viaje de ida y vuelta, y el callback los consume. Son valores efímeros de un único uso, no tokens.

*Alternativa:* implementarlo a mano con httpx y joserfc. Se descarta: más superficie propia en la parte más sensible.

### D6. Validación del callback
Con `authorize_access_token` + `parse_id_token`:
- firma con el JWKS del realm (Authlib refresca las claves si cambia el `kid`);
- `iss` igual al emisor del *discovery*;
- `aud` contiene `KEYCLOAK_CLIENT_ID`;
- `exp` vigente con una tolerancia de 60 s;
- `nonce` igual al de la petición;
- `state` igual al guardado (lo valida Authlib).

Cualquier fallo responde 400 con la página genérica, sin crear sesión, y audita `LOGIN_FAILED` con un motivo (`state`, `nonce`, `token`, `idp_error`), nunca con el token ni el código. El access token y el refresh token se descartan: el portal no llama APIs en nombre del usuario.

### D7. Enlace por `sub`, nunca por correo en el login
El callback busca `users.keycloak_sub == sub`. Si no existe, responde 403 "Su cuenta no está habilitada en el portal." El callback no enlaza por correo: si alguien cambiara su correo en Keycloak por el de otro usuario del portal, se apoderaría de su cuenta. El enlace sólo ocurre al aprovisionar (D12, D13), en el alta de usuarios (D15) y en el script de migración (D16), todos bajo control del portal.

### D8. Rol: el del token debe coincidir con el local
Los realm roles `Administrador`, `Proveedor` y `PMO` usan los mismos valores que `Role`. El realm agrega un *mapper* para que viajen en el ID token (`realm_access.roles`). Los demás roles (`offline_access`, `default-roles-…`) se ignoran.

En el login, el token debe traer **exactamente uno** de los tres, **igual** a `users.role`. Si no, 403 y `LOGIN_DENIED` (`role_missing` o `role_mismatch`). `require_roles` sigue leyendo `users.role`.

*Alternativa:* el token manda y el rol local se sincroniza en cada login. Se descarta porque el `CHECK` rol–proveedor y el alta viven en el portal: un cambio de rol hecho sólo en Keycloak escalaría privilegios en silencio (por ejemplo, un `Proveedor` convertido en `Administrador`). Con la coincidencia obligatoria, cambiar un rol exige cambiarlo en los dos lados.

### D9. Sesiones: se conserva `user_sessions`
El callback:
1. revoca el `sid` previo;
2. `request.session.clear()` (rota el CSRF);
3. crea una sesión nueva con `session_service.create`;
4. guarda el ID token en `user_sessions.id_token_hint`, del lado del servidor, para usarlo como `id_token_hint` en el logout;
5. actualiza `last_login_at` y audita `LOGIN_SUCCESS`.

Los tiempos siguen igual (60 min / 8 h). Cada petición se valida contra la BD local, sin llamar a Keycloak.

*Alternativas:*
- ID token en la cookie: la cookie va firmada, no cifrada. Se descarta.
- Logout sólo con `client_id`: Keycloak muestra una página de confirmación. Se descarta.

### D10. Logout y deshabilitación
- **`POST /logout`** (CSRF):
  - revoca la sesión local y audita `LOGOUT`;
  - responde 303 a `end_session_endpoint?id_token_hint=…&post_logout_redirect_uri=<raíz del portal>`;
  - si no hay *discovery*, igual revoca y redirige a `/`.
- **CSP:** Chrome aplica `form-action` también a las redirecciones que siguen a un POST, así que la CSP agrega el origen de `KEYCLOAK_SERVER_URL` a `form-action`.
- **Deshabilitar un usuario** (`toggle`):
  - el portal lo desactiva localmente y revoca sus sesiones siempre;
  - después, *best-effort*: `enabled=false` y `POST /users/{id}/logout` en Keycloak;
  - si Keycloak falla, el usuario igual queda sin acceso (el callback exige `is_active`); se audita `IDP_SYNC_FAILED` y se avisa al Administrador.
- **Habilitar:** primero Keycloak y después local. Si Keycloak falla, 503 y nada cambia.

### D11. Servicio `keycloak_admin`
`app/services/keycloak_admin.py` define un protocolo `IdentityAdmin` y su implementación HTTP. Las pruebas inyectan un falso con `get_identity_admin()`, igual que hoy `get_vault()`.

- **Token de la cuenta de servicio:** *client credentials* con `portal-facturas-admin`, en caché en memoria hasta 30 s antes de expirar.
- **Timeout:** explícito (`KEYCLOAK_TIMEOUT`, 10 s por omisión) en todas las llamadas.
- **Errores:** conexión, timeout, 5xx y 4xx inesperados se traducen a `IdentityProviderError` (hereda de `BusinessRuleError`, HTTP 503, "El servicio de identidad no está disponible. Intente más tarde."). Nunca provocan un traceback. Se registran sólo la operación, el código HTTP y la duración, nunca el cuerpo.
- **Operaciones:**
  - `find_by_email` (`exact=true`)
  - `create_user`: `username` = `email` = correo en minúsculas, `enabled`, `emailVerified=true`, nombre; el `sub` se toma del `Location`
  - `realm_roles_of` / `assign_realm_role`
  - `set_temporary_password`: `reset-password` con `temporary=true`
  - `require_update_password`
  - `get_user`, para leer `requiredActions`
  - `set_enabled`, `logout_user`
- **Permisos de la cuenta de servicio:** sólo `realm-management`: `manage-users`, `view-users` y `query-users`.

`secret_vault.py` se elimina: su papel (entregar la contraseña al IdP antes del commit) lo cumple `set_temporary_password`.

### D12. Aprovisionamiento en la autorización masiva
Cada proveedor "Registrado" se procesa dentro de un *savepoint* (`db.begin_nested()`):
1. cambio de estatus;
2. usuario local;
3. llamadas a Keycloak: crear o enlazar (D13), rol `Proveedor`, contraseña temporal y `UPDATE_PASSWORD`;
4. guardar el `keycloak_sub` y auditar.

Si Keycloak falla, se revierte **sólo ese savepoint**: el proveedor sigue "Registrado", se clasifica como `provisioning_failed` y se audita `SUPPLIER_PROVISIONING_FAILED` fuera del savepoint, con el código del error y sin cuerpos. Los demás proveedores continúan. Al final se confirma la transacción y después se envían los correos, igual que hoy.

*Riesgo cubierto por D13:* si la transacción final fallara después de crear usuarios en Keycloak, quedarían usuarios huérfanos allí. El siguiente intento los enlaza en lugar de duplicarlos.

### D13. Usuario ya existente en Keycloak
Si `find_by_email` encuentra un usuario:
- **Se enlaza** cuando (a) ningún usuario local tiene su `sub` y (b) sus realm roles reconocidos son ninguno o sólo `Proveedor`. Al enlazarlo se le asigna el rol, se le fija una contraseña temporal nueva y `UPDATE_PASSWORD`, y se envía el correo de acceso: el portal no conoce su contraseña anterior.
- **En otro caso** (tiene rol `Administrador` o `PMO`, o ya está enlazado a otro usuario local), el proveedor se trata como "correo en uso", igual que hoy con un usuario local de otro rol.

### D14. Estado de la contraseña y reenvío
- El expediente consulta `get_user(sub).requiredActions`:
  - con `UPDATE_PASSWORD` → "Temporal, pendiente de cambio";
  - sin ella → "Cambiada por el proveedor";
  - si Keycloak no responde → "No disponible", sin error de página.
- El listado de usuarios deja de mostrar "Contraseña temporal": exigiría una llamada por fila.
- El reenvío exige `UPDATE_PASSWORD` pendiente (misma regla de HU-10) y fija una contraseña temporal nueva en Keycloak, que invalida la anterior.
- `must_change_password` deja de leerse y escribirse.

### D15. Alta de usuarios internos
El formulario de `/admin/users` pierde el campo contraseña.

El alta:
1. valida como hoy;
2. crea el usuario local;
3. llama a Keycloak dentro de la transacción: crear o enlazar con la regla de D13 aplicada al rol pedido (por ejemplo, un `PMO` sólo se enlaza a un usuario sin roles o con rol `PMO`); asignar el rol; contraseña temporal y `UPDATE_PASSWORD`;
4. guarda el `sub`;
5. entrega la contraseña según D1.

Si Keycloak falla, 503 y no se crea nada.

### D16. Migración de datos y de usuarios existentes
Revisión `0015_keycloak_identity` (después de `0014_business_role_names`), con operaciones explícitas de PostgreSQL:
- `users.keycloak_sub VARCHAR(36)` nullable, con `UNIQUE` (`uq_users_keycloak_sub`);
- `users.password_hash` pasa a nullable;
- `user_sessions.id_token_hint TEXT` nullable;
- `DROP TABLE login_attempts`: son datos efímeros, con 24 h de retención. El downgrade la recrea vacía, con sus índices.
- El downgrade revierte el resto, salvo `password_hash NOT NULL` si hay filas nulas: en ese caso lanza `NotImplementedError` con la indicación de restaurar un respaldo.

`scripts/link_keycloak_users.py` (idempotente, con `--dry-run`) procesa cada usuario local sin `sub`:
1. busca en Keycloak por correo y enlaza con la regla de D13 (el rol esperado es el local), o crea el usuario con el rol local;
2. usuarios inactivos: se crean deshabilitados;
3. fija una contraseña temporal con `UPDATE_PASSWORD`;
4. guarda el `sub` y pone `password_hash = NULL`;
5. audita `USER_LINKED_TO_IDP`.

Entrega de las temporales: a los proveedores, por el correo de acceso; a los internos, se imprimen una sola vez en consola. Si se ejecuta dos veces, la segunda no toca a los ya enlazados.

### D17. Política de contraseñas del realm (RF-06, SEC-08)
```
length(8) and maxLength(128) and digits(1) and specialChars(1) and regexPattern(.*\p{L}.*)
and notUsername and notEmail and passwordHistory(1) and passwordBlacklist(common_passwords.txt)
```
- `passwordHistory(1)` sustituye a "distinta de la actual".
- La lista de comunes es el mismo `app/core/common_passwords.txt`, montado en el contenedor en `/opt/keycloak/data/password-blacklists/`.
- Keycloak compara la lista sin distinguir mayúsculas, pero sólo con la contraseña completa. Se pierde la detección de "palabra común decorada" (letras de `Summer2026!` en la lista). Se acepta: Keycloak aplica además `notUsername` y `notEmail`.

### D18. Fuerza bruta (SEC-04)
`bruteForceProtected: true`, `failureFactor: 5`, `bruteForceStrategy: MULTIPLE`, `waitIncrementSeconds: 60`, `maxFailureWaitSeconds: 3600`, `maxDeltaTimeSeconds: 86400`, `permanentLockout: false`. Equivale a lo local: 5 fallos, espera creciente, tope de 60 min y ventana de 24 h. El límite por IP no tiene equivalente en Keycloak (ver Riesgos).

### D19. Cambio voluntario de contraseña
"Cambiar contraseña" (menú) → `GET /account/password` → redirección al endpoint de autorización con `kc_action=UPDATE_PASSWORD` (Application Initiated Action). El regreso pasa por el callback normal: sesión nueva, CSRF nuevo. Con `kc_action_status=success` se audita `PASSWORD_CHANGED` (`forced: false`).

El cambio forzado del primer acceso ocurre dentro de Keycloak y queda en sus eventos: el realm activa `eventsEnabled` con `UPDATE_PASSWORD`, `LOGIN_ERROR` y `USER_DISABLED_BY_TEMPORARY_LOCKOUT`.

### D20. Configuración
Variables nuevas:

| Variable | Default | Validación |
|---|---|---|
| `KEYCLOAK_SERVER_URL` | ninguno | obligatoria; en `production` debe ser `https://` |
| `KEYCLOAK_REALM` | ninguno | obligatoria |
| `KEYCLOAK_CLIENT_ID` | `portal-facturas-web` | — |
| `KEYCLOAK_CLIENT_SECRET` | ninguno | `SecretStr` obligatoria, ≥ 32 caracteres, rechaza `change-me…` |
| `KEYCLOAK_ADMIN_CLIENT_ID` | `portal-facturas-admin` | — |
| `KEYCLOAK_ADMIN_CLIENT_SECRET` | ninguno | igual que el secreto del cliente |
| `KEYCLOAK_TIMEOUT` | 10 | entre 1 y 60 |
| `KEYCLOAK_PORT` | 58080 | sólo para compose |
| `KC_BOOTSTRAP_ADMIN_USERNAME` / `_PASSWORD` | — | sólo para compose |
| `DEMO_PASSWORD` | — | sólo para el seed en `development`, debe cumplir la política |

`scripts/create_env.py` genera los dos secretos de cliente, la contraseña del administrador inicial de Keycloak y `DEMO_PASSWORD`, con la misma regla de hoy (añade sólo las claves ausentes). `SECRET_KEY` ya no tiene default (SEC-01 cerrado); no se toca.

### D21. Entorno local
- **Servicio `keycloak` en `compose.yaml`:**
  - imagen `quay.io/keycloak/keycloak:26.7.4` (estable vigente al 2026-09-30, versión fija; se actualiza por PR);
  - comando `start-dev --import-realm`;
  - volumen `keycloak-data` para `/opt/keycloak/data/h2`, de modo que los usuarios sobreviven a los reinicios;
  - puerto `127.0.0.1:${KEYCLOAK_PORT:-58080}:8080`;
  - `KC_BOOTSTRAP_ADMIN_*` desde `.env`, con `:?` si faltan;
  - healthcheck con `KC_HEALTH_ENABLED=true`.
- **Realm versionado** en `infra/keycloak/realm-ultrasist-portal.json`:
  - roles, clientes, *mapper*, política, fuerza bruta, eventos y tiempos de sesión;
  - redirect URIs `http://127.0.0.1:8000/auth/callback` y `http://localhost:8000/auth/callback`, y los post-logout equivalentes;
  - **sin secretos ni usuarios**: los secretos de cliente se escriben como `${KEYCLOAK_CLIENT_SECRET}` y `${KEYCLOAK_ADMIN_CLIENT_SECRET}`, marcadores que Keycloak sustituye con variables de entorno al importar.
- `run_local.*` levanta `db` y `keycloak` con `--wait`.
- El seed crea las cuentas demo en el realm con `DEMO_PASSWORD`. `app/core/demo.py` conserva los correos y etiquetas, sin contraseñas, y el README deja de publicarlas (SEC-03).

### D22. Keycloak no disponible
- `/login` con el *discovery* inaccesible → 503 "El servicio de autenticación no está disponible."
- Autorización, alta, reenvío y habilitación → 503 (D11).
- Las sesiones ya abiertas no dependen de Keycloak y siguen hasta expirar.
- `/health` no consulta Keycloak.

### D23. Pruebas sin Keycloak
- `tests/idp.py` genera un par de claves RSA por sesión, sirve un *discovery*, un JWKS y un token endpoint falsos mediante un transporte simulado del cliente HTTP (sin red), y firma ID tokens con los claims que pida cada prueba.
- `login()` de `conftest.py` recorre el flujo real (`/login` → callback) contra ese IdP.
- `FakeIdentityAdmin` reemplaza a `keycloak_admin` en memoria: registra las llamadas y permite simular fallos por correo.
- Una prueba carga el realm JSON y verifica política, fuerza bruta, roles, PKCE y ausencia de secretos.

## Risks / Trade-offs

- **[Keycloak caído → nadie inicia sesión nueva]** → sesiones abiertas intactas (D22), 503 controlados y README con el diagnóstico. En producción, Keycloak necesita alta disponibilidad y monitoreo (D3).
- **[Desfase de reloj en `exp`/`iat`]** → tolerancia de 60 s (D6); los servidores deben sincronizar con NTP.
- **[Sin límite por IP]** → la limitación por correo pasa a Keycloak, pero no la de 20 fallos por IP en 15 min. Mitigación en despliegue: *rate limiting* en el proxy inverso frente a Keycloak. Queda como pendiente de D3.
- **[Lista de comunes menos estricta]** → se pierde la detección de palabras decoradas (D17). Se acepta.
- **[Usuarios huérfanos en Keycloak]** si la transacción falla después de crearlos → D13 los enlaza en el siguiente intento.
- **[Roles desincronizados]** → la coincidencia obligatoria (D8) niega el acceso en lugar de escalar privilegios. El Administrador ve `LOGIN_DENIED` en la auditoría.
- **[Contraseña temporal por correo (D1 = A)]** → es temporal, con `UPDATE_PASSWORD` y la política; nunca se persiste ni se escribe en el log. D1 = B la elimina.
- **[ID token guardado en la BD]** → contiene nombre y correo, que ya están en `users`. Se purga con la sesión (7 días) y no autoriza llamadas a APIs.
- **[Reescritura amplia de pruebas]** → el helper `login()` concentra el cambio; los escenarios de aislamiento y RBAC se conservan como regresión.
- **[Migración sobre Alembic]** → BD-03 ya está resuelto (`0001_postgresql_baseline` explícita). `0015` sigue la regla de una revisión por cambio y `alembic check` la verifica.

## Migration Plan

1. Desplegar Keycloak con el realm (D3, D21) y crear los secretos de los clientes.
2. Configurar las variables `KEYCLOAK_*` y hacer un respaldo (`scripts/backup.py`).
3. `alembic upgrade head` (`0015`).
4. `python scripts/link_keycloak_users.py --dry-run`; revisar; ejecutar sin `--dry-run`.
5. Arrancar el portal. Todos los usuarios migrados deben cambiar su contraseña en el primer acceso.

**Rollback:** volver a la versión anterior del portal y `alembic downgrade 0014`. Los usuarios enlazados ya no tienen `password_hash`: el downgrade lo detecta y exige restaurar el respaldo del paso 2.

## Open Questions

- ¿Quién administra Keycloak en producción? Cambiar un rol exige hacerlo en el portal y en Keycloak (D8).
