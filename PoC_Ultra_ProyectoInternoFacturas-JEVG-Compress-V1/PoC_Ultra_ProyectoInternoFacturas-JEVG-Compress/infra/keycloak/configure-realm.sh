#!/usr/bin/env bash
# Aplica al realm ultrasist-portal ya importado lo que --import-realm solo aplica al crearlo: el tema de login, el
# restablecimiento de contrasena, los eventos que se registran (incluidos los del restablecimiento) y el servidor de
# correo de Keycloak. Idempotente: repetirlo deja el mismo estado.
# No toca roles, flujos de autenticacion ni la politica de contrasenas; el cliente del portal, solo con PORTAL_URL.
#
# Local (run_local.* lo ejecuta despues de levantar Keycloak):
#   docker compose exec -T keycloak bash /opt/keycloak/scripts/configure-realm.sh
# QA y produccion, en el servidor de Keycloak: KCADM_USER y KCADM_PASSWORD de una cuenta administradora (de master o,
# con KCADM_REALM, del propio realm) y KEYCLOAK_SERVER si no es http://localhost:8080.
#
# Correo de Keycloak (opcional): con KEYCLOAK_SMTP_HOST definida se configura smtpServer con KEYCLOAK_SMTP_PORT,
# KEYCLOAK_SMTP_FROM, KEYCLOAK_SMTP_SECURITY (none | starttls | ssl) y, si el servidor la pide, KEYCLOAK_SMTP_USER y
# KEYCLOAK_SMTP_PASSWORD. Sin KEYCLOAK_SMTP_HOST no se toca el correo configurado en el realm.
#
# URL del portal (QA y produccion, opcional): con PORTAL_URL (https://) el cliente del portal (KEYCLOAK_CLIENT_ID,
# portal-facturas-web por omision) solo admite el callback (/auth/callback) y el cierre de sesion (/) de esa URL, en
# lugar de los locales del realm versionado. Sin PORTAL_URL no se toca el cliente.
set -euo pipefail

REALM=ultrasist-portal
# Deben coincidir con loginTheme, resetPasswordAllowed y enabledEventTypes de realm-ultrasist-portal.json (lo verifica
# una prueba). Los eventos son los del inicio de sesion y los del restablecimiento: la solicitud (SEND_RESET_PASSWORD),
# el enlace del correo (EXECUTE_ACTION_TOKEN, tambien si ya se uso o vencio) y el cambio (RESET_PASSWORD).
LOGIN_THEME=ultrasist
RESET_PASSWORD_ALLOWED=true
EVENT_TYPES='["LOGIN","LOGIN_ERROR","LOGOUT","LOGOUT_ERROR","CODE_TO_TOKEN","CODE_TO_TOKEN_ERROR","UPDATE_PASSWORD",'\
'"UPDATE_PASSWORD_ERROR","USER_DISABLED_BY_TEMPORARY_LOCKOUT","SEND_RESET_PASSWORD","SEND_RESET_PASSWORD_ERROR",'\
'"EXECUTE_ACTION_TOKEN","EXECUTE_ACTION_TOKEN_ERROR","RESET_PASSWORD","RESET_PASSWORD_ERROR"]'

fail() {
  echo "configure-realm: $*" >&2
  exit 1
}

