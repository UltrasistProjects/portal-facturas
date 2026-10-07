## MODIFIED Requirements

### Requirement: Rutas de almacenamiento relativas y portables
`documents.path` SHALL almacenar la ruta del archivo relativa a la raíz de almacenamiento, con separadores `/` (por ejemplo `invoices/10/ab12cd.pdf`). Al servir un archivo, el sistema SHALL resolver la ruta contra la raíz de almacenamiento configurada y MUST rechazar cualquier ruta que resuelva fuera de ella.

#### Scenario: Nuevo documento
- **WHEN** se sube un documento para la factura 10
- **THEN** `documents.path` es `invoices/10/<uuid>.<ext>` sin prefijo de unidad, usuario ni directorio del host

#### Scenario: Restauración en otra máquina
- **WHEN** la base de datos y `storage/` se restauran bajo una ruta de proyecto distinta
- **THEN** todos los documentos siguen siendo descargables

#### Scenario: Ruta manipulada fuera de la raíz
- **WHEN** un registro de `documents` contiene `../../.env` como ruta
- **THEN** la descarga responde HTTP 404 y no lee el archivo
