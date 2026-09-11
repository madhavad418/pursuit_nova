@echo off
start "PursuitNova API" cmd /k "cd /d %~dp0backend && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"
start "PursuitNova React" cmd /k "cd /d %~dp0frontend && npm run dev"
echo API: http://127.0.0.1:8000
echo React: http://127.0.0.1:5173
