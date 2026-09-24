# calidad-y-pruebas Specification

## Purpose
Pruebas aisladas de los datos de trabajo, cobertura de los módulos de riesgo con umbral, lint y formato automatizados y verificación integrada con el pipeline compartido.

## Requirements
### Requirement: Pruebas aisladas de los datos de trabajo
La suite de pruebas SHALL ejecutarse sobre una base de datos y un directorio de almacenamiento temporales creados por sesión de prueba, y MUST NOT leer, modificar ni borrar `data/invoice_portal.db` ni `storage/` del proyecto. Las pruebas MUST NOT depender de identificadores autoincrementales ni de folios del seed; SHALL localizar los datos por atributos de negocio.

#### Scenario: Ejecutar pytest con una base de trabajo existente
- **WHEN** existe `data/invoice_portal.db` con datos y se ejecuta `pytest`
- **THEN** al terminar, el archivo conserva el mismo SHA-256 y `storage/` no cambió

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
- limitación de intentos de login, política de contraseñas y revocación de sesiones;
- cabeceras de seguridad y ausencia de traceback;
- migraciones hasta `head` sobre una base vacía y sobre una base con el esquema `0001`.

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
La integración continua SHALL seguir siendo el pipeline compartido del equipo (`.github/workflows/calidad.yml`, SonarQube), sin workflows adicionales que dupliquen su lógica. `pytest` SHALL generar `coverage.xml` para ese pipeline. El proyecto SHALL incluir `scripts/check.py`, que ejecuta `ruff check`, `ruff format --check`, `alembic check`, `pytest` con umbral de cobertura y `pip-audit`, y termina con código distinto de cero si alguno falla.

#### Scenario: Código sin formatear
- **WHEN** se ejecuta `python scripts/check.py` con código sin formatear
- **THEN** el paso `ruff format --check` falla y el script termina con código distinto de cero

#### Scenario: Reporte de cobertura para SonarQube
- **WHEN** se ejecuta `pytest`
- **THEN** se genera `coverage.xml` en la raíz de la PoC

