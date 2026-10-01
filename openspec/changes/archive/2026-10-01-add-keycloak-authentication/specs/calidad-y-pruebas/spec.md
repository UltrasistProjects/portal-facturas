## ADDED Requirements

### Requirement: Pruebas sin Keycloak ni red
La suite MUST NOT requerir un servidor Keycloak ni acceso a la red:
- el flujo OIDC SHALL probarse contra un IdP simulado con un par de claves generado por sesión, un JWKS, un *discovery* y un token endpoint servidos por un transporte simulado del cliente HTTP, y ID tokens firmados a medida de cada prueba;
- la API de administración SHALL sustituirse por un cliente falso en memoria que registra las llamadas y permite simular fallos.

El helper de inicio de sesión de `tests/conftest.py` SHALL recorrer el flujo real `/login` → `/auth/callback` contra ese IdP simulado.

#### Scenario: Suite sin Keycloak
- **WHEN** se ejecuta `pytest` con el servicio `keycloak` detenido y sin red
- **THEN** la suite pasa y ninguna prueba intenta conectarse a `KEYCLOAK_SERVER_URL`

## MODIFIED Requirements

### Requirement: Cobertura de los módulos de mayor riesgo
La suite SHALL incluir pruebas de:
- `file_service`: extensión, verificación de contenido, tamaño, archivo vacío, path traversal y rutas relativas;
- `POST /invoices/{id}/documents`;
- autorización de descarga entre proveedores;
- bloqueo de aceptación por severidad `CRITICAL` en `POST /invoices/{id}/review`;
- reglas FIN-002, FIN-003, FIN-005 y FIN-006;
- el límite de DAT-001 en la zona horaria de negocio;
- el callback OIDC: callback válido, `state` inválido, `nonce` inválido, token expirado, audiencia incorrecta y firma inválida;
- enlace por `sub` y roles: cuenta desconocida, rol ausente o distinto (403), usuario inactivo, y aislamiento entre proveedores (404);
- el aprovisionamiento en Keycloak: éxito, fallo parcial, usuario ya existente y correo con otro rol;
- la ausencia de contraseñas temporales en la base de datos, la auditoría y el log;
- la configuración del realm versionado (política, fuerza bruta, clientes, sin secretos);
- revocación de sesiones y logout en Keycloak;
- cabeceras de seguridad y ausencia de traceback;
- migraciones hasta `head` sobre una base PostgreSQL vacía, con `alembic check` sin diferencias;
- respaldo y restauración con `pg_dump`/`pg_restore`.

#### Scenario: Suite completa
- **WHEN** se ejecuta `pytest`
- **THEN** existen y pasan pruebas para cada uno de los módulos y comportamientos enumerados
