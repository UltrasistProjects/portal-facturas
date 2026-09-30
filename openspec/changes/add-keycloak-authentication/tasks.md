> Rutas relativas a la raíz de la PoC (`PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress-V1/PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress/`). Requiere `correct-identity-provider-naming` aplicado. Los grupos 1–7 van en el commit de implementación y el grupo 8 en el de pruebas.

## 1. Infraestructura local

- [ ] 1.1 `infra/keycloak/realm-ultrasist-portal.json`:
  - roles `Administrador`, `Proveedor` y `PMO`;
  - cliente `portal-facturas-web` (confidencial, sólo Standard Flow, PKCE S256, redirect y post-logout URIs locales, *mapper* de realm roles al ID token);
  - cliente `portal-facturas-admin` (sólo cuenta de servicio con `manage-users`, `view-users` y `query-users`);
  - política (D17), fuerza bruta (D18), eventos (D19) y tiempos SSO (D4);
  - secretos como `${…}`; sin usuarios.
- [ ] 1.2 `compose.yaml`: servicio `keycloak` (`quay.io/keycloak/keycloak:26.7.4`, `start-dev --import-realm`, volumen `keycloak-data`, lista de comunes montada, `127.0.0.1:${KEYCLOAK_PORT:-58080}`, `:?` en secretos y administrador inicial, healthcheck) (D21).
- [ ] 1.3 `.env.example` con las variables `KEYCLOAK_*`, `KEYCLOAK_PORT`, `KC_BOOTSTRAP_ADMIN_*` y `DEMO_PASSWORD`, sin valores sensibles.
- [ ] 1.4 `scripts/create_env.py` genera los secretos de Keycloak, `KC_BOOTSTRAP_ADMIN_PASSWORD` y `DEMO_PASSWORD` (esta última cumpliendo la política) y completa un `.env` existente sin sobrescribir.
- [ ] 1.5 `run_local.sh`, `run_local.ps1` y `run_local.bat` levantan `db` y `keycloak` con `--wait`.

## 2. Configuración

- [ ] 2.1 `app/core/config.py`: settings `KEYCLOAK_*` con validadores (obligatorias, secretos `SecretStr` ≥ 32 sin `change-me`, `https://` en production, timeout 1–60) (D20).
- [ ] 2.2 `app/core/middleware.py`: `form-action 'self' <origen de Keycloak>` en la CSP (D10).

## 3. Datos

- [ ] 3.1 `app/models/__init__.py`: `User.keycloak_sub` único; `password_hash` nullable; `UserSession.id_token_hint`; se retira `LoginAttempt`.
- [ ] 3.2 Revisión `alembic/versions/0015_keycloak_identity.py` (`down_revision = "0014_business_role_names"`): columnas, `uq_users_keycloak_sub`, `DROP TABLE login_attempts` y downgrade según D16.
- [ ] 3.3 `scripts/link_keycloak_users.py`: idempotente, con `--dry-run`; enlaza o crea con la regla de D13; inactivos deshabilitados; temporal con `UPDATE_PASSWORD`; `password_hash = NULL`; auditoría `USER_LINKED_TO_IDP`; entrega de temporales según D1.

## 4. Autenticación

- [ ] 4.1 `app/services/oidc.py`: registro de Authlib con `server_metadata_url`, PKCE S256, `state` y `nonce`; validación de `iss`, `aud`, `exp` (60 s) y `nonce`; 503 si no hay *discovery* (D5, D6, D22).
- [ ] 4.2 `app/routers/auth.py`: `GET /login` (redirección), `GET /auth/callback` (enlace por `sub`, roles, `is_active`, rotación de sesión y CSRF, `id_token_hint`, auditoría), `POST /logout` (revocación local + `end_session_endpoint`) y `GET /account/password` (`kc_action=UPDATE_PASSWORD`) (D7–D10, D19).
- [ ] 4.3 `app/core/security.py`: se retiran `hash_password`, `verify_password`, `PasswordChangeRequired` y la verificación de `must_change_password`; `get_current_user` y `require_roles` siguen basados en la sesión y la BD local. `app/main.py`: se retira el handler de `PasswordChangeRequired`.
- [ ] 4.4 Se eliminan el formulario de login local, `auth/change_password.html`, los botones `data-demo` y su JS en `static/js/app.js`, `app/services/login_throttle.py` y la validación de contraseñas del usuario en `app/core/passwords.py` (se conserva `generate_password`). `app/core/demo.py` queda sin contraseñas.
- [ ] 4.5 `app/services/session_service.py`: guardar y leer `id_token_hint`, que se purga con la sesión.

## 5. Aprovisionamiento

