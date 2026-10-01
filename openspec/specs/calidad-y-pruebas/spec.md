# calidad-y-pruebas Specification

## Purpose
Pruebas aisladas de los datos de trabajo, cobertura de los módulos de riesgo con umbral, lint y formato automatizados y verificación integrada con el pipeline compartido.
## Requirements
### Requirement: Pruebas aisladas de los datos de trabajo
Cada sesión de pruebas SHALL crear una base de datos temporal `portal_test_<aleatorio>` en el servidor indicado por `TEST_DATABASE_URL` (o, si no existe, en el servidor de `DATABASE_URL`), aplicarle las migraciones y el seed, y eliminarla al terminar, también cuando la sesión falla. Usará además un directorio de almacenamiento temporal. La suite MUST NOT leer, modificar ni borrar la base de trabajo ni `storage/` del proyecto. Si el servidor no es alcanzable, la sesión SHALL fallar con un mensaje que indique cómo levantar el contenedor. Las pruebas MUST NOT depender de identificadores autoincrementales ni de folios del seed; SHALL localizar los datos por atributos de negocio.

#### Scenario: Ejecutar pytest con una base de trabajo existente
- **WHEN** la base de trabajo contiene datos y se ejecuta `pytest`
- **THEN** al terminar, el número de filas de cada tabla de la base de trabajo es el mismo, `storage/` no cambió y no queda ninguna base `portal_test_*`

#### Scenario: Servidor de pruebas no disponible
- **WHEN** el contenedor `db` está detenido y no hay `TEST_DATABASE_URL` alcanzable
- **THEN** `pytest` falla al iniciar la sesión con un mensaje que indica ejecutar `docker compose up -d --wait db`

#### Scenario: Cambio de orden del seed
- **WHEN** se reordenan los escenarios del seed
- **THEN** las pruebas siguen pasando

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

### Requirement: Umbral de cobertura medido
La ejecución de pruebas SHALL medir la cobertura de `app/` con `pytest-cov` y SHALL fallar si la cobertura total cae por debajo del umbral configurado en `pyproject.toml`. El umbral inicial es el valor medido al completar este cambio, redondeado hacia abajo, y nunca menor que 80 %.

#### Scenario: Cobertura insuficiente
- **WHEN** la cobertura total queda por debajo del umbral configurado
- **THEN** `pytest` termina con código de salida distinto de cero

### Requirement: Lint y formato automatizados
El código de `app/`, `tests/`, `scripts/` y `alembic/` SHALL pasar `ruff check` (incluidas las reglas E701/E702 de múltiples sentencias por línea e imports sin usar) y `ruff format --check`, con longitud de línea de 120. El reformateo inicial SHALL entregarse en un commit aislado, sin cambios funcionales.

#### Scenario: Múltiples sentencias por línea
- **WHEN** se introduce `db.add(x); db.commit()` en una línea
- **THEN** `ruff check` falla con E702

#### Scenario: Import sin usar
- **WHEN** un módulo importa un nombre que no usa
- **THEN** `ruff check` falla con F401

### Requirement: Verificación automatizada y pipeline compartido
La integración continua SHALL seguir siendo el pipeline compartido del equipo (`.github/workflows/calidad.yml`, SonarQube), sin workflows adicionales que dupliquen su lógica. `pytest` SHALL generar `coverage.xml` para ese pipeline y requiere un PostgreSQL alcanzable. El proyecto SHALL incluir `scripts/check.py`, que ejecuta:
- `ruff check` y `ruff format --check`;
- `alembic check` sobre una base temporal del servidor de pruebas;
- `pytest` con umbral de cobertura;
- `pip-audit`.

El script SHALL terminar con código distinto de cero si alguno falla.

#### Scenario: Código sin formatear
- **WHEN** se ejecuta `python scripts/check.py` con código sin formatear
- **THEN** el paso `ruff format --check` falla y el script termina con código distinto de cero

#### Scenario: Reporte de cobertura para SonarQube
- **WHEN** se ejecuta `pytest`
- **THEN** se genera `coverage.xml` en la raíz de la PoC

#### Scenario: Base temporal de alembic check
- **WHEN** termina `scripts/check.py`
- **THEN** no queda en el servidor la base temporal usada por `alembic check`

### Requirement: Pruebas sin Keycloak ni red
La suite MUST NOT requerir un servidor Keycloak ni acceso a la red:
- el flujo OIDC SHALL probarse contra un IdP simulado con un par de claves generado por sesión, un JWKS, un *discovery* y un token endpoint servidos por un transporte simulado del cliente HTTP, y ID tokens firmados a medida de cada prueba;
- la API de administración SHALL sustituirse por un cliente falso en memoria que registra las llamadas y permite simular fallos.

El helper de inicio de sesión de `tests/conftest.py` SHALL recorrer el flujo real `/login` → `/auth/callback` contra ese IdP simulado.

#### Scenario: Suite sin Keycloak
- **WHEN** se ejecuta `pytest` con el servicio `keycloak` detenido y sin red
- **THEN** la suite pasa y ninguna prueba intenta conectarse a `KEYCLOAK_SERVER_URL`

