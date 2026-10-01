## Why

RN-HU03-01, ya corregida por `correct-identity-provider-naming`, exige que las credenciales del proveedor se gestionen exclusivamente en el proveedor de identidad (Keycloak) y que el portal no guarde contraseñas ni sus hashes. Hoy el portal autentica por su cuenta: formulario `/login`, hash Argon2 en `users.password_hash` y un "resguardo" (`secret_vault`) con un adaptador nulo.

La remediación de la auditoría (2026-09-24) ya cerró SEC-01, SEC-03, SEC-04, SEC-07 y SEC-08 con controles locales: SECRET_KEY validada, credenciales demo sólo en `development`, limitación de intentos, sesiones del lado del servidor y política de contraseñas. Este cambio traslada esos controles a Keycloak **sin perder ninguno** y cubre RF-02, RF-03 y RF-06 con el IdP.

## What Changes

- **BREAKING:** se elimina el inicio de sesión local por contraseña. La autenticación pasa a OIDC Authorization Code + PKCE (S256) contra Keycloak. `GET /login` redirige a Keycloak, `GET /auth/callback` valida el ID token (firma JWKS, `iss`, `aud`, `exp`, `nonce`) y `POST /login` deja de existir.
- **Identidad y roles:** el usuario local se enlaza por el `sub` del token (`users.keycloak_sub`, único). El rol sale de los realm roles `Administrador`, `Proveedor` y `PMO`, y debe coincidir con `users.role`. El aislamiento por `supplier_id` sigue en la BD local.
- **Sesiones:** se conservan las sesiones revocables del servidor (`user_sessions`). El callback abre la sesión local y rota el identificador y el CSRF. Los access y refresh tokens no se guardan; el ID token se guarda sólo del lado del servidor, para el logout.
- **Logout:** revoca la sesión local y termina la sesión SSO en Keycloak (`end_session_endpoint`). Deshabilitar un usuario lo deshabilita también en Keycloak y cierra sus sesiones allí.
- **Aprovisionamiento (RF-02, RF-03):** autorizar proveedores crea o enlaza su usuario en Keycloak con el rol `Proveedor`, una credencial temporal y la acción requerida `UPDATE_PASSWORD`. Un fallo de Keycloak deja sin autorizar sólo a ese proveedor y se audita. El correo de acceso sigue la decisión abierta D1 de `design.md`; provisionalmente se usa la opción A (literal).
- **Primer acceso y política (RF-06):** los aplica Keycloak: acción requerida `UPDATE_PASSWORD` y política del realm equivalente a la local, incluida la lista de contraseñas comunes. "Cambiar contraseña" usa una acción iniciada por la aplicación (`kc_action=UPDATE_PASSWORD`). Se retiran `/account/password`, `login_throttle` y la validación local de contraseñas elegidas por el usuario.
- **Fuerza bruta:** la detección del realm (5 fallos, espera creciente, máximo 60 min) sustituye a la limitación por correo.
- **Alta de usuarios:** `/admin/users` crea el usuario en Keycloak y el formulario ya no pide contraseña.
- **Configuración:** variables `KEYCLOAK_*` obligatorias; los secretos no tienen valor por defecto y se validan al arrancar. `scripts/create_env.py` los genera para el entorno local.
- **Entorno local:** servicio `keycloak` en `compose.yaml` (26.7.4, `start-dev --import-realm`) con el realm versionado en `infra/keycloak/`, sin secretos. Los secretos de cliente entran por variables de entorno.
- **Credenciales demo:** salen del código y del README. El seed crea las cuentas demo en el realm de desarrollo con `DEMO_PASSWORD`, del `.env`.
- **Migración de usuarios:** un script idempotente enlaza o crea en Keycloak los usuarios locales y vacía su `password_hash`.

## Capabilities

### New Capabilities
<!-- Ninguna: el cambio reescribe capacidades existentes. -->

