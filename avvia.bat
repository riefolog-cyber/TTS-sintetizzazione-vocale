@echo off
REM ============================================================
REM  Avvia Kokoro TTS usando l'ambiente .venv (Python 3.11 x64)
REM ============================================================
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERRORE] Ambiente .venv non trovato.
    echo Esegui prima "installa.bat".
    pause
    exit /b 1
)

echo Avvio Kokoro TTS... apri http://localhost:8885
".venv\Scripts\python.exe" kokoro_app.py

pause