- [ ] 5.1 `app/services/keycloak_admin.py`: protocolo `IdentityAdmin`, implementación httpx con token de cuenta de servicio en caché, timeouts explícitos, `IdentityProviderError` (503) y log sin cuerpos; `get_identity_admin()` inyectable (D11).
- [ ] 5.2 `app/services/supplier_access_service.py`: savepoint por proveedor, crear o enlazar (D13), rol, temporal y `UPDATE_PASSWORD`, `keycloak_sub`, resultado `provisioning_failed` y auditoría `SUPPLIER_PROVISIONING_FAILED` (D12). Se elimina `app/services/secret_vault.py`.
- [ ] 5.3 Correo de acceso según D1 con la plantilla `SUPPLIER_CREDENTIALS` (RF-05) al correo del proveedor (RF-13); resumen de la autorización con la categoría de fallo de aprovisionamiento.
- [ ] 5.4 Expediente y reenvío con `requiredActions` de Keycloak ("No disponible" si no responde; 409 y 503 en el reenvío) (D14).
- [ ] 5.5 `app/routers/admin.py` y `admin/users.html`: alta sin contraseña con aprovisionamiento en Keycloak y entrega según D1 (D15); `toggle` sincronizado con Keycloak e `IDP_SYNC_FAILED` (D10); sin la columna "Contraseña temporal".
- [ ] 5.6 `scripts/seed_db.py` y `scripts/reset_demo.py`: cuentas demo en Keycloak (`DEMO_PASSWORD` en development; temporales aleatorias impresas una vez fuera de development) y `keycloak_sub` en los usuarios locales.

## 6. Dependencias

- [ ] 6.1 `requirements.txt` y `requirements.lock`: Authlib (estable vigente al implementar) y su cliente HTTP como dependencias de producción; `pip-audit` limpio.

## 7. Documentación

- [ ] 7.1 `README.md`: levantar Keycloak local, variables, flujo de inicio y cierre de sesión, alta de usuarios, migración con `link_keycloak_users.py`, qué pasa si Keycloak no está disponible.
- [ ] 7.2 `README.md`: retirar las contraseñas demo (quedan los correos y "contraseña: `DEMO_PASSWORD` de su `.env`") y la sección de cambio de contraseña local.
- [ ] 7.3 `README.md`, despliegue en QA/producción (D2, D3): instancia dedicada, secretos de los clientes, `common_passwords.txt` en el servidor, *rate limiting* por IP en el proxy y SMTP del realm con los mismos valores del portal (contraseña fuera del JSON).

## 8. Pruebas

- [ ] 8.1 `tests/idp.py`: IdP simulado (claves RSA por sesión, *discovery*, JWKS, token endpoint en un transporte simulado) y `FakeIdentityAdmin`; `login()` de `conftest.py` recorre `/login` → `/auth/callback` (D23).
- [ ] 8.2 Callback: válido, `state` inválido, `nonce` inválido, token expirado, `aud` incorrecta, firma ajena, `POST /login` 405, Keycloak caído 503.
- [ ] 8.3 Enlace y roles: `sub` desconocido 403, mismo correo con otro `sub` 403, rol ausente, dos roles o rol distinto 403, usuario inactivo sin acceso, auditoría `LOGIN_DENIED` sin tokens.
- [ ] 8.4 Regresión RBAC: un proveedor no ve facturas ni documentos de otro proveedor (404); las pruebas de aislamiento existentes pasan con el login nuevo.
- [ ] 8.5 Sesiones y logout: rotación de sid y CSRF, cookie sin tokens, logout con `id_token_hint` y `post_logout_redirect_uri`, cookie reutilizada, deshabilitación con Keycloak disponible y caído.
- [ ] 8.6 Aprovisionamiento: éxito, fallo parcial (savepoint), usuario ya existente enlazado, correo con rol interno como conflicto, reenvío (409, 503, temporal nueva), alta de usuarios (409, 503, `no-store`).
- [ ] 8.7 Ninguna contraseña temporal ni token en `users`, `audit_logs`, `email_deliveries` ni en el log; `password_hash` nulo en los usuarios creados.
- [ ] 8.8 Configuración: variables obligatorias, placeholders, `https` en production; realm JSON (política, fuerza bruta, clientes, PKCE, cuenta de servicio mínima, sin secretos ni usuarios); `create_env.py`; CSP con el origen de Keycloak.
- [ ] 8.9 Migraciones: `0015` sobre una base con datos, downgrade con y sin `password_hash` nulos, `alembic check`; `link_keycloak_users.py` idempotente y con `--dry-run`.
- [ ] 8.10 Reescribir o retirar `test_auth`, `test_primer_acceso`, `test_login_throttle`, `test_sesiones`, `test_credenciales_demo`, `test_usuarios_admin` y `test_acceso_proveedores` según los requirements retirados y los nuevos.

## 9. Verificación

- [ ] 9.1 `python scripts/check.py` en verde: ruff, formato, `alembic check`, pytest con el umbral de cobertura y `pip-audit`.
- [ ] 9.2 Verificación manual con Keycloak local: login demo, autorizar un proveedor, primer acceso con la temporal del `.eml`, política rechazada, 5 fallos con bloqueo, logout con cierre SSO, deshabilitación.
- [ ] 9.3 `rg -n -i "password_hash|hash_password|verify_password" app/` sólo devuelve el modelo (columna obsoleta hasta el cambio de limpieza).
- [ ] 9.4 `openspec validate add-keycloak-authentication --strict` sin errores.
