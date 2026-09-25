## ADDED Requirements

### Requirement: Reglas documentales según los archivos mínimos configurados
En cada prevalidación, el motor SHALL leer la configuración vigente de archivos mínimos para el origen del proveedor de la factura. Un tipo está presente cuando la factura tiene un documento vigente (`is_current`) de ese tipo. Las reglas documentales SHALL evaluarse así:
- DOC-001 (XML del CFDI, `CRITICAL`), DOC-002 (PDF del CFDI, `ERROR`), DOC-003 (Orden de compra, `ERROR`), DOC-004 (Vo.Bo. del líder de proyecto, `ERROR`) y DOC-008 (Invoice (PDF), `CRITICAL`) resultan `PASS` o `FAIL` cuando su tipo es Obligatorio para ese origen, y `NOT_APPLICABLE` en otro caso;
- DOC-009 (`ERROR`) genera un resultado por cada otro tipo activo que sea Obligatorio para ese origen, con la clave del tipo en `source_document`;
- los mensajes usan el nombre del tipo: "<nombre> presente" o "Falta <nombre>"; en `NOT_APPLICABLE`, "No requerido para proveedores nacionales" o "No requerido para proveedores internacionales";
- DOC-005, DOC-006 y DOC-007 no cambian.

Un `FAIL` de cualquiera de estas reglas SHALL dejar la factura en `REQUIRES_CORRECTION`. Una factura que ya salió de los estados editables SHALL conservar sus resultados aunque la configuración cambie después. Una factura editable SHALL evaluarse con la configuración vigente al volver a prevalidarse.

#### Scenario: Proveedor nacional sin Vo.Bo.
- **WHEN** con la configuración inicial se prevalida una factura de un proveedor nacional con XML del CFDI, PDF del CFDI y orden de compra, sin Vo.Bo.
- **THEN** DOC-001, DOC-002 y DOC-003 resultan `PASS`, DOC-004 resulta `FAIL` con severidad `ERROR` y el mensaje "Falta Vo.Bo. del líder de proyecto", DOC-008 resulta `NOT_APPLICABLE` y la factura queda en `REQUIRES_CORRECTION`

#### Scenario: Proveedor internacional sin Invoice
- **WHEN** se prevalida una factura de un proveedor internacional que no tiene Invoice (PDF)
- **THEN** DOC-008 resulta `FAIL` con severidad `CRITICAL` y el mensaje "Falta Invoice (PDF)", y DOC-001 y DOC-002 resultan `NOT_APPLICABLE` con el mensaje "No requerido para proveedores internacionales"

#### Scenario: Orden de compra opcional
- **WHEN** "Orden de compra" es Opcional para el origen del proveedor y se prevalida una factura sin orden de compra
- **THEN** DOC-003 resulta `NOT_APPLICABLE` y no descuenta puntos del score

#### Scenario: Tipo soporte obligatorio
- **WHEN** "Reporte de horas" es Obligatorio para Internacional y se prevalida una factura internacional sin ese documento
- **THEN** existe un resultado DOC-009 `FAIL` con `source_document = SOPORTE_<id>` y el mensaje "Falta Reporte de horas"

#### Scenario: Factura ya prevalidada
- **WHEN** una factura está en `PREVALIDATED` sin contrato cargado y el Administrador hace obligatorio "Contrato" para su origen
- **THEN** la factura sigue en `PREVALIDATED` con los mismos resultados y puede enviarse a revisión

#### Scenario: Factura editable prevalidada de nuevo
- **WHEN** una factura en `REQUIRES_CORRECTION` sin contrato cargado se vuelve a prevalidar después de que "Contrato" se hizo obligatorio para su origen
- **THEN** existe un resultado DOC-009 `FAIL` con el mensaje "Falta Contrato"
