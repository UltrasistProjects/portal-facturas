## Context

La HU-01 (`docs/stories/new/HU-01 Carga masiva de proveedores.md`) pide cargar el catálogo de proveedores desde un formato de Excel predefinido. Sus reglas (RD-01 a RD-10) se confirmaron en la revisión del 2026-09-24. Estado actual del PoC:

- **Alta:** sólo existe el formulario individual `POST /suppliers` (rol `ADMIN`), con validación Pydantic `SupplierCreate`.
- **`suppliers`:**
  - `rfc` es `VARCHAR(13)`, `NOT NULL` y único (`ix_suppliers_rfc`);
  - `supplier_type` es `PERSONA_FISICA`/`PERSONA_MORAL`;
  - `status` es `ACTIVE`/`INACTIVE`, con un `CHECK` llamado `supplierstatus` sobre `VARCHAR(8)`.
- **RFC en plantillas:** el RFC se muestra directamente en `suppliers/list.html`, `suppliers/detail.html`, `invoices/detail.html` y `components/invoice_table.html`.
- **Frontend:**
  - la CSP es `default-src 'self'`, sin scripts en línea;
  - Bootstrap 5 (con `Modal`) y `app/static/js/app.js` ya se cargan en `base.html`;
  - los errores se devuelven en JSON (`{"detail": ...}`) cuando la petición trae `Accept: application/json`.
- **Validación de facturas:** SUP-001 exige `supplier.status == ACTIVE`.
- **Pruebas y migraciones:**
  - las pruebas corren sobre una base PostgreSQL temporal por sesión, con el seed cargado;
  - `scripts/check.py` ejecuta ruff, `alembic check`, pytest con cobertura ≥ 93 % y `pip-audit`.

## Goals / Non-Goals

**Goals:**
- Carga masiva segura (archivo no confiable) y predecible (validación completa antes de escribir) del catálogo de proveedores Nacional e Internacional.
- Modelo de identidad fiscal por origen, garantizado por la base de datos.
- Confirmación explícita del Administrador antes de un registro parcial, sin guardar el archivo en el servidor.
- Sin cambios de comportamiento en el alta individual ni en la validación de facturas.

**Non-Goals:**
- Autorización de proveedores y ciclo `REGISTERED → Autorizado` (HU-02).
- Usuarios, contraseñas y correos (HU-03).
- Actualización de proveedores existentes, otros catálogos, contratos y datos bancarios.
- Pruebas de interfaz automatizadas en navegador: el proyecto no tiene esa infraestructura. El comportamiento del modal se verifica manualmente.

## Decisions

### D1. `openpyxl` para leer y generar, con defensa explícita contra XML hostil
- **Lectura:** `load_workbook(BytesIO, read_only=True, data_only=False, keep_links=False)`. `data_only=False` expone las fórmulas (`data_type == "f"`) para rechazarlas sin evaluarlas; `read_only` lee en streaming.
- **Antes de abrir el libro, el servicio inspecciona el ZIP:**
  - con `zipfile.is_zipfile` y la parte `xl/workbook.xml` presente;
  - con la suma de los tamaños descomprimidos declarados de hasta 50 MB (`ZipExtFile` nunca entrega más bytes de los declarados);
  - y rechaza cualquier parte `.xml` o `.rels` que contenga `<!DOCTYPE` o `<!ENTITY`, que Excel nunca emite.
- **Defensa en profundidad:** `defusedxml` se instala para que `openpyxl` use su `iterparse` seguro.
- **Generación de la plantilla:**
  - `openpyxl` en modo normal, con `DataValidation` de lista;
  - formato de texto (`@`) a nivel de columna, para no crear miles de celdas vacías.

*Alternativas:*
- `pandas`: arrastra numpy y no da acceso al tipo de celda (fórmula o fecha).
- `python-calamine`: sólo lee.
- Confiar sólo en `defusedxml`: depende de detalles internos de `openpyxl` (con `lxml` presente usa otro parser en algunas partes). La inspección previa es verificable con una prueba.

