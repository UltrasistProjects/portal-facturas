## MODIFIED Requirements

### Requirement: Errores de validación junto al campo
Con JavaScript, los formularios del portal SHALL validar en el navegador exactamente las reglas que ya declaran sus campos (`required`, `pattern`, `minlength`, `maxlength`, `min`, `max`, `step` y `type`), sin agregar ni quitar reglas, y MUST NOT mostrar la burbuja nativa del navegador. Cada error SHALL pintarse debajo de su campo (o de la zona de arrastre que contiene el campo de archivo), con el campo marcado como inválido (`is-invalid`, `aria-invalid="true"`) y el mensaje enlazado con `aria-describedby`.

Al enviar un formulario con campos inválidos, el envío MUST NOT proceder, igual que hoy; SHALL marcar todos los campos inválidos y llevar el foco al primero. Un campo SHALL validarse cuando el usuario confirma un valor cambiado (al salir del campo o al elegir una opción o archivo); desde que muestra un error, el mensaje SHALL actualizarse con cada cambio y desaparecer en cuanto el valor es válido. Un campo deshabilitado u oculto que no se valida hoy (por ejemplo, los que `supplier_form.js` deshabilita) MUST NOT mostrar error, y si lo mostraba, SHALL quitarse.

#### Scenario: Enviar con un obligatorio vacío
- **WHEN** el Administrador pulsa "Crear usuario" con "Nombre" vacío
- **THEN** el formulario no se envía, debajo de "Nombre" aparece "Este campo es obligatorio." y el foco queda en "Nombre"

#### Scenario: El error desaparece al corregir
- **WHEN** "Nombre" muestra el error y el Administrador escribe un carácter
- **THEN** el mensaje y la marca de inválido desaparecen sin enviar el formulario

#### Scenario: Error al salir del campo
- **WHEN** el proveedor escribe "agosto 2026" en "Periodo de servicio" y pasa al siguiente campo
- **THEN** debajo del campo aparece "Use el formato MM/AAAA, por ejemplo 08/2026." sin intentar el envío

#### Scenario: Recorrer campos sin escribir
- **WHEN** el usuario pasa con Tab por campos obligatorios vacíos sin cambiarlos
- **THEN** no aparece ningún error hasta que intente enviar

#### Scenario: Documento sin archivo
- **WHEN** el proveedor pulsa "Cargar documento" sin elegir archivo
- **THEN** el formulario no se envía, la zona de arrastre se marca como inválida y debajo aparece "Seleccione un archivo."

#### Scenario: Campo que deja de aplicar
- **WHEN** en el alta de proveedor "RFC" muestra "Este campo es obligatorio." y el Administrador cambia el origen a "Internacional"
- **THEN** el campo RFC se oculta como hoy y su mensaje desaparece

#### Scenario: Rechazar sin observaciones
- **WHEN** el PMO pulsa "Rechazar" con el campo de observaciones visible y vacío
- **THEN** el formulario no se envía y debajo del campo aparece "Capture las observaciones."

#### Scenario: Formularios con confirmación propia
- **WHEN** el Administrador pulsa "Cargar proveedores" en la carga masiva de proveedores sin elegir archivo
- **THEN** aparece el error junto al campo y no se hace la petición al servidor ni se abre ningún modal, igual que hoy
