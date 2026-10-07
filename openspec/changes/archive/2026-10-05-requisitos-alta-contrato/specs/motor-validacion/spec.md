## ADDED Requirements

### Requirement: Contrato y anexos disponibles según los requisitos del contrato
Al validar una factura, DOC-005 (`ERROR`) SHALL evaluar los requisitos obligatorios del contrato de la factura con la configuración vigente (capacidad `requisitos-alta-contrato`):
- `PASS` con el mensaje "Contrato/anexo disponible" si cada requisito obligatorio activo tiene al menos un documento vigente ligado al contrato;
- `FAIL` con el mensaje "Faltan documentos del contrato: <nombre>, <nombre>" si falta alguno, con los nombres en el orden del catálogo;
- `FAIL` con el mensaje "Falta contrato/anexo" si la factura no tiene contrato.

Los documentos de la factura y del expediente del proveedor MUST NOT contar para DOC-005. Un `FAIL` SHALL impedir el envío. Una factura que ya salió de los estados editables SHALL conservar su resultado aunque la configuración o los documentos del contrato cambien después.

#### Scenario: Factura demo con contrato completo
- **WHEN** se valida la factura demo A-CORRECTA después de la migración y de `reset_demo`
- **THEN** DOC-005 resulta `PASS` con "Contrato/anexo disponible"

#### Scenario: Contrato activo sin contrato firmado
- **WHEN** se valida una factura editable cuyo contrato "Activo" existía antes de la migración y no tiene documentos
- **THEN** DOC-005 resulta `FAIL` con "Faltan documentos del contrato: Contrato" y el envío no procede

#### Scenario: Requisito obligatorio agregado después de la activación
- **WHEN** el Administrador hace obligatoria la orden de compra y se valida una factura editable de un contrato activo sin orden de compra
- **THEN** DOC-005 resulta `FAIL` con "Faltan documentos del contrato: Orden de compra", el envío no procede y el contrato sigue "Activo"

#### Scenario: Contrato cargado en la factura
- **WHEN** una factura tiene cargado un documento "Contrato" de los archivos de la factura (HU-04) y su contrato no tiene contrato firmado
- **THEN** DOC-005 resulta `FAIL` con "Faltan documentos del contrato: Contrato"

## MODIFIED Requirements

### Requirement: Reglas documentales según los archivos mínimos configurados
En cada validación, el motor SHALL leer la configuración vigente de archivos mínimos para el origen del proveedor de la factura. Un tipo está presente cuando la factura tiene un documento vigente (`is_current`) de ese tipo. Las reglas documentales SHALL evaluarse así:
- DOC-001 (XML del CFDI, `CRITICAL`), DOC-002 (PDF del CFDI, `ERROR`), DOC-003 (Orden de compra, `ERROR`), DOC-004 (Vo.Bo. del líder de proyecto, `ERROR`) y DOC-008 (Invoice (PDF), `CRITICAL`) resultan `PASS` o `FAIL` cuando su tipo es Obligatorio para ese origen, y `NOT_APPLICABLE` en otro caso;
- DOC-009 (`ERROR`) genera un resultado por cada otro tipo activo que sea Obligatorio para ese origen, con la clave del tipo en `source_document`;
- los mensajes usan el nombre del tipo: "<nombre> presente" o "Falta <nombre>"; en `NOT_APPLICABLE`, "No requerido para proveedores nacionales" o "No requerido para proveedores internacionales";
- DOC-005 se evalúa conforme a "Contrato y anexos disponibles según los requisitos del contrato"; DOC-006 y DOC-007 no cambian.

Un `FAIL` de cualquiera de estas reglas SHALL impedir el envío. Una factura que ya salió de los estados editables SHALL conservar sus resultados aunque la configuración cambie después. Una factura editable SHALL evaluarse con la configuración vigente al verificarse o enviarse.

#### Scenario: Proveedor nacional sin Vo.Bo.
- **WHEN** con la configuración inicial se valida una factura de un proveedor nacional con XML del CFDI, PDF del CFDI y orden de compra, sin Vo.Bo.
- **THEN** DOC-001, DOC-002 y DOC-003 resultan `PASS`, DOC-004 resulta `FAIL` con severidad `ERROR` y el mensaje "Falta Vo.Bo. del líder de proyecto", DOC-008 resulta `NOT_APPLICABLE` y la factura conserva su estatus

#### Scenario: Proveedor internacional sin Invoice
- **WHEN** se valida una factura de un proveedor internacional que no tiene Invoice (PDF)
- **THEN** DOC-008 resulta `FAIL` con severidad `CRITICAL` y el mensaje "Falta Invoice (PDF)", y DOC-001 y DOC-002 resultan `NOT_APPLICABLE` con el mensaje "No requerido para proveedores internacionales"

#### Scenario: Orden de compra opcional
- **WHEN** "Orden de compra" es Opcional para el origen del proveedor y se valida una factura sin orden de compra
- **THEN** DOC-003 resulta `NOT_APPLICABLE` y no descuenta puntos del score

#### Scenario: Tipo soporte obligatorio
- **WHEN** "Reporte de horas" es Obligatorio para Internacional y se valida una factura internacional sin ese documento
- **THEN** existe un resultado DOC-009 `FAIL` con `source_document = SOPORTE_<id>` y el mensaje "Falta Reporte de horas"

#### Scenario: Factura ya enviada
- **WHEN** una factura está "Enviada" sin contrato cargado y el Administrador hace obligatorio "Contrato" para su origen
- **THEN** la factura sigue "Enviada" con los mismos resultados

#### Scenario: Factura en Observaciones enviada de nuevo
- **WHEN** una factura en "Observaciones" sin contrato cargado se envía después de que "Contrato" se hizo obligatorio para su origen
- **THEN** existe un resultado DOC-009 `FAIL` con el mensaje "Falta Contrato", el envío no procede y la factura sigue en "Observaciones"
