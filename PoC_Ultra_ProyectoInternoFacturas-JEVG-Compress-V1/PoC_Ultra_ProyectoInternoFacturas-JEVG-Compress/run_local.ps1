$ErrorActionPreference = "Stop"
# Los comandos nativos no detienen el script con ErrorActionPreference: se revisa $LASTEXITCODE.
& .\.venv\Scripts\python.exe scripts\create_env.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
docker compose up -d --wait db keycloak
if ($LASTEXITCODE -ne 0) { Write-Error "No se pudieron levantar PostgreSQL y Keycloak: revise que Docker este en ejecucion."; exit $LASTEXITCODE }
& .\.venv\Scripts\python.exe scripts\init_db.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
