## ADDED Requirements

### Requirement: Verificación del tema de login
El tema `ultrasist` SHALL verificarse de dos formas.

**Con pytest, sin Keycloak ni red** (`tests/test_tema_keycloak.py`), que comprueba:
- que el tema hereda de `base`;
- que cada plantilla sobrescrita conserva el `action` de su formulario (`url.loginAction`), sus nombres de campo, sus campos ocultos y el manejo de `message` y `messagesPerField`;
- que las plantillas no fijan texto visible, y que toda clave propia `ultrasist…` que usan existe en `messages_es.properties`;
- que las plantillas y el CSS propio no referencian URLs externas ni `data-demo`;
- que las copias de `resources/vendor/` son idénticas a las de `app/static/vendor/`;
- que la versión de Keycloak anotada en el tema es la misma que la imagen de `compose.yaml`;
- que la política de contraseñas tiene una sola `regexPattern`, porque `messages_es.properties` reescribe su mensaje como "debe incluir al menos una letra".

**Con un recorrido E2E en `tests/hu`**, contra Keycloak real y Mailpit:
- recorre los escenarios de "Pantallas de Keycloak con el diseño del portal" y "Restablecimiento de contraseña por correo" en 1440×900 y en 390×844, y verifica los eventos del restablecimiento con la API de administración de Keycloak;
- deja capturas como evidencia.

**SonarQube:** SHALL analizar `infra/keycloak/themes` junto con `app`, excluyendo los `vendor/`.

#### Scenario: Campo renombrado en una plantilla
- **WHEN** una plantilla del tema cambia el nombre del campo `password-new`
- **THEN** la prueba del contrato de formularios falla indicando la plantilla y el campo

#### Scenario: Texto fijo en una plantilla
- **WHEN** una plantilla del tema contiene texto visible fuera de `msg(...)`
- **THEN** la prueba de textos falla indicando la plantilla

#### Scenario: Recurso externo
- **WHEN** una plantilla o el CSS propio del tema referencia una URL `https://`
- **THEN** la prueba falla

#### Scenario: Actualización de Keycloak sin revisar el tema
- **WHEN** cambia la versión de la imagen de Keycloak en `compose.yaml` y no la versión anotada en el tema
- **THEN** la prueba falla indicando revisar las plantillas sobrescritas contra las de `base` de la nueva versión

#### Scenario: Alcance de SonarQube
- **WHEN** se inspecciona `sonar-project.properties`
- **THEN** `sonar.sources` incluye `app` e `infra/keycloak/themes`, y `sonar.exclusions` excluye los `vendor/` de ambos
