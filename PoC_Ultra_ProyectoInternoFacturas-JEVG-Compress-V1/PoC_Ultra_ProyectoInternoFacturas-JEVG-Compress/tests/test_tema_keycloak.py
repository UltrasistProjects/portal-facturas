"""Tema de login "ultrasist" de Keycloak (tema-login-keycloak; specs autenticacion-sesiones, infraestructura-local y
calidad-y-pruebas): plantillas que conservan el contrato de los formularios de Keycloak, textos solo en
messages_es.properties, sin recursos externos ni credenciales, assets identicos a los del portal y el tema asignado al
realm por el JSON versionado y por configure-realm.sh. Sin Keycloak ni red."""

import json
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest
import yaml

from app.core.config import settings
from tests.conftest import ROOT

KEYCLOAK_DIR = ROOT / "infra" / "keycloak"
THEME = KEYCLOAK_DIR / "themes" / "ultrasist" / "login"
TEMPLATES = sorted(THEME.glob("*.ftl"))
CSS = THEME / "resources" / "css" / "ultrasist.css"
REALM = json.loads((KEYCLOAK_DIR / "realm-ultrasist-portal.json").read_text(encoding="utf-8"))
SERVICES = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))["services"]
SCRIPT = (KEYCLOAK_DIR / "configure-realm.sh").read_text(encoding="utf-8")
LOGIN_ACTION = 'action="${url.loginAction}"'

# Lo que cada plantilla sobrescrita conserva de su original de base/login (Keycloak 26.7.4): a donde envia el
# formulario, los campos que Keycloak lee, los mensajes y los IDs que usa la suite tests/hu.
CONTRACT = {
    "login.ftl": [
        LOGIN_ACTION,
        'name="username"',
        'name="password"',
        'name="credentialId"',
        'name="rememberMe"',
        'name="login"',
        "messagesPerField.existsError('username','password')",
        "messagesPerField.getFirstError('username','password')",
        "<#if realm.resetPasswordAllowed>",
        "${url.loginResetCredentialsUrl}",
        "<@passkeys.conditionalUIData />",
        'id="username"',
        'id="password"',
        'id="kc-login"',
        'id="input-error"',
    ],
    "login-reset-password.ftl": [
        LOGIN_ACTION,
        'name="username"',
        "${(auth.attemptedUsername!'')}",
        "messagesPerField.existsError('username')",
        "${url.loginUrl}",
        'msg("emailInstruction")',
        'msg("emailInstructionUsername")',
        'id="input-error-username"',
    ],
    "login-update-password.ftl": [
        LOGIN_ACTION,
        'name="password-new"',
        'name="password-confirm"',
        "<@passwordCommons.logoutOtherSessions/>",
        'name="login"',
        "<#if isAppInitiatedAction??>",
        'name="cancel-aia" value="true"',
        "messagesPerField.existsError('password','password-confirm')",
        "messagesPerField.get('password')",
        "messagesPerField.get('password-confirm')",
        'id="password-new"',
        'id="password-confirm"',
        'id="kc-submit"',
        'id="kc-cancel"',
    ],
    "template.ftl": [
        '<#macro registrationLayout bodyClass="" displayInfo=false displayMessage=true displayRequiredFields=false>',
        '<#nested "header">',
        '<#nested "show-username">',
        '<#nested "form">',
        '<#nested "socialProviders">',
        '<#nested "info">',
        "<#if displayMessage && message?has_content && (message.type != 'warning' || !isAppInitiatedAction??)>",
        "${kcSanitize(message.summary)?no_esc}",
        "auth.showTryAnotherWayLink()",
        "checkAuthSession(",
        "startSessionPolling(",
        "${url.loginRestartFlowUrl}",
        "<@loginFooter.content/>",
    ],
}
DEMO_PASSWORDS = ("Admin#Demo2026", "Pmo#Demo2026", "Proveedor#Demo2026")


def properties(path: Path) -> dict[str, str]:
    """Pares clave=valor de un .properties de Keycloak (sin lineas de continuacion)."""
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith(("#", "!")):
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    return values


