## MODIFIED Requirements

### Requirement: Descarga segura de documentos
La descarga de documentos SHALL responder siempre con `Content-Type: application/octet-stream` y `Content-Disposition: attachment` con el nombre saneado, sin importar el MIME almacenado. La autorización existente se mantiene: un Proveedor sólo puede descargar documentos de facturas de su proveedor, y el documento debe pertenecer a la factura de la URL.

#### Scenario: Descarga de un PDF
- **WHEN** un usuario autorizado descarga un documento PDF
- **THEN** la respuesta tiene `Content-Type: application/octet-stream` y `Content-Disposition: attachment; filename="..."`

#### Scenario: Proveedor intenta descargar documento ajeno
- **WHEN** un Proveedor solicita la descarga de un documento de una factura de otro proveedor
- **THEN** la respuesta es HTTP 404

#### Scenario: Documento de otra factura
- **WHEN** se solicita `/invoices/{A}/documents/{D}/download` y `D` pertenece a la factura `B`
- **THEN** la respuesta es HTTP 404

### Requirement: Visualización segura de documentos
`GET /invoices/{invoice_id}/documents/{document_id}/view` SHALL mostrar el documento dentro de una página del portal, con la misma autorización que la descarga: un `Proveedor` sólo ve documentos de facturas de su proveedor y el documento debe pertenecer a la factura de la URL; en otro caso, HTTP 404. Según el formato del documento, determinado por la extensión verificada al cargarlo:
- **PDF:** cada página se muestra como una imagen PNG que el servidor renderiza con `GET .../pages/{n}` (`n` desde 1), a lo sumo las primeras 20 páginas, con el aviso "Se muestran las primeras 20 de N páginas" si hay más. Un PDF que no puede abrirse muestra "No se pudo mostrar el documento" y el enlace de descarga;
- **PNG y JPEG:** la imagen servida por `GET .../image` con el MIME de su extensión y `Content-Disposition: inline`;
- **XML y TXT:** su texto, escapado, en un bloque de texto preformateado; a lo sumo 200 000 caracteres, con el aviso "Se muestran los primeros 200,000 caracteres" si hay más.

`.../pages/{n}` SHALL responder HTTP 404 para una página inexistente o un documento que no es PDF, y `.../image` para un documento que no es PNG ni JPEG. Estas rutas MUST NOT entregar al navegador el archivo original como PDF, XML o texto. La descarga (`.../download`) SHALL seguir respondiendo como adjunto.

#### Scenario: PDF del CFDI
- **WHEN** el PMO abre "Ver" sobre el PDF del CFDI de una factura
- **THEN** la página muestra una imagen por página del PDF, cuyas respuestas son `image/png`

#### Scenario: XML con marcado
- **WHEN** el PMO abre "Ver" sobre un XML del CFDI
- **THEN** la página muestra el texto del XML escapado (`&lt;cfdi:Comprobante`) y el navegador no lo interpreta como XML

#### Scenario: Documento ajeno
- **WHEN** un proveedor pide "Ver" o una página de un documento de una factura de otro proveedor
- **THEN** la respuesta es HTTP 404

#### Scenario: Página inexistente
- **WHEN** se pide la página 99 de un PDF de una página
- **THEN** la respuesta es HTTP 404