### D2. Validación en tres fases con validadores propios
1. **Archivo** (`ImportFileError`, HTTP 400): extensión, tamaño, ZIP, XML, plantilla y límites.
2. **Filas:** normalización y reglas por columna. El resultado es una lista de `RowError(row, column, message)` en el orden de las columnas.
3. **Duplicados:**
   - dentro del archivo, en memoria;
   - contra la base, con tres consultas en lote: RFC con `IN`, `(country, foreign_tax_id)` con `tuple_(...).in_(...)`, y correos en `lower(suppliers.email)` y `lower(users.email)`.

Las filas se validan con funciones puras (`app/services/supplier_import_service.py`), no con un modelo Pydantic. Las reglas cruzadas (origen → RFC/ID/país, tipo de persona → longitud del RFC) y los mensajes exactos por columna que fija la spec se expresan de forma directa. Traducir los errores de Pydantic obligaría a mapear cada tipo de error. El correo se valida con `email_validator.validate_email(check_deliverability=False)`, la misma librería que usa `EmailStr` en `SupplierCreate`.

Una fila con errores no se evalúa contra el catálogo. Una fila sin errores se clasifica como:
- `skipped`, si su RFC o su par (país, ID) ya existe;
- `error`, si su correo pertenece a otro proveedor o a un usuario;
- `new`, en cualquier otro caso.

*Alternativa:* consultar la base fila por fila, lo que para 1000 filas son hasta 4000 consultas.

### D3. Modos `strict` y `partial`
- **`strict`** (predeterminado):
  - con al menos un error no escribe nada y responde 400 con los errores, el número de filas registrables (`registrable`) y el SHA-256 del archivo;
  - sin errores registra de inmediato.
- **`partial`:**
  - exige `expected_sha256` igual al SHA-256 del archivo recibido; si falta o no coincide, responde 409;
  - vuelve a validar todo y registra sólo las filas `new`.

La ventana emergente sólo aparece si `registrable > 0`.

*Alternativa:* registro parcial automático, que deja el catálogo a medias sin decisión del Administrador. Se descartó en la revisión de la HU.

### D4. Identidad fiscal por origen
- **Columnas nuevas en `suppliers`:**
  - `origin` (`SupplierOrigin`: `NATIONAL`/`INTERNATIONAL`, `VARCHAR(13)` con `CHECK supplierorigin`);
  - `foreign_tax_id` (`VARCHAR(40)`, nula);
  - `country` (`VARCHAR(2)`, no nula).
- `rfc` pasa a admitir `NULL`. El índice único `ix_suppliers_rfc` se conserva, porque PostgreSQL admite varios `NULL` en un índice único.
- **Restricciones nuevas:**
  - `uq_suppliers_country_foreign_tax_id`;
  - `ck_suppliers_origin_identity`:
    ```sql
    (origin = 'NATIONAL' AND rfc IS NOT NULL AND foreign_tax_id IS NULL AND country = 'MX')
    OR (origin = 'INTERNATIONAL' AND rfc IS NULL AND foreign_tax_id IS NOT NULL AND country <> 'MX')
    ```
- **Valores por defecto del modelo:** `origin = NATIONAL` y `country = "MX"`. El alta individual y el seed siguen funcionando sin cambios.
- **Propiedad `Supplier.tax_identifier`:** devuelve el RFC o `"<país> <identificador>"`, y la usan las plantillas que hoy muestran `rfc`.

*Alternativas:*
- RFC genérico `XEXX010101000`: choca con la unicidad.
- Tabla aparte para extranjeros: duplica consultas y flujos.