THEME_PROPERTIES = properties(THEME / "theme.properties")
MESSAGES = properties(THEME / "messages" / "messages_es.properties")


def without_freemarker(text: str) -> str:
    """El marcado HTML que queda al quitar comentarios, directivas, macros e interpolaciones de FreeMarker."""
    text = re.sub(r"<#--.*?-->", "", text, flags=re.S)
    text = re.sub(r"</?[#@][^>]*>", "", text)
    return re.sub(r"\$\{[^}]*\}", "", text)


class VisibleText(HTMLParser):
    """Texto visible y atributos legibles (alt, title, placeholder, aria-label y el value de los botones) fuera de
    <script>/<style>. El value de los campos ocultos no se muestra."""

    READABLE = {"alt", "title", "placeholder", "aria-label"}

    def __init__(self):
        super().__init__()
        self.texts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self._skip += 1
        attributes = dict(attrs)
        readable = set(self.READABLE)
        if tag == "input" and attributes.get("type") in {"submit", "button", "reset"}:
            readable.add("value")
        self.texts += [value for name, value in attrs if name in readable and value]

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            self.texts.append(data)


def test_tema_hereda_de_base_sin_estilos_de_keycloak():
    assert THEME_PROPERTIES["parent"] == "base" and THEME_PROPERTIES["locales"] == "es"
    assert "stylesCommon" not in THEME_PROPERTIES  # nada de PatternFly ni de keycloak.v2
    styles = THEME_PROPERTIES["styles"].split()
    assert styles == ["vendor/bootstrap.min.css", "vendor/bootstrap-icons.min.css", "css/ultrasist.css"]
    assert all((THEME / "resources" / style).is_file() for style in styles)
    assert {path.name for path in TEMPLATES} == set(CONTRACT)


def test_version_del_tema_igual_a_la_imagen_de_keycloak():
    image_version = SERVICES["keycloak"]["image"].rpartition(":")[2]
    assert THEME_PROPERTIES["keycloakVersion"] == image_version, (
        "Cambio la version de Keycloak: compare las plantillas del tema con las de base/login de la nueva version y "
        "actualice keycloakVersion en theme.properties"
    )
    for template in TEMPLATES:
        assert f"de Keycloak {image_version}" in template.read_text(encoding="utf-8").partition("-->")[0], template.name


@pytest.mark.parametrize("name", sorted(CONTRACT))
def test_contrato_de_los_formularios(name):
    text = (THEME / name).read_text(encoding="utf-8")
    missing = [fragment for fragment in CONTRACT[name] if fragment not in text]
    assert not missing, f"{name} perdio {missing}"


def test_formularios_envian_a_keycloak():
    for template in TEMPLATES:
        text = template.read_text(encoding="utf-8")
        actions = re.findall(r'<form\b[^>]*\baction="([^"]*)"', text)
        assert all(action == "${url.loginAction}" for action in actions), template.name
        assert text.count("<form") == len(actions), f"{template.name}: formulario sin action"


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda path: path.name)
def test_plantillas_sin_texto_fijo(template):
    parser = VisibleText()
    parser.feed(without_freemarker(template.read_text(encoding="utf-8")))
    fixed = [text.strip() for text in parser.texts if re.search(r"[^\W\d_]", text)]
    assert not fixed, f"{template.name}: texto visible fuera de messages_es.properties: {fixed}"


def test_claves_propias_definidas_y_usadas():
    used = {
        key
        for template in TEMPLATES
        for key in re.findall(r"""msg\(["'](ultrasist\w+)["']""", template.read_text(encoding="utf-8"))
    }
    defined = {key for key in MESSAGES if key.startswith("ultrasist")}
    assert used == defined, {"sin definir": used - defined, "sin usar": defined - used}


