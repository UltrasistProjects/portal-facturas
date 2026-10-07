> Rutas relativas a la raíz de la PoC (`PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress-V1/PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress/`), salvo `openspec/` y `docs/`.
>
> Cada grupo termina con `ruff` limpio y sus pruebas en verde.
>
> Las plantillas de referencia salen del JAR `org.keycloak.keycloak-themes-26.7.4.jar` de la imagen (`/opt/keycloak/lib/lib/main/`). Se extraen al scratchpad y no se versionan.

## 0. Aprobación

- [x] 0.1 Obtener la aprobación de las decisiones 1 a 4 del proposal (restablecimiento y EP-01, SMTP de Keycloak, Mailpit, "usted") y respuesta a las preguntas abiertas 2 y 4 del design (vigencia del enlace, eventos del restablecimiento). Si se rechaza la 1 o la 2, retirar el requisito "Restablecimiento de contraseña por correo", `resetPasswordAllowed`, el SMTP y Mailpit de los specs y de estas tareas antes de seguir.
  - **2026-10-06:** el usuario respondió "continue" a la propuesta. Se aplican las recomendaciones: decisiones 1 a 3 aprobadas y "usted" en la 4.
  - **Preguntas abiertas 2 y 4:** no se modifica el realm. El enlace mantiene su vigencia de 5 minutos y no se agregan eventos.

## 1. Estructura y estilos del tema

- [x] 1.1 `infra/keycloak/themes/ultrasist/login/theme.properties` (D2, D3):
  - `parent=base`, `import=common/keycloak`, `locales=es`;
  - `styles` con `vendor/bootstrap.min.css`, `vendor/bootstrap-icons.min.css` y `css/ultrasist.css`;
  - las clases `kc*` que usan las plantillas de `base` asignadas a clases de Bootstrap;
  - iconos de visibilidad de la contraseña `bi bi-eye` y `bi bi-eye-slash`;
  - la versión de Keycloak de referencia (`26.7.4`).
- [x] 1.2 `resources/vendor/` (D3):
  - copia idéntica de `app/static/vendor/bootstrap.min.css`, `bootstrap-icons.min.css` y `fonts/`;
  - README con versiones y licencias (MIT).
- [x] 1.3 `resources/img/`: `Ultrasistlogo.png` y `favicon.png` del portal.
- [x] 1.4 `resources/css/ultrasist.css` (D3):
  - reglas del login de `c5f389f^:app/static/css/app.css`, *tokens* `:root` y ajustes de `.btn`, `.btn-primary`, `.form-control` y `.alert` del portal;
  - estilos de las alertas por tipo, de la ayuda de RF-06 y del encabezado compacto con logo para menos de 700 px;
  - sin desplazamiento horizontal desde 360 px.

## 2. Plantillas y textos

- [x] 2.1 `template.ftl` a partir de `base/login/template.ftl` 26.7.4 (D3, D4):
  - layout del login anterior (panel de marca y tarjeta);
  - favicon y hojas de estilo del tema;
  - se conservan sin cambios los scripts de `authChecker` y de enlaces de un solo uso, el *importmap*, los mensajes (`displayMessage`, `kcSanitize`, regla de `isAppInitiatedAction`), `show-username` y reinicio del flujo, "probar otra forma", organización, `socialProviders`, `info` y pie;
  - clase `kc-feedback-text` en el texto de la alerta;
  - comentario de versión.
- [x] 2.2 `login.ftl` a partir de `base/login/login.ftl` 26.7.4:
  - contrato de D4 intacto y los IDs `username`, `password`, `kc-login`, `kc-form-login` e `input-error`;
  - enlace "¿Olvidó su contraseña?" sólo con `realm.resetPasswordAllowed`;
  - sin `data-demo` ni JS de acceso rápido.
- [x] 2.3 `login-reset-password.ftl` a partir de la de `base` 26.7.4: contrato de D4, `input-error-username` y el texto de instrucciones.
- [x] 2.4 `login-update-password.ftl` a partir de la de `base` 26.7.4 (D4, D6):
  - contrato de D4, con `logout-sessions` y `cancel-aia` en una acción iniciada por la aplicación;
  - IDs `kc-submit`, `kc-cancel` e `input-error-password*`;
  - ayuda de RF-06 enlazada con `aria-describedby`;
  - sin validación en el navegador.
- [x] 2.5 `messages/messages_es.properties` (UTF-8, D5):
  - claves `ultrasist…` del diseño;
  - textos del login anterior con acentos;
  - sobrescritura en español de México, con "usted", de las claves de Keycloak de estos flujos: login, credenciales inválidas, bloqueo, restablecimiento, confirmación, política (incluida `invalidPasswordRegexPatternMessage`), no coinciden, enlace expirado o usado, página expirada, error, información y volver al portal.

## 3. Realm y despliegue local

