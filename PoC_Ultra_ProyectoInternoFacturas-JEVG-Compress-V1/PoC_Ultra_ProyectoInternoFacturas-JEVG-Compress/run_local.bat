@echo off
.venv\Scripts\python.exe scripts\create_env.py || exit /b 1
docker compose up -d --wait db || (echo No se pudo levantar PostgreSQL: revise que Docker este en ejecucion. & exit /b 1)
.venv\Scripts\python.exe scripts\init_db.py || exit /b 1
.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
