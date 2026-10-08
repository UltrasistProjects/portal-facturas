## Context

- `app/repositories/pagination.py` ya tiene `Page` y `paginate(db, stmt, page, per_page)` (conteo con `SELECT count(*)` sobre la subconsulta, página fuera de rango ajustada a la última). `components/pagination.html` pinta "Página N de M · T registros" con `base_query`. Los usan las facturas y el Audit Log.
- `invoice_repository.escape_like` escapa `%`, `_` y `\` para `ILIKE ... ESCAPE '\'`.
- Proveedores, usuarios, contratos y claves cargan la tabla completa (`list(db.scalars(select(...)))`); la bitácora, `LIMIT 20`. `catalog_service.entries` también alimenta la plantilla de Excel, que debe seguir teniendo todas las claves.
- Las altas de usuario y contrato redirigen a la lista sin más; la de clave, a la lista con `?ok=created`; habilitar un usuario y enmendar un contrato redirigen a la lista sin página.

## Goals / Non-Goals

**Goals:** ninguna lista crece sin límite en una página; un registro recién creado siempre está a la vista; una acción no saca al usuario de la página donde estaba.

**Non-Goals:** ordenar por columnas, tamaño de página configurable, paginar formularios de configuración o resultados de archivos.

## Decisions

### D1. Utilidades compartidas
En `pagination.py`:
- `PER_PAGE = 25`;
- `escape_like(value)` se mueve aquí (`invoice_repository` lo importa);
- `search(stmt, q, *columns)`: sin `q` (tras `strip`) devuelve `stmt`; con `q`, agrega `OR` de `column.ilike('%q%', escape='\\')`;
- `list_query(**params)`: `urlencode` de los parámetros no vacíos, para `base_query` y para las redirecciones.

Cada listado arma su `select` con orden total (`..., id`) y llama a `paginate`. Todas las rutas aceptan `page: int = 1` como el listado de facturas.

### D2. Orden de cada listado
Proveedores por razón social y usuarios por nombre (se buscan por nombre); claves por clave. Contratos y envíos del más reciente al más antiguo (`id DESC` / `created_at DESC, id DESC`): lo nuevo es lo que se consulta. En contratos, las enmiendas siguen cargándose con `selectinload` sólo para la página.

### D3. Alta visible
- Usuario: `/admin/users?q=<correo>&ok=created` → "Usuario creado". El correo es único: la búsqueda deja sólo ese usuario.
- Contrato: `/contracts?q=<proyecto>&ok=created` → "Contrato creado". El más reciente va primero entre los que coinciden.
- Clave: `/admin/catalogs/{c}?q=<clave>&ok=created` → "Clave agregada".
`ok` sólo se traduce con un diccionario fijo de avisos; otro valor se ignora (como el resto del portal).

### D4. Retorno tras una acción
Los formularios de acción en filas (habilitar usuario, enmienda, editar/estado de clave) llevan `q`, `status` y `page` en campos ocultos. `back_to(url, form)` reconstruye la URL sólo con esas tres claves vía `list_query` (sin reflejar otra entrada ni abrir redirecciones a otro destino) y el router redirige ahí. `page` inválido se descarta.

### D5. Proveedores y la autorización por lotes
El formulario de autorización envuelve la tabla de la página; "Seleccionar todos" marca los Registrados de la página. `MAX_BATCH` no cambia. El filtro de estatus y la búsqueda comparten el formulario GET; la paginación los conserva.

### D6. Catálogos
`catalog_service.page_entries(db, catalog, q, page)` para la tabla y `counts(db, catalog)` (`count(*)` y `count(*) FILTER (WHERE is_active)`) para "N activas de M"; `entries` se queda para la plantilla de Excel.

### D7. Bitácora
`notification_service.deliveries_page(db, page)` reemplaza a `recent_deliveries`. La sección se titula "Bitácora de envíos". Los parámetros `ok` y `test` de la pantalla no pasan a la paginación.

## Risks / Trade-offs

- **[OFFSET en tablas grandes]** → con 25 por página y los volúmenes del MVP (cientos o pocos miles de registros) el costo es despreciable; los órdenes usan columnas indexadas o tablas chicas.
- **[Selección de proveedores entre páginas]** → la autorización por lotes opera sobre la página visible; para más de 25, se filtra por "Registrado" y se autoriza página por página.
