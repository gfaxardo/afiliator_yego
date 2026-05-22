@echo off
cd /d "C:\Users\Pc\Documents\Cursor Proyectos\Afiliator_Yego\afiliator_yego\backend"
start "uvicorn-test" /MIN python -m uvicorn app.main:app --host 127.0.0.1 --port 8771 --log-level warning
echo Server starting...
timeout /t 8 /nobreak >nul
python test_final_from_url.py
taskkill /FI "WINDOWTITLE eq uvicorn-test*" /F >nul 2>&1