### Modified Capabilities
- `autenticacion-sesiones`: login OIDC, enlace por `sub`, roles del token, primer acceso, política y fuerza bruta en el realm, logout en Keycloak y auditoría de acceso. Se eliminan la limitación local de intentos, la política local, el cambio de contraseña local y su auditoría. Cambian las credenciales demo y las sesiones.
- `acceso-proveedores`: aprovisionamiento en Keycloak al autorizar, fallo parcial, enlace de usuarios existentes, custodia de credenciales en el IdP (RN-HU03-01), estado de la contraseña leído de Keycloak, reenvío contra Keycloak y auditoría del aprovisionamiento.
- `administracion-usuarios`: alta sin contraseña en el formulario, con el usuario creado en Keycloak; habilitación y deshabilitación sincronizadas.
- `configuracion-entorno`: variables `KEYCLOAK_*` obligatorias y generación de sus secretos en `create_env.py`.
- `infraestructura-local`: servicio Keycloak en Docker Compose y realm versionado sin secretos.
- `proteccion-http`: `form-action` de la CSP admite el origen de Keycloak (redirección del logout).
- `observabilidad`: tokens, códigos de autorización, secretos de cliente y contraseñas temporales fuera del log.
- `calidad-y-pruebas`: cobertura del flujo OIDC y del aprovisionamiento, y pruebas sin Keycloak ni red.

## Impact

- **Depende de** `correct-identity-provider-naming`: se aplica y archiva primero. Ambos modifican "Usuario y contraseña temporal al autorizar"; este cambio lleva su versión final.
- **Código** (relativo a la raíz de la PoC):
  - `app/core/config.py`, `app/core/security.py`, `app/core/startup.py`, `app/core/middleware.py` (CSP), `app/core/demo.py`, `app/main.py`;
  - `app/routers/auth.py`, `app/routers/admin.py`, `app/routers/suppliers.py`;
  - nuevos `app/services/keycloak_admin.py`, `app/services/oidc.py` e `app/services/identity_service.py`; `app/services/supplier_access_service.py` y `app/services/session_service.py`; `app/core/logging_config.py` (log de `httpx` sólo con advertencias);
  - se eliminan `app/services/secret_vault.py`, `app/services/login_throttle.py`, `app/templates/auth/login.html` y `app/templates/auth/change_password.html`;
  - `app/core/passwords.py` conserva sólo `generate_password`.
- **Plantillas y JS:** `base.html` (menú "Cambiar contraseña"), `admin/users.html` (sin contraseña), `suppliers/detail.html`; `static/js/app.js` pierde el acceso rápido demo.
- **Esquema:** revisión `0015_keycloak_identity`:
  - `users.keycloak_sub` (único, nullable);
  - `users.password_hash` pasa a nullable (obsoleta);
  - `user_sessions.id_token_hint`;
  - se elimina `login_attempts`.
  - `password_hash` y `must_change_password` se eliminan en un cambio posterior, cuando todos los usuarios estén enlazados.
- **Infraestructura:** `compose.yaml` (servicio `keycloak`), `infra/keycloak/realm-ultrasist-portal.json`, `infra/keycloak/common_words.txt` (lista base, antes `app/core/common_passwords.txt`) e `infra/keycloak/common_passwords.txt` (generada), `.env.example`, `scripts/create_env.py`, `scripts/check.py`, `run_local.*`, `scripts/seed_db.py`, `scripts/reset_demo.py`; nuevos `scripts/link_keycloak_users.py` y `scripts/build_password_blacklist.py`.
- **Dependencias:** Authlib 1.7.2 (cliente OIDC; trae `cryptography` y `joserfc`) y `httpx` 0.28.1 en producción; `httpx` deja de ser sólo de desarrollo. Se elimina `pwdlib[argon2]` en este mismo cambio: ningún código lo usa.
- **Pruebas:** IdP simulado (JWKS y tokens firmados de prueba) y cliente de administración falso; se reescriben `test_auth`, `test_primer_acceso`, `test_login_throttle`, `test_sesiones`, `test_credenciales_demo`, `test_usuarios_admin` y `test_acceso_proveedores`, y el helper `login()` de `conftest.py`.
- **Documentación:** `README.md` (Keycloak local, variables, flujo, alta de usuarios, sin contraseñas demo).
- **Operación:** si Keycloak no está disponible, nadie puede iniciar sesión nueva ni autorizar proveedores. Las sesiones abiertas siguen funcionando hasta expirar.
