## ADDED Requirements

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
