@echo off
if not exist .env copy .env.example .env
.venv\Scripts\python.exe scripts\reset_demo.py
.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

