@echo off
REM Inicia o backend JARVIS (FastAPI) na porta 8000
cd /d "%~dp0backend"
if not exist "venv\Scripts\python.exe" (
  echo Criando ambiente virtual...
  python -m venv venv
  venv\Scripts\python.exe -m pip install --upgrade pip
  venv\Scripts\pip.exe install -r requirements.txt
)
echo Backend JARVIS em http://127.0.0.1:8000 (Ctrl+C para parar)
venv\Scripts\python.exe -m uvicorn main:app --port 8000
