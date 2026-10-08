> Todas las rutas son relativas a la raíz de la PoC (`PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress-V1/PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress/`). Cada grupo termina con `ruff` limpio y sus pruebas en verde sobre PostgreSQL.

## 1. Modelo y migración

- [x] 1.1 `app/core/constants.py`: enumeración `CatalogType` con etiquetas, formato de clave por catálogo y descripción del formato; `BUSINESS_RULES` sólo con `score_weights`.
- [x] 1.2 `app/models/__init__.py`: `ValidationSettings` (una fila, versión) y `CatalogEntry`, con sus restricciones (D1, D2). Añadirlos a `__all__`.
- [x] 1.3 Revisión `alembic/versions/0007_validation_rules_catalogs.py` (`down_revision = "0006_supplier_credentials"`):
  - tablas, restricciones e índices;
  - siembra de la configuración inicial con los valores de `BUSINESS_RULES`;
  - siembra de los catálogos del SAT (24 usos, 22 formas, 2 métodos, 19 regímenes) y las monedas `MXN`, `USD` y `EUR`;
  - downgrade bloqueado si la configuración pasó de la versión 1 o algún catálogo se modificó.

  Verificar `alembic check`.
- [x] 1.4 Pruebas en `tests/test_integridad.py` (tipo de catálogo, segunda configuración, CP inválido, usos vacíos, clave repetida, clave y descripción inválidas) y `tests/test_migraciones.py` (instalación nueva con conteos y valores; downgrade sin cambios y bloqueado).

## 2. Reglas de validación y motor

- [x] 2.1 `app/services/validation_settings_service.py`:
  - `RuleParameters` y `rule_parameters(db)`;
  - `normalize_name()`;
  - formulario y validación con los errores juntos (400);
  - guardado con versión (409), sin cambios sin escribir, auditoría `VALIDATION_SETTINGS_UPDATED` y evento `validation_settings.updated` tras el commit.
- [x] 2.2 `app/rules/xml_rules.py`: `xml_rules(data, error, params)` con XML-002…XML-005 configurables, XML-007 con monedas del catálogo, nuevas XML-009 y XML-010, y `NOT_APPLICABLE` para las comparaciones desactivadas (D3).
- [x] 2.3 `app/services/validation_engine.py`: leer `rule_parameters(db)` en cada prevalidación y pasarlos a `xml_rules`.
- [x] 2.4 `app/routers/admin.py`: `GET /admin/rules` (aviso `?ok=`) y `POST /admin/rules` (400 y 409 en la misma página). Plantilla `admin/rules.html` reescrita (D5); menú "Reglas de validación".

## 3. Catálogos

- [x] 3.1 `app/services/catalog_service.py`:
  - listado y conteos;
  - claves en uso;
  - alta, edición y cambio de estado con bloqueo consultivo, protecciones de clave en uso y última moneda (409), y auditoría (D4, D6).
- [x] 3.2 `app/services/catalog_template.py`: plantilla con el contenido vigente y hoja de instrucciones.
- [x] 3.3 Carga desde Excel en `catalog_service` (D7):
  - lectura con las protecciones de HU-01;
  - validación por fila y del catálogo completo;
  - aplicación en una transacción;
  - resumen, auditoría `CATALOG_IMPORTED` y eventos `catalog.import` y `catalog_import.read_failed`.
- [x] 3.4 `app/routers/admin.py`: rutas `/admin/catalogs*`. Plantillas `admin/catalogs.html` y `admin/catalog.html`; menú "Catálogos".

## 4. Pruebas de las capacidades

- [x] 4.1 `tests/test_reglas_validacion.py`:
  - fixture que restaura la configuración inicial;
  - acceso y CSRF; valores iniciales; cambio y siguiente prevalidación;
  - comparación desactivada; varios errores; clave inactiva;
  - edición concurrente, sin cambios y auditoría.
- [x] 4.2 Motor en `tests/test_reglas_validacion.py`: XML-009 con otro formato, XML-010 distinto, comparaciones desactivadas, monedas del catálogo, factura demo correcta y mensajes con el valor esperado.
- [x] 4.3 `tests/test_folio_y_reglas.py`: vista y cambio de parámetro con la configuración de la base de datos.
- [x] 4.4 `tests/test_catalogos.py`:
  - fixture que restaura los catálogos;
  - acceso, CSRF y 404;
  - listado y conteos; "En uso";
  - alta (y efecto en XML-007), formato inválido, clave repetida y edición;
  - desactivación de una clave en uso, de la última moneda y de una moneda (efecto en XML-007), y reactivación;
  - auditoría.
- [x] 4.5 Carga en `tests/test_catalogos.py`:
  - plantilla con el contenido vigente;
  - carga con claves nuevas y actualizadas;
  - filas con errores sin cambios;
  - archivo que no es la plantilla, extensión y tamaño;
  - carga que deja monedas sin activas;
  - auditoría de la carga.
- [x] 4.6 `tests/test_observabilidad.py`: `validation_settings.updated` sin valores y `catalog.import`.

## 5. Documentación y verificación

- [x] 5.1 `README.md`: secciones "Reglas de validación" y "Catálogos", reglas XML-009 y XML-010 en "Reglas implementadas" y limitaciones actualizadas.
- [x] 5.2 `python scripts/check.py` en verde: ruff, formato, `alembic check`, pytest con cobertura ≥ 93 % y `pip-audit`. *(618 pruebas, cobertura 96.50 %, sin vulnerabilidades conocidas.)*
- [x] 5.3 Verificación en la aplicación con navegador: editar las reglas, desactivar una comparación, alta y desactivación de claves, descarga y carga de la plantilla. *(Chromium headless (Playwright) sobre uvicorn y una base temporal: 21/21 verificaciones, incluidos el error de validación que conserva lo capturado, XML-010 desactivada, alta de `CAD`, plantilla descargada, modificada y cargada, carga rechazada por una clave en uso y consola sin errores ni violaciones de CSP.)*
- [x] 5.4 `openspec validate parametros-y-catalogos-validacion --strict` sin errores.