def test_mensajes_en_espanol_de_mexico_con_usted():
    for key, value in MESSAGES.items():
        assert not re.search(r"\b(tu|tus|has|puedes|debes|inténtalo|identificate)\b", value, re.I), key
        assert "Email" not in value, key
        # MessageFormat: un apostrofo simple desaparece del texto mostrado.
        assert "'" not in value.replace("''", ""), key
    # El bloqueo por fuerza bruta no se distingue de unas credenciales invalidas.
    assert MESSAGES["accountTemporarilyDisabledMessage"] == MESSAGES["invalidUserMessage"]
    assert MESSAGES["invalidUserMessage"] == "Correo o contraseña incorrectos."
    assert MESSAGES["doForgotPassword"] == "¿Olvidó su contraseña?"
    assert MESSAGES["emailSentMessage"].startswith("Si el correo está registrado")


def test_politica_con_una_sola_expresion_la_de_la_letra():
    # messages_es.properties reescribe invalidPasswordRegexPatternMessage como "debe incluir al menos una letra".
    patterns = [policy for policy in REALM["passwordPolicy"].split(" and ") if policy.startswith("regexPattern(")]
    assert patterns == ["regexPattern(.*\\p{L}.*)"]
    assert MESSAGES["invalidPasswordRegexPatternMessage"].endswith("debe incluir al menos una letra.")


def test_sin_recursos_externos_ni_credenciales():
    for path in [*TEMPLATES, CSS, THEME / "messages" / "messages_es.properties", THEME / "theme.properties"]:
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"https?://|//cdn|url\(\s*['\"]?//", text), f"{path.name}: recurso externo"
        assert "data-demo" not in text, path.name
        assert not any(password in text for password in DEMO_PASSWORDS), path.name
    for template in TEMPLATES:
        # Todo src/href sale del tema o de Keycloak (${url...}, ${p.loginUrl}...), nunca de una ruta fija.
        literal = re.findall(r'\b(?:src|href)="(?!\$\{|#")([^"]*)"', template.read_text(encoding="utf-8"))
        assert not literal, f"{template.name}: {literal}"


def test_assets_identicos_a_los_del_portal():
    copies = {
        THEME / "resources" / "img" / "Ultrasistlogo.png": ROOT / "app" / "static" / "img" / "Ultrasistlogo.png",
        THEME / "resources" / "img" / "favicon.png": ROOT / "app" / "static" / "img" / "favicon.png",
    }
    vendor = THEME / "resources" / "vendor"
    for path in vendor.rglob("*"):
        if path.is_file() and path.name != "README.md":
            copies[path] = ROOT / "app" / "static" / "vendor" / path.relative_to(vendor)
    assert len(copies) == 6
    for copy, original in copies.items():
        assert copy.read_bytes() == original.read_bytes(), f"{copy.name} difiere de {original}"


def test_diseno_movil():
    template = (THEME / "template.ftl").read_text(encoding="utf-8")
    assert '<meta name="viewport" content="width=device-width, initial-scale=1">' in template
    assert 'extraClass="login-mobile-brand"' in template
    css = CSS.read_text(encoding="utf-8")
    narrow = css.partition("@media (max-width: 700px)")[2]
    assert ".login-panel {\n    display: none;" in narrow and ".login-mobile-brand {\n    display: flex;" in narrow


def test_realm_declara_tema_y_restablecimiento():
    assert REALM["loginTheme"] == "ultrasist" and REALM["resetPasswordAllowed"] is True
    assert (REALM["defaultLocale"], REALM["supportedLocales"]) == ("es", ["es"])
    assert "smtpServer" not in REALM  # depende del entorno: lo aplica configure-realm.sh
    web = next(item for item in REALM["clients"] if item["clientId"] == settings.keycloak_client_id)
    assert web["directAccessGrantsEnabled"] is False  # el portal nunca recibe contrasenas (sin ROPC)