### D5. Estatus `REGISTERED`
- `SupplierStatus` gana `REGISTERED`.
- `SUPPLIER_STATUS_LABELS` (`Registrado`, `Activo`, `Inactivo`) se publica como global de Jinja, y el listado y el detalle muestran la etiqueta en lugar del valor crudo.
- `ACTIVE` no cambia. HU-02 decidirá su transición a "Autorizado".
- SUP-001 ya rechaza cualquier estatus distinto de `ACTIVE`.

### D6. Rutas
En `app/routers/suppliers.py`, declaradas **antes** de `/suppliers/{supplier_id}`, cuyo parámetro es `int` y respondería 422 a `import`:
- `GET /suppliers/import`: página, rol `ADMIN`;
- `GET /suppliers/import/template`: `.xlsx` como adjunto, rol `ADMIN`;
- `POST /suppliers/import`: multipart con `csrf_token`, `upload`, `mode` y `expected_sha256`; rol `ADMIN` y CSRF. Siempre responde JSON (`JSONResponse`); los errores de autenticación, rol y CSRF siguen el manejador global, que responde JSON si la petición lo pide.

### D7. El archivo no se conserva
Se procesa en memoria. La auditoría guarda su SHA-256 y su tamaño, y cada `SUPPLIER_CREATED` lleva `import_sha256`, lo que liga al proveedor con la carga. Guardar el archivo dejaría datos personales en `storage/`, y de ahí en respaldos y paquetes, el riesgo que señaló la auditoría técnica.

### D8. Límites como constantes del módulo de importación
- 5 MB por archivo, 50 MB descomprimidos y 1000 filas de datos.
- 200 errores mostrados.
- La lectura se corta al encontrar la fila con datos número 1001 (error de archivo), sin fiarse de la dimensión declarada de la hoja.
- `max_upload_mb` (20 MB) no se reutiliza: es un límite para documentos, no para un Excel tabular.

### D9. Revisión Alembic `0002_supplier_bulk_import`
**Upgrade:**
1. `add_column` de `origin` (nula), `foreign_tax_id` y `country` (nula).
2. `UPDATE suppliers SET origin = 'NATIONAL', country = 'MX'`.
3. `alter_column` a `NOT NULL` en `origin` y `country`, y `rfc` a nula.
4. `CHECK supplierorigin`.
5. Reemplazar el `CHECK supplierstatus` por uno con `REGISTERED` y ampliar `status` a `VARCHAR(10)`, para coincidir con el `Enum` del modelo (`alembic check` compara tipos).
6. `uq_suppliers_country_foreign_tax_id` y `ck_suppliers_origin_identity`.

**Downgrade:** lanza `NotImplementedError` ("… Restaure un respaldo.") si existen proveedores `INTERNATIONAL` o `REGISTERED`, porque revertir perdería datos. Si no existen, revierte explícitamente.

La revisión no importa los modelos (regla vigente de `migraciones-esquema`).

### D10. Unicidad del correo sólo en la carga
La carga rechaza un correo nuevo que ya usa otro proveedor (`lower(suppliers.email)`) o un usuario (`lower(users.email)`). No se añade una restricción sobre `suppliers.email`: exigiría cambiar el alta individual (fuera de alcance), y `users.email` ya es único, que es donde HU-03 materializa el acceso.

### D11. Confirmación sin estado en el servidor
`app/static/js/supplier_import.js` se carga sólo en `import.html`, mediante un bloque `scripts` nuevo en `base.html`. El script:
- **Envío:** intercepta el formulario y lo envía con `fetch` (`Accept: application/json`, `mode=strict`).
- **Respuesta 200:** pinta el resumen.
- **Respuesta 400 con `registrable > 0`:** guarda `sha256` y abre el modal de Bootstrap. La acción "No, corregir primero (Recomendado)" es `btn-primary` y recibe el foco en `shown.bs.modal`.
- **Botón "Agrega las filas válidas y omite el resto":** reenvía el mismo `File` con `mode=partial` y `expected_sha256`.
- **Cierre del modal sin elegir agregar** (botón, Esc o fondo): pinta la lista de errores.
- **Otros errores:** pinta `detail`.
- **Pintado:** todo con `textContent`, porque los valores vienen de un archivo no confiable.
- **Sin JavaScript:** la página muestra un aviso `<noscript>`.

