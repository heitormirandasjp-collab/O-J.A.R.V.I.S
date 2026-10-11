@echo off
REM Inicia o servidor JARVIS (UI + chat) na porta 8755
cd /d "%~dp0"
echo JARVIS Command Center em http://127.0.0.1:8755 (Ctrl+C para parar)
node server.js