def test_restablecimientos_registrados_en_los_eventos():
    # Solicitud enviada (SEND_RESET_PASSWORD) o rechazada por correo inexistente, cuenta deshabilitada o enlace usado o
    # vencido (RESET_PASSWORD_ERROR), enlace alterado (EXECUTE_ACTION_TOKEN_ERROR) y contrasena nueva (UPDATE_PASSWORD).
    # Keycloak los conserva 30 dias.
    reset_events = {
        "SEND_RESET_PASSWORD",
        "SEND_RESET_PASSWORD_ERROR",
        "EXECUTE_ACTION_TOKEN",
        "EXECUTE_ACTION_TOKEN_ERROR",
        "RESET_PASSWORD",
        "RESET_PASSWORD_ERROR",
        "UPDATE_PASSWORD",
        "UPDATE_PASSWORD_ERROR",
    }
    assert REALM["eventsEnabled"] and reset_events <= set(REALM["enabledEventTypes"])
    assert REALM["eventsExpiration"] == 30 * 24 * 3600


def test_script_coherente_con_el_realm_y_acotado():
    assert re.search(r"^LOGIN_THEME=(\S+)$", SCRIPT, re.M)[1] == REALM["loginTheme"]
    assert re.search(r"^RESET_PASSWORD_ALLOWED=(\S+)$", SCRIPT, re.M)[1] == str(REALM["resetPasswordAllowed"]).lower()
    # EVENT_TYPES se escribe en varias lineas ('...'\ + '...'): se unen antes de leerla como JSON.
    event_types = re.search(r"^EVENT_TYPES=((?:'[^']*'\\\n)*'[^']*')$", SCRIPT, re.M)[1]
    assert json.loads(re.sub(r"'\\?\n?", "", event_types)) == REALM["enabledEventTypes"]
    assert re.findall(r'"\$kcadm" update "([^"]+)"', SCRIPT) == ["realms/$REALM"]
    attributes = set(re.findall(r'-s "?([\w.]+)=', SCRIPT))
    assert attributes and all(
        name in {"loginTheme", "resetPasswordAllowed", "eventsEnabled", "enabledEventTypes"}
        or name.startswith("smtpServer.")
        for name in attributes
    )
    # Sin secretos: las contrasenas solo llegan por variables de entorno.
    assert not re.search(r"(?i)password=(?!\$)", SCRIPT)
    assert settings.keycloak_client_secret.get_secret_value() not in SCRIPT
    assert "trap 'rm -f \"$config\"' EXIT" in SCRIPT


def test_compose_monta_el_tema_y_el_script_en_solo_lectura():
    keycloak = SERVICES["keycloak"]
    assert "./infra/keycloak/themes/ultrasist:/opt/keycloak/themes/ultrasist:ro" in keycloak["volumes"]
    assert "./infra/keycloak/configure-realm.sh:/opt/keycloak/scripts/configure-realm.sh:ro" in keycloak["volumes"]
    environment = keycloak["environment"]
    assert environment["KEYCLOAK_SMTP_HOST"] == "${KEYCLOAK_SMTP_HOST:-mailpit}"
    assert environment["KEYCLOAK_SMTP_PASSWORD"] == "${KEYCLOAK_SMTP_PASSWORD:-}"


def test_mailpit_version_fija_y_solo_local():
    mailpit = SERVICES["mailpit"]
    assert re.fullmatch(r"axllent/mailpit:v\d+\.\d+\.\d+", mailpit["image"])
    assert mailpit["ports"] == ["127.0.0.1:${MAILPIT_PORT:-58025}:8025"]  # el SMTP (1025) no se publica
    assert mailpit["healthcheck"]["test"] == ["CMD", "/mailpit", "readyz"]


@pytest.mark.parametrize("name", ["run_local.sh", "run_local.ps1", "run_local.bat"])
def test_run_local_aplica_la_configuracion_del_realm(name):
    text = (ROOT / name).read_text(encoding="utf-8")
    up = text.index("docker compose up -d --wait db keycloak mailpit")
    assert text.index("docker compose exec -T keycloak bash /opt/keycloak/scripts/configure-realm.sh") > up


def test_sonar_analiza_el_tema_sin_vendor():
    sonar = properties(ROOT / "sonar-project.properties")
    assert sonar["sonar.sources"].split(",") == ["app", "infra/keycloak/themes"]
    assert set(sonar["sonar.exclusions"].split(",")) == {"app/static/vendor/**", "infra/keycloak/themes/**/vendor/**"}