*Alternativa:* guardar el archivo o las filas en `storage/temp` con un token. Deja datos personales en disco, exige limpiar las cargas abandonadas y contradice D7. Aceptar filas ya validadas desde el cliente permitiría registrar datos sin validar.

### D12. Contrato JSON de `POST /suppliers/import`

| Caso | HTTP | Cuerpo |
| --- | --- | --- |
| Error de archivo | 400 | `{"detail": "<mensaje>"}` |
| Filas con errores (`strict`) | 400 | `{"detail", "rows", "registrable", "invalid", "errors": [{"row", "column", "message", "text"}], "hidden_errors", "skipped": [...], "sha256"}` |
| Carga concluida | 200 | `{"result": "imported"\|"partial", "mode", "rows", "created", "skipped": [{"row", "identifier", "business_name"}], "invalid", "errors", "hidden_errors", "summary"}` |
| SHA-256 ausente o distinto (`partial`), conflicto de unicidad | 409 | `{"detail": "<mensaje>"}` |

`summary` es el texto que muestra la página ("10 filas leídas · 8 proveedores registrados · 2 omitidos", más " · N con errores" si aplica), con singular y plural correctos.

### D13. Módulos
- `app/core/countries.py`: códigos ISO 3166-1 alfa-2 con su nombre en español. Es una constante local, sin dependencia nueva.
- `app/services/supplier_template.py`: `HEADERS`, `TEMPLATE_VERSION` y `TEMPLATE_FILENAME`, y `build_template() -> bytes`.
- `app/services/supplier_import_service.py`: `ImportFileError`, `read_rows(content)`, `validate_rows(rows)`, `classify(db, rows)`, `register(db, ...)` e `import_suppliers(db, user, filename, content, mode, expected_sha256)`, que orquesta todo y emite el log y la auditoría.

## Risks / Trade-offs

- **[Carga simultánea de dos archivos con el mismo correo nuevo]** → sin restricción en `suppliers.email` (D10), ambas podrían registrarlo. Mitigación: la carga es una operación rara de un solo Administrador, y `users.email` único lo detectará al crear usuarios (HU-03). Los conflictos de RFC o (país, ID) sí los resuelve la base con 409.
- **[Excel convierte valores (números largos, fechas)]** → formato de texto en la plantilla, conversión de enteros a texto y errores explícitos ante fechas y fórmulas.
- **[Hojas con formato hasta la fila 1 048 576]** → lectura en streaming. Las filas vacías se recorren sin validarlas, y el límite de 50 MB descomprimidos acota el trabajo.
- **[LibreOffice o Google Sheets pierden las listas desplegables]** → la validación del servidor no depende de ellas.
- **[El catálogo cambia entre la validación y la confirmación]** → la segunda validación omite lo que ya existe; el resumen refleja lo realmente registrado.
- **[El archivo en disco cambia antes de confirmar]** → `expected_sha256` lo detecta (409).
- **[`rfc` que admite `NULL` rompe supuestos]** → el único uso de `rfc` como identidad es el alta individual (sólo nacionales). Las plantillas pasan a `tax_identifier`.

## Migration Plan

1. `pip install -r requirements.lock` (incluye `openpyxl` y `defusedxml`).
2. `alembic upgrade head`: aplica `0002_supplier_bulk_import`; los proveedores existentes quedan `NATIONAL`/`MX`.
3. **Reversión:** `alembic downgrade 0001_postgresql_baseline` sólo si no hay proveedores `INTERNATIONAL` ni `REGISTERED`; en otro caso, restaurar un respaldo (`scripts/restore_backup.py`).

## Open Questions

Ninguna. Las decisiones de negocio y arquitectura se confirmaron en la revisión de la HU (2026-09-24).
