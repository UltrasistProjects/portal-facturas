## MODIFIED Requirements

### Requirement: Bitácora de envíos
Cada intento de envío SHALL quedar registrado con:
- el evento, o ninguno si es el correo de prueba;
- el resultado (`SENT` o `FAILED`) y, si falló, el error técnico de hasta 300 caracteres;
- las direcciones de "Para" y de "Cc";
- el transporte (`smtp` o `file`) y el `Message-ID`;
- la entidad relacionada y su identificador, si los hay;
- el usuario que lo originó y la fecha.

La bitácora MUST NOT guardar el asunto ni el cuerpo del correo. `/admin/notifications` SHALL mostrar todos los envíos, paginados de 25 en 25 (spec `listados-paginados`), del más reciente al más antiguo, con fecha, evento ("Prueba" para el correo de prueba), destinatarios, resultado y error.

#### Scenario: Envío registrado sin contenido
- **WHEN** se envía el correo de Rechazada de una factura
- **THEN** existe un registro en la bitácora con el evento `INVOICE_REJECTED`, la entidad "Invoice" y su id, y ninguna columna contiene el asunto ni el cuerpo

#### Scenario: Envíos en la pantalla
- **WHEN** hay 30 envíos registrados y el Administrador abre `/admin/notifications`
- **THEN** la bitácora muestra los 25 más recientes, empezando por el último, y en la página 2 los 5 restantes
