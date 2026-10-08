## ADDED Requirements

### Requirement: Validación de archivos subidos por contenido
El sistema SHALL aceptar únicamente las extensiones `.xml`, `.pdf`, `.txt`, `.png`, `.jpg` y `.jpeg`, y SHALL verificar que el contenido del archivo corresponda a su extensión:
- PDF comienza con `%PDF-`
- PNG comienza con `\x89PNG\r\n\x1a\n`
- JPEG comienza con `\xff\xd8\xff`
- XML, tras un BOM UTF-8 opcional y espacios en blanco, comienza con `<`
- TXT es UTF-8 válido y no contiene bytes NUL

El `Content-Type` declarado por el cliente MUST NOT usarse para decidir la aceptación ni para el MIME almacenado. El MIME almacenado SHALL derivarse de la extensión verificada, y `application/octet-stream` MUST NOT almacenarse nunca como MIME de un documento. Se conservan los controles existentes: archivo no vacío, tamaño máximo `MAX_UPLOAD_MB` con lectura acotada, nombre de almacenamiento `uuid4`, verificación de path traversal y SHA-256.

#### Scenario: Ejecutable renombrado como PDF
- **WHEN** un proveedor sube `contrato.pdf` cuyo contenido comienza con `MZ`
- **THEN** la subida se rechaza con HTTP 400 y el mensaje "El contenido no corresponde a un PDF", y no se escribe ningún archivo en `storage/`

#### Scenario: PDF válido declarado como octet-stream
- **WHEN** el navegador envía un PDF válido con `Content-Type: application/octet-stream`
- **THEN** la subida se acepta y el documento se almacena con `mime_type = application/pdf`

#### Scenario: Imagen con extensión cruzada
- **WHEN** se sube `foto.png` cuyo contenido es un JPEG
- **THEN** la subida se rechaza con HTTP 400

#### Scenario: Texto con bytes binarios
- **WHEN** se sube `nota.txt` con un byte NUL
- **THEN** la subida se rechaza con HTTP 400

#### Scenario: XML con BOM
- **WHEN** se sube un CFDI `.xml` que comienza con BOM UTF-8
- **THEN** la verificación de contenido lo acepta y el parser CFDI lo procesa

#### Scenario: Extensión no permitida
- **WHEN** se sube `script.html`
- **THEN** la subida se rechaza con HTTP 400

#### Scenario: Archivo excede el tamaño
- **WHEN** se sube un archivo de `MAX_UPLOAD_MB` MB más 1 byte
- **THEN** la subida se rechaza sin leer más de `MAX_UPLOAD_MB` MB + 1 byte

### Requirement: Descarga segura de documentos
La descarga de documentos SHALL responder siempre con `Content-Type: application/octet-stream` y `Content-Disposition: attachment` con el nombre saneado, sin importar el MIME almacenado. La autorización existente se mantiene: un PROVIDER sólo puede descargar documentos de facturas de su proveedor, y el documento debe pertenecer a la factura de la URL.

#### Scenario: Descarga de un PDF
- **WHEN** un usuario autorizado descarga un documento PDF
- **THEN** la respuesta tiene `Content-Type: application/octet-stream` y `Content-Disposition: attachment; filename="..."`

#### Scenario: Proveedor intenta descargar documento ajeno
- **WHEN** un PROVIDER solicita la descarga de un documento de una factura de otro proveedor
- **THEN** la respuesta es HTTP 404

#### Scenario: Documento de otra factura
- **WHEN** se solicita `/invoices/{A}/documents/{D}/download` y `D` pertenece a la factura `B`
- **THEN** la respuesta es HTTP 404

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

#### Scenario: Migración de rutas absolutas existentes
- **WHEN** se migra una base que contiene `C:\Users\x\...\storage\suppliers\1\demo_962e8155a8.txt`
- **THEN** la ruta queda almacenada como `suppliers/1/demo_962e8155a8.txt`