- [x] 3.1 `infra/keycloak/realm-ultrasist-portal.json`: `loginTheme: "ultrasist"` y `resetPasswordAllowed: true`. No se tocan clientes, roles, flujos ni política.
- [x] 3.2 `infra/keycloak/configure-realm.sh` (D7, D8):
  - `kcadm.sh` con `KCADM_USER`/`KCADM_PASSWORD` o las credenciales de *bootstrap*, y configuración en un archivo temporal que se borra con `trap`;
  - actualiza `loginTheme` y `resetPasswordAllowed`;
  - `smtpServer` a partir de `KEYCLOAK_SMTP_*`, con autenticación y STARTTLS opcionales;
  - idempotente, con mensajes de error claros y sin imprimir contraseñas.
- [x] 3.3 `compose.yaml`:
  - en `keycloak`: montajes `:ro` del tema y del script, y variables `KEYCLOAK_SMTP_*` con valores por defecto hacia `mailpit`;
  - servicio `mailpit` (`axllent/mailpit:v1.31.4`): interfaz web en `127.0.0.1:${MAILPIT_PORT:-58025}`, SMTP sin publicar, healthcheck y `restart: "no"`.
- [x] 3.4 `run_local.sh`, `run_local.ps1` y `run_local.bat`: `up -d --wait db keycloak mailpit` y después `docker compose exec -T keycloak bash /opt/keycloak/scripts/configure-realm.sh`.
- [x] 3.5 `.env.example`: `MAILPIT_PORT` y `KEYCLOAK_SMTP_*` comentadas, con la nota de que en QA la contraseña SMTP se configura en Keycloak.
- [x] 3.6 Aplicarlo al Keycloak local existente sin borrar el volumen (`DOCKER_CONTEXT=default`):
  - recrear `keycloak` con los montajes nuevos, levantar `mailpit` y ejecutar el script dos veces;
  - verificar con GET a la API de administración `loginTheme`, `resetPasswordAllowed` y `smtpServer`, y que siguen los usuarios, los clientes y la política;
  - comprobar que la página de login carga `/login/ultrasist/` y no `keycloak.v2`.

## 4. Pruebas estáticas y calidad

- [x] 4.1 Nuevo `tests/test_tema_keycloak.py` (spec `calidad-y-pruebas`, D9):
  - herencia de `base`;
  - contrato de los tres formularios;
  - plantillas sin texto visible fijo, y claves `ultrasist…` presentes;
  - sin URLs externas ni `data-demo`;
  - `vendor/` idéntico al del portal;
  - versión del tema igual a la imagen de `compose.yaml`;
  - una sola `regexPattern` en la política;
  - realm con tema y restablecimiento, sin `smtpServer`, y `directAccessGrantsEnabled: false`;
  - montajes `:ro` y `mailpit` en `127.0.0.1` con versión exacta;
  - script coherente con el realm y sin secretos.
- [x] 4.2 Revisar `tests/test_realm_keycloak.py` y ampliarlo sólo si alguna de sus verificaciones de `compose.yaml` cambia con los montajes nuevos.
- [x] 4.3 `sonar-project.properties`: `sonar.sources=app,infra/keycloak/themes` y exclusión de `infra/keycloak/themes/**/vendor/**`.
- [x] 4.4 `ruff check`, `ruff format --check` y la suite completa con `DOCKER_CONTEXT=default python scripts/ci_tests.py`, en verde.
  - **2026-10-06:** 1215 pruebas pasan, cobertura de 97.06 %, ruff limpio. Una primera corrida dio un error en el *teardown* porque el E2E escribía en la base de trabajo al mismo tiempo; el guardián de `conftest.py` lo detectó. Repetida sin el E2E, pasa.
  - El quality gate de SonarQube corre en el PR hacia `qa`; no se puede ejecutar en local.

## 5. Verificación E2E con Keycloak real

- [x] 5.1 Antes de detener el `uvicorn --reload` del usuario en :8000 (lo exige la suite `tests/hu`), pedir autorización y hacer un respaldo con `scripts/backup.py`. Arrancar el portal con `MAIL_BACKEND=file MAIL_OUTBOX_DIR=./evidencias/_correos`.
  - **2026-10-06:** no había ningún servidor en :8000, así que no hubo que detener nada. Se levantó uno temporal con transporte `file` y se apagó al terminar.
- [x] 5.2 Recorrido del tema en `tests/hu`, siguiendo las convenciones de su README, en 1440×900 y en 390×844, con captura de cada página:
  - el Administrador crea un PMO;
  - primer acceso con la temporal, con errores de política (`Password123`, `Portal2026!`) y cambio obligatorio;
  - credenciales inválidas;
  - restablecimiento con un correo inexistente: mismo mensaje y sin correo en Mailpit;
  - restablecimiento con el correo del PMO: correo en Mailpit, nueva contraseña con un error de política y después una válida;
  - enlace reutilizado: página de enlace usado;
  - login con la contraseña nueva y rechazo de la anterior;
  - cambio voluntario con "Cancelar".

  En cada página: ninguna hoja de estilo de `keycloak.v2` ni de PatternFly, todas desde `/login/ultrasist/`, logo visible y `scrollWidth <= innerWidth`.
