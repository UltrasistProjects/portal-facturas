#!/usr/bin/env sh
set -eu
[ -f .env ] || cp .env.example .env
.venv/bin/python scripts/reset_demo.py
.venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

