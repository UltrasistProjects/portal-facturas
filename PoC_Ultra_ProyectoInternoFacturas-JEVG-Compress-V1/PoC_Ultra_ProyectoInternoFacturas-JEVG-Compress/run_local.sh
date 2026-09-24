#!/usr/bin/env sh
set -eu
.venv/bin/python scripts/create_env.py
.venv/bin/python scripts/reset_demo.py
.venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