- [x] 5.3 Regresión: ejecutar sin cambios las especificaciones de `tests/hu` que inician sesión (HU-10 y una por rol), y la grabación del video si se mantiene vigente. Restaurar `evidencias/playwright-resultados.json` si una corrida auxiliar lo sobrescribe.
  - **2026-10-06:** HU-01, HU-02, HU-03 y HU-10 en PASS (16/16 escenarios). HU-10 esperaba el título por defecto de Keycloak, "Modificar contraseña"; se cambió a "Cambiar contraseña", el del tema y el del menú del portal. Los selectores no cambiaron.
  - Se restauraron las evidencias versionadas de esa corrida parcial y se borraron sus archivos nuevos, para no mezclar corridas en el PDF de las HUs.
  - El video no se volvió a grabar: usa los mismos selectores que HU-10.
- [x] 5.4 Verificaciones manuales con captura:
  - enlace expirado (esperar más de 300 s);
  - cuenta deshabilitada en el portal: mismo mensaje y sin correo;
  - página expirada (volver atrás tras enviar un formulario);
  - confirmación de cierre de sesión (`/protocol/openid-connect/logout` sin `id_token_hint`).
  - **2026-10-06:** la cuenta deshabilitada y la confirmación de cierre quedaron dentro del E2E (5.2). La página expirada y el enlace vencido (310 s, en el mismo navegador y en otro) se capturaron en `evidencias/tema-login-keycloak/manual/`, todas con el tema.
- [x] 5.5 Revisar todas las capturas en escritorio y en móvil, y relanzar el `uvicorn --reload` del usuario en :8000 como estaba.

## 6. Documentación y cierre

- [x] 6.1 `README.md`, sección "Keycloak: inicio de sesión y cuentas":
  - el tema `ultrasist` y dónde editar textos y estilos;
  - `configure-realm.sh` y por qué existe (`--import-realm` no reimporta);
  - Mailpit (URL de la interfaz web) y el restablecimiento en local;
  - pasos de QA y producción (copiar el tema, reiniciar, script o consola, SMTP según D2);
  - procedimiento al actualizar Keycloak (`diff` contra `base`);
  - *rollback*.

  Retirar "para funciones futuras como la recuperación de contraseña".
- [x] 6.2 `docs/stories/epics/EP-01 Acceso y gestion de facturas del proveedor.md`: sacar la recuperación de contraseña de "Fuera del alcance" y anotar este cambio. Sólo si se aprobó la decisión 1.
- [x] 6.3 `openspec validate tema-login-keycloak --strict` sin errores.
- [x] 6.4 Resumen final para el usuario:
  - archivos creados y modificados;
  - cómo se despliega y activa el tema;
  - cómo se verificó cada criterio de aceptación, con sus evidencias;
  - hallazgos: SMTP, política vs. RF-06, `resetPasswordAllowed`, vigencia del enlace, eventos y alcance de EP-01.

## 7. Registro de los restablecimientos (pedido el 2026-10-06)

- [x] 7.1 `realm-ultrasist-portal.json` y `configure-realm.sh` (`EVENT_TYPES`): agregar `SEND_RESET_PASSWORD`, `SEND_RESET_PASSWORD_ERROR`, `EXECUTE_ACTION_TOKEN`, `EXECUTE_ACTION_TOKEN_ERROR`, `RESET_PASSWORD` y `RESET_PASSWORD_ERROR` a `enabledEventTypes` (D10). La vigencia del enlace no cambia.
- [x] 7.2 Aplicarlo al Keycloak local con el script (dos veces) y comprobar `GET /events/config`: los 15 tipos y la retención de 30 días.
- [x] 7.3 Pruebas:
  - `tests/test_tema_keycloak.py`: eventos del restablecimiento en el realm, retención de 30 días y `EVENT_TYPES` del script igual a `enabledEventTypes` del JSON;
  - E2E: paso final que consulta `GET /admin/realms/ultrasist-portal/events` y exige `SEND_RESET_PASSWORD`, `UPDATE_PASSWORD`/`UPDATE_PASSWORD_ERROR` y `RESET_PASSWORD_ERROR` con `user_not_found`, `expired_code` y `user_disabled`. Guarda los eventos en `verificaciones.json`.
  - Enlace alterado, a mano: `EXECUTE_ACTION_TOKEN_ERROR` / `invalid_code`.
- [x] 7.4 Specs (`autenticacion-sesiones`, `infraestructura-local`, `calidad-y-pruebas`), design (D10) y README.
