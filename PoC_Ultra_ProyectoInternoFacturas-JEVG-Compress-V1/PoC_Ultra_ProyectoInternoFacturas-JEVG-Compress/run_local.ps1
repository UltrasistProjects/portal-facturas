$ErrorActionPreference = "Stop"
# Los comandos nativos no detienen el script con ErrorActionPreference: se revisa $LASTEXITCODE.
& .\.venv\Scripts\python.exe scripts\create_env.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
docker compose up -d --wait db keycloak mailpit
if ($LASTEXITCODE -ne 0) { Write-Error "No se pudieron levantar PostgreSQL, Keycloak y Mailpit: revise que Docker este en ejecucion."; exit $LASTEXITCODE }
# --import-realm no reimporta un realm existente: el tema de login y el correo de Keycloak se aplican aqui (idempotente).
docker compose exec -T keycloak bash /opt/keycloak/scripts/configure-realm.sh
if ($LASTEXITCODE -ne 0) { Write-Error "No se pudo configurar el realm de Keycloak."; exit $LASTEXITCODE }
& .\.venv\Scripts\python.exe scripts\init_db.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
