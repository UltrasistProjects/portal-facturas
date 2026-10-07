# interfaz-usuario Specification

## Purpose
Interfaz del portal sin diálogos nativos del navegador: confirmaciones en modales del portal y errores de validación de los formularios en español junto a cada campo, con las mismas reglas que ya declaran los campos, formularios que se envían una sola vez y la validación nativa como respaldo sin JavaScript.
## Requirements
### Requirement: Confirmaciones en modales del portal
El código propio del portal (`app/static/js` y `app/templates`, sin `app/static/vendor`) MUST NOT usar `alert`, `confirm` ni `prompt`. Una acción que pide confirmación SHALL mostrar un modal de Bootstrap con la pregunta, un botón para aceptar y otro para cancelar. Cancelar, cerrar el modal o pulsar Esc MUST NOT ejecutar la acción. Aceptar SHALL ejecutar exactamente la misma acción que el botón ejecutaba antes de la confirmación, con los mismos datos.

#### Scenario: Autorizar con confirmación
- **WHEN** el PMO pulsa "Autorizar" en el panel de decisión de una factura "Enviada"
- **THEN** ve un modal con "¿Autorizar la factura {número} para su pago? Se notificará a Recepción de Facturas con copia al proveedor." y no se envía nada hasta que elige

#### Scenario: Aceptar la autorización
- **WHEN** el PMO acepta en el modal
- **THEN** se envía el formulario con `decision=ACCEPTED` y las observaciones capturadas, igual que antes, y la factura queda "Autorizada"

#### Scenario: Cancelar la autorización
- **WHEN** el PMO pulsa "Cancelar", cierra el modal o pulsa Esc
- **THEN** no se envía el formulario, la factura sigue "Enviada" y el foco vuelve al botón "Autorizar"

#### Scenario: Sin diálogos nativos en el código
- **WHEN** se revisan los archivos de `app/static/js` y `app/templates`, sin `app/static/vendor`
- **THEN** no contienen llamadas a `alert(`, `confirm(` ni `prompt(`

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

### Requirement: Mensajes de validación en español
Cada error SHALL mostrarse con un mensaje en español según la regla que no se cumple, y no con el texto del navegador:

| Regla | Mensaje |
|---|---|
| Obligatorio (texto) | "Este campo es obligatorio." |
| Obligatorio (lista) | "Seleccione una opción." |
| Obligatorio (archivo) | "Seleccione un archivo." |
| Obligatorio (casilla) | "Marque la casilla para continuar." |
| Correo electrónico | "Escriba un correo electrónico válido, por ejemplo nombre@empresa.com." |
| Longitud mínima | "Escriba al menos {N} caracteres." |
| Longitud máxima | "Escriba como máximo {N} caracteres." |
| Valor mínimo (número) | "El valor mínimo es {min}." |
| Valor mínimo (fecha) | "La fecha no puede ser anterior al {dd/mm/aaaa}." |
| Decimales (`step` de 0.01) | "Use como máximo 2 decimales." |
| Número o fecha incompletos | "Escriba un número válido." / "Escriba una fecha válida." |

Un campo SHALL poder declarar su propio mensaje para una regla con un atributo de presentación (`data-error-required`, `data-error-pattern`); el formato del campo (`pattern`) MUST tener siempre su mensaje propio. Una regla sin mensaje definido SHALL mostrar, junto al campo, el texto que da el navegador.

#### Scenario: Correo inválido
- **WHEN** el Administrador escribe "ana@" en "Email" del alta de usuario y sale del campo
- **THEN** ve "Escriba un correo electrónico válido, por ejemplo nombre@empresa.com."

#### Scenario: Monto con tres decimales
- **WHEN** el Administrador registra una enmienda con "Monto nuevo" 10.555
- **THEN** ve "Use como máximo 2 decimales." y no se envía

#### Scenario: Nombre de tipo de documento corto
- **WHEN** el Administrador escribe "ab" en el nombre de un tipo de documento y sale del campo
- **THEN** ve "Escriba al menos 3 caracteres."

### Requirement: Comportamiento sin JavaScript
Sin JavaScript, los formularios SHALL conservar la validación nativa del navegador y el panel de decisión SHALL enviar "Autorizar" sin confirmación, como hoy. El servidor SHALL seguir validando todos los datos con las mismas reglas y mensajes.

#### Scenario: Navegador sin JavaScript
- **WHEN** el usuario envía "Crear usuario" con "Nombre" vacío y JavaScript deshabilitado
- **THEN** el navegador bloquea el envío con su aviso nativo, como antes del cambio

### Requirement: Un solo envío por formulario
Con JavaScript, cada formulario `POST` del portal SHALL enviarse una sola vez: tras el primer envío SHALL ignorar los siguientes y deshabilitar sus botones de envío, de modo que un segundo clic mientras el servidor responde (por ejemplo, mientras sale el correo de una cancelación) MUST NOT repetir la operación. La petición SHALL conservar el nombre y el valor del botón pulsado, como la decisión del PMO. El bloqueo MUST NOT aplicarse a un envío que el navegador no hace porque el formulario es inválido, ni a los envíos que el script del formulario cancela para hacerlos por su cuenta (por `fetch` o tras su propio modal de confirmación). Al volver a la página con "Atrás" desde la caché del navegador, el formulario SHALL aceptar un nuevo envío y sus botones SHALL estar habilitados. Sin JavaScript, el servidor SHALL seguir rechazando la operación repetida con su error de negocio.

#### Scenario: Segundo clic mientras responde el servidor
- **WHEN** el proveedor pulsa "Cancelar factura" con su acuse y vuelve a pulsarlo antes de que el portal responda
- **THEN** el navegador hace una sola petición, el botón queda deshabilitado y la factura se cancela sin el error "La factura ya está cancelada"

#### Scenario: Decisión del PMO
- **WHEN** el PMO confirma "Autorizar" en el modal
- **THEN** la petición lleva `decision=ACCEPTED` y los botones del panel "Decisión" quedan deshabilitados

#### Scenario: Formulario inválido
- **WHEN** el usuario envía un formulario con un campo obligatorio vacío, lo corrige y lo envía de nuevo
- **THEN** el segundo envío procede: el primero no llegó a hacerse y no bloqueó el formulario

#### Scenario: Volver con "Atrás"
- **WHEN** el usuario envía un formulario y vuelve a la página con "Atrás" desde la caché del navegador
- **THEN** los botones del formulario están habilitados y un nuevo envío procede