# Muestra la salida de kcadm sin las contrasenas que pudiera repetir.
show() {
  local text=$1
  [ -z "${admin_password:-}" ] || text=${text//"$admin_password"/***}
  [ -z "${KEYCLOAK_SMTP_PASSWORD:-}" ] || text=${text//"$KEYCLOAK_SMTP_PASSWORD"/***}
  echo "$text" >&2
}

server=${KEYCLOAK_SERVER:-http://localhost:8080}
admin_realm=${KCADM_REALM:-master}
admin_user=${KCADM_USER:-${KC_BOOTSTRAP_ADMIN_USERNAME:-}}
admin_password=${KCADM_PASSWORD:-${KC_BOOTSTRAP_ADMIN_PASSWORD:-}}
kcadm=${KCADM:-/opt/keycloak/bin/kcadm.sh}

if [ -z "$admin_user" ] || [ -z "$admin_password" ]; then
  fail "defina KCADM_USER y KCADM_PASSWORD (o KC_BOOTSTRAP_ADMIN_USERNAME y KC_BOOTSTRAP_ADMIN_PASSWORD)"
fi

# La sesion de kcadm va a un archivo temporal que se borra al salir, no a ~/.keycloak.
config=$(mktemp)
trap 'rm -f "$config"' EXIT

if ! output=$("$kcadm" config credentials --config "$config" --server "$server" --realm "$admin_realm" \
  --user "$admin_user" --password "$admin_password" 2>&1); then
  show "$output"
  fail "no se pudo iniciar sesion en $server como $admin_user: revise que Keycloak este en ejecucion y la cuenta"
fi

if ! "$kcadm" get "realms/$REALM" --config "$config" --fields realm >/dev/null 2>&1; then
  fail "el realm $REALM no existe en $server (se importa al arrancar Keycloak con --import-realm)"
fi

settings=(
  -s "loginTheme=$LOGIN_THEME"
  -s "resetPasswordAllowed=$RESET_PASSWORD_ALLOWED"
  -s eventsEnabled=true
  -s "enabledEventTypes=$EVENT_TYPES"
)
mail="sin cambios"

if [ -n "${KEYCLOAK_SMTP_HOST:-}" ]; then
  [ -n "${KEYCLOAK_SMTP_FROM:-}" ] || fail "defina KEYCLOAK_SMTP_FROM, el remitente de los correos de Keycloak"
  case "${KEYCLOAK_SMTP_SECURITY:-none}" in
    none) starttls=false ssl=false ;;
    starttls) starttls=true ssl=false ;;
    ssl) starttls=false ssl=true ;;
    *) fail "KEYCLOAK_SMTP_SECURITY debe ser none, starttls o ssl" ;;
  esac
  port=${KEYCLOAK_SMTP_PORT:-25}
  settings+=(
    -s "smtpServer.host=$KEYCLOAK_SMTP_HOST"
    -s "smtpServer.port=$port"
    -s "smtpServer.from=$KEYCLOAK_SMTP_FROM"
    -s "smtpServer.fromDisplayName=${KEYCLOAK_SMTP_FROM_NAME:-Portal de Proveedores ULTRASIST}"
    -s "smtpServer.starttls=$starttls"
    -s "smtpServer.ssl=$ssl"
  )
  if [ -n "${KEYCLOAK_SMTP_USER:-}" ]; then
    [ -n "${KEYCLOAK_SMTP_PASSWORD:-}" ] || fail "defina KEYCLOAK_SMTP_PASSWORD para el usuario $KEYCLOAK_SMTP_USER"
    settings+=(
      -s smtpServer.auth=true
      -s "smtpServer.user=$KEYCLOAK_SMTP_USER"
      -s "smtpServer.password=$KEYCLOAK_SMTP_PASSWORD"
    )
  else
    settings+=(-s smtpServer.auth=false)
  fi
  mail="$KEYCLOAK_SMTP_HOST:$port"
fi

if ! output=$("$kcadm" update "realms/$REALM" --config "$config" "${settings[@]}" 2>&1); then
  show "$output"
  fail "no se pudo actualizar el realm $REALM"
fi

portal="sin cambios"

if [ -n "${PORTAL_URL:-}" ]; then
  url=${PORTAL_URL%/}
  case "$url" in
    https://*) ;;
    *) fail "PORTAL_URL debe comenzar con https://" ;;
  esac
  client=${KEYCLOAK_CLIENT_ID:-portal-facturas-web}
  if ! id=$("$kcadm" get clients -r "$REALM" --config "$config" -q "clientId=$client" --fields id --format csv \
    --noquotes 2>&1) || [ -z "$id" ]; then
    show "$id"
    fail "no se encontro el cliente $client en el realm $REALM"
  fi
  if ! output=$("$kcadm" update "clients/$id" -r "$REALM" --config "$config" \
    -s "baseUrl=$url/" \
    -s "redirectUris=[\"$url/auth/callback\"]" \
    -s "attributes.\"post.logout.redirect.uris\"=$url/" 2>&1); then
    show "$output"
    fail "no se pudo actualizar el cliente $client"
  fi
  portal=$url
fi

echo "Realm $REALM: tema de login $LOGIN_THEME, restablecimiento de contrasena $RESET_PASSWORD_ALLOWED," \
  "eventos del restablecimiento registrados, correo $mail, portal $portal."
