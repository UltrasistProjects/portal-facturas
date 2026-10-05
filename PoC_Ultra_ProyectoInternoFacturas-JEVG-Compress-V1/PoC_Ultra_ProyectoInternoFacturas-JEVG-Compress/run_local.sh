#!/usr/bin/env sh
# Levanta el portal en local: crea el entorno y .env si faltan, arranca PostgreSQL y Keycloak, aplica las migraciones y
# deja uvicorn en primer plano (Ctrl+C lo detiene; los contenedores siguen). Se puede repetir sin riesgo: conserva los
# datos y reanuda lo que este detenido, como Keycloak tras reiniciar la maquina (no se reinicia solo).
set -eu
cd "$(dirname "$0")"

[ -x .venv/bin/python ] || sh scripts/create_venv.sh
.venv/bin/python scripts/create_env.py

# Con dos motores de Docker (el del sistema y Docker Desktop) cada uno puede tener su copia del proyecto, con datos
# propios. Sin DOCKER_CONTEXT se usa el contexto cuyo db publica POSTGRES_PORT (la base a la que apunta DATABASE_URL);
# si ninguno esta corriendo, el unico que tenga el proyecto; si no hay ninguno, el contexto actual.
project=portal-facturas
port=$(sed -n 's/^POSTGRES_PORT=//p' .env)
port=${port:-55432}
contexts=$(docker context ls --format '{{.Name}}' 2>/dev/null || true)
containers() { # contexto [filtros de docker ps]
  _context=$1
  shift
  DOCKER_CONTEXT=$_context docker ps -a --filter "label=com.docker.compose.project=$project" "$@" \
    --format '{{.Names}} {{.Ports}}' 2>/dev/null || true
}
if [ -z "${DOCKER_CONTEXT:-}" ]; then
  found=""
  for c in $contexts; do
    [ -n "$(containers "$c")" ] || continue
    found="$found $c"
    if containers "$c" --filter label=com.docker.compose.service=db --filter status=running | grep -q ":$port->"; then
      DOCKER_CONTEXT=$c
    fi
  done
  set -- $found
  if [ -z "${DOCKER_CONTEXT:-}" ] && [ $# -gt 1 ]; then
    echo "Hay copias de $project en los contextos de Docker:$found. Elija una: DOCKER_CONTEXT=<contexto> $0" >&2
    exit 1
  fi
  if [ $# -eq 1 ]; then DOCKER_CONTEXT=${DOCKER_CONTEXT:-$1}; fi
fi

if [ -n "${DOCKER_CONTEXT:-}" ]; then
  export DOCKER_CONTEXT
  echo "Docker: contexto $DOCKER_CONTEXT."
  # Una copia corriendo en otro contexto ocupa los puertos y su Keycloak tiene otros usuarios: se detiene sin borrar nada.
  for c in $contexts; do
    [ "$c" != "$DOCKER_CONTEXT" ] || continue
    if [ -n "$(containers "$c" --filter status=running)" ]; then
      echo "Deteniendo la copia de $project en el contexto $c (conserva contenedores y datos)."
      DOCKER_CONTEXT=$c docker compose -p "$project" stop
    fi
  done
fi

docker compose up -d --wait db keycloak
.venv/bin/python scripts/init_db.py

if .venv/bin/python -c "import json, urllib.request as r
assert json.load(r.urlopen('http://127.0.0.1:8000/health', timeout=2))['status'] == 'ok'" 2>/dev/null; then
  echo "El portal ya esta en ejecucion: http://127.0.0.1:8000"
  exit 0
fi
echo "Portal: http://127.0.0.1:8000"
exec .venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
