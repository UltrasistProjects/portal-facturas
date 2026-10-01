## MODIFIED Requirements

### Requirement: Sin datos sensibles en logs
El log MUST NOT contener:
- contraseñas, incluidas las temporales, ni hashes;
- identificadores de sesión, tokens CSRF, códigos de autorización, `state`, `nonce` ni `code_verifier`;
- ID tokens, access tokens ni refresh tokens, ni los cuerpos de las respuestas del token endpoint o de la API de administración de Keycloak;
- `SECRET_KEY`, `SMTP_PASSWORD`, `KEYCLOAK_CLIENT_SECRET` ni `KEYCLOAK_ADMIN_CLIENT_SECRET`;
- RFC, datos bancarios, contenido de archivos ni nombres originales de archivo;
- el asunto, el cuerpo o los destinatarios de los correos.

Las llamadas a Keycloak SHALL registrarse sólo con la operación, el código HTTP y la duración.

#### Scenario: Revisión del log tras el flujo completo
- **WHEN** se ejecuta el flujo de callback rechazado, inicio de sesión exitoso, subida de documentos, validación y revisión, y se busca en el log `password`, `csrf`, el código de autorización, el ID token, el RFC del proveedor y el RFC receptor
- **THEN** no hay coincidencias

#### Scenario: Revisión del log tras aprovisionar
- **WHEN** se autorizan proveedores, uno con Keycloak devolviendo un error con cuerpo, y se buscan en el log las contraseñas temporales, el token de la cuenta de servicio, los secretos de los clientes y el cuerpo del error
- **THEN** no hay coincidencias, y sí hay líneas con la operación, el código HTTP y la duración

#### Scenario: Revisión del log tras enviar correos
- **WHEN** con `SMTP_PASSWORD` definida se guarda el buzón, se envía un correo de prueba y se envía un correo de evento, y se busca en el log la contraseña SMTP, las direcciones del buzón y de la prueba, y el asunto enviado
- **THEN** no hay coincidencias
